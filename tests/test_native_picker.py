"""Hermetic parenting/deadline/protocol contracts; never open a native dialog."""
import json
import os
from pathlib import Path
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

from workspace import native_picker as picker
from workspace import desktop

PROPOSAL = Path(__file__).resolve().parents[1]

class NativePickerTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(picker.os, 'getuid', return_value=1000),
                        patch.object(picker.os, 'geteuid', return_value=1000),
                        patch.object(picker.time, 'monotonic', return_value=100),
                        patch.object(picker, 'resolve_parent', return_value=(0x12345, ':0')),
                        patch.object(picker.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '/tmp/owned source \n', ''))]
        self.uid, self.euid, self.clock, self.parent, self.run = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def test_verified_real_xid_is_attached_with_correct_title_and_child_only_xcb(self):
        before = dict(os.environ)
        result = picker.choose_directory(220)
        self.assertEqual(result, {'status': 'selected', 'path': '/tmp/owned source '})
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], ['/usr/bin/kdialog', '--title', picker.CAPTION, '--attach', str(0x12345), '--getexistingdirectory', str(Path.home())])
        self.assertEqual(kwargs['env']['QT_QPA_PLATFORM'], 'xcb')
        self.assertEqual(kwargs['env']['DISPLAY'], ':0')
        self.assertEqual(kwargs['timeout'], 120)
        self.assertEqual(dict(os.environ), before)

    def test_missing_or_ambiguous_owned_parent_never_opens_unparented_dialog(self):
        self.parent.side_effect = RuntimeError('native_recording_owned_X11_window_not_unique')
        self.assertEqual(picker.choose_directory(220), {'status': 'error', 'code': 'parent_unavailable'})
        self.run.assert_not_called()

    def test_invalid_parent_identity_never_reaches_native_command(self):
        for parent in [(0, ':0'), (True, ':0'), ('0x12345', ':0'), (2**32, ':0'), (12, 'remote:0'), (12, None)]:
            with self.subTest(parent=parent):
                self.parent.return_value = parent
                self.assertEqual(picker.choose_directory(220)['code'], 'parent_unavailable')
        self.run.assert_not_called()

    def test_wrong_user_never_resolves_or_opens_gui(self):
        self.uid.return_value = 0
        self.assertEqual(picker.choose_directory(220), {'status': 'error', 'code': 'operator_required'})
        self.parent.assert_not_called()
        self.run.assert_not_called()

    def test_expired_or_unbounded_deadline_never_opens_gui(self):
        for deadline in [100, 99, 221, float('inf'), float('nan')]:
            with self.subTest(deadline=deadline):
                self.assertEqual(picker.choose_directory(deadline)['code'], 'deadline_exceeded')
        self.run.assert_not_called()

    def test_parent_resolution_consumes_the_same_budget(self):
        self.clock.side_effect = [100, 105]
        picker.choose_directory(220)
        self.assertEqual(self.run.call_args.kwargs['timeout'], 115)

    def test_resolution_exhaustion_does_not_launch_gui_after_deadline(self):
        self.clock.side_effect = [100, 220]
        self.assertEqual(picker.choose_directory(220)['code'], 'deadline_exceeded')
        self.run.assert_not_called()

    def test_only_native_cancel_exit_is_reported_cancelled(self):
        self.run.return_value.returncode = 1
        self.assertEqual(picker.choose_directory(220), {'status': 'cancelled'})
        for code in [2, 254, -9]:
            with self.subTest(code=code):
                self.run.return_value.returncode = code
                self.assertEqual(picker.choose_directory(220), {'status': 'error', 'code': 'dialog_failed'})

    def test_timeout_and_launch_failure_are_errors_not_cancellation(self):
        self.run.side_effect = subprocess.TimeoutExpired('kdialog', 120)
        self.assertEqual(picker.choose_directory(220)['code'], 'deadline_exceeded')
        self.run.side_effect = OSError('private display details')
        self.assertEqual(picker.choose_directory(220), {'status': 'error', 'code': 'dialog_failed'})

    def test_invalid_selection_is_rejected_before_existing_preview_boundary(self):
        for selected in ['', 'relative/path\n', '/tmp/a\0b\n', '/' + 'x' * 4096]:
            with self.subTest(selected=selected[:30]):
                self.run.return_value.stdout = selected
                self.assertEqual(picker.choose_directory(220)['code'], 'invalid_selection')


class NativePickerProtocolTests(unittest.TestCase):
    def test_selected_path_and_cancel_use_exact_shapes(self):
        for expected in [{'status': 'selected', 'path': '/tmp/ spaces '}, {'status': 'cancelled'}]:
            self.assertEqual(desktop._picker_reply(json.dumps(expected)), expected)

    def test_foreign_error_details_and_ambiguous_shapes_are_rejected(self):
        invalid = [[], {}, {'status': 'cancelled', 'path': '/tmp/hidden'},
                   {'status': 'selected', 'path': 'relative'}, {'status': 'selected', 'path': '/tmp/a\0b'},
                   {'status': 'selected', 'path': '/' + 'x' * 4096},
                   {'status': 'error', 'code': 'unknown_private_cause'},
                   {'status': 'error', 'code': ['parent_unavailable']},
                   {'status': 'error', 'code': 'parent_unavailable', 'stderr': 'private data'}]
        for item in invalid:
            with self.subTest(item=str(item)[:60]):
                with self.assertRaisesRegex(RuntimeError, 'native_picker_invalid_reply'):
                    desktop._picker_reply(json.dumps(item))
        for raw in ['not JSON', ' ' * 16385, '{"status":"selected","path":"/\\ud800"}']:
            with self.assertRaisesRegex(RuntimeError, 'native_picker_invalid_reply'):
                desktop._picker_reply(raw)

    def test_known_error_exposes_only_static_actionable_message(self):
        with self.assertRaisesRegex(RuntimeError, 'verified Hermes app window is unavailable'):
            desktop._picker_reply('{"status":"error","code":"parent_unavailable"}')


class NativePickerChildTests(unittest.TestCase):
    def setUp(self):
        self.process = Mock(pid=1234, returncode=0)
        self.process.communicate.return_value = ('{"status":"selected","path":"/tmp/owned"}', '')
        self.patches = [patch.object(desktop, 'desktop_environment', return_value={'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'wayland-1'}),
                        patch.object(desktop.time, 'monotonic', return_value=100),
                        patch.object(desktop.subprocess, 'Popen', return_value=self.process),
                        patch.object(desktop.os, 'killpg')]
        self.environment, self.clock, self.popen, self.kill = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def test_fixed_unprivileged_helper_uses_environment_and_exclusive_process_group(self):
        self.assertEqual(desktop.choose_import_directory(), {'status': 'selected', 'path': '/tmp/owned'})
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], ['/usr/bin/python3', '-I', str(PROPOSAL / 'workspace/native_picker.py'), '219'])
        self.assertEqual(kwargs['env'], self.environment.return_value)
        self.assertTrue(kwargs['start_new_session'])
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(self.process.communicate.call_args.kwargs['timeout'], 119.5)
        self.kill.assert_not_called()

    def test_environment_refresh_consumes_original_deadline_not_a_new_budget(self):
        self.clock.side_effect = [100, 103, 103]
        desktop.choose_import_directory()
        self.assertEqual(self.popen.call_args.args[0][-1], '219')
        self.assertEqual(self.process.communicate.call_args.kwargs['timeout'], 116.5)

    def test_busy_chooser_does_not_spawn_or_refresh_desktop_state(self):
        desktop._picker_lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'already open'):
                desktop.choose_import_directory()
        finally:
            desktop._picker_lock.release()
        self.environment.assert_not_called()
        self.popen.assert_not_called()

    def test_timeout_kills_only_owned_process_group_and_is_never_cancel(self):
        self.process.communicate.side_effect = [subprocess.TimeoutExpired('helper', 119.5), ('', '')]
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            desktop.choose_import_directory()
        self.kill.assert_called_once_with(self.process.pid, signal.SIGKILL)
        self.assertFalse(desktop._picker_lock.locked())

    def test_child_crash_is_not_cancel_and_lock_is_released(self):
        self.process.returncode = -9
        with self.assertRaisesRegex(RuntimeError, 'chooser failed'):
            desktop.choose_import_directory()
        self.assertFalse(desktop._picker_lock.locked())

    def test_launch_error_and_invalid_protocol_do_not_leak_details_or_lock(self):
        self.popen.side_effect = OSError('private environment details')
        with self.assertRaisesRegex(RuntimeError, 'chooser failed'):
            desktop.choose_import_directory()
        self.assertFalse(desktop._picker_lock.locked())
        self.popen.side_effect = None
        self.process.communicate.return_value = ('secret private output', '')
        with self.assertRaisesRegex(RuntimeError, 'native_picker_invalid_reply'):
            desktop.choose_import_directory()
        self.assertFalse(desktop._picker_lock.locked())


class ExistingEnvironmentBoundaryTests(unittest.TestCase):
    def test_session_refresh_keeps_existing_display_whitelist_and_does_not_adopt_auth(self):
        output = 'DISPLAY=:0\nWAYLAND_DISPLAY=wayland-1\nXAUTHORITY=/private/auth\nTOKEN=secret\n'
        with patch.dict(desktop.os.environ, {'HOME': '/home/mani'}, clear=True), patch.object(desktop.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
            result = desktop.desktop_environment()
        self.assertEqual(result['DISPLAY'], ':0')
        self.assertNotIn('XAUTHORITY', result)
        self.assertNotIn('TOKEN', result)


if __name__ == '__main__':
    unittest.main()
