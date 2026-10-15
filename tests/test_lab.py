import concurrent.futures
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
import hashlib
import io
import sys
from lab.doctor import verify_artifact
from lab.process import identity, open_owned
from lab.relay import validate_request
from lab.report import blocked_matrix, write_results
from lab.runtime import qemu_argv
from lab.state import RunStore
from lab.transport import GuestTransport, bounded_process
from lab.preparation import fetch_candidate, REPOSITORY
from lab.schedule import paired_schedule


class ReportTests(unittest.TestCase):
    def test_offline_status_ignores_private_artifact_directories(self):
        from lab import cli
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            store = RunStore(state)
            run_id = store.create()
            (state / 'runtime-update-mask').mkdir()
            output = io.StringIO()
            with patch.object(cli, 'STATE', state), patch.object(cli.NativeClient, 'available', return_value=False), \
                    patch.object(cli, 'public_snapshot', return_value={'reason':'protected_native_status_snapshot_unavailable'}), \
                    patch('sys.stdout', output):
                self.assertEqual(cli.main(['status']), 0)
            self.assertEqual([row['run_id'] for row in json.loads(output.getvalue())['offline_fixture_ledger']], [run_id])

    def test_report_includes_imported_native_matrix(self):
        from lab import cli
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            write_results(results / 'matrix', blocked_matrix(['B01'], 'smoke_gate_failed'))
            output = io.StringIO()
            with patch.object(cli, 'RESULTS', results), patch('sys.stdout', output):
                self.assertEqual(cli.main(['report']), 0)
            self.assertEqual(json.loads(output.getvalue()),
                             {'matrix': {'actual_trials': 0, 'records': 2}})


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = RunStore(Path(self.temporary.name) / "state")
        self.run_id = self.store.create()
        self.token = self.store.token(self.run_id)

    def test_private_state_and_secret(self):
        self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.store.directory(self.run_id) / "secret.json").stat().st_mode & 0o777, 0o600)

    def test_wrong_token_denied_without_call(self):
        self.assertEqual(self.store.admit(self.run_id, "wrong", uuid.uuid4().hex, 5), "invalid_token")
        self.assertEqual(self.store.read(self.run_id)["calls"], 0)

    def test_replay_survives_new_store(self):
        job = uuid.uuid4().hex
        self.assertIsNone(self.store.admit(self.run_id, self.token, job, 5))
        restarted = RunStore(self.store.root)
        self.assertEqual(restarted.admit(self.run_id, self.token, job, 5), "reject_duplicate")

    def test_budget_atomic_across_threads_and_stores(self):
        run_id = self.store.create(max_calls=3)
        token = self.store.token(run_id)
        def attempt(_):
            return RunStore(self.store.root).admit(run_id, token, uuid.uuid4().hex, 5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(20)))
        self.assertEqual(results.count(None), 3)
        self.assertEqual(self.store.read(run_id)["calls"], 3)

    def test_output_reservations_not_refunded(self):
        run_id = self.store.create(max_tokens=10)
        token = self.store.token(run_id)
        self.assertIsNone(self.store.admit(run_id, token, uuid.uuid4().hex, 6))
        self.assertEqual(self.store.admit(run_id, token, uuid.uuid4().hex, 6), "token_budget_exhausted")

    def test_expiry_equality_revokes_and_heartbeat_cannot_revive(self):
        self.store.mutate(self.run_id, lambda m: self.store.active(m, m["deadline"]))
        self.assertFalse(self.store.heartbeat(self.run_id))
        self.assertEqual(self.store.read(self.run_id)["reason"], "absolute_expiry")

    def test_heartbeat_loss_and_clock_regression(self):
        for kind in ("heartbeat_lost", "invalid_or_regressed_host_clock"):
            run_id = self.store.create()
            now = lambda m: m["issued"] + 45 if kind == "heartbeat_lost" else m["issued"] - 1
            self.assertEqual(self.store.mutate(run_id, lambda m: self.store.active(m, now(m))), kind)

    def test_invalid_time_and_budgets(self):
        for value in (True, -1, 0, 6000, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.create(ttl=value)
        self.assertEqual(self.store.admit(self.run_id, self.token, uuid.uuid4().hex, True), "invalid_output_budget")

    def test_run_path_traversal_and_symlink_denied(self):
        for value in ("../elsewhere", "/tmp", "", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.directory(value)
        run_id = uuid.uuid4().hex
        (self.store.root / run_id).symlink_to(self.temporary.name)
        with self.assertRaises(ValueError):
            self.store.directory(run_id)

    def test_only_registered_inode_cleanup_and_idempotence(self):
        directory = self.store.directory(self.run_id)
        overlay = directory / "controller.qcow2"
        overlay.write_text("owned")
        unrelated = directory / "unrelated.txt"
        unrelated.write_text("preserve")
        self.store.register_resource(self.run_id, overlay.name)
        result = self.store.cleanup(self.run_id, lambda *args: None)
        self.assertEqual(result["removed"], [overlay.name])
        self.assertTrue(unrelated.exists())
        self.assertFalse((directory / "secret.json").exists())
        self.assertEqual(self.store.cleanup(self.run_id, lambda *args: None)["removed"], [])

    def test_replaced_resource_and_symlink_preserved(self):
        directory = self.store.directory(self.run_id)
        overlay = directory / "controller.qcow2"
        overlay.write_text("owned")
        self.store.register_resource(self.run_id, overlay.name)
        preserved = directory / "saved.qcow2"
        overlay.rename(preserved)
        overlay.write_text("replacement")
        result = self.store.cleanup(self.run_id, lambda *args: None)
        self.assertEqual(result["refused"], [overlay.name])
        self.assertTrue(overlay.exists())
        self.assertTrue(preserved.exists())

    def test_cleanup_dry_run_changes_nothing(self):
        before = self.store.read(self.run_id)
        self.store.cleanup(self.run_id, lambda *args: self.fail("must not stop"), dry_run=True)
        self.assertEqual(self.store.read(self.run_id), before)
        self.assertTrue((self.store.directory(self.run_id) / "secret.json").exists())

    def test_unknown_resource_denied(self):
        with self.assertRaises(ValueError):
            self.store.register_resource(self.run_id, "../../personal")

    def test_cleanup_refuses_unconfirmed_termination(self):
        with self.assertRaises(RuntimeError):
            self.store.cleanup(self.run_id, lambda *args: [{"outcome": "termination_unconfirmed"}])
        self.assertTrue((self.store.directory(self.run_id) / "secret.json").exists())


class RequestTests(unittest.TestCase):
    def request(self, **changes):
        return json.dumps({"model": "arm", "messages": [{"role": "user", "content": "synthetic"}], **changes}).encode()

    def test_text_request_with_matched_defaults(self):
        result = validate_request(self.request(), "arm")
        self.assertEqual((result["max_tokens"], result["temperature"], result["seed"]), (1024, 0.0, 41))

    def test_file_url_media_admin_and_tools_denied(self):
        for field in ("image", "url", "tools", "tool_choice", "file", "backend", "command"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_request(self.request(**{field: "arbitrary"}), "arm")
        with self.assertRaises(ValueError):
            validate_request(self.request(messages=[{"role": "user", "content": [{"type": "image_url"}]}]), "arm")

    def test_wrong_model_and_invalid_sampling(self):
        for changes in ({"model": "other"}, {"max_tokens": 1025}, {"max_tokens": True}, {"temperature": math.nan},
                        {"top_p": -1}, {"stream": True}, {"seed": True}, {"messages": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_request(self.request(**changes), "arm")

    def test_duplicate_keys_and_depth_denied(self):
        with self.assertRaises(ValueError):
            validate_request(b'{"model":"arm","model":"arm","messages":[]}', "arm")
        with self.assertRaises(ValueError):
            validate_request(b"[" * 100 + b"0" + b"]" * 100, "arm")


class RuntimeTests(unittest.TestCase):
    def test_guest_output_is_bounded_before_JSON_parsing(self):
        with self.assertRaises(ValueError):
            bounded_process([sys.executable, "-c", "import sys;sys.stdout.write('x'*70000)"], b"{}", 2)

    def test_stalled_guest_transport_is_killed_on_timeout(self):
        with self.assertRaises(TimeoutError):
            bounded_process([sys.executable, "-c", "import time;time.sleep(10)"], b"{}", 0.1)

    def test_bounded_guest_input_and_response(self):
        raw = b'{"fixture":true}'
        output = bounded_process([sys.executable, "-c", "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"], raw, 2)
        self.assertEqual(output, raw)

    def test_QEMU_has_KVM_restriction_no_host_sharing_and_loopback(self):
        command = qemu_argv("controller", "/var/lib/lab/controller.qcow2", "/var/lib/lab/controller.seed", 22022, str(uuid.uuid4()))
        joined = " ".join(command)
        self.assertIn("accel=kvm", joined)
        self.assertIn("restrict=on", joined)
        self.assertIn("127.0.0.1:22022", joined)
        for option in ("tcg", "virtfs", "guestfwd", "vnc", "spice", "vfio", "0.0.0.0"):
            self.assertNotIn(option, joined)

    def test_bad_VM_and_option_injection_rejected(self):
        for vm, path, port in (("router", "/tmp/a", 22022), ("controller", "/tmp/a,if=none", 22022), ("controller", "/tmp/a", True)):
            with self.assertRaises(ValueError):
                qemu_argv(vm, path, "/tmp/seed", port, str(uuid.uuid4()))

    def test_pidfd_identity_mismatch_never_targets_real_process(self):
        record = identity(os.getpid())
        record["start_ticks"] += 1
        self.assertIsNone(open_owned(record))

    def test_artifact_hash_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image"
            path.write_bytes(b"fixture")
            with self.assertRaises(ValueError):
                verify_artifact({"path": str(path), "bytes": 7, "sha256": "0" * 64})

    def test_transport_requires_pinned_full_inventory(self):
        with self.assertRaises(ValueError):
            GuestTransport({"router": {}})

    def test_blocked_records_never_count_as_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = blocked_matrix(["B01", "B04", "B08"], "isolation_unverified")
            result = write_results(directory, rows)
            self.assertEqual(result, {"actual_trials": 0, "records": 6})
            self.assertTrue(all(row["passed"] is None for row in rows))

    def test_counterbalanced_schedule_preserves_limits_and_prompt(self):
        root = Path(__file__).resolve().parents[1]
        cases = json.loads((root / "bench/cases.json").read_text())["cases"]
        trials = paired_schedule(cases, repeats=2)
        self.assertEqual(len(trials), 12)
        self.assertEqual(trials[0]["arm"], "normal")
        self.assertEqual(trials[6]["arm"], "abliterated")
        self.assertEqual(trials[0]["prompt_sha256"], trials[3]["prompt_sha256"])
        self.assertTrue(all(trial["output_tokens"] == 1024 for trial in trials))


class PreparationTests(unittest.TestCase):
    def pin(self, data=b"GGUFfixture"):
        return {"repo": REPOSITORY, "revision": "1" * 40, "filename": "fixture.Q4_K_M.gguf",
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def test_bad_repository_and_unpinned_candidate_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            for changes in ({"repo": "other/repo"}, {"revision": "main"}, {"filename": "../weights.gguf"}, {"bytes": True}, {"sha256": None}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    fetch_candidate({**self.pin(), **changes}, directory, dry_run=True)

    def test_verified_data_only_fetch_and_idempotence(self):
        data = b"GGUFfixture"
        with tempfile.TemporaryDirectory() as directory, patch("lab.preparation.urllib.request.urlopen", return_value=io.BytesIO(data)) as fetch:
            self.assertTrue(fetch_candidate(self.pin(data), directory)["verified"])
            self.assertTrue(fetch_candidate(self.pin(data), directory)["verified"])
            self.assertEqual(fetch.call_count, 1)

    def test_wrong_bytes_are_removed_and_never_published(self):
        with tempfile.TemporaryDirectory() as directory, patch("lab.preparation.urllib.request.urlopen", return_value=io.BytesIO(b"incorrect")):
            with self.assertRaises(ValueError):
                fetch_candidate(self.pin(), directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_dry_run_never_fetches(self):
        with tempfile.TemporaryDirectory() as directory, patch("lab.preparation.urllib.request.urlopen") as fetch:
            self.assertTrue(fetch_candidate(self.pin(), directory, dry_run=True)["dry_run"])
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
