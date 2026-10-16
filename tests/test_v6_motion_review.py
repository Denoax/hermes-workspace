"""Private fixture lifecycle/provenance tests; no browser, X11 or real timer."""
from copy import deepcopy
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import v6_motion_review as motion


class FakeProcess:
    def __init__(self, running=True):
        self.running = running
        self.signals = []
    def poll(self):
        return None if self.running else 0
    def send_signal(self, value):
        self.signals.append(value)


class FakeTimer:
    def __init__(self, seconds, callback):
        self.seconds, self.callback = seconds, callback
        self.started = self.cancelled = self.joined = False
    def start(self):
        self.started = True
    def cancel(self):
        self.cancelled = True
    def join(self, timeout):
        self.joined = timeout
    def is_alive(self):
        return False


class RecordingWatchdogTests(unittest.TestCase):
    def test_early_stop_signals_only_its_own_running_child(self):
        child, other = FakeProcess(), FakeProcess()
        guard = motion.ClipWatchdog(child, timer_factory=FakeTimer)
        self.assertEqual(guard.timer.seconds, 24)
        self.assertTrue(guard.timer.daemon)
        guard.start(); guard.timer.callback()
        self.assertTrue(guard.fired)
        self.assertEqual(child.signals, [signal.SIGINT])
        self.assertEqual(other.signals, [])
        guard.close()
        self.assertTrue(guard.timer.cancelled)
        self.assertEqual(guard.timer.joined, 2)

    def test_already_exited_child_is_not_signalled(self):
        child = FakeProcess(False)
        guard = motion.ClipWatchdog(child, timer_factory=FakeTimer)
        guard.timer.callback()
        self.assertEqual(child.signals, [])
        self.assertTrue(guard.fired)

    def test_cap_cannot_be_widened_or_removed(self):
        for seconds in (0, -1, 25, 30, float('inf')):
            with self.subTest(seconds=seconds), self.assertRaises(RuntimeError):
                motion.ClipWatchdog(FakeProcess(), seconds=seconds, timer_factory=FakeTimer)


class OriginalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.proof = {'id': 'a' * 32, 'name': 'owned-context.txt', 'mime': 'text/plain', 'bytes': 77,
                      'sha256': 'b' * 64, 'draft_sha256': 'c' * 64}

    def test_single_and_resumed_receipts_return_the_original_proof(self):
        for receipt in ({'checks': {'A_genuine_UTF8_draft_and_attachment': self.proof}},
                        {'resumed_from': {'checks': {'A_genuine_UTF8_draft_and_attachment': self.proof}}}):
            with self.subTest(receipt=receipt):
                self.assertEqual(motion.attachment_proof(receipt), self.proof)

    def test_aggregate_needs_a_passed_actual_A_subcheck_without_changing_overall_status(self):
        receipt = {'kind': 'actual_interaction_subcheck_aggregate', 'status': 'PARTIAL',
                   'subchecks': {'A_genuine_UTF8_draft_and_attachment': {'outcome': 'PASS', 'value': self.proof}}}
        self.assertEqual(motion.attachment_proof(receipt), self.proof)
        self.assertEqual(receipt['status'], 'PARTIAL')
        receipt['subchecks']['A_genuine_UTF8_draft_and_attachment']['outcome'] = 'UNVERIFIED'
        with self.assertRaises(RuntimeError):
            motion.attachment_proof(receipt)

    def test_missing_or_malformed_attachment_receipt_is_not_replaced_with_fixture(self):
        for receipt in ({}, {'checks': {'A_genuine_UTF8_draft_and_attachment': {'id': 'a' * 32}}},
                        {'checks': {'A_genuine_UTF8_draft_and_attachment': {**self.proof, 'id': 'user-file'}}}):
            with self.subTest(receipt=receipt), self.assertRaises(RuntimeError):
                motion.attachment_proof(receipt)

    def test_aggregate_values_and_hashes_must_match_preserved_original_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            nonce, aid = 'V6interaction-012345abcdef', 'a' * 32
            sources = []
            originals = []
            for index, check in enumerate(('one', 'two')):
                folder = base / str(index) / 'owned'; folder.mkdir(parents=True)
                artifact = {'case': {'nonce': nonce, 'records': {'A': {'id': aid}}}, 'checks': {check: True}}
                run = {'status': 'FAIL', 'source_sha256_before': {'source.py': str(index) * 64}}
                path, run_path = folder / 'interactions.json', folder.parent / 'run.json'
                path.write_text(json.dumps(artifact)); run_path.write_text(json.dumps(run)); originals.append(path)
                sources.append({'artifact': str(path.relative_to(base)), 'sha256': motion.sha(path.read_bytes()),
                                'run_artifact': str(run_path.relative_to(base)), 'run_sha256': motion.sha(run_path.read_bytes()),
                                'overall_status': 'FAIL', 'source_sha256': run['source_sha256_before']})
            receipt = {'kind': 'actual_interaction_subcheck_aggregate', 'status': 'PARTIAL',
                       'case': {'nonce': nonce, 'records': {'A': {'id': aid}}}, 'receipts': sources,
                       'subchecks': {'one': {'source_receipt': 0, 'value': True}, 'two': {'source_receipt': 1, 'value': True}}}
            path = base / 'aggregate.json'; path.write_text(json.dumps(receipt))
            result = motion.verify_aggregate_bytes(receipt, path)
            self.assertEqual(result['status'], 'PASS')
            self.assertFalse(result['whole_sequence_promoted_to_PASS'])
            changed = deepcopy(receipt); changed['subchecks']['one']['value'] = False
            with self.assertRaisesRegex(RuntimeError, 'aggregate_value'):
                motion.verify_aggregate_bytes(changed, path)
            originals[0].write_text('Changed original bytes')
            with self.assertRaisesRegex(RuntimeError, 'bytes_changed'):
                motion.verify_aggregate_bytes(receipt, path)


if __name__ == '__main__':
    unittest.main()
