"""Hermetic installer safety contracts; never call systemd, root or inference."""
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native import production_setup as setup


def fixture_plan():
    digest = hashlib.sha256(b'fixture').hexdigest()
    return {'version': 1, 'units': setup.unit_texts(), 'old_user_unit_sha256': digest, 'recovery_before_sha256': digest, 'recovery_source': {'path': str(setup.ROOT / 'native/recovery.py'), 'sha256': digest}, 'normal_configuration_sha256': {name: digest for name in setup.NORMAL_FILES}, 'application_sources': {str(setup.ROOT / relative): digest for relative in ('workspace/server.py', 'workspace/production_client.py')}}


class FrozenPlanTests(unittest.TestCase):
    def test_only_exact_loopback_units_and_fixed_application_sources_are_admitted(self):
        plan = fixture_plan()
        self.assertEqual(setup.validate_plan(plan), plan)
        for role in ('socket', 'service', 'user'):
            changed = copy.deepcopy(plan)
            changed['units'][role] += '\nExecStart=/bin/sh\n'
            with self.assertRaises(ValueError):
                setup.validate_plan(changed)
        changed = copy.deepcopy(plan)
        changed['application_sources']['/tmp/unreviewed.py'] = '0' * 64
        with self.assertRaises(ValueError):
            setup.validate_plan(changed)

    def test_unrelated_normal_files_and_unreviewed_recovery_source_are_rejected(self):
        plan = fixture_plan()
        plan['normal_configuration_sha256']['.ssh/config'] = '0' * 64
        with self.assertRaises(ValueError):
            setup.validate_plan(plan)
        plan = fixture_plan()
        plan['recovery_source']['path'] = '/tmp/arbitrary.py'
        with self.assertRaises(ValueError):
            setup.validate_plan(plan)

    def test_unit_contract_keeps_data_nonroot_private_tmp_and_launcher_proxy_separate(self):
        units = setup.unit_texts()
        self.assertIn('ListenStream=127.0.0.1:18791\n', units['socket'])
        for setting in ('User=mani\n', 'Group=mani\n', 'PrivateTmp=yes\n', 'PrivateUsers=no\n', 'NoNewPrivileges=yes\n', 'CapabilityBoundingSet=\n', 'AmbientCapabilities=\n', 'Requires=user@1000.service\n'):
            self.assertIn(setting, units['service'])
        self.assertNotIn('[Install]', units['service'])
        self.assertIn('PrivateTmp=no\n', units['user'])
        self.assertIn('production_client.py stop\n', units['user'])
        self.assertNotIn('server.py', units['user'])


class NamespaceProofTests(unittest.TestCase):
    def good(self):
        return {'uid': 1000, 'gid': 1000, 'socket_uid': 0, 'parent_uid': 0, 'root_peer_uid': 0, 'parent_mode': 0o755, 'is_socket': True, 'user_namespace': 'initial', 'mount_namespace': 'private', 'no_new_privileges': '1', 'effective_capabilities': '0000000000000000', 'normal_pid': 123, 'normal_executable': '/owned/llama-server', 'normal_command_readable': True}

    def test_same_uid_host_identity_root_peer_and_private_mount_pass(self):
        self.assertEqual(setup.validate_proof(self.good(), 'initial', 'host')['normal_pid'], 123)

    def test_actual_unmapped_root_regression_is_rejected(self):
        proof = self.good()
        proof.update(root_peer_uid=65534, socket_uid=65534, parent_uid=65534)
        with self.assertRaisesRegex(RuntimeError, 'real_root_peer'):
            setup.validate_proof(proof, 'initial', 'host')

    def test_capabilities_missing_private_tmp_or_unreadable_normal_process_fail(self):
        for field, value in [('uid', 0), ('user_namespace', 'child'), ('mount_namespace', 'host'), ('no_new_privileges', '0'), ('effective_capabilities', '1'), ('normal_command_readable', False), ('normal_pid', 0), ('normal_executable', '')]:
            proof = self.good()
            proof[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                setup.validate_proof(proof, 'initial', 'host')


class FileAndRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'owned-file'
        self.file.write_bytes(b'owned before')

    def test_pinned_read_rejects_changed_bytes_and_bounded_input(self):
        digest = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.assertEqual(setup.read_pinned(self.file, digest), b'owned before')
        with self.assertRaises(ValueError):
            setup.read_file(self.file, maximum=2)
        self.file.write_bytes(b'changed by user')
        with self.assertRaises(RuntimeError):
            setup.read_pinned(self.file, digest)

    def test_symlink_ancestor_leaf_and_hardlinks_are_not_privileged_inputs(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.file)
        with self.assertRaises(OSError):
            setup.read_file(alias)
        directory = self.root / 'directory'
        directory.mkdir()
        (directory / 'f').write_text('fixture')
        link = self.root / 'link'
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(OSError):
            setup.read_file(link / 'f')
        os.link(self.file, self.root / 'hardlink')
        with self.assertRaises(ValueError):
            setup.read_file(self.file)

    def test_registered_drift_is_rejected_before_any_service_mutation(self):
        item = setup.fingerprint(self.file)
        register = {'version': 1, 'files': [item]}
        setup.inspect_register(register)
        self.file.write_text('unrelated changed work')
        with patch.object(setup, 'command') as command:
            with self.assertRaisesRegex(RuntimeError, 'preserve_registered_file_drift'):
                setup.inspect_register(register)
            command.assert_not_called()
        self.assertEqual(self.file.read_text(), 'unrelated changed work')

    def test_register_update_preserves_unrelated_items_and_restore_contract(self):
        item = setup.fingerprint(self.file)
        item.update(action='restore', backup='/approved/private/backup', before_sha256='a' * 64)
        other = {'path': '/other/owned', 'sha256': 'b' * 64}
        original = {'version': 1, 'files': [item, other], 'retained': ['models', 'conversations']}
        replacement = {**item, 'inode': item['inode'] + 1, 'sha256': 'c' * 64}
        result = setup.record_files(original, [replacement])
        self.assertEqual(result['files'][0]['backup'], item['backup'])
        self.assertEqual(result['files'][1], other)
        self.assertEqual(result['retained'], original['retained'])
        self.assertNotEqual(result['files'][0]['inode'], original['files'][0]['inode'])


if __name__ == '__main__':
    unittest.main()
