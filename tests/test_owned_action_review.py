"""Harmless ownership/fixture guards and fake native transport; no live GUI."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import owned_action_review as actions
import owned_native_picker as picker
import probe_v5_owned_actions as runner


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.prefix = 'V5review-1234abcd'
        self.project = {'id': 'a' * 32, 'label': self.prefix + ' · Owned project'}
        self.session = {'id': 'b' * 32, 'project': 'a' * 32, 'title': self.prefix + ' · Owned session'}
        self.record = {'status': 'PASS_SCOPED_TECHNICAL', 'prefix': self.prefix, 'projects': [self.project], 'sessions': [self.session]}

    def test_known_owned_navigation_must_still_match_actual_records(self):
        self.assertEqual(actions.owned_navigation(self.record, [self.project], [self.session]), self.prefix)
        changed = {**self.session, 'title': 'A new user title'}
        with self.assertRaisesRegex(RuntimeError, 'changed_preserve'):actions.owned_navigation(self.record, [self.project], [changed])
        changed = {**self.session, 'project': 'c' * 32}
        with self.assertRaisesRegex(RuntimeError, 'moved_preserve'):actions.owned_navigation(self.record, [self.project], [changed])

    def test_suffix_receipt_requires_exact_suffix_and_current_owned_records(self):
        project = {**self.project, 'label': 'Owned project · ' + self.prefix}
        session = {**self.session, 'title': 'Owned session · ' + self.prefix}
        record = {**self.record, 'nonce_location': 'suffix', 'projects': [project], 'sessions': [session]}
        self.assertEqual(actions.owned_navigation(record, [project], [session]), self.prefix)
        with self.assertRaisesRegex(RuntimeError, 'positive_owned'):
            actions.owned_navigation({**record, 'nonce_location': 'prefix'}, [project], [session])
        with self.assertRaisesRegex(RuntimeError, 'changed_preserve'):
            actions.owned_navigation(record, [project], [{**session, 'title': 'Changed · ' + self.prefix}])

    def test_deletion_requires_new_creation_receipt_and_empty_live_state(self):
        nonce = self.prefix + '-actions-5678abcd'
        case = {'nonce': nonce, 'project_id': 'a' * 32, 'delete_session': 'b' * 32, 'created_session_ids': ['b' * 32]}
        row = {**self.session, 'title': nonce + ' · Empty delete case'}
        snapshot = {'messages': [], 'runs': []}; draft = {'text': '', 'mode': 'chat'}
        self.assertEqual(actions.disposable_session(case, [row], snapshot, draft, [], 0), row['id'])
        for changed_case, changed_row, changed_snapshot, changed_draft, jobs, attachments in (
                ({**case, 'created_session_ids': []}, row, snapshot, draft, [], 0),
                (case, {**row, 'title': 'User content'}, snapshot, draft, [], 0),
                (case, row, {'messages': [{'text': 'new user text'}]}, draft, [], 0),
                (case, row, {'runs': [{'state': 'completed'}]}, draft, [], 0),
                (case, row, snapshot, {'text': 'unsent', 'mode': 'chat'}, [], 0),
                (case, row, snapshot, draft, [{'state': 'completed'}], 0),
                (case, row, snapshot, draft, [], 1)):
            with self.subTest(snapshot=changed_snapshot), self.assertRaises(RuntimeError):
                actions.disposable_session(changed_case, [changed_row], changed_snapshot, changed_draft, jobs, attachments)

    def test_delete_video_refuses_to_expose_a_global_unsent_draft_or_attachment(self):
        self.assertTrue(actions.empty_new_draft({}))
        self.assertFalse(actions.empty_new_draft({'hermes:new-draft': 'private text'}))
        self.assertFalse(actions.empty_new_draft({'hermes:draft-attachments:v1:new': json.dumps({'version': 1, 'ids': ['a' * 32]})}))
        self.assertFalse(actions.empty_new_draft({'hermes:draft-attachments:v1:new': 'invalid'}))
        self.assertTrue(actions.empty_new_draft({'hermes:draft-attachments:v1:new': json.dumps({'version': 1, 'ids': []})}))

    def test_exact_empty_draft_representation_can_be_restored_without_overwriting_text(self):
        original = {'hermes:new-draft': None, 'hermes-ui:sounds': 'on', 'attachments': 'unchanged'}
        self.assertEqual(actions.empty_storage_restoration(original, original), {})
        self.assertEqual(actions.empty_storage_restoration(original, {**original, 'hermes:new-draft': ''}),
                         {'hermes:new-draft': {'expected': '', 'value': None}})
        self.assertEqual(actions.empty_storage_restoration({**original, 'hermes:new-draft': ''}, original),
                         {'hermes:new-draft': {'expected': None, 'value': ''}})
        for changed in ({**original, 'hermes:new-draft': 'new user text'},
                        {**original, 'hermes-ui:sounds': 'off'}, {**original, 'attachments': 'new selection'}, {}):
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                actions.empty_storage_restoration(original, changed)
        with self.assertRaises(RuntimeError):
            actions.empty_storage_restoration({**original, 'hermes:new-draft': 'preserve me'}, original)

    def test_selection_uses_new_document_hydration_before_any_further_input(self):
        events = []
        class Browser:
            def reload_ready(self):events.append('hydrated')
            def call(self, *args):raise AssertionError('raw reload bypasses hydration')
        review = actions.OwnedActionReview.__new__(actions.OwnedActionReview)
        review.b = Browser(); review.original_view = {'session_id': None}
        review.case = {'permission_session': 'b' * 32, 'created_session_ids': ['b' * 32], 'project_id': 'a' * 32}
        review.rpc = lambda method, fields:events.append(method)
        review.filter_owned = lambda:events.append('privacy_filter')
        self.assertEqual(review.select('permission_session'), 'b' * 32)
        self.assertEqual(events, ['view.write', 'hydrated', 'privacy_filter'])

    def test_reload_releases_old_native_mapping_before_waiting_for_new_document(self):
        events = []
        class Native:
            def close(self):events.append('closed')
        class Browser:
            _native_input = Native(); _native_coordinates = (1, 1, 0, 0, '0x1')
            _native_diagnostics = {'status': 'PASS'}
            def reload_ready(self):
                self_outer.assertIsNone(self._native_input)
                self_outer.assertIsNone(self._native_coordinates)
                self_outer.assertEqual(self._native_diagnostics, {})
                events.append('hydrated')
        self_outer = self
        review = actions.OwnedActionReview.__new__(actions.OwnedActionReview); review.b = Browser()
        review.reload_ready()
        self.assertEqual(events, ['closed', 'hydrated'])

    def test_an_empty_owned_record_does_not_authorize_deleting_a_different_selected_record(self):
        nonce = self.prefix + '-actions-5678abcd'
        case = {'nonce': nonce, 'project_id': 'a' * 32, 'delete_session': 'b' * 32, 'created_session_ids': ['b' * 32]}
        row = {**self.session, 'title': nonce + ' · Empty delete case'}
        view = {'session_id': 'b' * 32, 'project_id': 'a' * 32}
        self.assertEqual(actions.selected_owned_session(case, 'delete_session', view, [row], row['title']), row['id'])
        with self.assertRaisesRegex(RuntimeError, 'selected_view'):
            actions.selected_owned_session(case, 'delete_session', {**view, 'session_id': 'c' * 32}, [row], row['title'])
        with self.assertRaisesRegex(RuntimeError, 'selected_UI'):
            actions.selected_owned_session(case, 'delete_session', view, [row], 'A different selected conversation')
        with self.assertRaisesRegex(RuntimeError, 'selected_UI'):
            actions.selected_owned_session(case, 'delete_session', view, [row, {**row, 'id': 'c' * 32}], row['title'])

    def test_fixture_receipt_rejects_drift_additions_and_symlinks(self):
        nonce = self.prefix + '-actions-5678abcd'
        with tempfile.TemporaryDirectory() as directory:
            receipt = actions.make_import_fixture(Path(directory), nonce)
            expected = actions.verify_import_fixture(receipt)
            self.assertEqual(set(expected), {'README.md', 'notes/context.txt'})
            root = Path(receipt['root']); original = (root / 'README.md').read_text()
            (root / 'README.md').write_text('changed')
            with self.assertRaisesRegex(RuntimeError, 'bytes_changed'):actions.verify_import_fixture(receipt)
            (root / 'README.md').write_text(original)
            (root / 'extra.txt').write_text('do not copy')
            with self.assertRaisesRegex(RuntimeError, 'inventory_changed'):actions.verify_import_fixture(receipt)
            (root / 'extra.txt').unlink(); (root / 'notes/context.txt').unlink(); (root / 'notes/context.txt').symlink_to(root / 'README.md')
            with self.assertRaisesRegex(RuntimeError, 'bytes_changed'):actions.verify_import_fixture(receipt)

    def test_expected_import_snapshot_matches_real_catalog_contract(self):
        # Only a temporary Catalog/Files instance; no App/server/native imports.
        checkout = Path(os.environ.get('HERMES_TEST_CHECKOUT', str(SCRIPTS.parent)))
        sys.path.insert(0, str(checkout))
        from workspace.catalog import Catalog
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); receipt = actions.make_import_fixture(parent, self.prefix + '-actions-5678abcd')
            texts = actions.verify_import_fixture(receipt)
            catalog = Catalog(parent / 'catalog')
            try:
                project = catalog.create('Harmless fixture project')['id']
                preview = catalog.import_preview(project, receipt['root'])
                catalog.import_commit(project, preview['ticket'])
                self.assertEqual(catalog.snapshot(project)['sha256'], actions.expected_snapshot(texts))
                actions.verify_import_fixture(receipt)
            finally:catalog.db.close()

    def test_read_only_exact_ticket_pair_prevents_copying_another_selected_root(self):
        checkout = Path(os.environ.get('HERMES_TEST_CHECKOUT', str(SCRIPTS.parent)))
        sys.path.insert(0, str(checkout))
        from workspace.catalog import Catalog
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory); receipt = actions.make_import_fixture(parent, self.prefix + '-actions-5678abcd')
            catalog = Catalog(parent / 'catalog')
            try:
                project = catalog.create('Own import target')['id']
                preview = catalog.import_preview(project, receipt['root'])
                with patch.object(actions, 'CATALOG', parent / 'catalog/catalog.sqlite3'):
                    result = actions.verify_import_ticket(project, preview['ticket'], receipt)
                    self.assertTrue(result['read_only_ticket_query'])
                    self.assertNotIn(receipt['root'], str(result))
                    self.assertEqual(result['files'], receipt['files'])
                    with self.assertRaisesRegex(RuntimeError, 'missing_or_expired'):
                        actions.verify_import_ticket('e' * 32, preview['ticket'], receipt)
                    catalog.db.execute('UPDATE imports SET source=? WHERE id=?', ('/some/other/source', preview['ticket'])); catalog.db.commit()
                    with self.assertRaisesRegex(RuntimeError, 'another_source_no_copy'):
                        actions.verify_import_ticket(project, preview['ticket'], receipt)
                files = catalog.files(project)
                try:self.assertEqual(files.tree(), [])
                finally:files.close()
            finally:catalog.db.close()


class NativePickerTests(unittest.TestCase):
    def setUp(self):
        self.server = {'pid': 100, 'uids': [1000] * 4, 'parent': 1, 'start': '111', 'argv': ['/usr/bin/python3', '-I', '/review/server.py']}
        self.process = {'pid': 200, 'uids': [1000] * 4, 'parent': 100, 'start': '222',
                        'argv': ['/usr/bin/kdialog', '--getexistingdirectory', str(Path.home()), picker.CAPTION]}
        self.client = {'pid': 200, 'class': 'org.kde.kdialog', 'title': picker.CAPTION, 'address': '0xabc123', 'xwayland': False, 'floating': True}

    def test_exact_native_dialog_owner_arguments_uid_and_window_are_required(self):
        self.assertEqual(picker.chooser_identity(self.client, self.process, self.server, 1000)['pid'], 200)
        self.assertEqual(picker.chooser_identity({**self.client, 'title': 'KDialog'}, self.process, self.server, 1000)['pid'], 200)
        for key, value in (('parent', 99), ('uids', [0] * 4), ('argv', ['/usr/bin/kdialog', '--yesno', 'unrelated'])):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                picker.chooser_identity(self.client, {**self.process, key: value}, self.server, 1000)
        for key, value in (('address', 'activewindow'), ('title', 'Unrelated chooser'), ('pid', 201)):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                picker.chooser_identity({**self.client, key: value}, self.process, self.server, 1000)

    def test_only_bounded_ASCII_path_keys_are_constructed_without_clipboard(self):
        keys = picker.path_keys('/tmp/V5review_a-1/file.txt')
        self.assertIn(('SHIFT', 'v'), keys); self.assertIn(('SHIFT', 'minus'), keys)
        self.assertIn(('', 'slash'), keys); self.assertIn(('', 'period'), keys)
        for path in ('relative', '/tmp/../private', '/tmp/a;exec', '/tmp/a$(x)', '/tmp/name with spaces'):
            with self.subTest(path=path), self.assertRaises(ValueError):picker.path_keys(path)

    def fake_driver(self, change_target=False):
        current = {'clients': [], 'clock': 0, 'reads': 0}; sent = []
        def command(args):
            if args[1:] == ['clients', '-j']:
                current['reads'] += 1
                if change_target and current['reads'] > 2 and current['clients']:
                    return json.dumps([{**self.client, 'address': '0xdef456'}])
                return json.dumps(current['clients'])
            if args[1:] == ['activewindow', '-j']:return json.dumps(self.client)
            self.assertEqual(args[:2], ['/usr/bin/hyprctl', 'dispatch'])
            if 'send_shortcut' in args[2]:
                sent.append(args[2]); current['clients'] = []
            elif 'window.close' in args[2]:current['clients'] = []
            else:self.assertIn('hl.dsp.focus(', args[2])
            return 'ok\n'
        def process(pid):return copy.deepcopy(self.server if pid == 100 else self.process)
        def sleep(seconds):current['clock'] += seconds
        with patch.object(picker.os, 'getuid', return_value=1000):
            driver = picker.NativePickerDriver(100, '/review/server.py', command, process, lambda: current['clock'], sleep)
        current['clients'] = [self.client]
        return driver, sent

    def test_cancel_targets_only_the_verified_address_and_reports_protocol_scope(self):
        driver, sent = self.fake_driver()
        result = driver('cancel_picker', '/tmp/owned-source')
        self.assertTrue(result['actual_native_chooser'])
        self.assertEqual(len(sent), 1)
        self.assertIn('address:0xabc123', sent[0]); self.assertIn('Escape', sent[0])
        self.assertNotIn('activewindow', sent[0]); self.assertNotIn('exec', sent[0])

    def test_window_identity_change_before_first_key_delivers_no_input(self):
        driver, sent = self.fake_driver(change_target=True)
        with self.assertRaisesRegex(RuntimeError, 'target_changed'):driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(sent, [])


class RunnerBoundaries(unittest.TestCase):
    def test_cleanup_attempts_restoration_and_release_after_recording_failure(self):
        seen = []
        def broken():
            seen.append('recording'); raise RuntimeError('capture failed')
        result = runner.cleanup_steps([('recording', broken), ('restore', lambda:seen.append('restore')),
                                       ('browser', lambda:seen.append('browser'))])
        self.assertEqual(seen, ['recording', 'restore', 'browser'])
        self.assertEqual(result['recording'], {'status': 'failed', 'error_category': 'RuntimeError'})
        self.assertEqual(result['restore']['status'], 'ok')

    def test_segments_finish_independently_and_reaching_native_cap_is_a_failure(self):
        now = [0.0]; finished = []; saved = []; receipts = []
        class Recording:
            def __init__(self, browser, output):self.name = output.name
            def hold(self, seconds):now[0] += seconds
            def finish(self):
                finished.append(self.name); return {'seconds': 1, 'frames': 60}
        clips = runner.RotatingRecordings(None, Path('/unused'), receipts, lambda:saved.append(True), Recording, lambda:now[0])
        clips.segment('first'); clips.hold(.5); clips.segment('second')
        self.assertEqual(len(finished), 1)
        now[0] += 30
        with self.assertRaisesRegex(RuntimeError, 'acquisition_cap'):clips.finish()
        self.assertEqual(len(finished), 2)
        self.assertEqual([r['status'] for r in receipts], ['PASS_SCOPED_TECHNICAL', 'FAIL'])
        self.assertEqual(len(saved), 2)
        clips.finish(); self.assertEqual(len(finished), 2)

    def test_a_hold_cannot_silently_outlive_a_bounded_native_recording(self):
        now = [0.0]
        class Recording:
            def __init__(self, *args):pass
            def hold(self, seconds):raise AssertionError('must fail before sleeping')
        clips = runner.RotatingRecordings(None, Path('/unused'), [], lambda:None, Recording, lambda:now[0])
        clips.segment('bounded'); now[0] = 28.5
        with self.assertRaisesRegex(RuntimeError, 'acquisition_cap'):clips.hold(.6)

    def test_frozen_source_snapshot_records_adverse_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'SOURCES', ('one.py',)):
            root = Path(directory); (root / 'one.py').write_text('before')
            before = runner.source_snapshot(root)
            (root / 'one.py').write_text('after')
            self.assertNotEqual(before, runner.source_snapshot(root))

    def test_expected_denial_reasons_match_authoritative_dispatcher(self):
        checkout = Path(os.environ.get('HERMES_TEST_CHECKOUT', str(SCRIPTS.parent)))
        sys.path.insert(0, str(checkout))
        from workspace.actions import Actions
        from workspace.catalog import Catalog
        from workspace.permissions import Permissions
        from workspace.server import Application
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(Path(directory) / 'catalog')
            try:
                app = Application.__new__(Application); app.catalog = catalog
                app.permissions = Permissions(catalog); app.actions = Actions(catalog, app.permissions)
                project = catalog.create('Harmless dispatcher fixture')['id']
                session = catalog.session(project, 'normal')['id']; other = catalog.session(project, 'normal')['id']
                action = app.call('permissions.request', {'session_id': session, 'run_id': None, 'request_id': 'd' * 32,
                                  'action': {'type': 'workspace.write', 'path': 'blocked.txt', 'text': 'do not write', 'expected_sha256': None}})
                for method, fields, kind, reason in (
                    ('actions.execute', {'session_id': session, 'action_id': action['id']}, PermissionError, 'action_not_approved_denied'),
                    ('actions.execute', {'session_id': other, 'action_id': action['id']}, ValueError, 'unknown_owned_action'),
                    ('recording.authorize', {'session_id': session}, PermissionError, 'permission_required_microphone'),
                    ('workspace.file.write', {'project_id': project, 'relative_path': 'bypass.txt', 'text': 'no', 'expected_sha256': None}, PermissionError, 'scoped_action_required')):
                    with self.subTest(method=method), self.assertRaisesRegex(kind, '^' + reason + '$'):
                        app.call(method, fields)
                files = catalog.files(project)
                try:self.assertEqual(files.tree(), [])
                finally:files.close()
            finally:catalog.db.close()


if __name__ == '__main__':unittest.main()
