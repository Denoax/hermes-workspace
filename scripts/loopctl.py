#!/usr/bin/env python3
"""Hermes requirement/evidence bookkeeping. No agent, shell or network execution.

This detects omissions, stale files and basic scope mismatches. It cannot attest
that a claimed observation is true or authenticate a human approval in JSON.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

STATUSES = {"TODO", "IN_PROGRESS", "VERIFY", "BLOCKED", "DONE"}
KINDS = {"review", "build", "test", "browser", "visual", "motion", "native", "production", "physical", "human"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scoped(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("relative scoped path required")
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise ValueError("path escapes project")
    return path


def load(root, requirements_path, state_path):
    rp, sp = scoped(root, requirements_path), scoped(root, state_path)
    return json.loads(rp.read_text()), json.loads(sp.read_text()), digest(rp)


def inspect(root, requirements, state, expected_hash):
    errors = []
    if requirements.get("schema_version") != 1 or state.get("schema_version") != 1:
        errors.append("unsupported schema version")
    tasks = requirements.get("tasks", [])
    ids = [task.get("id") for task in tasks]
    if not ids or any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        return ["requirements must have unique nonempty task IDs"]
    if state.get("requirements_sha256") != expected_hash:
        errors.append("requirement file drift: rebase only with an explicit scope decision")
    states = state.get("tasks", {})
    if not isinstance(states, dict) or set(states) != set(ids):
        return errors + ["state IDs differ from the complete requirement inventory"]
    evidence = state.get("evidence", {})
    if not isinstance(evidence, dict):
        return errors + ["evidence registry must be an object"]
    active = [x for x in ids if states[x].get("status") == "IN_PROGRESS"]
    if len(active) > 1:
        errors.append("more than one IN_PROGRESS task")
    graph = {}
    for task in tasks:
        task_id = task["id"]
        dependencies = task.get("depends_on", [])
        graph[task_id] = dependencies
        if not isinstance(dependencies, list) or any(d not in states or d == task_id for d in dependencies):
            errors.append(task_id + ": invalid dependencies")
            graph[task_id] = []
    visited, visiting = set(), set()
    def visit(task_id):
        if task_id in visiting:
            return False
        if task_id in visited:
            return True
        visiting.add(task_id)
        for dependency in graph[task_id]:
            if not visit(dependency):
                return False
        visiting.remove(task_id)
        visited.add(task_id)
        return True
    if any(not visit(task_id) for task_id in ids):
        errors.append("dependency cycle")
    for task in tasks:
        task_id = task["id"]
        item = states[task_id]
        status = item.get("status")
        if status not in STATUSES:
            errors.append(task_id + ": unknown status")
            continue
        if status == "BLOCKED" and not item.get("blocker", "").strip():
            errors.append(task_id + ": blocked task needs a concrete blocker")
        if status != "DONE":
            continue
        if any(states[d].get("status") != "DONE" for d in graph[task_id]):
            errors.append(task_id + ": dependency not DONE")
        required = task.get("required_evidence", [])
        if not required or any(x not in KINDS for x in required):
            errors.append(task_id + ": invalid required evidence kinds")
        selected = item.get("evidence", [])
        if not isinstance(selected, list) or not selected:
            errors.append(task_id + ": DONE without evidence")
            continue
        kinds = set()
        for evidence_id in selected:
            record = evidence.get(evidence_id)
            label = task_id + "/" + str(evidence_id)
            if not isinstance(record, dict):
                errors.append(label + ": missing evidence record")
                continue
            kind = record.get("kind")
            if kind not in KINDS or record.get("outcome") != "PASS" or record.get("fixture") is not False:
                errors.append(label + ": completion needs a non-fixture PASS with a known kind")
                continue
            kinds.add(kind)
            try:
                artifact = scoped(root, record.get("artifact"))
                if not artifact.is_file() or digest(artifact) != record.get("sha256"):
                    errors.append(label + ": artifact missing or hash mismatch")
                sources = record.get("source_files")
                if not isinstance(sources, dict) or not sources:
                    errors.append(label + ": current source-file hashes required")
                else:
                    for name, wanted in sources.items():
                        source = scoped(root, name)
                        if not source.is_file() or digest(source) != wanted:
                            errors.append(label + ": stale source " + name)
            except (ValueError, OSError, TypeError) as exc:
                errors.append(label + ": " + str(exc))
            if kind == "production":
                if record.get("app_url") != requirements.get("production_url") or record.get("via") != "existing_hermes_pin":
                    errors.append(label + ": production scope must be the actual Hermes pin and URL")
                if not record.get("runtime_identity"):
                    errors.append(label + ": installed runtime identity required")
                target = task.get("production_model")
                if target and record.get("model") != target:
                    errors.append(label + ": wrong local model")
            if kind in {"visual", "motion"}:
                if not record.get("viewport") or not record.get("theme"):
                    errors.append(label + ": viewport and theme required")
                if not set(task.get("reference_ids", [])).issubset(record.get("reference_ids", [])):
                    errors.append(label + ": exact reference identities missing")
            if kind == "motion":
                duration = record.get("duration_seconds")
                if record.get("continuous") is not True or type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                    errors.append(label + ": continuous recording and duration required; a still frame cannot prove motion")
            if kind == "human":
                approval = state.get("human_approval") or {}
                if approval.get("source") != "user" or not approval.get("reference") or task_id not in approval.get("task_ids", []):
                    errors.append(label + ": actual user approval reference required; model self-approval is invalid")
        missing = set(required) - kinds
        if missing:
            errors.append(task_id + ": missing evidence kinds " + ", ".join(sorted(missing)))
    return errors


def choose(requirements, state):
    tasks = requirements["tasks"]
    states = state["tasks"]
    for wanted in ("IN_PROGRESS", "VERIFY", "TODO"):
        for task in tasks:
            if task.get("manual") or states[task["id"]]["status"] != wanted:
                continue
            if all(states[d]["status"] == "DONE" for d in task.get("depends_on", [])):
                return {"action": "WORK", "task": task}
    manual = [x["id"] for x in tasks if x.get("manual") and states[x["id"]]["status"] != "DONE" and all(states[d]["status"] == "DONE" for d in x.get("depends_on", []))]
    if manual:
        return {"action": "WAIT_FOR_USER", "task_ids": manual}
    if all(x["status"] == "DONE" for x in states.values()):
        return {"action": "REVIEW_COMPLETION_CLAIM", "note": "Ledger consistency is not proof of observation truth or human identity."}
    return {"action": "REPLAN_BLOCKED_WORK", "task_ids": [x["id"] for x in tasks if states[x["id"]]["status"] != "DONE"]}


def checkpoint(requirements, state, choice, requirements_path, state_path):
    lines = ["# Hermes continuation checkpoint", "", "Read and apply $reference-led-design. Preserve current user work.", "", "## Goal", "", requirements["objective"], "", "## Read first", "", "- Project instructions and current git/worktree status", "- " + requirements_path, "- " + state_path, "- Current PLAN.md and this checkpoint", "", "## Constraints", ""]
    lines += ["- " + x for x in requirements.get("constraints", [])]
    lines += ["", "## Complete inventory", ""]
    for task in requirements["tasks"]:
        item = state["tasks"][task["id"]]
        lines.append("- " + task["id"] + " | " + item["status"] + " | " + task["title"])
        if item.get("blocker"):
            lines.append("  Blocker: " + item["blocker"])
        if item.get("notes"):
            lines.append("  Next/recovery: " + item["notes"])
    lines += ["", "## Next selection", "", json.dumps(choice, ensure_ascii=False, indent=2), "", "## Resume rule", "", "Check the actual files and runtime before editing. Read only the chosen task's relevant evidence and source records. Unfinished work survives context resets. Tests, visual review and human approval are separate. Update state and PLAN.md, then checkpoint and continue.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--requirements", default=".agent/hermes-loop/requirements.json")
    parser.add_argument("--state", default=".agent/hermes-loop/state.json")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--complete", action="store_true")
    commands.add_parser("next")
    output = commands.add_parser("checkpoint")
    output.add_argument("--output", default=".agent/hermes-loop/RESUME.md")
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        requirements, state, expected = load(root, args.requirements, args.state)
        errors = inspect(root, requirements, state, expected)
        remaining = [task["id"] for task in requirements["tasks"] if state["tasks"].get(task["id"], {}).get("status") != "DONE"]
        if args.command == "validate":
            if args.complete and remaining:
                errors.append("completion requested with remaining work: " + ", ".join(remaining))
            result = {"structural_valid": not errors, "errors": errors, "remaining": remaining, "observation_truth_attested": False, "human_identity_authenticated": False}
        elif errors:
            result = {"action": "REPAIR_LEDGER_OR_REVALIDATE_EVIDENCE", "errors": errors}
        else:
            result = choose(requirements, state)
            if args.command == "checkpoint":
                target = scoped(root, args.output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=".resume-", delete=False) as out:
                        temporary = Path(out.name)
                        out.write(checkpoint(requirements, state, result, args.requirements, args.state))
                        out.flush()
                        os.fsync(out.fileno())
                    os.replace(temporary, target)
                finally:
                    if temporary is not None and temporary.exists():
                        temporary.unlink()
                result["checkpoint"] = args.output
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if errors else 0
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
