"""Isolated normal-user filesystem and deterministic window-bound contracts."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from workspace.launcher import prepare_control_directory


@unittest.skipUnless(os.getuid() == 1000, 'operator UID1000 filesystem contract')
class UserControlDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hermes-control-contract-')
        self.root = Path(self.temporary.name)
        self.parent = self.root / 'systemd'
        self.parent.mkdir(mode=0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_control_is_created_private_and_repeated_calls_preserve_inode(self):
        prepare_control_directory(self.parent)
        child = self.parent / 'user.control'
        before = child.stat()
        self.assertEqual(before.st_mode & 0o777, 0o700)
        self.assertEqual(before.st_uid, 1000)
        prepare_control_directory(self.parent)
        self.assertEqual(child.stat().st_ino, before.st_ino)

    def test_symlink_parent_is_not_followed(self):
        link = self.root / 'link'
        link.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(OSError):
            prepare_control_directory(link)
        self.assertFalse((self.parent / 'user.control').exists())

    def test_symlink_child_is_not_followed(self):
        destination = self.root / 'outside'
        destination.mkdir()
        (self.parent / 'user.control').symlink_to(destination, target_is_directory=True)
        with self.assertRaises(OSError):
            prepare_control_directory(self.parent)
        self.assertEqual(list(destination.iterdir()), [])

    def test_writable_parent_or_child_is_rejected_without_permission_repair(self):
        self.parent.chmod(0o770)
        with self.assertRaisesRegex(RuntimeError, 'untrusted_user_control_parent'):
            prepare_control_directory(self.parent)
        self.parent.chmod(0o700)
        child = self.parent / 'user.control'
        child.mkdir(mode=0o700)
        child.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, 'untrusted_user_control_directory'):
            prepare_control_directory(self.parent)
        self.assertEqual(child.stat().st_mode & 0o777, 0o777)

    def test_wrong_operator_uid_is_rejected_before_filesystem_access(self):
        with patch('workspace.launcher.os.getuid', return_value=1001):
            with self.assertRaisesRegex(RuntimeError, 'fixed_normal_user'):
                prepare_control_directory(self.root / 'absent')
        self.assertFalse((self.root / 'absent').exists())


class WindowGeometryTests(unittest.TestCase):
    def test_monitor_offset_scale_reserved_edges_and_rotation_are_logical(self):
        from workspace.launcher import monitor_work_area
        monitor = {'x':1920,'y':0,'width':3840,'height':2160,'scale':2,'reserved':[10,20,30,40]}
        self.assertEqual(monitor_work_area(monitor), (1930,20,1880,1020))
        monitor.update(transform=1,reserved=[0,0,0,0])
        self.assertEqual(monitor_work_area(monitor), (1920,0,1080,1920))

    def test_preferred_window_fits_a_small_scaled_display(self):
        from workspace.launcher import requested_window_size
        monitor = {'x':0,'y':0,'width':1920,'height':1080,'scale':2}
        self.assertEqual(requested_window_size(monitor), (928,508))

    def test_native_clipped_rail_position_is_rejected_and_centered_surface_fits(self):
        from workspace.launcher import surface_inside_monitor
        monitor = {'x':0,'y':0,'width':1920,'height':1080,'scale':1}
        self.assertFalse(surface_inside_monitor({'at':[-268,-57],'size':[1320,900]},monitor))
        self.assertTrue(surface_inside_monitor({'at':[300,90],'size':[1320,900]},monitor))
        monitor['x'] = -1920
        self.assertTrue(surface_inside_monitor({'at':[-1620,90],'size':[1320,900]},monitor))

    def test_invalid_monitor_geometry_is_not_used_for_window_placement(self):
        from workspace.launcher import monitor_work_area
        for changes in ({'scale':0},{'width':float('nan')},{'reserved':[0,9999,0,0]}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    monitor_work_area({'x':0,'y':0,'width':1920,'height':1080,'scale':1,**changes})
