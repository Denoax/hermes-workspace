#!/usr/bin/python3
"""Fixed no-agent boot diagnostics; never qualifies, changes policy or infers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

sys.dont_write_bytecode = True
SELF = Path('/usr/local/lib/mani-vmlab-setup/diagnose_guest_boot.py')
SETUP = SELF.parent
INSTALL = Path('/usr/local/lib/mani-vmlab')
REGISTER = SETUP / 'runtime-installed.json'
CONFIG = Path('/etc/mani-vmlab/config.json')
PUBLIC = Path('/var/lib/mani-vmlab-review')
PACK = '766142c86543e30b61d7667cc5846ea3c61974a644903ca3ba2b3c0306911d4b'
RECOVERY_SHA = '666c82c6efcf8b89d37d20aade6ea4eca06405a625613946e04eb62b57cbc584'
ROLES = ('controller', 'worker_a', 'worker_b')

# The child reads no conversation content and has only the desktop user's rights.
IDLE_PROBE = '''from pathlib import Path
import json,os,sqlite3,stat
p=Path('/home/mani/HermesLab/catalog.sqlite3')
i=p.lstat()
if not stat.S_ISREG(i.st_mode) or i.st_uid!=1000 or i.st_mode&0o077 or i.st_nlink!=1:
 raise RuntimeError('private_production_catalog_required')
with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=1) as c:
 active=c.execute("SELECT count(*) FROM chat_runs WHERE state NOT IN ('completed','cancelled','failed')").fetchone()[0]
print(json.dumps({'no_active_text_turn':active==0}))
'''


def protected(path, directory=False):
    path = Path(path)
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('protected_diagnostic_parent_required')
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise PermissionError('protected_diagnostic_file_required')
    return info


def read_protected(path, maximum=4 * 1024 * 1024):
    info = protected(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or opened.st_size > maximum:
            raise RuntimeError('bounded_protected_diagnostic_input_required')
        raw = source.read(maximum + 1)
        if len(raw) > maximum:
            raise RuntimeError('diagnostic_input_limit')
        return raw, opened


def verify_registered():
    raw, _ = read_protected(REGISTER)
    register = json.loads(raw)
    entries = register.get('installed_files')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 512:
        raise RuntimeError('fixed_runtime_register_required')
    verified = set()
    for item in entries:
        path = Path(item['path'])
        if not path.is_absolute() or '..' in path.parts or path in verified:
            raise RuntimeError('registered_path_required')
        installed, info = read_protected(path)
        if ((info.st_dev, info.st_ino) != (item['device'], item['inode'])
                or hashlib.sha256(installed).hexdigest() != item['sha256']):
            raise RuntimeError('registered_runtime_drift')
        verified.add(path)
    required = {'supervisor.py', 'vm_service.py', 'proxy.py', 'evidence.py',
                'lab/state.py', 'lab/process.py', 'lab/transport.py',
                'guest/qualify.py', 'guest/bootstrap.py'}
    if not {INSTALL / name for name in required} <= verified:
        raise RuntimeError('required_diagnostic_runtime_not_registered')
    config, _ = read_protected(CONFIG)
    settings = json.loads(config)
    if settings.get('source_pack_sha256') != PACK or settings.get('agents_enabled') is not False:
        raise RuntimeError('reviewed_runtime_pack_required')
    recovery, _ = read_protected(SETUP / 'recovery.py')
    if hashlib.sha256(recovery).hexdigest() != RECOVERY_SHA:
        raise RuntimeError('reviewed_normal_verifier_required')
    return len(verified)


def require_idle_text():
    result = subprocess.run(
        ['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--init-groups',
         '/usr/bin/python3', '-I', '-c', IDLE_PROBE],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=5,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    if (result.returncode or len(result.stdout) > 1024
            or json.loads(result.stdout) != {'no_active_text_turn': True}):
        raise RuntimeError('finish_production_text_owner_before_diagnostic')
    with urllib.request.urlopen('http://127.0.0.1:8080/slots', timeout=2) as response:
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise RuntimeError('normal_slot_probe_unavailable')
    slots = json.loads(raw)
    if not slots or any(slot.get('is_processing') is not False for slot in slots):
        raise RuntimeError('normal_inference_active_or_unverified')


def failure_category(error):
    """Never return raw stderr, command arguments, keys or exception messages."""
    text = getattr(error, 'private_stderr', '').lower()
    for needles, category in (
        (('host key verification failed', 'remote host identification has changed'), 'host_key_verification_failed'),
        (('permission denied (publickey',), 'public_key_authentication_failed'),
        (('no matching host key type', 'no matching key exchange method'), 'ssh_algorithm_mismatch'),
        (('connection refused',), 'connection_refused'),
        (('connection timed out', 'operation timed out'), 'connection_timeout'),
        (('no route to host', 'network is unreachable'), 'route_unavailable'),
        (('connection reset',), 'ssh_handshake_reset'),
        (('connection closed', 'closed by remote host'), 'ssh_handshake_closed'),
        (('bad configuration option', 'unsupported option'), 'ssh_client_configuration'),
        (('fixed_native_proxy_only',), 'proxy_contract_refused'),
        (('filenotfounderror',), 'proxy_path_missing'),
        (('permissionerror',), 'proxy_permission_denied'),
        (('traceback',), 'helper_or_proxy_exception'),
    ):
        if any(needle in text for needle in needles):
            return category
    if isinstance(error, TimeoutError):
        return 'bounded_transport_timeout'
    if isinstance(error, ValueError):
        return 'invalid_bounded_guest_reply'
    if getattr(error, 'exit_code', None) is not None:
        return 'unclassified_transport_failure'
    return 'native_transport_error'


def run_probe(control, normal_check, idle_check, window_check, record, clock=time.monotonic):
    """Exercise only the unchanged no-agent provision and exact cleanup paths."""
    done = threading.Event()
    owner = {'run': None}
    heartbeat_errors = []
    start = clock()
    original_ssh = control.ssh

    def created(run_id):
        if not re.fullmatch(r'[0-9a-f]{32}', run_id):
            raise RuntimeError('owned_diagnostic_run_required')
        owner['run'] = run_id

    def ssh(run_id, role, operation, request=None):
        if run_id != owner['run'] or role not in ROLES or operation != 'health' or request is not None:
            raise RuntimeError('fixed_no_agent_health_only')
        attempt = {'role': role, 'elapsed_seconds': round(clock() - start, 3)}
        try:
            result = original_ssh(run_id, role, operation)
            expected = {'healthy': True, 'role': role, 'agents_enabled': False}
            attempt.update(transport_answered=True, healthy=result == expected,
                           category='ready' if result == expected else 'runtime_installation_not_ready'
                           if result == {**expected, 'healthy': False} else 'unexpected_health_reply')
            return result
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            attempt.update(transport_answered=False, healthy=False, category=failure_category(error))
            raise
        finally:
            if len(record['attempts']) < 180:
                record['attempts'].append(attempt)

    def beat():
        ticks = 0
        while not done.wait(5):
            run_id = owner['run']
            if run_id:
                try:
                    control.store.heartbeat(run_id)
                except (OSError, ValueError, RuntimeError):
                    heartbeat_errors.append('owned_lease_heartbeat_unavailable')
            ticks += 1
            if ticks % 2 == 0:
                print('No-agent boot diagnostic active; existing readiness budget and watchdogs remain enforced.', flush=True)

    thread = None
    control.ssh = ssh
    try:
        record['normal_before'] = normal_check()
        if control.active_run() or window_check():
            raise RuntimeError('finish_existing_fleet_or_window_before_diagnostic')
        idle_check()
        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        result = control.provision(on_created=created)
        record['provision_status'] = 'ok' if result.get('status') == 'ok' else 'failed'
        error = str(result.get('error', ''))
        record['failure_code'] = error if re.fullmatch(r'pinned_guest_control_not_ready:(controller|worker_a|worker_b)', error) else None
        record['boot_ready'] = result.get('status') == 'ok'
    finally:
        done.set()
        if thread:
            thread.join(timeout=6)
        control.ssh = original_ssh
        if owner['run']:
            try:
                cleanup = control.cleanup(owner['run'])
                record['cleanup'] = {'status': cleanup['status'], 'refused_count': len(cleanup.get('refused', []))}
            except (OSError, ValueError, RuntimeError):
                record['cleanup'] = {'status': 'failed', 'code': 'exact_owned_cleanup_unconfirmed'}
        else:
            record['cleanup'] = {'status': 'not_needed', 'no_fleet_created': True}
        record['normal_after'] = normal_check()
        record['heartbeat_errors'] = sorted(set(heartbeat_errors))
        record['total_seconds'] = round(clock() - start, 3)
    return record['boot_ready'] and record['cleanup']['status'] == 'ok'


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF or sys.argv[1:] != ['diagnose']:
        raise SystemExit('fixed_protected_guest_boot_diagnostic_only')
    protected(SELF)
    protected(SETUP, directory=True)
    protected(INSTALL, directory=True)
    protected(PUBLIC, directory=True)
    verified = verify_registered()
    sys.path.insert(0, str(INSTALL))
    import supervisor
    import window
    from lab.state import atomic_json
    spec = importlib.util.spec_from_file_location('diagnostic_normal_verifier', SETUP / 'recovery.py')
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    report = PUBLIC / ('guest-boot-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8] + '.json')
    record = {'evidence_kind': 'protected_no_agent_boot_diagnostic', 'source_pack_sha256': PACK,
              'verified_registered_files': verified, 'attempts': [], 'boot_ready': False,
              'qualification_granted': False, 'model_inference_started': False,
              'readiness_budget_changed': False, 'host_packages_changed': False}
    control = None
    success = False
    def interrupt(_number, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        if window.state().get('status') != 'closed':
            raise RuntimeError('finish_existing_window_before_diagnostic')
        require_idle_text()
        control = supervisor.Supervisor()
        success = run_probe(control, recovery.NativeServices().verify_normal_profile,
                            require_idle_text, lambda: window.state().get('status') != 'closed', record)
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as error:
        record['diagnostic_error'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else type(error).__name__
    finally:
        if control:
            control.firewall.close()
        atomic_json(report, record)
        report.chmod(0o644)
        print('Sanitized no-agent diagnostic: ' + str(report), flush=True)
    raise SystemExit(0 if success else 2)


if __name__ == '__main__':
    main()
