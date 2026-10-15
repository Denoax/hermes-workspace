import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from native import install_runtime
from lab.qualification import network_supported, confinement_supported
from native.install_runtime import validated_pack, EXPECTED_FILES
from native.rollback_runtime import permitted_file


class QualificationEvidence(unittest.TestCase):
    def example(self):
        positive = {'operation': 'positive', 'endpoints': [{'responded': True}]*4}
        probes = {key: {'connected': False} for key in ('host_v4', 'host_v6', 'owned_outside_v4', 'owned_outside_v6')}
        probes.update({key: {'reply_received': False} for key in ('DNS_v4', 'DNS_v6')})
        boundary = {'operation': 'counters', 'endpoints': [{'tcp': 0, 'udp': 0}]*4}
        return positive, {'probes': probes}, boundary

    def test_denials_need_working_positive_controls_and_outside_observation(self):
        positive, guest, boundary = self.example()
        self.assertTrue(network_supported(positive, guest, boundary))
        self.assertFalse(network_supported({}, guest, boundary))
        self.assertFalse(network_supported(positive, guest, {}))

    def test_a_single_forbidden_connection_or_boundary_packet_invalidates_result(self):
        positive, guest, boundary = self.example()
        guest['probes']['host_v4']['connected'] = True
        self.assertFalse(network_supported(positive, guest, boundary))
        guest['probes']['host_v4']['connected'] = False
        boundary['endpoints'] = [{'tcp': 1, 'udp': 0}]*4
        self.assertFalse(network_supported(positive, guest, boundary))

    def test_missing_family_or_wrong_types_do_not_pass(self):
        positive, guest, boundary = self.example()
        del guest['probes']['host_v6']
        self.assertFalse(network_supported(positive, guest, boundary))
        self.assertFalse(confinement_supported({'nonroot_dedicated_UID': 1}))


class InstallRecoveryContracts(unittest.TestCase):
    def test_partial_install_checkpoint_records_created_file_identity_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root/'code'
            code.mkdir()
            partial = code/'supervisor.py'
            partial.write_text('# partial owned installation\n')
            helper = root/'helpers'
            helper.mkdir()
            with patch.multiple(install_runtime, INSTALL=code, CONFIG=root/'config',
                                DATA=root/'data', UNIT=root/'unit', SELF=helper/'installer.py'):
                record = {'status': 'failed_partial_installation'}
                install_runtime.checkpoint(record)
            saved = json.loads((helper/'runtime-installed.json').read_text())
            self.assertEqual(saved['status'], 'failed_partial_installation')
            self.assertEqual(saved['installed_files'][0]['inode'], partial.stat().st_ino)
            self.assertEqual(saved['installed_files'][0]['sha256'], hashlib.sha256(partial.read_bytes()).hexdigest())
            self.assertFalse((helper/'runtime-installed.json.tmp').exists())

    def test_unknown_archive_member_and_tampered_hash_rejected_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                for name in EXPECTED_FILES:
                    archive.writestr(name, '# owned fixture source\n')
                archive.writestr('../unexpected', 'denied')
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                validated_pack(path, checksum)
            with self.assertRaises(ValueError):
                validated_pack(path, '0'*64)

    def test_exact_source_pack_is_recoverable_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                for name in EXPECTED_FILES:
                    archive.writestr(name, '# owned fixture source\n')
            result = validated_pack(path, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(set(result), EXPECTED_FILES)

    def test_rollback_targets_do_not_include_personal_home_or_cache(self):
        for path in ['/home/mani/.hermes/config.yaml', '/etc/passwd', '/home/mani-vmlab-data/package-cache/file',
                     '/usr/local/lib/mani-vmlab/../../unrelated']:
            self.assertFalse(permitted_file(path))
        self.assertTrue(permitted_file('/usr/local/lib/mani-vmlab/lab/state.py'))


if __name__ == '__main__':
    unittest.main()
