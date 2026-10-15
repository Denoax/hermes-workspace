#!/usr/bin/python3
"""Outside native observer of actual no-agent VM deadline/crash termination.

Fixed protected operations only. Reduces a lab lease or signals only an exact
owned VM/supervisor pidfd; never changes normal services or exposes this to guests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
sys.dont_write_bytecode = True
import time

SELF = Path('/usr/local/lib/mani-vmlab-setup/watchdog_probe.py')
INSTALL = Path('/usr/local/lib/mani-vmlab')
REGISTER = SELF.with_name('runtime-installed.json')
STATE = Path('/var/lib/mani-vmlab-setup')
MODES = ('absolute_deadline', 'heartbeat_loss', 'VM_crash', 'owner_crash', 'supervisor_hang')


def protected(path):
    info = path.lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
        raise PermissionError('protected_probe_source_required')


def systemctl(*args):
    return subprocess.check_output(['/usr/bin/systemctl', *args], stdin=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, timeout=15,
                                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_protected_outside_probe_only')
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=(*MODES, 'all'))
    mode = parser.parse_args().operation
    for path in (SELF, SELF.parent, INSTALL, REGISTER):
        protected(path)
    registered = json.loads(REGISTER.read_text())
    for item in registered['installed_files']:
        path = Path(item['path'])
        protected(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('runtime_changed_requalify_source')
    if mode == 'all':
        results = []
        for operation in MODES:
            outcome = subprocess.run(['/usr/bin/python3', '-I', str(SELF), operation],
                                     stdin=subprocess.DEVNULL, capture_output=True, timeout=240,
                                     env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            if len(outcome.stdout) > 65536 or len(outcome.stderr) > 65536:
                raise RuntimeError('outside_probe_output_limit')
            if outcome.returncode:
                results.append({'operation': operation, 'status': 'failed', 'exit': outcome.returncode,
                                'error': outcome.stderr.decode(errors='replace')[-1500:]})
            else:
                results.append(json.loads(outcome.stdout))
        passed = all(row.get('all_three_VMs_exited') is True and row.get('cleanup_status') == 'ok' for row in results)
        receipt = {'results': results, 'all_passed': passed,
            'source_pack_sha256': json.loads(Path('/etc/mani-vmlab/config.json').read_text())['source_pack_sha256'],
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
        sys.path.insert(0, str(INSTALL))
        import supervisor
        receipt['policy_files'] = {name:hashlib.sha256((INSTALL/name).read_bytes()).hexdigest()
                                  for name in supervisor.WATCHDOG_POLICY_FILES}
        from lab.state import atomic_json
        atomic_json(STATE/'VM-watchdog-qualified.json', receipt)
        print(json.dumps(receipt))
        if not passed:
            raise SystemExit(2)
        return
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(INSTALL))
    import supervisor
    supervisor.initialize_imports()
    from lab.process import open_owned, identity
    from lab.state import atomic_json
    control = supervisor.Supervisor()
    run_id = control.active_run()
    if not run_id:
        created = control.provision()
        if created['status'] != 'ok':
            raise RuntimeError('fresh_no_agent_boot_failed:'+json.dumps(created))
        run_id = created['run_id']
    manifest = control.store.read(run_id)
    if manifest['execution_kind'] != 'real_no_agent_VM' or not manifest.get('control_verified'):
        raise RuntimeError('pinned_no_agent_control_required')
    if control.configuration['agents_enabled'] is not False:
        raise RuntimeError('no_agent_tests_only')
    records = {r['role']: r for r in manifest['processes'] if r['role'] in ('controller', 'worker_a', 'worker_b')}
    if set(records) != {'controller', 'worker_a', 'worker_b'}:
        raise RuntimeError('exact_live_fleet_required')
    descriptors = {}
    daemon_fd = None
    stopped_daemon = False
    try:
        for role, record in records.items():
            descriptor = open_owned(record)
            if descriptor is None or select.select([descriptor], [], [], 0)[0]:
                if descriptor is not None:
                    os.close(descriptor)
                raise RuntimeError('owned_VM_not_live_before_probe')
            descriptors[role] = descriptor
        daemon_pid = int(systemctl('show', 'mani-vmlab-supervisor.service', '-p', 'MainPID', '--value'))
        daemon_record = identity(daemon_pid)
        daemon_fd = open_owned(daemon_record)
        if daemon_fd is None or str(INSTALL/'supervisor.py').encode() not in Path(f'/proc/{daemon_pid}/cmdline').read_bytes().split(b'\0'):
            raise RuntimeError('owned_protected_supervisor_required')
        observer_group = Path('/proc/self/cgroup').read_text()
        observed_groups = [Path(f'/proc/{r["pid"]}/cgroup').read_text() for r in records.values()]
        observed_groups.append(Path(f'/proc/{daemon_pid}/cgroup').read_text())
        outside = all(group != observer_group for group in observed_groups)
        if not outside:
            raise RuntimeError('observer_must_be_outside_all_owned_workload_cgroups')
        start = time.monotonic()
        if mode == 'absolute_deadline':
            control.store.mutate(run_id, lambda m: m.update(deadline=start+2, heartbeat=start, heartbeat_timeout=30))
        elif mode == 'heartbeat_loss':
            control.store.mutate(run_id, lambda m: m.update(deadline=start+30, heartbeat=start, heartbeat_timeout=2))
        elif mode == 'VM_crash':
            signal.pidfd_send_signal(descriptors['controller'], signal.SIGKILL)
        elif mode == 'owner_crash':
            stopped_daemon = True
            signal.pidfd_send_signal(daemon_fd, signal.SIGKILL)
        else:
            stopped_daemon = True
            signal.pidfd_send_signal(daemon_fd, signal.SIGSTOP)
        exits = {}
        remaining = set(descriptors)
        budget = 20 if mode == 'supervisor_hang' else 8
        while remaining and time.monotonic()-start < budget:
            ready, _, _ = select.select([descriptors[role] for role in remaining], [], [], 0.1)
            for role in list(remaining):
                if descriptors[role] in ready:
                    exits[role] = time.monotonic()-start
                    remaining.remove(role)
        evidence = {'operation': mode, 'evidence_kind': 'actual_KVM_process_pidfd_observer', 'run_id': run_id,
                    'source_pack_sha256': control.configuration['source_pack_sha256'],
                    'guest_agents_enabled': False, 'VM_exit_after_trigger_seconds': exits,
                    'all_three_VMs_exited': not remaining, 'remaining_VM_roles': sorted(remaining),
                    'observer_outside_supervisor_and_VM_cgroups': outside,
                    'system_manager_supervisor_result': systemctl('show', 'mani-vmlab-supervisor.service', '-p', 'Result', '--value').decode().strip()}
        atomic_json(STATE/(mode+'-'+run_id+'.json'), evidence)
    finally:
        if stopped_daemon and daemon_fd is not None:
            # A hung owner is restored/retired by exact pidfd, never by PID name.
            if not select.select([daemon_fd], [], [], 0)[0]:
                try:
                    signal.pidfd_send_signal(daemon_fd, signal.SIGCONT)
                    signal.pidfd_send_signal(daemon_fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # The manager completed termination between the signals.
        control.stop(run_id, 'outside_probe_teardown')
        cleanup = control.cleanup(run_id)
        if stopped_daemon:
            systemctl('start', 'mani-vmlab-supervisor.service')
        for descriptor in descriptors.values():
            os.close(descriptor)
        if daemon_fd is not None:
            os.close(daemon_fd)
    evidence['cleanup_status'] = cleanup['status']
    evidence['cleanup_refused'] = cleanup['refused']
    atomic_json(STATE/(mode+'-'+run_id+'.json'), evidence)
    print(json.dumps(evidence))
    if not evidence['all_three_VMs_exited'] or cleanup['status'] != 'ok':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
