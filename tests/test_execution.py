"""Outside grading/orchestration contracts with a fixture client, never model trials."""
import unittest
from lab.execution import execute_matrix


class FixtureClient:
    def __init__(self, answer=None, blocked=False):
        self.answer = answer
        self.blocked = blocked
        self.calls = []

    def call(self, operation, **fields):
        self.calls.append((operation, fields))
        if operation == 'run_case':
            if self.blocked:
                return {'status': 'blocked', 'reason': 'fixture_missing_backend'}
            return {'status': 'ok', 'evidence_kind': 'real_guest_Hermes', 'answer': self.answer,
                    'model_sha256': 'a'*64, 'finish_reason': 'stop'}
        return {'status': 'ok'}


class OutsideGrading(unittest.TestCase):
    def test_blocked_case_is_unscored_and_teardown_is_always_requested(self):
        client = FixtureClient(blocked=True)
        rows = execute_matrix(client, 'a'*32, ['B01'])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['passed'] is None and row['status'] == 'blocked' for row in rows))
        self.assertEqual([name for name, _ in client.calls[-2:]], ['stop', 'cleanup'])

    def test_normal_only_case_is_not_labelled_paired(self):
        client = FixtureClient(answer='{"stale_workers":["B"]}')
        row = execute_matrix(client, 'a'*32, ['B01'], arms=('normal',))[0]
        self.assertEqual(row['execution_kind'], 'normal_guest_Hermes')
        self.assertTrue(row['passed'])

    def test_wrong_answer_is_graded_outside_guest(self):
        client = FixtureClient(answer='{"stale_workers":[]}')
        row = execute_matrix(client, 'a'*32, ['B01'], arms=('normal',))[0]
        self.assertFalse(row['passed'])
        self.assertEqual(row['category'], 'incorrect')

    def test_candidate_only_case_retains_candidate_identity(self):
        client=FixtureClient(answer='{"stale_workers":["B"]}')
        row=execute_matrix(client,'a'*32,['B01'],arms=('abliterated',))[0]
        self.assertEqual(row['execution_kind'],'abliterated_guest_Hermes')
        self.assertEqual(row['arm'],'abliterated')

    def test_non_guest_evidence_is_rejected_and_fleet_stopped(self):
        client = FixtureClient(answer='{}')
        original = client.call
        def wrong(operation, **fields):
            response = original(operation, **fields)
            if operation == 'run_case':
                response['evidence_kind'] = 'host_mock'
            return response
        client.call = wrong
        with self.assertRaises(ValueError):
            execute_matrix(client, 'a'*32, ['B01'])
        self.assertEqual([name for name, _ in client.calls[-2:]], ['stop', 'cleanup'])


if __name__ == '__main__':
    unittest.main()
