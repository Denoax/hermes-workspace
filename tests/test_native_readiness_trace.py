"""Hermetic trace safety checks; no installed files, systemd, VM or GPU use."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'native/readiness_trace.py'
spec = importlib.util.spec_from_file_location('proposed_readiness_trace', SOURCE)
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


class TraceContractTests(unittest.TestCase):
    def created(self):
        return {'phase': 'created', 'run_id': 'a' * 32, 'elapsed_seconds': 0}

    def health(self):
        return {'phase': 'health', 'run_id': 'a' * 32, 'role': 'controller',
                'attempt': 1, 'elapsed_seconds': 1, 'duration_seconds': 0.1,
                'category': 'runtime_installation_not_ready'}

    def raw(self, events):
        return b''.join((json.dumps(item) + '\n').encode() for item in events)

    def test_only_sanitized_bounded_events_are_public(self):
        events = [self.created(), self.health()]
        self.assertEqual(trace.validate_events(self.raw(events)), events)
        changes = [('role', 'foreign'), ('category', '/private/SECRET'), ('prompt', 'SECRET'),
                   ('attempt', 61), ('duration_seconds', -1), ('elapsed_seconds', float('nan'))]
        for key, value in changes:
            bad = self.health()
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                trace.validate_events(self.raw([self.created(), bad]))

    def test_unowned_run_or_attempt_reordering_is_rejected(self):
        bad = self.health()
        bad['run_id'] = 'b' * 32
        with self.assertRaises(ValueError):trace.validate_events(self.raw([self.created(), bad]))
        bad = self.health()
        bad['attempt'] = 2
        with self.assertRaises(ValueError):trace.validate_events(self.raw([self.created(), bad]))
        with self.assertRaises(ValueError):trace.validate_events(self.raw([self.created(), self.created()]))

    def test_partial_trailing_write_preserves_completed_owned_creation(self):
        complete = self.raw([self.created()])
        events, partial = trace.complete_trace_prefix(complete + b'{"phase":"health"')
        self.assertTrue(partial)
        self.assertEqual(events, [self.created()])
        self.assertEqual(trace.complete_trace_prefix(complete), ([self.created()], False))
        self.assertEqual(trace.complete_trace_prefix(b'{'), ([], True))

    def test_child_command_has_fixed_source_case_and_private_generated_path(self):
        path = trace.SETUP / ('.readiness-trace-' + 'c' * 32 + '.jsonl')
        command = trace.child_command(path)
        self.assertEqual(command[:3], ['/usr/bin/python3', '-I', '-c'])
        self.assertIn(str(trace.SELF), command[3])
        self.assertIn(str(path), command[3])
        self.assertNotIn('sudo', command)
        for foreign in ('/tmp/trace.jsonl', str(trace.SETUP / '../private'), str(trace.SETUP / '.readiness-trace-shell.jsonl')):
            with self.subTest(path=foreign), self.assertRaises(ValueError):trace.child_command(foreign)

    def test_trace_file_cannot_grow_beyond_fixed_limit(self):
        with tempfile.TemporaryFile() as stream:
            trace.append_event(stream.fileno(), self.created())
            stream.seek(0)
            self.assertEqual(trace.validate_events(stream.read()), [self.created()])
            stream.seek(trace.MAX_TRACE_BYTES)
            stream.write(b'x')
            stream.flush()
            with self.assertRaises(RuntimeError):trace.append_event(stream.fileno(), self.health())

    def test_successful_scenario_receipt_is_bound_to_its_observed_creation(self):
        receipt = {'operation': 'absolute_deadline', 'run_id': 'a' * 32, 'source_pack_sha256': 'pinned-pack',
                   'all_three_VMs_exited': True, 'VM_exit_after_trigger_seconds': dict.fromkeys(trace.ROLES, 2.1),
                   'observer_outside_supervisor_and_VM_cgroups': True, 'cleanup_status': 'ok', 'cleanup_refused': [],
                   'unrelated_private_field': 'SECRET'}
        result = trace.scenario_receipt(json.dumps(receipt).encode(), ['a' * 32], 'pinned-pack')
        self.assertNotIn('SECRET', json.dumps(result))
        for key, value in (('run_id', 'b' * 32), ('operation', 'all'), ('source_pack_sha256', 'old-pack'),
                           ('all_three_VMs_exited', False), ('cleanup_status', 'failed')):
            changed = {**receipt, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                trace.scenario_receipt(json.dumps(changed).encode(), ['a' * 32], 'pinned-pack')

    def test_pressure_is_read_only_and_missing_sources_are_explicit(self):
        text = 'some avg10=0.12 avg60=0.10 avg300=0.05 total=12345\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=10\n'
        with patch.object(Path, 'read_text', return_value=text):result = trace.pressure_snapshot()
        self.assertEqual(result['cpu']['some'], {'avg10_percent': 0.12, 'total_microseconds': 12345})
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError()):result = trace.pressure_snapshot()
        self.assertEqual(result, dict.fromkeys(('cpu', 'io', 'memory'), {'status': 'unavailable'}))


class OriginalCaseObservation(unittest.TestCase):
    def control_type(self, active=None, outcomes=()):
        instances = []
        class Control:
            def __init__(self):
                self.firewall = SimpleNamespace(close=Mock())
                self.cleanup = Mock(return_value={'status': 'ok'})
                self.heartbeat = Mock()
                self.responses = list(outcomes)
                self.original_calls = []
                instances.append(self)

            def active_run(self):
                return active

            def provision(self, on_created=None):
                on_created('a' * 32)
                return {'status': 'ok', 'run_id': 'a' * 32}

            def ssh(self, run_id, role, operation):
                self.original_calls.append((run_id, role, operation))
                result = self.responses.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result
        return Control, instances

    def test_observer_preserves_results_exceptions_and_method_ownership(self):
        false = {'healthy': False, 'role': 'controller', 'agents_enabled': False}
        true = {**false, 'healthy': True}
        error = RuntimeError('PRIVATE-DETAILS')
        control_type, instances = self.control_type(outcomes=(false, error, true))
        methods = (control_type.__init__, control_type.provision, control_type.ssh)
        events = []
        def invoke():
            control = control_type()
            control.provision()
            self.assertIs(control.ssh('a' * 32, 'controller', 'health'), false)
            with self.assertRaises(RuntimeError) as failure:control.ssh('a' * 32, 'controller', 'health')
            self.assertIs(failure.exception, error)
            self.assertIs(control.ssh('a' * 32, 'controller', 'health'), true)
            return 'original case result'
        result = trace.observe_watchdog(control_type, invoke, events.append, lambda _error: 'ssh_handshake_closed')
        self.assertEqual(result, 'original case result')
        self.assertEqual([item['category'] for item in events if item['phase'] == 'health'],
                         ['runtime_installation_not_ready', 'ssh_handshake_closed', 'ready'])
        self.assertNotIn('PRIVATE', json.dumps(events))
        self.assertEqual((control_type.__init__, control_type.provision, control_type.ssh), methods)
        instances[0].heartbeat.assert_not_called()
        instances[0].cleanup.assert_called_once_with('a' * 32)
        instances[0].firewall.close.assert_called_once_with()
        self.assertEqual(len(instances[0].original_calls), 3)

    def test_exception_before_original_finally_still_cleans_only_created_run(self):
        control_type, instances = self.control_type()
        def invoke():
            control = control_type()
            control.provision()
            raise RuntimeError('original provisioning failed')
        with self.assertRaises(RuntimeError):
            trace.observe_watchdog(control_type, invoke, lambda _event: None, lambda _error: 'native_transport_error')
        instances[0].cleanup.assert_called_once_with('a' * 32)
        instances[0].firewall.close.assert_called_once_with()

    def test_existing_fleet_is_preserved_and_never_targeted_for_cleanup(self):
        control_type, instances = self.control_type(active='d' * 32)
        with self.assertRaisesRegex(RuntimeError, 'preserve_existing_fleet'):
            trace.observe_watchdog(control_type, control_type, lambda _event: None, lambda _error: 'native_transport_error')
        instances[0].cleanup.assert_not_called()
        instances[0].firewall.close.assert_called_once_with()

    def test_guest_operations_or_foreign_run_are_not_added_by_instrumentation(self):
        control_type, instances = self.control_type()
        def invoke():
            control = control_type()
            control.provision()
            for run_id, role, operation, request in (('b' * 32, 'controller', 'health', None),
                                                    ('a' * 32, 'controller', 'solve', {})):
                with self.assertRaisesRegex(RuntimeError, 'fixed_no_agent_health_trace_only'):
                    control.ssh(run_id, role, operation, request)
        trace.observe_watchdog(control_type, invoke, lambda _event: None, lambda _error: 'native_transport_error')
        self.assertEqual(instances[0].original_calls, [])

    def test_failed_exact_cleanup_cannot_leave_a_successful_case_result(self):
        control_type, instances = self.control_type()
        def invoke():
            control = control_type()
            control.provision()
            control.cleanup.return_value = {'status': 'failed'}
            return 'passed original scenario'
        with self.assertRaisesRegex(RuntimeError, 'exact_owned_trace_cleanup_unconfirmed'):
            trace.observe_watchdog(control_type, invoke, lambda _event: None, lambda _error: 'native_transport_error')
        instances[0].firewall.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
