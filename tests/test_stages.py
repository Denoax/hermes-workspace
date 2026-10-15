import unittest
import uuid
from lab.readiness import REQUIREMENTS, stage_results
from lab.native_client import request_schema
from native.vm_service import qemu_command, service_text, unit_name
from lab.images import checksum_for_image, IMAGE


class StagedReadiness(unittest.TestCase):
    def test_missing_candidate_Hermes_and_GPU_do_not_block_no_agent_provision(self):
        facts = {name: True for name in REQUIREMENTS['provision']}
        results = stage_results(facts)
        self.assertTrue(results['provision'].ready)
        self.assertFalse(results['normal'].ready)
        self.assertFalse(results['paired'].ready)

    def test_cold_sudo_is_not_an_ordinary_operation_gate(self):
        facts = {name: True for name in REQUIREMENTS['provision']}
        facts['native_admin_cached'] = False
        self.assertTrue(stage_results(facts)['provision'].ready)

    def test_unknown_or_boolean_enable_flag_cannot_grant_readiness(self):
        results = stage_results({'execution_enabled': True})
        self.assertTrue(all(not stage.ready for stage in results.values()))
        with self.assertRaises(ValueError):
            stage_results({'kvm': 1})

    def test_network_failure_blocks_model_execution_with_booted_guests(self):
        facts = {key: True for key in REQUIREMENTS['paired']}
        facts['network_qualified'] = False
        self.assertEqual(stage_results(facts)['paired'].missing, ('network_qualified',))

    def test_models_and_workers_have_separate_requirements(self):
        facts = {key: True for key in REQUIREMENTS['normal']}
        self.assertTrue(stage_results(facts)['normal'].ready)
        self.assertFalse(stage_results(facts)['workers'].ready)


class FixedNativeContract(unittest.TestCase):
    def test_out_of_scope_commands_and_targets_rejected(self):
        for operation in ('shell', 'install', 'exec', 'load_model', 'sudo', {}, []):
            with self.assertRaises(ValueError):
                request_schema(operation)
        with self.assertRaises(ValueError):
            request_schema('stop', run_id='../../other')
        with self.assertRaises(ValueError):
            request_schema('run_case', vm_id='router')

    def test_service_template_is_nonroot_KVM_with_private_network_and_deadline(self):
        text = service_text(uuid.uuid4().hex, 'controller', str(uuid.uuid4()), 480)
        for expected in ('User=mani-vmlab-vm', 'PrivateNetwork=yes', 'PrivateIPC=yes', 'RootDirectory=',
                         'NoNewPrivileges=yes', 'RuntimeMaxSec=480', 'DeviceAllow=/dev/kvm rw', 'KillMode=control-group',
                         'BindsTo=mani-vmlab-supervisor.service', 'hostfwd=unix:/control/ssh.sock'):
            self.assertIn(expected, text)
        for denied in ('virtfs', 'guestfwd', 'VNC', '/home/mani/', 'docker.sock', 'Restart=always'):
            self.assertNotIn(denied, text)

    def test_injected_units_and_runtime_caps_rejected(self):
        for run_id in ('other.service', uuid.uuid4().hex+'\nExecStart=/bin/sh'):
            with self.assertRaises(ValueError):
                unit_name(run_id, 'controller')
        with self.assertRaises(ValueError):
            service_text(uuid.uuid4().hex, 'controller', str(uuid.uuid4()), 5401)
        with self.assertRaises(ValueError):
            qemu_command('router', str(uuid.uuid4()))

    def test_signed_checksum_must_name_one_exact_image(self):
        checksum = 'a'*64
        raw = (checksum+' *'+IMAGE+'\n').encode()
        self.assertEqual(checksum_for_image(raw), checksum)
        with self.assertRaises(ValueError):
            checksum_for_image(raw+raw)
        with self.assertRaises(ValueError):
            checksum_for_image((checksum+' *other.img\n').encode())


if __name__ == '__main__':
    unittest.main()
