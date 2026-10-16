"""No-inference actual-pin interaction checks on freshly recorded owned cases.

Importing this module performs no PC or application action. The caller owns the
real ProductionPin, recording lifecycle, native qualification and final cleanup.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

ID = re.compile(r"[0-9a-f]{32}\Z")
NONCE = re.compile(r"V6interaction-[0-9a-f]{12}\Z")
INTENT = "hermes-ui:composing-intent:v1"
NEW_SELECTION = "hermes:draft-attachments:v1:new"


class BrowserVisibleFixture:
    """One guarded harmless file under the existing browser-accessible parent."""
    def __init__(self, parent, payload):
        parent = Path(parent)
        check(not any(p.is_symlink() for p in (parent, *parent.parents)), "fixture_parent_symlink_refused")
        self.root = Path(tempfile.mkdtemp(prefix="hermes-v6-interaction-", dir=parent))
        self.path = self.root / "owned-context.txt"
        self.root.chmod(0o700)
        with self.path.open("xb") as stream:
            stream.write(payload)
        self.path.chmod(0o600)
        self.expected = hashlib.sha256(payload).hexdigest()
        self.directory_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        self.file_identity = (self.path.stat().st_dev, self.path.stat().st_ino)
        self.closed = False
        check(self.path.read_bytes() == payload, "browser_visible_fixture_bytes_mismatch")

    def cleanup(self):
        if self.closed:
            return
        check(not self.root.is_symlink() and self.root.is_dir(), "owned_fixture_directory_changed_preserve_it")
        directory = self.root.stat()
        check((directory.st_dev, directory.st_ino) == self.directory_identity and directory.st_uid == os.getuid(),
              "owned_fixture_directory_identity_changed")
        check(list(self.root.iterdir()) == [self.path] and not self.path.is_symlink() and self.path.is_file(),
              "owned_fixture_inventory_changed_preserve_it")
        source = self.path.stat()
        check((source.st_dev, source.st_ino) == self.file_identity and source.st_uid == os.getuid()
              and hashlib.sha256(self.path.read_bytes()).hexdigest() == self.expected,
              "owned_fixture_file_changed_preserve_it")
        self.path.unlink()
        self.root.rmdir()
        self.closed = True


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def sha(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def selection_ids(raw):
    if raw is None:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise RuntimeError("attachment_selection_shape_changed") from None
    check(isinstance(value, dict) and value.get("version") == 1 and isinstance(value.get("ids"), list),
          "attachment_selection_shape_changed")
    ids = value["ids"]
    check(len(ids) <= 8 and all(isinstance(v, str) and ID.fullmatch(v) for v in ids) and len(set(ids)) == len(ids),
          "attachment_selection_ids_changed")
    return ids


def owned_row(case, role, rows):
    check(bool(NONCE.fullmatch(case.get("nonce", ""))), "positive_case_nonce_required")
    item = case.get("records", {}).get(role)
    check(isinstance(item, dict) and isinstance(item.get("id"), str) and ID.fullmatch(item["id"]), "created_record_receipt_required")
    check(item.get("kind") in ("project", "conversation"), "known_owned_record_kind_required")
    check(item["id"] in case.get("created_ids", []) and len(case["created_ids"]) == len(set(case["created_ids"])),
          "record_not_in_unique_created_inventory")
    field = "label" if item["kind"] == "project" else "title"
    check(item[field].startswith(case["nonce"] + " · "), "owned_record_prefix_required")
    matches = [row for row in rows if row.get("id") == item["id"]]
    check(len(matches) == 1 and matches[0].get(field) == item[field], "owned_record_renamed_or_removed_preserve_it")
    relation = "parent" if item["kind"] == "project" else "project"
    check(matches[0].get(relation) == item.get(relation), "owned_record_scope_changed_preserve_it")
    return matches[0]


def disposable(case, role, rows, snapshot, draft, jobs, raw_selection):
    check(role in ("D", "E"), "only_explicit_empty_deletion_roles_permitted")
    row = owned_row(case, role, rows)
    check(row["id"] != case.get("records", {}).get("A", {}).get("id"), "draft_owner_cannot_be_deleted")
    check(not snapshot.get("messages") and not snapshot.get("runs") and not jobs,
          "owned_empty_case_acquired_content_preserve_it")
    check(draft == {"text": "", "mode": "chat"} and not selection_ids(raw_selection),
          "owned_empty_case_acquired_draft_preserve_it")
    return row["id"]


def presentation_changes(original, current, owned_projects):
    """Return compare-and-swap restoration only for known presentation bookkeeping."""
    check(set(original) == set(current), "presentation_storage_inventory_changed")
    changes = {}
    for key, before in original.items():
        after = current[key]
        if before == after:
            continue
        if key == "hermes:new-draft":
            check(before in (None, "") and after in (None, ""), "new_user_draft_preserved_no_restore")
        elif key == NEW_SELECTION:
            check(not selection_ids(before) and not selection_ids(after), "new_user_attachments_preserved_no_restore")
        elif key == INTENT:
            if after is not None:
                try:
                    intent = json.loads(after)
                except (TypeError, ValueError):
                    raise RuntimeError("unexpected_composing_intent_preserved") from None
                check(isinstance(intent, dict) and set(intent) == {"version", "project_id"}
                      and intent["version"] == 1 and intent["project_id"] in owned_projects,
                      "unexpected_composing_scope_preserved")
        else:
            raise RuntimeError("original_draft_attachment_or_sound_state_changed")
        changes[key] = {"expected": after, "value": before}
    return changes


def continuation_case(prior, projects, sessions):
    required = ("empty_A_is_conversation", "new_conversation_visible_and_focused",
                "composing_reload_and_breadcrumb_overview", "B_staged_rename_move_Cancel_preserves_A_and_B",
                "explicit_B_Save_keeps_viewed_A_unchanged")
    check(all(prior.get("checks", {}).get(name) is True for name in required), "prior_B_sequence_not_complete")
    case = prior.get("case", {})
    check(set(case.get("records", {})) == {"P", "Q", "A", "B", "D", "E"}, "exact_original_six_record_case_required")
    records = case["records"]
    created = case.get("created_ids", [])
    session_ids = case.get("created_session_ids", [])
    before = case.get("before_session_ids", [])
    check(len(created) == 6 and set(created) == {row["id"] for row in records.values()}
          and len(session_ids) == 4 and set(session_ids) == {records[key]["id"] for key in ("A", "B", "D", "E")}
          and "before_session_ids" in case and isinstance(before, list)
          and all(isinstance(value, str) and ID.fullmatch(value) for value in before)
          and not set(before).intersection(created), "original_case_creation_inventory_changed")
    for role in ("P", "Q", "A", "B", "D", "E"):
        owned_row(case, role, projects if records[role]["kind"] == "project" else sessions)
    attachment = prior.get("checks", {}).get("A_genuine_UTF8_draft_and_attachment")
    check(isinstance(attachment, dict) and isinstance(attachment.get("id"), str) and ID.fullmatch(attachment["id"])
          and re.fullmatch("[0-9a-f]{64}", attachment.get("sha256", ""))
          and re.fullmatch("[0-9a-f]{64}", attachment.get("draft_sha256", "")), "prior_real_A_attachment_receipt_required")
    return json.loads(json.dumps(case))


class OwnedInteractions:
    def __init__(self, browser, rpc, output, recovery):
        from scripts.probe_v4_visual import input_text
        self.b, self.input_text = browser, input_text
        self.rpc = lambda method, fields=None: rpc(browser, method, fields or {})
        self.output = Path(output)
        self.output.mkdir(mode=0o700, parents=True, exist_ok=True)
        check(not any(p.is_symlink() for p in (self.output, *self.output.parents))
              and self.output.stat().st_uid == os.getuid() and not self.output.stat().st_mode & 0o077,
              "private_interaction_output_required")
        check(browser.identity.get("url") == "http://127.0.0.1:18791/hermes-workspace"
              and browser.identity.get("catalog") == "production" and browser.identity.get("isolated_server") is False,
              "actual_production_pin_required")
        self.original_view = self.rpc("view.read")
        check(isinstance(self.original_view, dict) and not self.original_view.get("editor")
              and not self.original_view.get("file_path") and not self.original_view.get("files_open"),
              "preserve_original_file_editor_before_interaction_probe")
        check(not browser.evaluate("!!document.querySelector('#cancel-response,.recording-indicator,dialog[open]')"
                                   "||document.querySelectorAll('#composer .attachment').length>0"),
              "preserve_original_run_recording_panel_or_attachments")
        sid = self.original_view.get("session_id")
        self.original_draft = self.rpc("draft.read", {"session_id": sid}) if sid else None
        expected = self.original_draft["text"] if sid else ""
        check(browser.evaluate("document.querySelector('#prompt').value") == expected,
              "unsaved_original_input_preserved_probe_not_started")
        self.storage_keys = list(dict.fromkeys(["hermes-ui:sounds", "hermes-ui:interface-volume", "hermes:new-draft",
                            NEW_SELECTION, INTENT, "hermes:draft-attachments:v1:" + (sid or "new")]))
        self.original_storage = self.storage()
        check(not self.original_storage.get("hermes:new-draft") and not selection_ids(self.original_storage.get(NEW_SELECTION)),
              "global_new_draft_preserved_probe_not_started")
        self.original_filter = browser.evaluate("document.querySelector('.rail-search input').value")
        self.original_scroll = browser.evaluate("document.querySelector('.conversation').scrollTop")
        self.case = {"nonce": "V6interaction-" + uuid.uuid4().hex[:12], "created_ids": [], "records": {}}
        recovery = Path(recovery)
        check("private-state" in recovery.parts and not any(p.is_symlink() for p in (recovery, *recovery.parents)),
              "separate_private_recovery_directory_required")
        recovery.mkdir(mode=0o700, parents=True, exist_ok=True)
        check(recovery.stat().st_uid == os.getuid() and not recovery.stat().st_mode & 0o077,
              "owner_only_private_recovery_directory_required")
        # This contains original user presentation/draft text. It is deliberately
        # outside review output and must never enter source/publication/ZIP.
        backup = recovery / (self.case["nonce"] + "-presentation.json")
        with backup.open("x") as stream:
            json.dump({"version": 1, "kind": "private_v6_presentation_recovery", "view": self.original_view,
                       "draft": self.original_draft, "storage": self.original_storage,
                       "filter": self.original_filter, "scroll": self.original_scroll}, stream)
        backup.chmod(0o600)
        self.private_recovery_file = backup.name
        self.report = {"status": "IN_PROGRESS", "scope": "actual production pin18791; fresh owned records and native pointer; no inference",
                       "pin": browser.identity, "case": self.case, "checks": {}, "captures": [], "attachments_created": [],
                       "private_recovery": "Original presentation retained outside review output; exclude all private-state files from review ZIP.",
                       "private_recovery_file": backup.name,
                       "original_presentation_sha256": sha({"view": self.original_view, "storage": self.original_storage,
                                                            "filter": self.original_filter, "draft": self.original_draft}),
                       "remaining": ["No live/finished model stream is created by this no-inference helper.",
                                     "Native key events and XTEST/compositor pointer are synthesized, not human physical input.",
                                     "File input upload is genuine but CDP file selection does not test the native chooser.",
                                     "Motion/listening approval and guest/device/reboot coverage remain separate."]}
        self.a_baseline = None
        self.upload_fixture = None
        self.save()

    def stage(self, name):
        check(bool(re.fullmatch("[a-z][a-z0-9_]{0,79}", name)), "fixed_diagnostic_step_required")
        self.report["phase"] = name
        self.report.setdefault("steps", []).append(name)
        self.save()

    def cleanup_fixture(self):
        if self.upload_fixture is not None:
            self.upload_fixture.cleanup()

    def adopt_existing(self, receipt):
        path = Path(receipt)
        check(not path.is_symlink() and path.is_file() and path.stat().st_uid == os.getuid()
              and path.stat().st_size <= 256 * 1024, "bounded_owned_prior_receipt_required")
        raw = path.read_bytes()
        prior = json.loads(raw)
        run_path = path.parent.parent / "run.json"
        check(path.name == "interactions.json" and path.parent.name == "owned" and not run_path.is_symlink(),
              "exact_owned_prior_report_pair_required")
        run = json.loads(run_path.read_text())
        check(run.get("owned_case_report") == "owned/interactions.json" and run.get("source_unchanged") is True
              and run.get("phase") == "explicit_row_target_management"
              and run.get("cleanup") and all(row.get("status") == "ok" for row in run["cleanup"].values()),
              "prior_restoration_or_source_identity_not_proven")
        self.case = continuation_case(prior, self.rpc("workspace.list"), self.rpc("session.list"))
        self.report["case"] = self.case
        attachment = prior["checks"]["A_genuine_UTF8_draft_and_attachment"]
        a = self.guard("A")
        draft = self.rpc("draft.read", {"session_id": a["id"]})
        check(sha(draft["text"].encode()) == attachment["draft_sha256"] and draft["mode"] == "chat",
              "existing_A_draft_changed_preserve_it")
        snapshot = self.rpc("chat.snapshot", {"session_id": a["id"]})
        check(not snapshot["messages"] and not snapshot["runs"] and not self.rpc("session.jobs", {"session_id": a["id"]}),
              "existing_A_acquired_activity_preserve_it")
        metadata = self.rpc("attachment.metadata", {"id": attachment["id"]})
        check(all(metadata[key] == attachment[key] for key in ("id", "name", "mime", "bytes", "sha256")),
              "existing_A_attachment_metadata_changed")
        raw_selection = self.b.evaluate("localStorage.getItem(" + json.dumps("hermes:draft-attachments:v1:" + a["id"]) + ")")
        check(selection_ids(raw_selection) == [attachment["id"]], "existing_A_attachment_selection_changed")
        self.guard_empty("D")
        self.guard_empty("E")
        self.report["resumed_from"] = {"receipt_sha256": sha(raw), "run_sha256": sha(run_path.read_bytes()),
                                       "scope": "Earlier attachment/New/B results retained as historical measurements; not repeated.",
                                       "checks": prior["checks"], "source_sha256": run["source_sha256_before"]}
        self.report["attachments_created"] = []
        self.stage("existing_owned_case_guarded")
        return draft["text"]

    def baseline_existing_a(self, text):
        self.b.wait("document.querySelector('#prompt').value===" + json.dumps(text)
                    + "&&document.querySelectorAll('#composer .attachment').length===1")
        self.a_baseline = self.a_state()
        self.stage("existing_a_baseline_rehydrated")

    def save(self):
        path = self.output / "interactions.json"
        path.write_text(json.dumps(self.report, indent=2) + "\n")
        path.chmod(0o600)

    def storage(self):
        return self.b.evaluate("Object.fromEntries(" + json.dumps(self.storage_keys) + ".map(k=>[k,localStorage.getItem(k)]))")

    def poll(self, callback, code, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = callback()
            if value:
                return value
            time.sleep(.08)
        raise RuntimeError(code)

    def require_native(self):
        check(getattr(self.b, "_native_coordinates", None) and getattr(self.b, "_native_diagnostics", {}).get("status") == "PASS",
              "current_native_pointer_qualification_required")

    def reload(self):
        native = getattr(self.b, "_native_input", None)
        if native:
            native.close()
        self.b._native_input = None
        self.b._native_coordinates = None
        self.b._native_diagnostics = {}
        self.b.reload_ready()

    def filter_owned(self):
        self.input_text(self.b, ".rail-search input", self.case["nonce"])
        self.b.wait("!!document.querySelector('#conversation-options-" + self.case["records"]["A"]["id"] + "')&&"
                    "[...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')]"
                    ".every(e=>e.textContent.startsWith(" + json.dumps(self.case["nonce"] + " · ") + "))")

    def capture(self, name):
        from scripts.settled_overlay import settled_overlay
        check(bool(re.fullmatch("[a-z][a-z0-9-]{0,70}", name)), "fixed_capture_name_required")
        check(self.b.evaluate("document.querySelector('.rail-search input').value===" + json.dumps(self.case["nonce"]) + "&&"
                              "!!document.querySelector('#conversation-options-" + self.case["records"]["A"]["id"] + "')&&"
                              "[...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')]"
                              ".every(e=>e.textContent.startsWith(" + json.dumps(self.case["nonce"] + " · ") + "))"),
              "filter_owned_names_before_any_capture")
        settled = settled_overlay(self.b)
        check(settled["status"] in ("settled", "no_overlay"), "capture_overlay_not_settled")
        path = self.output / (name + ".png")
        self.b.capture(path)
        self.report["captures"].append({"file": path.name, "sha256": sha(path.read_bytes()), "overlay_guard": settled})
        self.save()

    def guard(self, role):
        kind = self.case["records"][role]["kind"]
        return owned_row(self.case, role, self.rpc("workspace.list" if kind == "project" else "session.list"))

    def guard_empty(self, role):
        sid = self.case["records"][role]["id"]
        raw = self.b.evaluate("localStorage.getItem(" + json.dumps("hermes:draft-attachments:v1:" + sid) + ")")
        return disposable(self.case, role, self.rpc("session.list"), self.rpc("chat.snapshot", {"session_id": sid}),
                          self.rpc("draft.read", {"session_id": sid}), self.rpc("session.jobs", {"session_id": sid}), raw)

    def create(self):
        for role in ("P", "Q"):
            before = {row["id"] for row in self.rpc("workspace.list")}
            row = self.rpc("workspace.create", {"label": self.case["nonce"] + " · Project " + role})
            check(ID.fullmatch(row["id"]) and row["id"] not in before and row["id"] not in self.case["created_ids"],
                  "fresh_project_creation_receipt_required")
            self.case["created_ids"].append(row["id"])
            self.case["records"][role] = {**row, "kind": "project"}
            self.save()
        q, p = self.guard("Q"), self.guard("P")
        self.rpc("folder.update", {"project_id": q["id"], "label": q["label"], "parent": p["id"], "color": q["color"]})
        self.case["records"]["Q"]["parent"] = p["id"]
        self.guard("Q")
        self.case["before_session_ids"] = [row["id"] for row in self.rpc("session.list")]
        check(all(ID.fullmatch(value) for value in self.case["before_session_ids"]), "precreation_session_id_inventory_invalid")
        self.case["created_session_ids"] = []
        self.save()
        for role in ("A", "B", "D", "E"):
            before = {row["id"] for row in self.rpc("session.list")}
            row = self.rpc("session.create", {"project_id": p["id"], "arm": "normal"})
            check(ID.fullmatch(row["id"]) and row["id"] not in before and row["id"] not in self.case["created_ids"],
                  "fresh_session_creation_receipt_required")
            self.case["created_ids"].append(row["id"])
            self.case["created_session_ids"].append(row["id"])
            self.case["records"][role] = {**row, "kind": "conversation", "title": self.case["nonce"] + " · Conversation " + role}
            self.save()
            # The first rename is bound to the just-issued, previously absent ID.
            snapshot = self.rpc("chat.snapshot", {"session_id": row["id"]})
            observed = next((item for item in self.rpc("session.list") if item["id"] == row["id"]), None)
            check(observed and observed["title"] == "New conversation" and observed["project"] == p["id"]
                  and not snapshot["messages"] and not snapshot["runs"] and not self.rpc("session.jobs", {"session_id": row["id"]})
                  and self.rpc("draft.read", {"session_id": row["id"]}) == {"text": "", "mode": "chat"},
                  "fresh_session_acquired_content_before_initial_label")
            self.rpc("session.rename", {"session_id": row["id"], "title": self.case["records"][role]["title"]})
            self.guard(role)
        self.save()

    def select_a(self):
        a, p = self.guard("A"), self.guard("P")
        self.rpc("view.write", {"state": {**self.original_view, "project_id": p["id"], "session_id": a["id"], "arm": "normal"}})
        self.reload()
        self.filter_owned()

    def a_state(self):
        a = self.guard("A")
        view = self.rpc("view.read")
        check(view["session_id"] == a["id"] and view["project_id"] == a["project"], "view_left_owned_A")
        return {"session": view["session_id"], "project": view["project_id"], "arm": view["arm"],
                "draft": self.rpc("draft.read", {"session_id": a["id"]}),
                "ui": self.b.evaluate("({text:document.querySelector('#prompt').value,model:document.querySelector('#model-picker').value,"
                                      "scroll:document.querySelector('.conversation').scrollTop,count:document.querySelectorAll('#composer .attachment').length})"),
                "selection": self.b.evaluate("localStorage.getItem(" + json.dumps("hermes:draft-attachments:v1:" + a["id"]) + ")")}

    def assert_a(self):
        current = self.a_state()
        baseline = self.a_baseline
        check(baseline is not None and all(current[k] == baseline[k] for k in ("session", "project", "arm", "draft", "selection")),
              "A_scope_draft_or_attachment_changed")
        check(all(current["ui"][k] == baseline["ui"][k] for k in ("text", "model", "count"))
              and abs(current["ui"]["scroll"] - baseline["ui"]["scroll"]) <= 1,
              "A_rendered_draft_model_or_reading_position_changed")
        return current

    def prepare_a(self):
        from scripts.probe_v4_uploads import OBSERVE_UPLOADS
        from workspace import launcher
        self.stage("empty_a_context")
        a = self.guard("A")
        snap = self.rpc("chat.snapshot", {"session_id": a["id"]})
        check(not snap["messages"] and not snap["runs"] and not self.b.evaluate("!!document.querySelector('.project-dashboard')")
              and self.b.evaluate("!!document.querySelector('.empty-state')"), "empty_A_must_show_conversation_not_dashboard")
        self.report["checks"]["empty_A_is_conversation"] = True
        text = self.case["nonce"] + " unsent A draft; never submit this verification text."
        self.input_text(self.b, "#prompt", text)
        self.poll(lambda: self.rpc("draft.read", {"session_id": a["id"]})["text"] == text, "A_draft_not_saved")
        self.stage("a_draft_saved")
        fixture = self.output / "owned-context.txt"
        payload = ("Harmless UTF-8 context for " + self.case["nonce"] + ": maple, café, 你好.\n").encode()
        with fixture.open("xb") as stream:
            stream.write(payload)
        fixture.chmod(0o600)
        # Brave Flatpak cannot read arbitrary host review output. Reuse the
        # established browser-profile-parent location from v4/v5 upload probes.
        self.upload_fixture = BrowserVisibleFixture(launcher.PROFILE.parent, payload)
        self.report["upload_fixture"] = {"bytes": len(payload), "sha256": sha(payload),
                                         "browser_accessible_parent": "existing dedicated profile parent"}
        self.stage("browser_visible_fixture_ready")
        self.b.evaluate(OBSERVE_UPLOADS)
        self.stage("upload_observer_installed")
        document = self.b.call("DOM.getDocument")["root"]["nodeId"]
        node = self.b.call("DOM.querySelector", {"nodeId": document, "selector": "#composer input[type=file]"})["nodeId"]
        check(node, "actual_composer_file_input_missing")
        self.b.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(self.upload_fixture.path)]})
        self.stage("actual_file_input_selected")
        try:
            self.b.wait("globalThis.__hermesUploadReview.summary().pending===0&&globalThis.__hermesUploadReview.summary().records.length===1"
                        "&&document.querySelectorAll('#composer .attachment').length===1")
        except Exception as error:
            self.report["upload_diagnostic"] = self.upload_diagnostic(sha(payload))
            self.stage("upload_observer_or_chip_wait_failed")
            raise RuntimeError("actual_upload_observer_or_chip_not_ready") from error
        self.report["upload_diagnostic"] = self.upload_diagnostic(sha(payload))
        self.stage("upload_response_and_chip_observed")
        uploaded = self.b.evaluate("globalThis.__hermesUploadReview.summary().records[0]")
        check(ID.fullmatch(uploaded["id"]) and uploaded["sha256"] == sha(payload) and uploaded["bytes"] == len(payload),
              "actual_uploaded_bytes_do_not_match_owned_UTF8_fixture")
        check(self.rpc("attachment.metadata", {"id": uploaded["id"]})["sha256"] == sha(payload), "canonical_attachment_hash_mismatch")
        self.b.evaluate("globalThis.__hermesUploadReview.cleanup()")
        self.report["attachments_created"].append(uploaded)
        self.a_baseline = self.a_state()
        check(selection_ids(self.a_baseline["selection"]) == [uploaded["id"]], "A_selection_does_not_match_real_upload")
        self.report["checks"]["A_genuine_UTF8_draft_and_attachment"] = {"draft_sha256": sha(text.encode()), **uploaded}
        self.capture("empty-a-with-real-draft-and-attachment")

    def upload_diagnostic(self, expected_sha):
        # Counts and expected-fixture matches only: no arbitrary filenames,
        # input text, error text or authenticated material enter this diagnostic.
        try:
            return self.b.evaluate("(()=>{const o=globalThis.__hermesUploadReview?.summary();const f=document.querySelector('#composer input[type=file]');"
                                   "return {observer_present:!!o,pending:o?.pending??null,record_count:o?.records?.length??null,"
                                   "expected_sha_seen:o?.records?.some(r=>r.sha256===" + json.dumps(expected_sha) + ")??false,"
                                   "file_input_present:!!f,selected_file_count:f?.files?.length??null,"
                                   "selected_file_bytes:f?.files?.[0]?.size??null,chip_count:document.querySelectorAll('#composer .attachment').length,"
                                   "error_banner_present:!!document.querySelector('.error-banner')}})()")
        except Exception as error:
            return {"diagnostic_error_category": type(error).__name__}

    def button(self, text, scope="document"):
        token = "owned-v6-" + uuid.uuid4().hex
        self.b.wait("(()=>{const r=" + scope + ";return !!r&&[...r.querySelectorAll('button')].filter(e=>e.textContent.trim()==="
                    + json.dumps(text) + "&&!e.disabled).length===1})()")
        self.b.evaluate("(()=>{const e=[..." + scope + ".querySelectorAll('button')].find(e=>e.textContent.trim()==="
                        + json.dumps(text) + ");e.dataset.v6Interaction=" + json.dumps(token) + ";e.scrollIntoView({block:'nearest'})})()")
        self.b.click('[data-v6-interaction="' + token + '"]')

    def row_menu(self, role, action):
        from scripts.settled_overlay import settled_overlay
        self.require_native()
        row = self.guard(role)
        kind = self.case["records"][role]["kind"]
        selector = "#" + ("folder-options-" if kind == "project" else "conversation-options-") + row["id"]
        self.stage("row_" + role.lower() + "_trigger_scroll")
        self.b.evaluate("document.querySelector(" + json.dumps(selector) + ").scrollIntoView({block:'nearest'})")
        self.b.click(selector)
        self.stage("row_" + role.lower() + "_menu_wait")
        self.b.wait("!!document.querySelector('#row-actions[role=menu]')")
        check(settled_overlay(self.b)["status"] == "settled", "row_menu_not_settled")
        self.stage("row_" + role.lower() + "_menu_open")
        self.assert_a()
        self.button(action, "document.querySelector('#row-actions')")
        self.stage("row_" + role.lower() + "_dialog_wait")
        self.b.wait("!!document.querySelector('dialog[open]')&&!document.querySelector('#row-actions')")
        check(settled_overlay(self.b)["status"] == "settled", "management_dialog_not_settled")
        self.stage("row_" + role.lower() + "_dialog_open")
        field = "label" if kind == "project" else "title"
        check(row[field] in self.b.evaluate("document.querySelector('dialog[open]').textContent")
              or self.b.evaluate("document.querySelector('dialog[open] input')?.value") == row[field],
              "management_dialog_does_not_name_exact_row_target")

    def composing(self, qualify):
        self.require_native()
        self.b.click("#new-session")
        self.b.wait("document.activeElement.id==='prompt'&&!document.querySelector('.project-dashboard')"
                    "&&!!document.querySelector('.empty-state')&&document.querySelector('#prompt').value===''")
        p = self.guard("P")
        self.poll(lambda: self.rpc("view.read")["session_id"] is None, "new_conversation_did_not_clear_viewed_session")
        check(json.loads(self.b.evaluate("localStorage.getItem(" + json.dumps(INTENT) + ")")) == {"version": 1, "project_id": p["id"]},
              "versioned_composing_intent_not_bound_to_P")
        self.report["checks"]["new_conversation_visible_and_focused"] = True
        self.capture("new-conversation-visible")
        self.reload()
        self.filter_owned()
        qualify("new_conversation_reload")
        check(self.rpc("view.read")["session_id"] is None and not self.b.evaluate("!!document.querySelector('.project-dashboard')")
              and self.b.evaluate("!!document.querySelector('.empty-state')"), "new_conversation_not_retained_on_reload")
        self.b.click(".conversation-title .workspace-location")
        self.b.wait("!!document.querySelector('.project-dashboard')")
        self.b.wait("localStorage.getItem(" + json.dumps(INTENT) + ")===null")
        self.report["checks"]["composing_reload_and_breadcrumb_overview"] = True
        a = self.guard("A")
        self.b.click('.session-row:has(#conversation-options-' + a["id"] + ')>button:first-child')
        self.b.wait("document.querySelector('#prompt').value===" + json.dumps(self.a_baseline["ui"]["text"]))
        self.b.wait("document.querySelectorAll('#composer .attachment').length===1")
        self.assert_a()
        self.save()

    def stage_conversation(self, title, project):
        self.input_text(self.b, "dialog[open] .app-form input", title)
        selector = "dialog[open] .app-form select"
        options = self.b.evaluate("[...document.querySelector(" + json.dumps(selector) + ").options].map(o=>o.value)")
        check(project in options, "owned_destination_project_not_in_real_select")
        self.b.click(selector)
        for _ in options:
            self.b.key("ArrowUp")
        for _ in range(options.index(project)):
            self.b.key("ArrowDown")
        self.b.key("Enter")
        self.b.wait("document.querySelector(" + json.dumps(selector) + ").value===" + json.dumps(project))

    def management(self):
        b, q = self.guard("B"), self.guard("Q")
        self.row_menu("B", "Rename or move…")
        self.stage_conversation(self.case["nonce"] + " · B cancelled edit", q["id"])
        check(self.guard("B")["project"] == b["project"], "staged_move_wrote_before_Save")
        self.button("Cancel", "document.querySelector('dialog[open]')")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.guard("B")
        self.assert_a()
        self.report["checks"]["B_staged_rename_move_Cancel_preserves_A_and_B"] = True
        self.row_menu("B", "Rename or move…")
        title = self.case["nonce"] + " · B explicitly saved"
        self.stage_conversation(title, q["id"])
        self.guard("B")
        self.guard("Q")
        self.button("Save changes", "document.querySelector('dialog[open]')")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.poll(lambda: any(row["id"] == b["id"] and row["title"] == title and row["project"] == q["id"]
                              for row in self.rpc("session.list")), "explicit_B_Save_not_observed")
        self.case["records"]["B"].update(title=title, project=q["id"])
        self.guard("B")
        self.assert_a()
        self.report["checks"]["explicit_B_Save_keeps_viewed_A_unchanged"] = True
        self.folder_management()

    def enter_dialog_text(self, selector, text):
        check(text.startswith(self.case["nonce"] + " · "), "owned_dialog_input_prefix_required")
        self.b.evaluate("document.querySelector(" + json.dumps(selector) + ").scrollIntoView({block:'nearest'})")
        self.b.click(selector)
        self.b.wait("document.activeElement===document.querySelector(" + json.dumps(selector) + ")")
        self.b.key("a", "KeyA", 2)
        self.b.call("Input.insertText", {"text": text})
        self.b.wait("document.querySelector(" + json.dumps(selector) + ").value===" + json.dumps(text))

    def folder_management(self):
        q = self.guard("Q")
        self.stage("q_cancel_open")
        self.row_menu("Q", "Edit folder…")
        self.stage("q_cancel_input")
        self.enter_dialog_text("dialog[open] input", self.case["nonce"] + " · Q cancelled edit")
        self.stage("q_cancel_escape")
        self.b.key("Escape")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.guard("Q")
        self.assert_a()
        self.stage("q_cancel_verified")
        self.row_menu("Q", "Edit folder…")
        label = self.case["nonce"] + " · Q explicitly saved"
        self.stage("q_save_input")
        self.enter_dialog_text("dialog[open] input", label)
        self.guard("Q")
        self.stage("q_save_click")
        self.button("Save folder", "document.querySelector('dialog[open]')")
        self.stage("q_save_close_wait")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.poll(lambda: any(row["id"] == q["id"] and row["label"] == label for row in self.rpc("workspace.list")),
                  "unselected_Q_Save_not_observed")
        self.case["records"]["Q"]["label"] = label
        self.guard("Q")
        self.assert_a()
        self.stage("q_save_verified")
        self.report["checks"]["unselected_Q_Cancel_and_Save_preserve_A"] = True
        self.capture("a-preserved-after-b-and-q-management")
        self.save()

    def deletion(self):
        widget = 'dialog[open] [data-slot="delete-button"]'
        self.guard_empty("D")
        self.row_menu("D", "Review deletion…")
        self.b.click(widget + ' [aria-label="Delete"]')
        self.wait_delete_open(widget)
        self.b.click(widget + ' [aria-label="Cancel"]')
        self.b.wait("document.querySelector(" + json.dumps(widget) + ").dataset.state==='closed'")
        self.guard_empty("D")
        self.assert_a()
        self.b.click(widget + ' [aria-label="Delete"]')
        self.wait_delete_open(widget)
        self.b.key("Escape")
        if self.b.evaluate("!!document.querySelector('dialog[open]')"):
            self.b.key("Escape")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.guard_empty("D")
        self.assert_a()
        self.row_menu("D", "Review deletion…")
        self.b.click(widget + ' [aria-label="Delete"]')
        self.wait_delete_open(widget)
        deleted = self.guard_empty("D")
        self.b.click(widget + ' [aria-label="Confirm delete"]')
        self.poll(lambda: not any(row["id"] == deleted for row in self.rpc("session.list")), "known_empty_D_delete_not_observed")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.assert_a()
        self.report["checks"]["D_actual_core_Cancel_Escape_and_confirm_only_known_empty"] = {"deleted_id": deleted}
        self.save()

    def wait_delete_open(self, widget):
        # Wait on the original core's actual 48+84 width, rather than clicking
        # a moving circle as soon as React exposes its open state.
        self.b.wait("(()=>{const e=document.querySelector(" + json.dumps(widget) + ");return e?.dataset.state==='open'"
                    "&&Math.abs(e.getBoundingClientRect().width-132)<=.5})()")

    def stale_target(self):
        self.guard_empty("E")
        self.row_menu("E", "Rename or move…")
        stale = self.guard_empty("E")
        self.rpc("content.delete", {"kind": "conversation", "id": stale})
        self.poll(lambda: not any(row["id"] == stale for row in self.rpc("session.list")), "owned_empty_E_fault_delete_not_observed")
        self.input_text(self.b, "dialog[open] .app-form input", self.case["nonce"] + " · E stale edit")
        self.button("Save changes", "document.querySelector('dialog[open]')")
        self.b.wait("!!document.querySelector('dialog[open] [role=alert]')||"
                    "(!document.querySelector('dialog[open]')&&!!document.querySelector('.error-banner[role=alert]'))")
        clear = self.b.evaluate("(()=>{const e=document.querySelector('dialog[open] [role=alert]')||document.querySelector('.error-banner[role=alert]');"
                                "if(!e||!e.textContent.trim())return false;const r=e.getBoundingClientRect();"
                                "const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return r.width>0&&r.height>0&&(e===hit||e.contains(hit))})()")
        check(clear, "stale_E_error_is_not_visible_above_native_modal")
        self.assert_a()
        self.report["checks"]["stale_owned_E_error_never_adopts_A"] = {"fault_deleted_id": stale, "visible_alert": True}
        self.capture("stale-target-clear-error-a-preserved")
        self.b.key("Escape")
        self.b.wait("!document.querySelector('dialog[open]')")
        self.save()

    def restore(self):
        from scripts.probe_v4_visual import close_panels
        self.b.evaluate("globalThis.__hermesUploadReview?.cleanup()")
        close_panels(self.b)
        view = self.rpc("view.read")
        if self.a_baseline is not None:
            a = self.guard("A")
            selection = self.b.evaluate("localStorage.getItem(" + json.dumps("hermes:draft-attachments:v1:" + a["id"]) + ")")
            check(self.rpc("draft.read", {"session_id": a["id"]}) == self.a_baseline["draft"]
                  and selection == self.a_baseline["selection"], "new_A_user_edit_preserved_no_restore")
            if view.get("session_id") == a["id"]:
                self.assert_a()
        owned_sessions = {row["id"] for row in self.case["records"].values() if row["kind"] == "conversation"}
        owned_projects = {row["id"] for row in self.case["records"].values() if row["kind"] == "project"}
        check(view == self.original_view or view.get("session_id") in owned_sessions
              or view.get("session_id") is None and view.get("project_id") in owned_projects,
              "unexpected_user_view_preserved_no_restore")
        changes = presentation_changes(self.original_storage, self.storage(), owned_projects)
        self._restore_storage(changes)
        self.rpc("view.write", {"state": self.original_view})
        self.reload()
        # Hydration may normalize absent/empty new-draft bookkeeping. Reconcile
        # only known empty forms once more; never restore text or nonempty IDs.
        self._restore_storage(presentation_changes(self.original_storage, self.storage(), owned_projects))
        if self.original_filter:
            self.input_text(self.b, ".rail-search input", self.original_filter)
        self.b.evaluate("document.querySelector('.conversation').scrollTop=" + json.dumps(self.original_scroll))
        original = self.rpc("draft.read", {"session_id": self.original_view["session_id"]}) if self.original_draft is not None else None
        check(self.rpc("view.read") == self.original_view and original == self.original_draft and self.storage() == self.original_storage,
              "original_view_draft_or_storage_not_restored")
        check(self.b.evaluate("document.querySelector('.rail-search input').value") == self.original_filter,
              "original_filter_not_restored")
        self.report["checks"]["original_presentation_restored_without_catalog_reset"] = True
        self.report["checks"]["new_owned_A_draft_attachment_and_records_retained"] = True
        self.save()

    def _restore_storage(self, changes):
        self.b.evaluate("(()=>{const changes=" + json.dumps(changes) + ";for(const[k,c]of Object.entries(changes)){"
                        "if(localStorage.getItem(k)!==c.expected)throw Error('concurrent_storage_change_preserved')}"
                        "for(const[k,c]of Object.entries(changes)){if(c.value===null)localStorage.removeItem(k);else localStorage.setItem(k,c.value)}})()")
