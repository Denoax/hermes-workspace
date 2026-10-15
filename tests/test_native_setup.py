"""Hermetic cache-copy tests; never invoke native setup or personal cache."""
import os
from pathlib import Path
import tempfile
import unittest
from native.setup import file_record, copy_exact, safe_directory, PACKAGE_FILE


class CachePreservation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        self.target = Path(self.temp.name) / 'target'
        self.source.mkdir()
        self.target.mkdir()
        self.source_fd = os.open(self.source, os.O_DIRECTORY)
        self.target_fd = os.open(self.target, os.O_DIRECTORY)
        self.addCleanup(os.close, self.source_fd)
        self.addCleanup(os.close, self.target_fd)
        self.name = 'owned-fixture-1.0-1-x86_64.pkg.tar.zst'
        (self.source/self.name).write_bytes(b'package-fixture-not-an-installable-archive')

    def test_copy_preserves_source_and_exact_bytes(self):
        record = file_record(self.source_fd, self.name)
        copy_exact(self.source_fd, self.target_fd, record)
        self.assertEqual((self.source/self.name).read_bytes(), (self.target/self.name).read_bytes())
        self.assertTrue((self.source/self.name).exists())

    def test_repeat_verified_copy_is_idempotent(self):
        record = file_record(self.source_fd, self.name)
        copy_exact(self.source_fd, self.target_fd, record)
        inode = (self.target/self.name).stat().st_ino
        copy_exact(self.source_fd, self.target_fd, record)
        self.assertEqual(inode, (self.target/self.name).stat().st_ino)

    def test_stale_plan_and_conflicting_target_fail_without_source_deletion(self):
        record = file_record(self.source_fd, self.name)
        (self.target/self.name).write_bytes(b'preserve-existing-data')
        with self.assertRaises(RuntimeError):
            copy_exact(self.source_fd, self.target_fd, record)
        self.assertEqual((self.target/self.name).read_bytes(), b'preserve-existing-data')
        (self.source/self.name).write_bytes(b'new-version')
        with self.assertRaises(RuntimeError):
            copy_exact(self.source_fd, self.target_fd, record)
        self.assertTrue((self.source/self.name).exists())

    def test_symlinks_and_hardlinks_are_rejected(self):
        signature = self.name+'.sig'
        (self.source/signature).symlink_to(self.source/self.name)
        with self.assertRaises(OSError):
            file_record(self.source_fd, signature)
        os.link(self.source/self.name, self.source/'other')
        with self.assertRaises(ValueError):
            file_record(self.source_fd, self.name)

    def test_unrelated_paths_and_partial_files_are_excluded(self):
        for value in ['../personal.pkg.tar.zst', 'download-partial', 'config.yaml', 'nested/x.pkg.tar.zst']:
            self.assertFalse(PACKAGE_FILE.fullmatch(value))

    def test_user_writable_directory_cannot_be_privileged_state(self):
        with self.assertRaises(PermissionError):
            fd = safe_directory(self.source)
            os.close(fd)


if __name__ == '__main__':
    unittest.main()
