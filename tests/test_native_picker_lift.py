"""Exact-owned window adaptation and focus drift; fake compositor only."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import owned_native_picker as picker


class ChooserLift(unittest.TestCase):
    def make_driver(self, floating=False, lose_focus_after_key=False, lose_focus_before_key=False):
        server = {'pid': 100, 'uids': [1000] * 4, 'parent': 1, 'start': '111', 'argv': ['/usr/bin/python3', '-I', '/review/server.py']}
        process = {'pid': 200, 'uids': [1000] * 4, 'parent': 100, 'start': '222',
                   'argv': ['/usr/bin/kdialog', '--getexistingdirectory', str(Path.home()), picker.CAPTION]}
        client = {'pid': 200, 'class': 'org.kde.kdialog', 'title': 'KDialog', 'address': '0xabc123',
                  'xwayland': False, 'floating': floating}
        state = {'clients': [], 'active': {}, 'clock': 0, 'dispatches': [], 'active_reads': 0}
        def command(args):
            if args[1:] == ['clients', '-j']:return json.dumps(state['clients'])
            if args[1:] == ['activewindow', '-j']:
                state['active_reads'] += 1
                if lose_focus_before_key and state['active_reads'] > 1:state['active'] = {'pid': 999, 'address': '0x999'}
                return json.dumps(state['active'])
            self.assertEqual(args[:2], ['/usr/bin/hyprctl', 'dispatch'])
            code = args[2]; state['dispatches'].append(code)
            self.assertIn('address:0xabc123', code)
            self.assertNotIn('activewindow', code)
            if 'window.float' in code:
                self.assertIn('action="on"', code)
                self.assertFalse(client['floating']); client['floating'] = True
            elif 'hl.dsp.focus' in code:state['active'] = dict(client)
            elif 'window.close' in code:state['clients'] = []
            elif 'send_shortcut' in code:
                if lose_focus_after_key:state['active'] = {'pid': 999, 'address': '0x999'}
                if 'Escape' in code:state['clients'] = []
            else:raise AssertionError('Unexpected native mutation: ' + code)
            return 'ok\n'
        def read_process(pid):return copy.deepcopy(server if pid == 100 else process)
        def sleep(seconds):state['clock'] += seconds
        with patch.object(picker.os, 'getuid', return_value=1000):
            driver = picker.NativePickerDriver(100, '/review/server.py', command, read_process, lambda:state['clock'], sleep)
        state['clients'] = [client]
        return driver, state, process, client

    def test_tiled_fresh_chooser_is_floated_and_focused_by_exact_address_once(self):
        driver, state, _, _ = self.make_driver()
        result = driver('cancel_picker', '/tmp/owned-source')
        dispatches = state['dispatches']
        self.assertEqual(sum('window.float' in code for code in dispatches), 1)
        self.assertEqual(sum('hl.dsp.focus' in code for code in dispatches), 1)
        self.assertEqual(sum('send_shortcut' in code for code in dispatches), 1)
        self.assertTrue(result['operator_window_lift']['float_applied'])
        self.assertIn('unassisted production dialog parenting remains unverified', result['operator_window_lift']['scope'])
        self.assertEqual(result['targeted_shortcuts'], 1)
        self.assertEqual(state['clients'], [])

    def test_already_floating_chooser_is_never_toggled_back_to_tiling(self):
        driver, state, _, _ = self.make_driver(floating=True)
        result = driver('cancel_picker', '/tmp/owned-source')
        self.assertFalse(any('window.float' in code for code in state['dispatches']))
        self.assertFalse(result['operator_window_lift']['float_applied'])

    def test_focus_drift_after_a_key_aborts_without_refocus_or_more_typing(self):
        driver, state, _, _ = self.make_driver(lose_focus_after_key=True)
        with self.assertRaisesRegex(RuntimeError, 'native_chooser_focus_changed'):
            driver('preview_cancel', '/tmp/owned-source')
        self.assertEqual(sum('hl.dsp.focus' in code for code in state['dispatches']), 1)
        self.assertEqual(sum('send_shortcut' in code for code in state['dispatches']), 1)
        self.assertEqual(sum('window.close' in code for code in state['dispatches']), 1)
        self.assertFalse(any('Return' in code for code in state['dispatches']))
        self.assertEqual(state['active'], {'pid': 999, 'address': '0x999'})
        self.assertEqual(state['clients'], [])

    def test_focus_drift_before_first_key_sends_no_shortcut(self):
        driver, state, _, _ = self.make_driver(lose_focus_before_key=True)
        with self.assertRaisesRegex(RuntimeError, 'native_chooser_focus_changed'):
            driver('preview_cancel', '/tmp/owned-source')
        self.assertFalse(any('send_shortcut' in code for code in state['dispatches']))
        self.assertEqual(sum('hl.dsp.focus' in code for code in state['dispatches']), 1)

    def test_changed_uid_refuses_every_window_or_input_mutation(self):
        driver, state, process, _ = self.make_driver()
        process['uids'] = [0] * 4
        with self.assertRaisesRegex(RuntimeError, 'exact_owned_native_chooser_required'):
            driver('cancel_picker', '/tmp/owned-source')
        self.assertEqual(state['dispatches'], [])

    def test_changed_pid_start_refuses_the_lift_even_if_address_is_reused(self):
        driver, state, process, client = self.make_driver()
        driver.target = picker.chooser_identity(client, process, driver.server, 1000)
        driver.deadline = 25
        process['start'] = 'new process'
        with self.assertRaisesRegex(RuntimeError, 'target_changed'):driver._lift_once()
        self.assertEqual(state['dispatches'], [])


if __name__ == '__main__':unittest.main()
