"""Adversarial bookkeeping checks using temporary synthetic files, not PC tests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/loopctl.py"
spec = importlib.util.spec_from_file_location("loopctl", SCRIPT)
loopctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loopctl)


class LedgerChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "source.py").write_text("version = 1\n")
        (self.root / "result.txt").write_text("Synthetic validator test evidence only\n")
        self.req = {"schema_version": 1, "objective": "Preserve all work", "production_url": "http://127.0.0.1:18791/hermes-workspace", "tasks": [{"id": "A", "title": "A", "depends_on": [], "required_evidence": ["test"], "reference_ids": []}, {"id": "B", "title": "B", "depends_on": ["A"], "required_evidence": ["test"], "reference_ids": []}]}
        self.state = {"schema_version": 1, "requirements_sha256": "expected", "tasks": {"A": {"status": "TODO", "evidence": []}, "B": {"status": "TODO", "evidence": []}}, "evidence": {}, "human_approval": None}

    def errors(self):
        return loopctl.inspect(self.root, self.req, self.state, "expected")

    def done(self, kind="test"):
        self.req["tasks"][0]["required_evidence"] = [kind]
        self.state["tasks"]["A"] = {"status": "DONE", "evidence": ["E"]}
        record = {"kind": kind, "outcome": "PASS", "fixture": False, "artifact": "result.txt", "sha256": loopctl.digest(self.root / "result.txt"), "source_files": {"source.py": loopctl.digest(self.root / "source.py")}}
        self.state["evidence"]["E"] = record
        return record

    def test_incomplete_state_selects_work_without_claiming_completion(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(loopctl.choose(self.req, self.state)["task"]["id"], "A")

    def test_missing_requirement_is_rejected(self):
        del self.state["tasks"]["B"]
        self.assertTrue(self.errors())

    def test_requirement_drift_is_rejected(self):
        self.state["requirements_sha256"] = "changed"
        self.assertTrue(self.errors())

    def test_done_without_evidence_is_rejected(self):
        self.state["tasks"]["A"]["status"] = "DONE"
        self.assertTrue(self.errors())

    def test_matching_artifact_and_sources_can_validate(self):
        self.done()
        self.assertEqual(self.errors(), [])

    def test_artifact_tamper_is_rejected(self):
        self.done()
        (self.root / "result.txt").write_text("changed")
        self.assertTrue(self.errors())

    def test_stale_source_is_rejected(self):
        self.done()
        (self.root / "source.py").write_text("version = 2\n")
        self.assertTrue(self.errors())

    def test_fixture_cannot_complete_a_live_requirement(self):
        self.done()["fixture"] = True
        self.assertTrue(self.errors())

    def test_path_escape_is_rejected(self):
        self.done()["artifact"] = "../outside.txt"
        self.assertTrue(self.errors())

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            p = Path(outside) / "evidence.txt"
            p.write_text("outside")
            (self.root / "external.txt").symlink_to(p)
            self.done()["artifact"] = "external.txt"
            self.assertTrue(self.errors())

    def test_isolated_server_is_not_production(self):
        r = self.done("production")
        r.update(app_url="http://127.0.0.1:18793/hermes-workspace", via="existing_hermes_pin", runtime_identity="synthetic-runtime")
        self.assertTrue(self.errors())

    def test_correct_metadata_does_not_claim_observation_truth(self):
        r = self.done("production")
        r.update(app_url=self.req["production_url"], via="existing_hermes_pin", runtime_identity="synthetic-runtime", model="normal")
        self.req["tasks"][0]["production_model"] = "normal"
        self.assertEqual(self.errors(), [])
        # This intentionally demonstrates the documented limit: metadata cannot
        # authenticate a real UI observation. The validator is not a truth oracle.

    def test_wrong_model_is_rejected(self):
        r = self.done("production")
        r.update(app_url=self.req["production_url"], via="existing_hermes_pin", runtime_identity="synthetic-runtime", model="abliterated")
        self.req["tasks"][0]["production_model"] = "normal"
        self.assertTrue(self.errors())

    def test_boolean_duration_cannot_pass_motion(self):
        r = self.done("motion")
        r.update(viewport=[1440, 900], theme="dark", continuous=True, duration_seconds=True)
        self.assertTrue(self.errors())

    def test_nonfinite_duration_cannot_pass_motion(self):
        for duration in (float("inf"), float("nan")):
            r = self.done("motion")
            r.update(viewport=[1440, 900], theme="dark", continuous=True, duration_seconds=duration)
            self.assertTrue(self.errors())

    def test_pending_dependency_prevents_done(self):
        self.state["tasks"]["B"] = {"status": "DONE", "evidence": []}
        self.assertTrue(self.errors())

    def test_two_active_writers_are_visible_in_state(self):
        for item in self.state["tasks"].values():
            item["status"] = "IN_PROGRESS"
        self.assertTrue(self.errors())

    def test_dependency_cycle_is_rejected(self):
        self.req["tasks"][0]["depends_on"] = ["B"]
        self.assertTrue(self.errors())

    def test_blocker_needs_a_reason(self):
        self.state["tasks"]["A"]["status"] = "BLOCKED"
        self.assertTrue(self.errors())

    def test_blocked_work_stays_in_inventory_while_independent_work_continues(self):
        self.state["tasks"]["A"].update(status="BLOCKED", blocker="Native step awaits protected local authentication")
        self.req["tasks"][1]["depends_on"] = []
        self.assertEqual(self.errors(), [])
        self.assertEqual(loopctl.choose(self.req, self.state)["task"]["id"], "B")

    def test_visual_reference_identity_is_required(self):
        r = self.done("visual")
        r.update(viewport="1440x900@1", theme="dark", reference_ids=[])
        self.req["tasks"][0]["reference_ids"] = ["R11"]
        self.assertTrue(self.errors())

    def test_still_frame_cannot_claim_continuous_motion(self):
        r = self.done("motion")
        r.update(viewport="1440x900@1", theme="dark", reference_ids=[])
        self.assertTrue(self.errors())

    def test_model_cannot_supply_human_approval_source(self):
        self.done("human")
        self.state["human_approval"] = {"source": "model", "reference": "looks great", "task_ids": ["A"]}
        self.assertTrue(self.errors())

    def test_manual_task_yields_for_user_instead_of_retrying(self):
        self.req["tasks"] = [self.req["tasks"][0]]
        del self.state["tasks"]["B"]
        self.req["tasks"][0]["manual"] = True
        self.assertEqual(loopctl.choose(self.req, self.state)["action"], "WAIT_FOR_USER")

    def test_cli_checkpoint_and_completion_gate_preserve_unfinished_work(self):
        raw = json.dumps(self.req).encode()
        (self.root / "requirements.json").write_bytes(raw)
        self.state["requirements_sha256"] = hashlib.sha256(raw).hexdigest()
        self.state["tasks"]["A"].update(status="IN_PROGRESS", notes="Keep partial implementation; next inspect the real pin")
        (self.root / "state.json").write_text(json.dumps(self.state))
        base = [sys.executable, str(SCRIPT), "--root", str(self.root), "--requirements", "requirements.json", "--state", "state.json"]
        run = subprocess.run(base + ["checkpoint", "--output", "RESUME.md"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        text = (self.root / "RESUME.md").read_text()
        self.assertIn("A | IN_PROGRESS", text)
        self.assertIn("B | TODO", text)
        self.assertIn("next inspect the real pin", text)
        self.assertIn("$reference-led-design", text)
        run = subprocess.run(base + ["validate", "--complete"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)["remaining"], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
