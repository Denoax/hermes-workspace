"""Fixture-only identity/focus regressions; no native GUI or selection occurs."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'scripts'))
import unassisted_native_picker as picker


class UnassistedChooser(unittest.TestCase):
    def fixture(self, *, preexisting=False, floating=True, active=True, transient=500,
                xwayland=True, lose_focus_after_key=False, lose_focus_before_key=False,
                exit_on_return=True):
        server = {'pid': 100, 'uids': [1000] * 4, 'parent': 1, 'start': '111',
                  'argv': ['/usr/bin/python3', '-I', '/review/server.py']}
        helper = {'pid': 150, 'uids': [1000] * 4, 'parent': 100, 'start': '151',
                  'argv': ['/usr/bin/python3', '-I', '/review/native_picker.py', '119.0']}
        process = {'pid': 200, 'uids': [1000] * 4, 'parent': 150, 'start': '222',
                   'argv': ['/usr/bin/kdialog', '--title', picker.CAPTION, '--attach', '500', '--getexistingdirectory', str(Path.home())]}
        client = {'pid': 200, 'class': 'org.kde.kdialog', 'title': picker.CAPTION,
                  'address': '0xabc123', 'xwayland': xwayland, 'floating': floating,
                  'mapped': True, 'hidden': False}
        native = {'xid': 600, 'xres_pid': 200, 'viewable': True,
                  'transient_for': transient, 'method': 'bounded_XQueryTree_depth2_count4096'}
        state = {'clients': [client] if preexisting else [], 'active': dict(client) if active else {'pid': 999, 'address': '0x999'},
                 'clock': 0, 'dispatches': [], 'active_reads': 0, 'parent': (500, ':0')}
        processes = {100: server, 150: helper, 200: process}
        def command(args):
            if args[1:] == ['clients', '-j']: return json.dumps(state['clients'])
            if args[1:] == ['activewindow', '-j']:
                state['active_reads'] += 1
                if lose_focus_before_key and state['active_reads'] > 1:
                    state['active'] = {'pid': 999, 'address': '0x999'}
                return json.dumps(state['active'])
            self.assertEqual(args[:2], ['/usr/bin/hyprctl', 'dispatch'])
            code = args[2]; state['dispatches'].append(code)
            self.assertNotIn('window.float', code)
            self.assertNotIn('hl.dsp.focus', code)
            self.assertNotIn('activewindow', code)
            self.assertIn('address:0xabc123', code)
            if 'window.close' in code:
                state['clients'] = []
            elif 'send_shortcut' in code:
                if lose_focus_after_key:
                    state['active'] = {'pid': 999, 'address': '0x999'}
                if 'Escape' in code or (exit_on_return and 'Return' in code):
                    state['clients'] = []
            else:
                raise AssertionError('Unauthorized compositor mutation: ' + code)
            return 'ok\n'
        def read(pid):
            return copy.deepcopy(processes[pid])
        def sleep(seconds):
            state['clock'] += seconds
        with patch.object(picker.os, 'getuid', return_value=1000):
            driver = picker.NativePickerDriver(100, '/review/server.py', command, read,
                lambda: state['clock'], sleep, lambda: state['parent'], lambda pid, display, parent: copy.deepcopy(native))
        state['clients'] = [client]
        return driver, state, server, helper, process, client, native

    def test_completion_popup_cannot_ambiguate_the_exact_Hermes_parent(self):
        main = {'xid': 600, 'transient_for': 500}
        popup = {'xid': 601, 'transient_for': 602}
        self.assertEqual(picker.select_parented_window([popup, main], 500), main)
        self.assertEqual(picker.select_parented_window([main], 500), main)

    def test_completion_compositor_client_is_not_mistaken_for_the_primary(self):
        driver, state, _, _, _, main, _ = self.fixture()
        popup = {**main, 'address': '0xabc456', 'title': ''}
        state['clients'].append(popup)
        result = driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(result['target']['address'], main['address'])
        self.assertEqual(len(state['dispatches']), 1)
        self.assertIn('address:0xabc123', state['dispatches'][0])
        self.assertNotIn('address:0xabc456', state['dispatches'][0])

    def test_same_process_completion_focus_requires_XRes_widget_ancestry(self):
        driver, state, _, _, _, main, _ = self.fixture()
        driver.target=driver._candidates()[0]
        state['active']={**main,'address':'0xabc456','title':''}
        proof={'within_owned_chooser':True,'input_focus_xid':601}
        from unittest.mock import Mock
        driver.focus_reader=Mock(return_value=proof)
        driver._already_parented_and_ready()
        driver.focus_reader.assert_called_once_with(200,':0',600)
        self.assertEqual(driver.completion_focus,{601:proof})
        self.assertEqual(state['dispatches'],[])

    def test_same_process_but_unattested_completion_focus_stops_input(self):
        driver, state, _, _, _, main, _ = self.fixture()
        state['active']={**main,'address':'0xabc456','title':''}
        driver.focus_reader=lambda *_:{'within_owned_chooser':False}
        with self.assertRaisesRegex(RuntimeError,'outside_attested_widget_family'):
            driver('preview_cancel','/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in v for v in state['dispatches']))

    def test_duplicate_primary_or_missing_parent_is_refused(self):
        for rows in [[], [{'xid': 601, 'transient_for': 602}],
                     [{'xid': 600, 'transient_for': 500}, {'xid': 601, 'transient_for': 500}]]:
            with self.subTest(rows=rows), self.assertRaises(picker.ChooserWindowObservationError):
                picker.select_parented_window(rows, 500)
        for parent in [None, 0, True]:
            with self.subTest(parent=parent), self.assertRaisesRegex(RuntimeError, 'verified_Hermes_X11_parent_required'):
                picker.select_parented_window([], parent)

    def test_correct_parent_focus_and_float_are_observed_without_window_adaptation(self):
        driver, state, *_ = self.fixture()
        result = driver('cancel_picker', '/tmp/owned-source')
        self.assertTrue(result['unassisted_parenting']['verified_transient_parent'])
        self.assertFalse(result['unassisted_parenting']['float_applied'])
        self.assertFalse(result['unassisted_parenting']['focus_applied'])
        self.assertEqual(result['target']['xid'], 600)
        self.assertEqual(result['target']['transient_for'], 500)
        self.assertEqual(len(state['dispatches']), 1)
        self.assertIn('send_shortcut', state['dispatches'][0])
        self.assertIn('Escape', state['dispatches'][0])

    def test_commit_uses_actual_targeted_path_keys_and_return_not_an_import_API(self):
        driver, state, *_ = self.fixture()
        result = driver('commit', '/tmp/Owned_source')
        self.assertEqual(result['phase'], 'commit')
        self.assertEqual(result['targeted_shortcuts'], 2 + len(picker.path_keys('/tmp/Owned_source')) + 1)
        self.assertTrue(all('send_shortcut' in code for code in state['dispatches']))
        self.assertFalse(any('window.close' in code for code in state['dispatches']))

    def test_lost_viewable_window_stops_keys_and_retains_owned_observation(self):
        driver, state, *_ = self.fixture()
        original_reader = driver.x11_reader
        def read(pid, display, parent):
            if state['dispatches']:
                raise picker.ChooserWindowObservationError([])
            return original_reader(pid, display, parent)
        driver.x11_reader = read
        with self.assertRaisesRegex(RuntimeError, 'native_chooser_X11_window_not_unique'):
            driver('preview_cancel', '/tmp/owned-source')
        self.assertEqual(len(state['dispatches']), 1)
        self.assertEqual(driver.last_failure['last_acknowledged_key'], {'mods': 'CTRL', 'key': 'l'})
        self.assertEqual(driver.last_failure['x11_observation']['matching_viewable_owned_windows'], 0)
        self.assertEqual(driver.last_failure['cleanup']['status'], 'refused_or_failed')

    def test_tiled_chooser_fails_before_typing_and_only_exact_owned_cleanup_is_allowed(self):
        driver, state, *_ = self.fixture(floating=False)
        with self.assertRaisesRegex(RuntimeError, 'not_already_XWayland_and_floating'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(sum('send_shortcut' in code for code in state['dispatches']), 0)
        self.assertEqual(sum('window.close' in code for code in state['dispatches']), 1)

    def test_native_wayland_chooser_is_not_silently_accepted_as_parented_xcb(self):
        driver, state, *_ = self.fixture(xwayland=False)
        with self.assertRaisesRegex(RuntimeError, 'not_already_XWayland_and_floating'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))

    def test_wrong_transient_parent_refuses_input(self):
        driver, state, *_ = self.fixture(transient=999)
        with self.assertRaisesRegex(RuntimeError, 'transient_parent_incorrect'):
            driver('commit', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))

    def test_missing_transient_parent_refuses_input(self):
        driver, state, *_ = self.fixture(transient=None)
        with self.assertRaisesRegex(RuntimeError, 'transient_parent_incorrect'):
            driver('commit', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))

    def test_unfocused_chooser_is_not_refocused_by_the_driver(self):
        driver, state, *_ = self.fixture(active=False)
        with self.assertRaisesRegex(RuntimeError, 'focus_changed'):
            driver('preview_cancel', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))
        self.assertEqual(state['active'], {'pid': 999, 'address': '0x999'})

    def test_focus_drift_before_first_shortcut_sends_no_input(self):
        driver, state, *_ = self.fixture(lose_focus_before_key=True)
        with self.assertRaisesRegex(RuntimeError, 'focus_changed'):
            driver('preview_cancel', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))

    def test_focus_drift_after_one_key_stops_before_more_typing(self):
        driver, state, *_ = self.fixture(lose_focus_after_key=True)
        with self.assertRaisesRegex(RuntimeError, 'focus_changed'):
            driver('preview_cancel', '/tmp/owned-source')
        self.assertEqual(sum('send_shortcut' in code for code in state['dispatches']), 1)
        self.assertFalse(any('Return' in code for code in state['dispatches']))

    def test_every_helper_chain_and_argv_change_refuses_all_mutation(self):
        mutations = [
            lambda helper, proc: helper.update(parent=999),
            lambda helper, proc: helper.update(uids=[0] * 4),
            lambda helper, proc: helper.update(argv=['/usr/bin/python3', '-I', '/other/helper.py', '119']),
            lambda helper, proc: helper.update(argv=['/usr/bin/python3', '-I', '/review/native_picker.py', 'nan']),
            lambda helper, proc: proc.update(parent=100),
            lambda helper, proc: proc.update(uids=[0] * 4),
            lambda helper, proc: proc.update(argv=['/usr/bin/kdialog', '--getexistingdirectory', str(Path.home())]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                driver, state, _, helper, proc, *_ = self.fixture()
                mutate(helper, proc)
                with self.assertRaises((RuntimeError, TimeoutError)):
                    driver('cancel_picker', '/tmp/owned-source')
                self.assertEqual(state['dispatches'], [])

    def test_server_restart_and_parent_replacement_refuse_all_mutation(self):
        driver, state, server, *_ = self.fixture()
        server['start'] = 'new-server'
        with self.assertRaisesRegex(RuntimeError, 'server_identity_changed'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(state['dispatches'], [])
        driver, state, *_ = self.fixture()
        state['parent'] = (501, ':0')
        with self.assertRaisesRegex(RuntimeError, 'parent_identity_changed'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(state['dispatches'], [])

    def test_changed_process_start_or_xid_refuses_cleanup_instead_of_touching_reused_identity(self):
        for changed in ['process', 'helper', 'xid']:
            with self.subTest(changed=changed):
                driver, state, _, helper, process, _, native = self.fixture()
                driver.target = driver._candidates()[0]
                if changed == 'process': process['start'] = 'new-process'
                elif changed == 'helper': helper['start'] = 'new-helper'
                else: native['xid'] = 601
                driver._cleanup()
                self.assertEqual(state['dispatches'], [])

    def test_xres_pid_mismatch_or_hidden_window_never_receives_shortcuts(self):
        driver, state, _, _, _, client, native = self.fixture()
        native['xres_pid'] = 999
        with self.assertRaisesRegex(RuntimeError, 'exact_owned_parented_chooser'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(state['dispatches'], [])
        driver, state, _, _, _, client, _ = self.fixture()
        client['hidden'] = True
        with self.assertRaisesRegex(RuntimeError, 'not_already_visible'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))

    def test_duplicate_owned_chooser_refuses_all_input(self):
        driver, state, _, _, _, client, _ = self.fixture()
        state['clients'] = [client, {**client, 'address': '0xabc124'}]
        with self.assertRaisesRegex(RuntimeError, 'unique_owned_native_chooser'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(state['dispatches'], [])

    def test_deadline_stops_retry_and_closes_only_the_exact_chooser(self):
        driver, state, *_ = self.fixture(exit_on_return=False)
        with self.assertRaisesRegex(TimeoutError, 'did_not_finish'):
            driver('commit', '/tmp/owned-source')
        self.assertLessEqual(state['clock'], 25.2)
        self.assertEqual(sum('window.close' in code for code in state['dispatches']), 1)

    def test_preexisting_owned_chooser_is_preserved(self):
        with self.assertRaisesRegex(RuntimeError, 'preserve_preexisting'):
            self.fixture(preexisting=True)

    def test_same_process_identity_is_not_reused_for_a_second_phase(self):
        driver, state, _, _, _, client, _ = self.fixture()
        driver('cancel_picker', '/tmp/owned-source')
        state['clients'] = [client]
        before = len(state['dispatches'])
        with self.assertRaisesRegex(RuntimeError, 'fresh_native_chooser'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(len(state['dispatches']), before)

    def test_invalid_phase_or_fixture_path_never_dispatches(self):
        driver, state, *_ = self.fixture()
        for phase, path in [('unknown', '/tmp/owned-source'), ('commit', '/tmp/../secret'), ('commit', '/tmp/non ASCII name')]:
            with self.assertRaises(ValueError):
                driver(phase, path)
        self.assertEqual(state['dispatches'], [])

    def test_invalid_x11_metadata_request_is_rejected_before_native_access(self):
        for pid, display in [(0, ':0'), (True, ':0'), (200, 'remote:0')]:
            with self.assertRaisesRegex(RuntimeError, 'local_X11_chooser_metadata'):
                picker.owned_chooser_x11(pid, display, 500)


if __name__ == '__main__':
    unittest.main()
