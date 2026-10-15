"""Real bounded subprocess/controller tests with synthetic Codex events only."""
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import looprun


class RunnerChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "logs"
        self.log.mkdir()

    def run_child(self, code, seconds=2, max_bytes=8192):
        return looprun.execute([sys.executable, "-c", code], self.root, "test input only", self.log, seconds, max_bytes)

    def ledger(self, manual=False):
        self.directory = self.root / ".agent/hermes-loop"
        self.directory.mkdir(parents=True)
        req = {"schema_version": 1, "objective": "Synthetic controller integration", "tasks": [
            {"id": "A", "title": "A", "depends_on": [], "required_evidence": ["test"]},
            {"id": "B", "title": "B", "depends_on": ["A"], "required_evidence": ["human"] if manual else ["test"], "manual": manual}]}
        text = json.dumps(req)
        (self.directory / "requirements.json").write_text(text)
        state = {"schema_version": 1, "requirements_sha256": hashlib.sha256(text.encode()).hexdigest(),
                 "tasks": {k: {"status": "TODO", "evidence": []} for k in ("A", "B")}, "evidence": {}, "human_approval": None}
        (self.directory / "state.json").write_text(json.dumps(state))
        (self.root / "source.txt").write_text("synthetic fixed source")
        return req, state

    def fake_cli(self, update=True):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        binary = self.root / "fake-codex"
        binary.write_text("#!" + sys.executable + "\n" + '''import sys,json,pathlib,hashlib
if '--version' in sys.argv:
 print('synthetic-test-cli');sys.exit()
if '--help' in sys.argv:
 print('--json --sandbox');sys.exit()
prompt=sys.stdin.read()
pathlib.Path('received-prompt.txt').write_text(prompt)
print(json.dumps({'type':'thread.started','thread_id':'synthetic-thread'}))
''' + ('''p=pathlib.Path('.agent/hermes-loop/state.json');s=json.loads(p.read_text())
k=next(k for k,v in s['tasks'].items() if v['status']!='DONE')
f=pathlib.Path(k+'.txt');f.write_text('synthetic utility evidence only')
s['evidence'][k]={'kind':'test','outcome':'PASS','fixture':False,'artifact':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'source_files':{'source.txt':hashlib.sha256(pathlib.Path('source.txt').read_bytes()).hexdigest()}}
s['tasks'][k]={'status':'DONE','evidence':[k]};p.write_text(json.dumps(s))
''' if update else "") + "print(json.dumps({'type':'turn.completed'}))\n")
        binary.chmod(0o700)
        return binary

    def invoke(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            status = looprun.main(["--root", str(self.root), *args])
        return status, out.getvalue(), err.getvalue()

    def test_successful_process_is_not_completion_claim(self):
        result = self.run_child("print('{\"type\":\"turn.completed\"}')")
        self.assertEqual(result["exit"], 0)
        self.assertNotIn("all_work_complete", result)

    def test_missing_completion_is_rejected(self):
        with self.assertRaises(looprun.StopRun): self.run_child("print('{}')")

    def test_failure_event_is_rejected_even_with_zero_exit(self):
        with self.assertRaises(looprun.StopRun): self.run_child("print('{\"type\":\"turn.failed\"}')")

    def test_nonzero_exit_is_rejected(self):
        with self.assertRaises(looprun.StopRun): self.run_child("import sys;print('{\"type\":\"turn.completed\"}');sys.exit(3)")

    def test_malformed_event_is_rejected(self):
        with self.assertRaises(looprun.StopRun): self.run_child("print('not JSON')")

    def test_unexpected_event_shape_is_rejected(self):
        with self.assertRaises(looprun.StopRun): self.run_child("print('[]')")

    def test_stdout_limit_is_enforced(self):
        with self.assertRaisesRegex(looprun.StopRun, "output limit"): self.run_child("print('x'*9000)")

    def test_stderr_counts_toward_limit(self):
        with self.assertRaisesRegex(looprun.StopRun, "output limit"): self.run_child("import sys;sys.stderr.write('x'*9000)")

    def test_timeout_stops_real_owned_process(self):
        with self.assertRaisesRegex(looprun.StopRun, "time limit"):
            self.run_child("import time;time.sleep(10)", seconds=0.12)

    def test_preflight_launches_no_codex(self):
        self.ledger()
        status, out, _ = self.invoke(["--codex", "/does/not/exist"])
        self.assertEqual(status, 0)
        self.assertIn("preflight_only_no_agent_launched", out)

    def test_execution_requires_exclusive_writer_attestation(self):
        self.ledger()
        status, _, err = self.invoke(["--run"])
        self.assertEqual(status, 2)
        self.assertIn("exclusive-writer", err)

    def test_real_bounded_controller_keeps_human_pending(self):
        self.ledger(manual=True)
        binary = self.fake_cli()
        status, out, err = self.invoke(["--run", "--exclusive-writer", "--codex", str(binary)])
        self.assertEqual(status, 0, err)
        report = json.loads(out)
        self.assertEqual(len(report["cycles"]), 1)
        self.assertEqual(report["stop"]["action"], "WAIT_FOR_USER")
        self.assertFalse(report["all_work_complete"])
        self.assertEqual(json.loads((self.directory / "state.json").read_text())["tasks"]["B"]["status"], "TODO")
        self.assertIn("$reference-led-design", (self.root / "received-prompt.txt").read_text())
        self.assertEqual((self.directory / "runtime").stat().st_mode & 0o777, 0o700)

    def test_status_prose_churn_does_not_extend_batch(self):
        self.ledger()
        binary = self.fake_cli(update=False)
        status, out, err = self.invoke(["--run", "--exclusive-writer", "--codex", str(binary)])
        self.assertEqual(status, 0, err)
        report = json.loads(out)
        self.assertEqual(len(report["cycles"]), 2)
        self.assertIn("no-progress limit", report["stop"])

    def test_cycle_limit_keeps_remaining_work(self):
        self.ledger()
        binary = self.fake_cli()
        status, out, err = self.invoke(["--run", "--exclusive-writer", "--codex", str(binary), "--max-cycles", "1"])
        self.assertEqual(status, 0, err)
        self.assertEqual(json.loads(out)["stop"], "cycle limit")
        self.assertIn("B | TODO", (self.directory / "RESUME.md").read_text())

    def test_evidence_removal_is_not_progress(self):
        before = {"tasks": {"A": {"status": "DONE", "evidence": ["a"]}}, "evidence": {"a": {"sha256": "a"}}}
        after = {"tasks": {"A": {"status": "TODO", "evidence": []}}, "evidence": {}}
        self.assertFalse(looprun.progress(after)-looprun.progress(before))

    def test_second_controller_cannot_take_held_writer_lock(self):
        self.ledger()
        binary = self.fake_cli()
        runtime = self.directory / "runtime"
        runtime.mkdir(mode=0o700)
        with (runtime / "writer.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            status, _, _ = self.invoke(["--run", "--exclusive-writer", "--codex", str(binary)])
        self.assertEqual(status, 2)
        self.assertFalse((self.root / "received-prompt.txt").exists())

    def test_changed_requirement_scope_stops_and_preserves_failure_receipt(self):
        self.ledger()
        binary = self.fake_cli(update=False)
        with binary.open("a") as out:
            out.write("p=pathlib.Path('.agent/hermes-loop/requirements.json');r=json.loads(p.read_text());r['objective']='changed';p.write_text(json.dumps(r))\n")
        status, _, err = self.invoke(["--run", "--exclusive-writer", "--codex", str(binary)])
        self.assertEqual(status, 2)
        self.assertIn("ledger invalid", err)
        receipt = next((self.directory / "runtime").glob("batch-*/summary.json"))
        self.assertIn("ledger invalid", json.loads(receipt.read_text())["stop"])

    def test_interrupt_checkpoints_without_claiming_completion(self):
        from unittest.mock import patch
        self.ledger()
        binary = self.fake_cli(update=False)
        with patch.object(looprun, "execute", side_effect=KeyboardInterrupt):
            status, _, err = self.invoke(["--run", "--exclusive-writer", "--codex", str(binary)])
        self.assertEqual(status, 2)
        self.assertIn("KeyboardInterrupt", err)
        self.assertIn("A | TODO", (self.directory / "RESUME.md").read_text())


if __name__ == "__main__":
    unittest.main()
