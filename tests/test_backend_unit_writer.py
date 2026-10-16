"""Temporary-filesystem unit writer regressions; all service/model I/O stubbed."""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'native/backend.py'
if os.environ.get('BACKEND_WRITER_REGRESSION_SOURCE'):
    SOURCE = Path(os.environ['BACKEND_WRITER_REGRESSION_SOURCE'])
spec = importlib.util.spec_from_file_location('backend_writer_subject', SOURCE)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class BackendUnitWriter(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / backend.UNIT

    def start_with_only_temporary_file_io(self, arm):
        """Exercise the actual start write, including the unmodified old source."""
        def local_path(value):
            return self.directory if value == '/run/systemd/system' else Path(value)
        props = {'model_alias':backend.ALIAS, 'default_generation_settings':{'n_ctx':8192}, 'build_info':'fixture'}
        with patch.dict(sys.modules, {'window':SimpleNamespace(active=lambda:True)}), \
                patch.object(backend, 'Path', side_effect=local_path), \
                patch.object(backend, 'stop'), patch.object(backend, 'artifacts_current', return_value=True), \
                patch.object(backend.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                patch.object(backend, 'get', side_effect=lambda path: {'status':'ok'} if path == '/health' else props):
            return backend.start(arm)

    def test_fresh_start_under_private_umask_writes_exact_unit_with_registered_mode(self):
        previous = os.umask(0o077)
        try:
            self.start_with_only_temporary_file_io('abliterated')
        finally:
            os.umask(previous)
        self.assertEqual(self.path.read_bytes(), backend.unit_text('abliterated').encode())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_known_arm_rewrite_preserves_inode_and_sets0644_without_template_changes(self):
        self.path.write_text(backend.unit_text('normal'));self.path.chmod(0o600)
        before = self.path.stat()
        backend._write_unit(self.path, 'abliterated')
        self.assertEqual(self.path.stat().st_ino, before.st_ino)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)
        self.assertEqual(self.path.read_bytes(), backend.unit_text('abliterated').encode())
        backend._write_unit(self.path, 'normal')
        self.assertEqual(self.path.read_bytes(), backend.unit_text('normal').encode())

    def test_unknown_or_empty_existing_file_is_preserved_including_mode_and_inode(self):
        for raw in (b'unknown-content-sentinel',b'',backend.unit_text('normal').encode()+b'\n'):
            with self.subTest(raw=raw[:20]):
                self.path.write_bytes(raw);self.path.chmod(0o600)
                before = self.path.stat()
                with self.assertRaisesRegex(RuntimeError, 'preserve_unregistered_backend_unit'):
                    backend._write_unit(self.path, 'normal')
                after = self.path.stat()
                self.assertEqual((after.st_ino,after.st_mode,after.st_mtime_ns),
                                 (before.st_ino,before.st_mode,before.st_mtime_ns))
                self.assertEqual(self.path.read_bytes(),raw)

    def test_symlinks_nonregular_files_and_hardlinks_are_never_followed_or_rewritten(self):
        target = self.directory / 'target';target.write_text(backend.unit_text('normal'));target.chmod(0o600)
        original = target.read_bytes();before = target.stat()
        for kind in ('symlink','dangling','directory','fifo','hardlink'):
            with self.subTest(kind=kind):
                if kind == 'symlink':self.path.symlink_to(target)
                elif kind == 'dangling':self.path.symlink_to(self.directory/'absent')
                elif kind == 'directory':self.path.mkdir()
                elif kind == 'fifo':os.mkfifo(self.path)
                else:os.link(target,self.path)
                with self.assertRaisesRegex(RuntimeError, 'preserve_unregistered_backend_unit'):
                    backend._write_unit(self.path, 'abliterated')
                if kind == 'directory':self.path.rmdir()
                else:self.path.unlink()
                self.assertEqual(target.read_bytes(),original)
                self.assertEqual((target.stat().st_ino,target.stat().st_mode),(before.st_ino,before.st_mode))

    def test_invalid_arm_is_rejected_before_creating_a_file(self):
        with self.assertRaisesRegex(ValueError,'pinned_model_arm_required'):
            backend._write_unit(self.path,'unknown')
        self.assertFalse(self.path.exists())

    def test_generated_unit_hashes_are_the_unchanged_reviewed_templates(self):
        expected={'normal':'b7759999d69739d1e7bffc14a5e721efdb362b0912734bc82562f7798925ce51',
                  'abliterated':'a46298d81716912a2c329f5b89f7f736fad65280f4c93d3864c3b044606a35fe'}
        for arm,digest in expected.items():
            with self.subTest(arm=arm):
                self.assertEqual(hashlib.sha256(backend.unit_text(arm).encode()).hexdigest(),digest)


if __name__ == '__main__':
    unittest.main()
