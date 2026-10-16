"""Temporary ledger/ZIP contracts only; no native, GPU, GUI or publication."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import canonical_v5_acceptance as canonical_v5
import canonical_v6_acceptance as canonical
import package_v5_review as shared
import package_v6_review as package
import prepare_v6_scope as scope
from v6_review_profile import NAME, TASK_IDS, V5_TASK_IDS, V6_TASK_IDS
import test_v5_review_package as fixtures


class V6CanonicalAndArchiveTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CanonicalAndPackageTests('test_complete_package_round_trip_and_source_identity')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        prototype = fixture.requirements['tasks'][0]
        fixture.requirements['tasks'] = [{**deepcopy(prototype), 'id': name} for name in TASK_IDS]
        fixture.state['tasks'] = {name: {'status': 'TODO', 'evidence': [], 'notes': 'Temporary utility fixture only.'}
                                  for name in TASK_IDS}
        fixture.state['tasks'][TASK_IDS[0]].update(status='DONE', evidence=['fixture-review'])
        fixture.state['tasks'][TASK_IDS[1]].update(acceptance_status='PARTIAL', evidence=['fixture-review'])
        fixture.state['tasks'][TASK_IDS[2]].update(status='BLOCKED', blocker='Deliberate fixture boundary')
        fixture.state['tasks'][TASK_IDS[3]].update(status='VERIFY', evidence=['fixture-review'])
        fixture.write_ledger()

    def generate(self):
        fixture = self.fixture
        return canonical.generate(fixture.live, fixture.base / 'public', fixture.review, fixtures.controller.inspect)

    def package_inputs(self):
        fixture = self.fixture
        result = self.generate()
        for name in ('rollback.md', 'source-export-recipe.md'):
            (fixture.review / name).write_text('Temporary test fixture; no live operation.\n')
        (fixture.review / 'source-export.json').write_bytes(shared.encoded({'source_files': {
            'app.py': shared.digest(fixture.source['files']['app.py'])}}))
        (fixture.review / 'diff-manifest.json').write_bytes(shared.encoded({'changes': []}))
        return sorted(result['required_review_files'] + ['rollback.md', 'source-export-recipe.md',
                                                       'source-export.json', 'diff-manifest.json'])

    def test_exact_57_rows_preserve_old_and_append_new_without_invented_passes(self):
        acceptance = self.generate()['acceptance']
        self.assertEqual([row['id'] for row in acceptance['rows']], list(TASK_IDS))
        self.assertEqual(acceptance['summary']['counts'], {'PASS': 1, 'PARTIAL': 2, 'BLOCKED': 1, 'UNVERIFIED': 53})
        self.assertEqual(acceptance['summary']['overall'], 'PARTIAL')
        self.assertEqual(acceptance['summary']['unfinished_ids'][-1], 'V6-HUMAN')
        self.assertFalse(acceptance['human_identity_authenticated_by_generator'])

    def test_v5_default_rejects_v6_and_v6_rejects_truncated_v5_inventory(self):
        fixture = self.fixture
        with self.assertRaisesRegex(ValueError, 'exact_36'):
            canonical_v5.generate(fixture.live, fixture.base / 'public', fixture.review, fixtures.controller.inspect)
        fixture.requirements['tasks'] = fixture.requirements['tasks'][:36]
        fixture.state['tasks'] = {name: item for name, item in fixture.state['tasks'].items() if name in V5_TASK_IDS}
        fixture.write_ledger()
        with self.assertRaisesRegex(ValueError, 'exact_57'):
            self.generate()

    def test_wrong_old_or_new_id_and_reordered_inventory_are_rejected_even_at_57(self):
        fixture = self.fixture
        for index in (0, 36):
            original = fixture.requirements['tasks'][index]['id']
            fixture.requirements['tasks'][index]['id'] = 'UNKNOWN'
            fixture.state['tasks']['UNKNOWN'] = fixture.state['tasks'].pop(original)
            fixture.write_ledger()
            with self.assertRaisesRegex(ValueError, 'exact_57'):
                self.generate()
            fixture.requirements['tasks'][index]['id'] = original
            fixture.state['tasks'][original] = fixture.state['tasks'].pop('UNKNOWN')
        fixture.requirements['tasks'][36:38] = reversed(fixture.requirements['tasks'][36:38])
        fixture.write_ledger()
        with self.assertRaisesRegex(ValueError, 'exact_57'):
            self.generate()

    def test_summary_needs_all_57_actual_done_rows_and_current_proofs(self):
        fixture = self.fixture
        for item in fixture.state['tasks'].values():
            item.clear()
            item.update(status='DONE', evidence=['fixture-review'], notes='Fixture only')
        fixture.write_ledger()
        acceptance = self.generate()['acceptance']
        self.assertEqual(acceptance['summary']['counts']['PASS'], 57)
        self.assertEqual(acceptance['summary']['overall'], 'PASS')
        (fixture.live / 'app.py').write_text('A changed fixture source\n')
        with self.assertRaisesRegex(ValueError, 'stale source'):
            self.generate()

    def test_v6_roundtrip_has_fixed_root_and_rejects_v5_root_before_extraction(self):
        fixture = self.fixture
        output = fixture.base / 'complete-v6.zip'
        receipt = package.package(fixture.base / 'public', fixture.review, self.package_inputs(), output)
        extracted, count = package.verify(output, fixture.base / 'extracted-v6')
        self.assertEqual(extracted.name, NAME)
        self.assertEqual(receipt['payloads_verified'], count)
        with zipfile.ZipFile(output) as archive:
            self.assertTrue(all(name.startswith(NAME + '/') for name in archive.namelist()))
        with self.assertRaisesRegex(ValueError, 'fixed_regular_archive_root'):
            shared.verify(output, fixture.base / 'wrong-version')
        self.assertFalse((fixture.base / 'wrong-version').exists())

    def test_v6_packager_rejects_canonical_row_or_ledger_omission(self):
        fixture = self.fixture
        files = self.package_inputs()
        acceptance = json.loads((fixture.review / 'acceptance.json').read_text())
        acceptance['rows'].pop(10)
        (fixture.review / 'acceptance.json').write_bytes(shared.encoded(acceptance))
        with self.assertRaisesRegex(ValueError, 'exact_ledger_inventory'):
            package.package(fixture.base / 'public', fixture.review, files, fixture.base / 'omitted.zip')

    def test_generic_archive_root_parameter_cannot_escape_destination(self):
        fixture = self.fixture
        for name in ('../outside', 'root/nested', '/absolute'):
            with self.assertRaises(ValueError):
                shared.verify(fixture.base / 'absent.zip', fixture.base / 'never-created', archive_name=name)
        self.assertFalse((fixture.base / 'never-created').exists())


class AdditiveScopeTests(unittest.TestCase):
    def setUp(self):
        self.requirements = {'objective': 'Original v5 objective', 'constraints': ['preserve'], 'tasks': [
            {'id': name, 'depends_on': [], 'required_evidence': ['review']} for name in V5_TASK_IDS]}
        self.extension = {'schema_version': 1, 'tasks': [
            {'id': name, 'depends_on': []} for name in V6_TASK_IDS]}
        self.state = {'tasks': {name: {'status': 'TODO', 'evidence': [], 'notes': 'Original pending scope'}
                                for name in V5_TASK_IDS}, 'human_approval': None,
                      'evidence': {'baseline': {'source_files': {'baseline.py': 'a' * 64}},
                                   'ui': {'source_files': {'ui.tsx': 'b' * 64}}}}
        self.state['tasks']['BASE-01'].update(status='DONE', evidence=['baseline'])
        self.state['tasks']['UI-01'].update(status='DONE', evidence=['ui'])
        self.state['tasks']['CHAT-01'].update(status='DONE', evidence=['baseline'])
        next(task for task in self.requirements['tasks'] if task['id'] == 'CHAT-01')['depends_on'] = ['UI-01']
        self.state['tasks']['VM-01'].update(status='BLOCKED', blocker='Native authentication absent')

    def test_only_changed_completion_and_dependent_done_reopen_with_history(self):
        original_requirements, original_state = deepcopy(self.requirements), deepcopy(self.state)
        requirements, state, affected = scope.extend(self.requirements, self.state, self.extension, {'ui.tsx'})
        self.assertEqual(set(affected), {'UI-01', 'CHAT-01'})
        self.assertEqual(requirements['tasks'][:36], original_requirements['tasks'])
        self.assertEqual(state['evidence'], original_state['evidence'])
        self.assertEqual(state['tasks']['BASE-01'], original_state['tasks']['BASE-01'])
        self.assertEqual(state['tasks']['VM-01'], original_state['tasks']['VM-01'])
        for name in affected:
            self.assertEqual(state['tasks'][name]['status'], 'VERIFY')
            self.assertEqual(state['tasks'][name]['history'][-1]['previous_claim'], original_state['tasks'][name])
            self.assertEqual(state['tasks'][name]['evidence'], original_state['tasks'][name]['evidence'])
        self.assertEqual(self.requirements, original_requirements)
        self.assertEqual(self.state, original_state)
        self.assertIsNone(state['human_approval'])

    def test_all57_rows_have_one_active_task_and_no_new_completion_or_approval(self):
        requirements, state, _ = scope.extend(self.requirements, self.state, self.extension, set())
        self.assertEqual([task['id'] for task in requirements['tasks']], list(TASK_IDS))
        self.assertEqual([name for name, item in state['tasks'].items() if item['status'] == 'IN_PROGRESS'], ['V6-BASE'])
        self.assertTrue(all(state['tasks'][name]['evidence'] == [] for name in V6_TASK_IDS))
        self.assertTrue(all(state['tasks'][name]['status'] in {'TODO', 'IN_PROGRESS'} for name in V6_TASK_IDS))

    def test_scope_change_refuses_active_batch_or_missing_original_row(self):
        self.state['tasks']['UI-04']['status'] = 'IN_PROGRESS'
        with self.assertRaisesRegex(ValueError, 'stop_current_batch'):
            scope.extend(self.requirements, self.state, self.extension, set())
        self.state['tasks'].pop('UI-04')
        with self.assertRaisesRegex(ValueError, 'exact_live_v5'):
            scope.extend(self.requirements, self.state, self.extension, set())

    def test_wrong_extension_identity_or_reapplication_is_rejected(self):
        self.extension['tasks'][0]['id'] = 'V6-HUMAN'
        with self.assertRaisesRegex(ValueError, 'exact_additive_v6'):
            scope.extend(self.requirements, self.state, self.extension, set())
        self.requirements['tasks'].append({'id': 'V6-BASE'})
        with self.assertRaisesRegex(ValueError, 'exact_live_v5'):
            scope.extend(self.requirements, self.state, self.extension, set())


if __name__ == '__main__':
    unittest.main()
