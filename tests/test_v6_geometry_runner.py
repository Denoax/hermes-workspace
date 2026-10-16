"""Receipt/real-size planning only; this suite opens no native window."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_v6_geometry as probe


class ExistingOwnedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.case = {'nonce': 'V6interaction-012345abcdef', 'created_ids': [digit * 32 for digit in 'abcd'],
                     'before_session_ids': ['e' * 32], 'records': {}}
        for role, digit, kind, field in (('P', 'a', 'project', 'label'), ('Q', 'b', 'project', 'label'),
                                       ('A', 'c', 'conversation', 'title'), ('B', 'd', 'conversation', 'title')):
            self.case['records'][role] = {'id': digit * 32, 'kind': kind, field: self.case['nonce'] + ' · ' + role}
        self.receipt = {'status': 'PASS_SCOPED_TECHNICAL', 'case': self.case}

    def test_completed_before_inventory_and_distinct_new_roles_are_retained(self):
        loaded = probe.load_case(self.receipt)
        self.assertEqual(loaded, self.case)
        loaded['records']['A']['title'] = 'Changed private copy'
        self.assertNotEqual(loaded, self.case)
        converted = probe.surface_case(self.case)
        self.assertEqual(converted['created_session_ids'], ['c' * 32, 'd' * 32])
        self.assertEqual(converted['before_session_ids'], ['e' * 32])
        self.assertEqual(converted['viewed_session_id'], 'c' * 32)
        self.assertEqual(converted['target_session_id'], 'd' * 32)

    def test_partial_receipt_or_missing_before_inventory_cannot_be_promoted(self):
        for status in ('PARTIAL', 'IN_PROGRESS', 'PASS', None):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                probe.load_case({**self.receipt, 'status': status})
        self.case.pop('before_session_ids')
        with self.assertRaisesRegex(RuntimeError, 'before_inventory'):
            probe.load_case(self.receipt)

    def test_preexisting_A_or_B_is_rejected(self):
        for role in ('A', 'B'):
            changed = deepcopy(self.receipt)
            changed['case']['before_session_ids'].append(self.case['records'][role]['id'])
            with self.subTest(role=role), self.assertRaisesRegex(RuntimeError, 'new_distinct'):
                probe.load_case(changed)

    def test_unowned_title_or_unknown_role_or_duplicate_creation_is_rejected(self):
        changed = deepcopy(self.receipt); changed['case']['records']['B']['title'] = 'User conversation'
        with self.assertRaises(RuntimeError):
            probe.load_case(changed)
        changed = deepcopy(self.receipt); changed['case']['records'].pop('Q')
        with self.assertRaises(RuntimeError):
            probe.load_case(changed)
        changed = deepcopy(self.receipt); changed['case']['created_ids'].append('c' * 32)
        with self.assertRaises(RuntimeError):
            probe.load_case(changed)

    def test_malformed_nonce_is_rejected_without_creating_a_case(self):
        for nonce in ('V6review-1234abcd', 'V6interaction-1234', 'V6interaction-012345ABCDEF', 'user-project'):
            changed = deepcopy(self.receipt); changed['case']['nonce'] = nonce
            with self.subTest(nonce=nonce), self.assertRaises(RuntimeError):
                probe.load_case(changed)


class NativeSizePlanningTests(unittest.TestCase):
    def setUp(self):
        self.chrome = {'outerWidth': 1320, 'innerWidth': 1320, 'outerHeight': 928, 'innerHeight': 900}
        self.work_area = (0, 24, 1920, 1056)

    def test_exact_desktop_and_narrow_requests_preserve_requested_CSS_dimensions(self):
        for width, height in ((1320, 900), (1280, 800), (1440, 900), (390, 844), (640, 420)):
            with self.subTest(size=(width, height)):
                result = probe.native_size_plan(width, height, self.chrome, self.work_area, native_size=(1320, 928))
                self.assertEqual(result['status'], 'READY')
                self.assertEqual(result['requested_CSS'], [width, height])
                self.assertEqual(result['requested_outer'], [width, height + 28])
                self.assertFalse(result['clamped'])

    def test_full_HD_exceeding_reserved_work_area_is_blocked_without_clamping(self):
        result = probe.native_size_plan(1920, 1080, self.chrome, self.work_area, native_size=(1320, 928))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['requested_outer'], [1920, 1108])
        self.assertFalse(result['clamped'])

    def test_large_enough_monitor_can_support_the_exact_full_HD_request(self):
        self.assertEqual(probe.native_size_plan(1920, 1080, self.chrome, (0, 0, 2560, 1440), native_size=(1320, 928))['status'], 'READY')

    def test_xwayland_js_decorations_are_not_added_to_the_actual_surface(self):
        chrome = {'outerWidth': 1327, 'innerWidth': 1320, 'outerHeight': 905, 'innerHeight': 900}
        result = probe.native_size_plan(1320, 900, chrome, self.work_area, native_size=(1320, 900))
        self.assertEqual(result['requested_outer'], [1320, 900])
        self.assertEqual(result['status'], 'READY')

    def test_unrequested_or_nonfinite_geometry_cannot_be_silently_substituted(self):
        with self.assertRaisesRegex(RuntimeError, 'fixed_geometry'):
            probe.native_size_plan(1888, 1024, self.chrome, self.work_area, native_size=(1320, 928))
        changed = {**self.chrome, 'outerWidth': float('nan')}
        with self.assertRaisesRegex(RuntimeError, 'finite_browser_size'):
            probe.native_size_plan(1320, 900, changed, self.work_area, native_size=(1320, 928))


class ScopedAggregateTests(unittest.TestCase):
    def setUp(self):
        fixture = ExistingOwnedReceiptTests()
        fixture.setUp()
        case = deepcopy(fixture.case)
        for role, digit in (('D', '0'), ('E', '1')):
            case['created_ids'].append(digit * 32)
            case['records'][role] = {'id': digit * 32, 'kind': 'conversation', 'title': case['nonce'] + ' · ' + role}
        sources = []
        for index, digit in enumerate(('a', 'b')):
            sources.append({'artifact': f'attempt-{index}/owned/interactions.json', 'sha256': digit * 64,
                            'run_artifact': f'attempt-{index}/run.json', 'run_sha256': str(index + 2) * 64,
                            'overall_status': 'FAIL', 'source_sha256': {'workspace/frontend/src/main.tsx': 'c' * 64}})
        checks = {name: {'outcome': 'PASS', 'source_receipt': 0 if index < 6 else 1, 'value': True}
                  for index, name in enumerate(probe.SUBCHECKS)}
        checks['A_genuine_UTF8_draft_and_attachment']['value'] = {
            'id': '2' * 32, 'name': 'owned-context.txt', 'mime': 'text/plain', 'bytes': 77,
            'sha256': '3' * 64, 'draft_sha256': '4' * 64}
        checks['D_actual_core_Cancel_Escape_and_confirm_only_known_empty']['value'] = {'deleted_id': '0' * 32}
        checks['stale_owned_E_error_never_adopts_A']['value'] = {'fault_deleted_id': '1' * 32, 'visible_alert': True}
        self.receipt = {'kind': probe.AGGREGATE, 'status': 'PARTIAL', 'interaction_subchecks_complete': True,
                        'case': case, 'subchecks': checks, 'receipts': sources}

    def test_complete_scoped_aggregate_retains_both_failed_attempt_identities(self):
        self.assertEqual(probe.load_case(self.receipt), self.receipt['case'])
        self.assertEqual(self.receipt['status'], 'PARTIAL')
        self.assertEqual([row['overall_status'] for row in self.receipt['receipts']], ['FAIL', 'FAIL'])

    def test_incomplete_aggregate_cannot_bypass_the_completed_case_gate(self):
        for field, value in [('interaction_subchecks_complete', False), ('status', 'PASS_SCOPED_TECHNICAL'), ('kind', 'generic_aggregate')]:
            changed = deepcopy(self.receipt); changed[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                probe.load_case(changed)

    def test_missing_failed_or_false_subcheck_is_rejected(self):
        first = probe.SUBCHECKS[0]
        for kind in ('missing', 'failed', 'false', 'bad_index'):
            changed = deepcopy(self.receipt)
            if kind == 'missing': del changed['subchecks'][first]
            elif kind == 'failed': changed['subchecks'][first]['outcome'] = 'FAIL'
            elif kind == 'false': changed['subchecks'][first]['value'] = False
            else: changed['subchecks'][first]['source_receipt'] = True
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                probe.load_case(changed)

    def test_malformed_unpaired_or_duplicate_receipt_identity_is_rejected(self):
        for field, value in [('sha256', 'not-a-sha'), ('run_sha256', 42), ('artifact', '../outside/owned/interactions.json'),
                             ('run_artifact', 'other-attempt/run.json'), ('source_sha256', {}), ('overall_status', 'PASS')]:
            changed = deepcopy(self.receipt); changed['receipts'][0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                probe.load_case(changed)
        changed = deepcopy(self.receipt); changed['receipts'][1] = deepcopy(changed['receipts'][0])
        with self.assertRaises(RuntimeError): probe.load_case(changed)

    def test_deleted_or_stale_check_cannot_adopt_the_viewed_A_identity(self):
        changed = deepcopy(self.receipt)
        changed['subchecks']['D_actual_core_Cancel_Escape_and_confirm_only_known_empty']['value']['deleted_id'] = changed['case']['records']['A']['id']
        with self.assertRaises(RuntimeError): probe.load_case(changed)


if __name__ == '__main__':
    unittest.main()
