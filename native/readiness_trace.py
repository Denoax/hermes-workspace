#!/usr/bin/python3
"""One captured watchdog readiness trace; no policy repair or qualification."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys
import threading
import time
import uuid

sys.dont_write_bytecode = True
SELF = Path('/usr/local/lib/mani-vmlab-setup/readiness_trace.py')
SETUP = SELF.parent
INSTALL = Path('/usr/local/lib/mani-vmlab')
DATA = Path('/home/mani-vmlab-data')
PUBLIC = Path('/var/lib/mani-vmlab-review')
DIAGNOSTIC = SETUP / 'diagnose_guest_boot.py'
DIAGNOSTIC_SHA = '4e89928d5af57c56a3066a1940b6e738f66fde545cc18e548fa5c6ac1aa93d07'
WATCHDOG = SETUP / 'watchdog_probe.py'
WATCHDOG_SHA = 'b48e2913bb84127e768f686fffcc01920246cd1019d4d37bbb6ecb5d6afed280'
ROLES = ('controller', 'worker_a', 'worker_b')
CATEGORIES = frozenset({'ready', 'runtime_installation_not_ready', 'unexpected_health_reply',
    'host_key_verification_failed', 'public_key_authentication_failed', 'ssh_algorithm_mismatch',
    'connection_refused', 'connection_timeout', 'route_unavailable', 'ssh_handshake_reset',
    'ssh_handshake_closed', 'ssh_client_configuration', 'proxy_contract_refused',
    'proxy_path_missing', 'proxy_permission_denied', 'helper_or_proxy_exception',
    'bounded_transport_timeout', 'invalid_bounded_guest_reply', 'unclassified_transport_failure',
    'native_transport_error'})
RUN = re.compile(r'[0-9a-f]{32}\Z')
TRACE_NAME = re.compile(r'\.readiness-trace-[0-9a-f]{32}\.jsonl\Z')
MAX_TRACE_BYTES = 128 * 1024


def load_support():
    # Reuse the reviewed v4 ownership, register and stderr sanitization checks.
    # A new helper cannot silently select different installed diagnostic code.
    for path, expected in ((DIAGNOSTIC, DIAGNOSTIC_SHA), (WATCHDOG, WATCHDOG_SHA)):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or info.st_size > 1024 * 1024 or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise RuntimeError('reviewed_protected_helper_required')
    spec = importlib.util.spec_from_file_location('readiness_trace_support', DIAGNOSTIC)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    for path in (SELF, DIAGNOSTIC, WATCHDOG):
        support.protected(path)
    support.verify_registered()
    return support


def trace_path(path):
    path = Path(path)
    if path.parent != SETUP or not TRACE_NAME.fullmatch(path.name):
        raise ValueError('fixed_private_trace_path_required')
    return path


def append_event(descriptor, event):
    raw = (json.dumps(event, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(raw) > 1024 or os.fstat(descriptor).st_size + len(raw) > MAX_TRACE_BYTES:
        raise RuntimeError('bounded_trace_limit')
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written == 0:
            raise OSError('trace_write_closed')
        view = view[written:]


def validate_events(raw):
    if len(raw) > MAX_TRACE_BYTES:
        raise ValueError('bounded_trace_limit')
    result = []
    known = set()
    attempts = {}
    previous_clock = 0
    for line in raw.splitlines():
        event = json.loads(line)
        if not isinstance(event, dict) or event.get('phase') not in ('created', 'health'):
            raise ValueError('fixed_trace_event_required')
        run_id = event.get('run_id')
        if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
            raise ValueError('owned_trace_run_required')
        elapsed = event.get('elapsed_seconds')
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < previous_clock:
            raise ValueError('finite_trace_clock_required')
        previous_clock = elapsed
        if event['phase'] == 'created':
            if set(event) != {'phase', 'run_id', 'elapsed_seconds'} or run_id in known:
                raise ValueError('one_owned_trace_run_required')
            known.add(run_id)
        else:
            fields = {'phase', 'run_id', 'role', 'attempt', 'elapsed_seconds', 'duration_seconds', 'category'}
            duration = event.get('duration_seconds')
            if (set(event) != fields or run_id not in known or event.get('role') not in ROLES
                    or type(event.get('attempt')) is not int or not 1 <= event['attempt'] <= 60
                    or event.get('category') not in CATEGORIES
                    or type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
                raise ValueError('fixed_health_trace_required')
            key = (run_id, event['role'])
            if event['attempt'] != attempts.get(key, 0) + 1:
                raise ValueError('ordered_health_attempts_required')
            attempts[key] = event['attempt']
        result.append(event)
    if len(known) > 1 or len(result) > 181:
        raise ValueError('one_bounded_fleet_trace_required')
    return result


def complete_trace_prefix(raw):
    """Keep positive creation evidence if an interrupted last write is partial."""
    if len(raw) > MAX_TRACE_BYTES:
        raise ValueError('bounded_trace_limit')
    partial = bool(raw and not raw.endswith(b'\n'))
    if partial:
        raw = raw.rsplit(b'\n', 1)[0] + b'\n' if b'\n' in raw else b''
    return validate_events(raw), partial


def scenario_receipt(raw, owned, source_pack):
    if not isinstance(raw, bytes) or len(raw) > 65536:
        raise ValueError('bounded_scenario_receipt_required')
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get('operation') != 'absolute_deadline'
            or receipt.get('run_id') not in owned or len(owned) != 1
            or receipt.get('source_pack_sha256') != source_pack):
        raise ValueError('scenario_receipt_creation_binding_required')
    exits = receipt.get('VM_exit_after_trigger_seconds')
    if (receipt.get('all_three_VMs_exited') is not True
            or receipt.get('observer_outside_supervisor_and_VM_cgroups') is not True
            or receipt.get('cleanup_status') != 'ok' or receipt.get('cleanup_refused') != []
            or not isinstance(exits, dict) or set(exits) != set(ROLES)
            or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                   for value in exits.values())):
        raise ValueError('original_scenario_criteria_not_proven')
    allowed = ('operation', 'run_id', 'source_pack_sha256', 'all_three_VMs_exited',
               'VM_exit_after_trigger_seconds', 'observer_outside_supervisor_and_VM_cgroups',
               'cleanup_status', 'cleanup_refused')
    return {key: receipt[key] for key in allowed}


def observe_watchdog(supervisor_type, invoke, emit, classify, clock=time.monotonic):
    """Add observations to the original case; no extra heartbeat or retries."""
    original_init = supervisor_type.__init__
    original_provision = supervisor_type.provision
    original_ssh = supervisor_type.ssh
    controls = []
    owned = {}
    attempts = {}
    start = clock()

    def initialize(control, *args, **kwargs):
        original_init(control, *args, **kwargs)
        controls.append(control)
        if control.active_run():
            raise RuntimeError('preserve_existing_fleet_before_trace')

    def provision(control, on_created=None):
        if on_created is not None:
            raise RuntimeError('unchanged_watchdog_case_required')
        def created(run_id):
            if not isinstance(run_id, str) or not RUN.fullmatch(run_id) or owned:
                raise RuntimeError('one_owned_trace_run_required')
            owned[run_id] = control
            emit({'phase': 'created', 'run_id': run_id, 'elapsed_seconds': round(clock() - start, 6)})
        return original_provision(control, on_created=created)

    def ssh(control, run_id, role, operation, request=None):
        if owned.get(run_id) is not control or role not in ROLES or operation != 'health' or request is not None:
            raise RuntimeError('fixed_no_agent_health_trace_only')
        key = (run_id, role)
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] > 60:
            raise RuntimeError('original_readiness_attempt_limit_changed')
        began = clock()
        category = 'native_transport_error'
        try:
            result = original_ssh(control, run_id, role, operation)
            expected = {'healthy': True, 'role': role, 'agents_enabled': False}
            category = ('ready' if result == expected else 'runtime_installation_not_ready'
                        if result == {**expected, 'healthy': False} else 'unexpected_health_reply')
            return result
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            category = classify(error)
            if category not in CATEGORIES:
                category = 'native_transport_error'
            raise
        finally:
            emit({'phase': 'health', 'run_id': run_id, 'role': role, 'attempt': attempts[key],
                  'elapsed_seconds': round(began - start, 6),
                  'duration_seconds': round(clock() - began, 6), 'category': category})

    supervisor_type.__init__ = initialize
    supervisor_type.provision = provision
    supervisor_type.ssh = ssh
    try:
        return invoke()
    finally:
        supervisor_type.__init__ = original_init
        supervisor_type.provision = original_provision
        supervisor_type.ssh = original_ssh
        try:
            # The original case normally cleans itself. This also covers a
            # failure before its own finally block; cleanup targets only IDs
            # observed at this exact invocation's creation boundary.
            for run_id, control in owned.items():
                if control.cleanup(run_id).get('status') != 'ok':
                    raise RuntimeError('exact_owned_trace_cleanup_unconfirmed')
        finally:
            for control in controls:
                control.firewall.close()


def child(path):
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_protected_trace_child_only')
    support = load_support()
    path = trace_path(path)
    support.protected(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if info.st_nlink != 1 or info.st_mode & 0o077:
            raise RuntimeError('private_single_link_trace_required')
        sys.path.insert(0, str(INSTALL))
        import supervisor
        import window
        if window.state().get('status') != 'closed':
            raise RuntimeError('finish_existing_window_before_trace')
        support.require_idle_text()
        old_argv = sys.argv
        sys.argv = [str(WATCHDOG), 'absolute_deadline']
        try:
            observe_watchdog(supervisor.Supervisor, lambda: runpy.run_path(str(WATCHDOG), run_name='__main__'),
                             lambda event: append_event(descriptor, event), support.failure_category)
        finally:
            sys.argv = old_argv
    finally:
        os.close(descriptor)


def child_command(path):
    path = trace_path(path)
    # Fixed reviewed source and one supervisor-generated path; no user/model
    # command, source path, environment or watchdog operation can be supplied.
    code = ("import runpy; m=runpy.run_path(" + repr(str(SELF)) +
            ",run_name='readiness_trace_child'); m['child'](" + repr(str(path)) + ")")
    return ['/usr/bin/python3', '-I', '-c', code]


def pressure_snapshot():
    result = {}
    for name in ('cpu', 'io', 'memory'):
        try:
            rows = {}
            for line in (Path('/proc/pressure') / name).read_text().splitlines():
                fields = line.split()
                if fields[0] not in ('some', 'full'):
                    raise ValueError('pressure_shape')
                values = dict(field.split('=', 1) for field in fields[1:])
                average, total = float(values['avg10']), int(values['total'])
                if not math.isfinite(average) or average < 0 or total < 0:
                    raise ValueError('pressure_values')
                rows[fields[0]] = {'avg10_percent': average, 'total_microseconds': total}
            result[name] = {'status': 'observed', **rows}
        except (OSError, ValueError, KeyError, IndexError):
            result[name] = {'status': 'unavailable'}
    return result


def resource_snapshot():
    names = ('MemAvailable', 'MemTotal', 'SwapFree', 'SwapTotal')
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024
              for line in Path('/proc/meminfo').read_text().splitlines()
              if line.split(':')[0] in names}
    disk = os.statvfs(DATA)
    return {'CPU_threads': os.cpu_count(), 'memory_bytes': memory,
            'lab_filesystem_available_bytes': disk.f_bavail * disk.f_frsize,
            'KVM_access': os.access('/dev/kvm', os.R_OK | os.W_OK),
            'host_pressure': pressure_snapshot()}


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF or sys.argv[1:] != ['trace']:
        raise SystemExit('fixed_protected_readiness_trace_only')
    support = load_support()
    support.protected(PUBLIC, directory=True)
    sys.path.insert(0, str(INSTALL))
    import supervisor
    import window
    from lab.state import RunStore, atomic_json
    recovery_spec = importlib.util.spec_from_file_location('trace_normal_verifier', SETUP / 'recovery.py')
    recovery = importlib.util.module_from_spec(recovery_spec)
    recovery_spec.loader.exec_module(recovery)
    normal = recovery.NativeServices().verify_normal_profile
    before = normal()
    gate = Path('/var/lib/mani-vmlab-setup/VM-watchdog-qualified.json')
    def gate_hash():
        if not gate.exists():
            return None
        support.protected(gate)
        return hashlib.sha256(gate.read_bytes()).hexdigest()
    gate_before = gate_hash()
    if window.state().get('status') != 'closed':
        raise RuntimeError('finish_existing_window_before_trace')
    store = RunStore(DATA / 'runs')
    if any(store.read(p.name)['status'] == 'active' for p in store.root.iterdir() if p.is_dir()):
        raise RuntimeError('preserve_existing_fleet_before_trace')
    support.require_idle_text()
    nonce = uuid.uuid4().hex
    path = SETUP / ('.readiness-trace-' + nonce + '.jsonl')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    identity = os.fstat(descriptor)
    os.close(descriptor)
    report = PUBLIC / ('readiness-trace-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + nonce[:8] + '.json')
    record = {'evidence_kind': 'one_captured_original_watchdog_readiness_trace',
              'qualification_granted': False, 'full_watchdog_receipt_changed': False,
              'source_pack_sha256': support.PACK,
              'model_inference_started': False, 'normal_before': before,
              'resources_before': resource_snapshot(),
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'kernel': os.uname().release,
              'policy_files': {name: hashlib.sha256((INSTALL / name).read_bytes()).hexdigest()
                               for name in supervisor.WATCHDOG_POLICY_FILES},
              'watchdog_helper_sha256': WATCHDOG_SHA, 'diagnostic_support_sha256': DIAGNOSTIC_SHA,
              'child_context': {'operation': 'absolute_deadline', 'environment': {'PATH': '/usr/bin:/bin', 'LANG': 'C'},
                                'stdin': 'DEVNULL', 'stdout': 'PIPE', 'stderr': 'PIPE', 'timeout_seconds': 240},
              'independent_lease_heartbeat_added': False, 'readiness_budgets_changed': False}
    done = threading.Event()
    def progress():
        while not done.wait(10):
            print('One captured no-agent readiness trace is active; original admission and watchdog budgets remain enforced.', flush=True)
    worker = threading.Thread(target=progress, daemon=True)
    worker.start()
    child_stdout = None
    try:
        result = subprocess.run(child_command(path), stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=240, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
        if len(result.stdout) > 65536 or len(result.stderr) > 65536:
            raise RuntimeError('outside_probe_output_limit')
        record['child_exit_code'] = result.returncode
        record['child_stderr_bytes'] = len(result.stderr)
        # Raw stderr is deliberately excluded. Per-attempt categories carry
        # the useful distinction without private paths, keys or command text.
        if result.returncode == 0:
            child_stdout = result.stdout
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        record['trace_error'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else type(error).__name__
    finally:
        done.set()
        worker.join(timeout=1)
        try:
            raw = path.read_bytes()
            events, partial = complete_trace_prefix(raw)
            record['events'] = events
            record['partial_last_trace_write'] = partial
            # A timed-out child may not reach its finally. Reuse only the exact
            # creation IDs carried by the protected observer, never all fleets.
            owned = [event['run_id'] for event in events if event['phase'] == 'created']
            control = None
            try:
                if owned:
                    control = supervisor.Supervisor()
                    record['cleanup'] = {run: {'status': control.cleanup(run)['status']} for run in owned}
            finally:
                if control:
                    control.firewall.close()
            if child_stdout is not None:
                record['standalone_scenario'] = scenario_receipt(child_stdout, owned, support.PACK)
            record['normal_after'] = normal()
            record['resources_after'] = resource_snapshot()
            record['full_watchdog_receipt_changed'] = gate_hash() != gate_before
            record['registered_files_after'] = support.verify_registered()
            record['same_policy_source_after'] = record['policy_files'] == {
                name: hashlib.sha256((INSTALL / name).read_bytes()).hexdigest()
                for name in supervisor.WATCHDOG_POLICY_FILES}
            record['window_after'] = window.state().get('status')
            record['active_fleet_after'] = any(store.read(p.name)['status'] == 'active' for p in store.root.iterdir() if p.is_dir())
        except (OSError, ValueError, RuntimeError) as error:
            record['finalization_error'] = type(error).__name__
        finally:
            atomic_json(report, record)
            report.chmod(0o644)
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                path.unlink()
            print('Sanitized readiness trace: ' + str(report), flush=True)
    if (record.get('child_exit_code') != 0 or record.get('trace_error') or record.get('finalization_error')
            or record.get('active_fleet_after') or record.get('window_after') != 'closed'
            or record.get('full_watchdog_receipt_changed') or not record.get('same_policy_source_after')
            or not record.get('cleanup') or any(item['status'] != 'ok' for item in record['cleanup'].values())):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
