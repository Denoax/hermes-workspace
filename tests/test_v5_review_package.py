"""Hermetic temporary files/ZIPs and read-only Git fakes; no native/Git mutation."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import package_v5_review as package
import canonical_v5_acceptance as canonical

# Reuse the actual ledger validator while testing only harmless local fixtures.
CONTROLLER = Path(os.environ.get('HERMES_TEST_CONTROLLER_SOURCE', str(SCRIPTS / 'loopctl.py')))
spec = importlib.util.spec_from_file_location('v5_package_controller_test', CONTROLLER)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class CanonicalAndPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.live, self.review = self.base / 'live', self.base / 'review'
        self.loop = self.live / canonical.LOOP
        self.loop.mkdir(parents=True); self.review.mkdir()
        app = b'print("fixture")\n'
        (self.live / 'app.py').write_bytes(app)
        (self.live / 'evidence.json').write_text('{"scope":"harmless fixture"}\n')
        self.source = {'commit': 'a' * 40, 'tree': 'b' * 40, 'files': {'app.py': app}, 'modes': {'app.py': '100644'}}
        self.requirements = {'schema_version': 1, 'production_url': 'http://127.0.0.1:18791/hermes-workspace',
                             'tasks': [{'id': f'R{i:02}', 'title': f'Row{i}', 'acceptance': 'fixture contract',
                                        'depends_on': [], 'required_evidence': ['review']} for i in range(36)]}
        self.state = {'schema_version': 1, 'tasks': {task['id']: {'status': 'TODO', 'evidence': [], 'notes': 'Fixture scope only'}
                                                   for task in self.requirements['tasks']},
                      'evidence': {'fixture-review': {'kind': 'review', 'outcome': 'PASS', 'fixture': False,
                                   'artifact': 'evidence.json', 'sha256': package.digest((self.live / 'evidence.json').read_bytes()),
                                   'source_files': {'app.py': package.digest(app)}, 'scope': 'Test fixture only'}}}
        self.state['tasks']['R00'].update(status='DONE', evidence=['fixture-review'])
        self.state['tasks']['R01'].update(acceptance_status='PARTIAL', evidence=['fixture-review'])
        self.state['tasks']['R02'].update(status='BLOCKED', blocker='Native fixture deliberately absent')
        self.state['tasks']['R03'].update(status='VERIFY', evidence=['fixture-review'])
        self.write_ledger()
        for name in ('PLAN.md', 'RESUME.md'):(self.loop / name).write_text('Harmless fixture checkpoint\n')
        self.publication = {'status': 'PENDING', 'commit': self.source['commit'], 'tree': self.source['tree'], 'reason': 'Fixture has no remote'}
        self.write_publication()
        self.patcher = patch.object(package, 'committed_source', return_value=self.source)
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def write_ledger(self):
        data = package.encoded(self.requirements)
        (self.loop / 'requirements.json').write_bytes(data)
        self.state['requirements_sha256'] = package.digest(data)
        (self.loop / 'state.json').write_bytes(package.encoded(self.state))

    def write_publication(self):
        (self.review / 'publication.json').write_bytes(package.encoded(self.publication))

    def generate(self):return canonical.generate(self.live, self.base / 'public', self.review, controller.inspect)

    def package_inputs(self):
        result = self.generate()
        (self.review / 'rollback.md').write_text('Fixture rollback only; no host operation.\n')
        (self.review / 'source-export-recipe.md').write_text('Fixture recipe; no Git mutation.\n')
        (self.review / 'source-export.json').write_bytes(package.encoded({'source_files': {'app.py': package.digest(self.source['files']['app.py'])}}))
        (self.review / 'diff-manifest.json').write_bytes(package.encoded({'changes': []}))
        files = sorted(result['required_review_files'] + ['rollback.md', 'source-export.json', 'diff-manifest.json', 'source-export-recipe.md'])
        return files

    def test_canonical_has_exact_inventory_and_honest_partial_without_false_DONE(self):
        result = self.generate()['acceptance']
        self.assertEqual(len(result['rows']), 36)
        self.assertEqual(result['summary']['counts'], {'PASS': 1, 'PARTIAL': 2, 'BLOCKED': 1, 'UNVERIFIED': 32})
        self.assertEqual(result['rows'][1]['ledger_status'], 'TODO')
        self.assertEqual(result['rows'][1]['status'], 'PARTIAL')
        self.assertEqual(result['rows'][4]['status'], 'UNVERIFIED')
        self.assertEqual(result['summary']['overall'], 'PARTIAL')
        self.assertEqual(result['summary']['publication_status'], 'PENDING')
        evidence = result['evidence']['fixture-review']
        self.assertTrue(evidence['source_files']['app.py']['current'])
        self.assertTrue((self.review / evidence['archive_path'].removeprefix('review/')).is_file())

    def test_missing_inventory_and_false_PASS_override_are_rejected(self):
        self.state['tasks']['R01']['acceptance_status'] = 'PASS'; self.write_ledger()
        with self.assertRaisesRegex(ValueError, 'only_ledger_DONE'):self.generate()
        self.state['tasks'].pop('R35'); self.write_ledger()
        with self.assertRaisesRegex(ValueError, 'exact_36'):self.generate()

    def test_stale_DONE_source_proof_cannot_pass_generation(self):
        (self.live / 'app.py').write_text('changed after evidence\n')
        with self.assertRaisesRegex(ValueError, 'stale source'):self.generate()

    def test_published_receipt_updates_summary_and_is_bound_to_current_source(self):
        self.publication.pop('reason')
        self.publication.update(status='PUBLISHED', remote_commit=self.source['commit'], remote_tree=self.source['tree'],
                                repository_url='https://github.com/example/fixture', branch='main', verification_artifact='remote.json')
        (self.review / 'remote.json').write_text('{"scope":"remote verification fixture"}\n')
        self.write_publication()
        result = self.generate()['acceptance']
        self.assertEqual(result['summary']['publication_status'], 'PUBLISHED')
        self.assertEqual(result['summary']['overall'], 'PARTIAL')
        self.publication['remote_tree'] = 'c' * 40; self.write_publication()
        with self.assertRaisesRegex(ValueError, 'exact_remote'):self.generate()

    def test_complete_package_round_trip_and_source_identity(self):
        files = self.package_inputs()
        output = self.base / 'review.zip'
        receipt = package.package(self.base / 'public', self.review, files, output)
        extracted, count = package.verify(output, self.base / 'clean')
        self.assertEqual(receipt['payloads_verified'], count)
        self.assertEqual((extracted / 'source/app.py').read_bytes(), self.source['files']['app.py'])
        self.assertEqual(receipt['sha256'], package.digest(output.read_bytes()))
        (self.review / 'not-selected-personal.txt').write_text('Must stay excluded')
        with zipfile.ZipFile(output) as archive:self.assertFalse(any('personal' in name for name in archive.namelist()))

    def test_late_publication_or_summary_edit_requires_canonical_regeneration(self):
        files = self.package_inputs()
        self.publication['reason'] = 'Changed after canonical generation'; self.write_publication()
        with self.assertRaisesRegex(ValueError, 'publication_or_summary'):package.package(self.base / 'public', self.review, files, self.base / 'late.zip')
        self.generate()
        acceptance = json.loads((self.review / 'acceptance.json').read_text())
        acceptance['summary']['counts']['PASS'] = 36
        (self.review / 'acceptance.json').write_bytes(package.encoded(acceptance))
        with self.assertRaisesRegex(ValueError, 'publication_or_summary'):package.package(self.base / 'public', self.review, files, self.base / 'forged.zip')

    def test_private_unknown_files_are_not_exported_and_explicit_private_add_is_refused(self):
        (self.live / 'private-state').mkdir(); (self.live / 'private-state/secret.txt').write_text('not source')
        exported = package.export_source(self.live, self.base / 'public', {'add': [], 'remove': []}, self.base / 'export')
        self.assertEqual(set(exported['source_files']), {'app.py'})
        with self.assertRaisesRegex(ValueError, 'private_or_runtime'):
            package.export_source(self.live, self.base / 'public', {'add': ['private-state/secret.txt'], 'remove': []}, self.base / 'bad-export')

    def test_mutable_loop_snapshot_is_review_only_even_when_baseline_tracked(self):
        name = canonical.LOOP + 'state.json'
        self.source['files'][name] = b'{"historical":"baseline"}\n'
        self.source['modes'][name] = '100644'
        result = package.export_source(self.live, self.base / 'public', {'add': [], 'remove': []}, self.base / 'export')
        self.assertEqual(result['excluded_mutable_loop_paths'], [name])
        self.assertNotIn(name, result['source_files'])


class CommittedSourceTests(unittest.TestCase):
    def test_source_snapshot_uses_commit_blobs_and_never_worktree_bytes(self):
        commit, tree, object_id = 'a' * 40, 'b' * 40, 'c' * 40
        def read_git(_root, *args):
            if args[0] == 'status':return b''
            if args == ('rev-parse', 'HEAD'):return (commit + '\n').encode()
            if args == ('rev-parse', commit + '^{tree}'):return (tree + '\n').encode()
            if args == ('ls-tree', '-r', '-z', commit):return ('100644 blob ' + object_id + '\tapp.py\0').encode()
            if args == ('cat-file', 'blob', object_id):return b'committed source\n'
            self.fail('Unexpected Git read: ' + str(args))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'app.py').write_text('Unrelated worktree content\n')
            with patch.object(package, 'git', side_effect=read_git):result = package.committed_source(root)
            self.assertEqual(result['files']['app.py'], b'committed source\n')
            with patch.object(package, 'git', return_value=b' M app.py\n'), self.assertRaisesRegex(ValueError, 'clean_committed'):
                package.committed_source(root)


class ArchiveBoundaryTests(unittest.TestCase):
    def archive(self, root, entries, checksums=None):
        target = root / 'fixture.zip'
        checksums = checksums if checksums is not None else ''.join(package.digest(data) + '  ' + name + '\n' for name, data, _mode in sorted(entries))
        with zipfile.ZipFile(target, 'w') as archive:
            for name, data, mode in entries + [('SHA256SUMS.txt', checksums.encode(), stat.S_IFREG | 0o600)]:
                info = zipfile.ZipInfo(package.NAME + '/' + name); info.external_attr = mode << 16
                archive.writestr(info, data)
        return target

    def test_unsafe_names_private_paths_and_symlinks_fail_before_extraction(self):
        for name, mode in (('../escape', stat.S_IFREG), ('a/../../escape', stat.S_IFREG),
                           ('a\\escape', stat.S_IFREG), ('.', stat.S_IFREG),
                           ('private-state/file', stat.S_IFREG), ('source/.ENV', stat.S_IFREG), ('source/link', stat.S_IFLNK)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); target = self.archive(root, [(name, b'fixture', mode)])
                with self.assertRaises(ValueError):package.verify(target, root / 'extract')
                self.assertFalse((root / 'extract').exists())

    def test_checksum_traversal_duplicates_and_tampering_fail_before_extraction(self):
        valid = package.digest(b'fixture') + '  source/file.txt\n'
        for checksums in ('0' * 64 + '  ../../foreign\n', valid + valid, '0' * 64 + '  source/file.txt\n'):
            with self.subTest(checksums=checksums), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); target = self.archive(root, [('source/file.txt', b'fixture', stat.S_IFREG)], checksums)
                with self.assertRaises(ValueError):package.verify(target, root / 'extract')
                self.assertFalse((root / 'extract').exists())

    def test_existing_destination_is_never_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = self.archive(root, [('source/file.txt', b'fixture', stat.S_IFREG)])
            destination = root / 'existing'; destination.mkdir(); sentinel = destination / 'keep'; sentinel.write_text('keep')
            with self.assertRaises(FileExistsError):package.verify(target, destination)
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_duplicate_zip_members_are_refused_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertWarns(UserWarning):
                target = self.archive(root, [('source/file.txt', b'one', stat.S_IFREG), ('source/file.txt', b'two', stat.S_IFREG)])
            with self.assertRaisesRegex(ValueError, 'unique_members'):package.verify(target, root / 'extract')
            self.assertFalse((root / 'extract').exists())

    def test_limits_credentials_raw_events_and_source_symlink_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'credential_pattern'):package.checked('source/example.txt', ('ghp_' + 'A' * 40).encode())
        with self.assertRaisesRegex(ValueError, 'raw_CLI'):package.checked('review/events.jsonl', b'{}\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'target').write_text('fixture'); (root / 'link').symlink_to(root / 'target')
            with self.assertRaisesRegex(ValueError, 'symlink'):package.read_scoped(root, 'link')
            target = self.archive(root, [('source/file.txt', b'fixture', stat.S_IFREG)])
            with patch.object(package, 'MAX_TOTAL', 1), self.assertRaises(ValueError):package.verify(target, root / 'extract')
            self.assertFalse((root / 'extract').exists())


if __name__ == '__main__':unittest.main()
