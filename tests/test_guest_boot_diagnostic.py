"""Hermetic diagnostic tests; never start guests, native services or models."""
import json
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from native import diagnose_guest_boot as diagnostic
from native.diagnose_guest_boot import failure_category, run_probe


class BootDiagnosticTests(unittest.TestCase):
    def record(self):
        return {'attempts': [], 'boot_ready': False, 'qualification_granted': False}

    def control(self, provision):
        control = Mock()
        control.active_run.return_value = None
        control.cleanup.return_value = {'status': 'ok', 'refused': []}
        control.provision.side_effect = lambda on_created: provision(control, on_created)
        return control

    def test_stderr_classification_excludes_sensitive_raw_diagnostics(self):
        for text, category in (
            ('Permission denied (publickey). SECRET-KEY /private/path', 'public_key_authentication_failed'),
            ('Host key verification failed: SECRET', 'host_key_verification_failed'),
            ('kex_exchange_identification: Connection reset by peer SECRET', 'ssh_handshake_reset'),
            ('Connection refused /private/ssh.sock', 'connection_refused'),
            ('FileNotFoundError: secret path', 'proxy_path_missing'),
            ('unrecognized SECRET', 'unclassified_transport_failure'),
        ):
            error = RuntimeError('SECRET-ARGUMENTS')
            error.private_stderr = text
            error.exit_code = 255
            result = failure_category(error)
            self.assertEqual(result, category)
            self.assertNotIn('SECRET', result)
        self.assertEqual(failure_category(TimeoutError()), 'bounded_transport_timeout')

    def test_healthy_false_and_true_are_recorded_without_changing_provision_budget(self):
        run_id = 'a' * 32
        def provision(control, created):
            created(run_id)
            for _ in range(2):
                control.ssh(run_id, 'controller', 'health')
            return {'status': 'ok', 'run_id': run_id}
        control = self.control(provision)
        responses = [{'healthy': value, 'role': 'controller', 'agents_enabled': False} for value in (False, True)]
        original = Mock(side_effect=responses)
        control.ssh = original
        normal = Mock(return_value={'healthy': True, 'four_configuration_hashes_equal': True})
        idle = Mock()
        record = self.record()
        self.assertTrue(run_probe(control, normal, idle, lambda: False, record))
        self.assertEqual([item['category'] for item in record['attempts']], ['runtime_installation_not_ready', 'ready'])
        self.assertEqual(normal.call_count, 2)
        idle.assert_called_once_with()
        control.cleanup.assert_called_once_with(run_id)
        self.assertIs(control.ssh, original)
        self.assertFalse(record['qualification_granted'])

    def test_failed_transport_preserves_only_category_and_always_cleans_owned_run(self):
        run_id = 'b' * 32
        error = RuntimeError('SECRET')
        error.private_stderr = 'Permission denied (publickey) SECRET'
        error.exit_code = 255
        def provision(control, created):
            created(run_id)
            try:
                control.ssh(run_id, 'controller', 'health')
            except RuntimeError:
                pass
            return {'status': 'failed', 'error': 'pinned_guest_control_not_ready:controller'}
        control = self.control(provision)
        control.ssh.side_effect = error
        record = self.record()
        self.assertFalse(run_probe(control, Mock(return_value={'healthy': True}), Mock(), lambda: False, record))
        self.assertEqual(record['failure_code'], 'pinned_guest_control_not_ready:controller')
        self.assertEqual(record['attempts'][0]['category'], 'public_key_authentication_failed')
        self.assertNotIn('SECRET', json.dumps(record))
        control.cleanup.assert_called_once_with(run_id)

    def test_unexpected_exception_after_creation_still_cleans_and_checks_normal(self):
        run_id = 'c' * 32
        def provision(_control, created):
            created(run_id)
            raise ValueError('private unexpected details')
        control = self.control(provision)
        normal = Mock(return_value={'healthy': True})
        with self.assertRaises(ValueError):
            run_probe(control, normal, Mock(), lambda: False, self.record())
        control.cleanup.assert_called_once_with(run_id)
        self.assertEqual(normal.call_count, 2)

    def test_existing_fleet_window_or_text_owner_prevents_provision(self):
        for guard in ('fleet', 'window', 'text'):
            control = self.control(lambda *_: self.fail('must not provision'))
            control.active_run.return_value = 'd' * 32 if guard == 'fleet' else None
            idle = Mock(side_effect=RuntimeError('busy') if guard == 'text' else None)
            with self.subTest(guard=guard), self.assertRaises(RuntimeError):
                run_probe(control, Mock(return_value={'healthy': True}), idle, lambda: guard == 'window', self.record())
            control.provision.assert_not_called()
            control.cleanup.assert_not_called()

    def test_cleanup_failure_cannot_be_reported_as_success(self):
        def provision(_control, created):
            created('e' * 32)
            return {'status': 'ok'}
        control = self.control(provision)
        control.cleanup.side_effect = RuntimeError('private details')
        record = self.record()
        self.assertFalse(run_probe(control, Mock(return_value={'healthy': True}), Mock(), lambda: False, record))
        self.assertEqual(record['cleanup'], {'status': 'failed', 'code': 'exact_owned_cleanup_unconfirmed'})


class RegisteredInputTests(unittest.TestCase):
    def setUp(self):
        names=('supervisor.py','vm_service.py','proxy.py','evidence.py',
               'lab/state.py','lab/process.py','lab/transport.py','guest/qualify.py','guest/bootstrap.py')
        self.raw=b'protected installed fixture'
        self.info=SimpleNamespace(st_dev=1,st_ino=2)
        self.entries=[{'path':str(diagnostic.INSTALL/name),'device':1,'inode':2,
                       'sha256':hashlib.sha256(self.raw).hexdigest()} for name in names]
        self.config={'source_pack_sha256':diagnostic.PACK,'agents_enabled':False}

    def read(self,path):
        if path==diagnostic.REGISTER:return json.dumps({'installed_files':self.entries}).encode(),self.info
        if path==diagnostic.CONFIG:return json.dumps(self.config).encode(),self.info
        return self.raw,self.info

    def verify(self):
        with patch.object(diagnostic,'read_protected',side_effect=self.read),patch.object(diagnostic,'RECOVERY_SHA',hashlib.sha256(self.raw).hexdigest()):
            return diagnostic.verify_registered()

    def test_exact_registered_source_and_no_agent_config_are_required(self):
        self.assertEqual(self.verify(),9)
        self.config['agents_enabled']=True
        with self.assertRaisesRegex(RuntimeError,'reviewed_runtime_pack_required'):self.verify()

    def test_registered_byte_or_inode_drift_is_rejected_before_import(self):
        for field,value in (('sha256','0'*64),('inode',3)):
            original=self.entries[0][field]
            self.entries[0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'registered_runtime_drift'):self.verify()
            self.entries[0][field]=original

    def test_omitted_or_duplicate_import_cannot_weaken_register(self):
        missing=self.entries.pop(0)
        with self.assertRaisesRegex(RuntimeError,'not_registered'):self.verify()
        self.entries.extend((missing,missing))
        with self.assertRaisesRegex(RuntimeError,'registered_path_required'):self.verify()


if __name__ == '__main__':
    unittest.main()
