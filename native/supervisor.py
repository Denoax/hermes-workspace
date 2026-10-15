#!/usr/bin/python3
"""Fixed native no-agent fleet supervisor. Not a root agent or generic shell API.

Installed source, config and runtime root must be root-owned. The only operator
peer is the existing desktop UID; guests have neither this socket nor that UID.
Guest/model execution remains gated separately from no-agent boot/qualification.
"""
import hashlib
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import uuid
sys.dont_write_bytecode=True

INSTALL = Path('/usr/local/lib/mani-vmlab')
DATA = Path('/home/mani-vmlab-data')
CONFIG = Path('/etc/mani-vmlab/config.json')
OPERATOR_UID = 1000
SOCKET = Path('/run/mani-vmlab/control.sock')
WATCHDOG_POLICY_FILES = ('supervisor.py', 'vm_service.py', 'guest/qualify.py',
                         'guest/bootstrap.py', 'lab/state.py', 'lab/process.py')


def protected(path):
    info = Path(path).lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
        raise PermissionError('native_installation_must_be_protected')


def initialize_imports():
    protected(INSTALL)
    protected(INSTALL/'supervisor.py')
    protected(CONFIG)
    sys.path.insert(0, str(INSTALL))


def execute(argv, seconds=15):
    from lab.transport import bounded_process
    try:
        return bounded_process(argv, b'', seconds)
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        raise RuntimeError('native_operation_failed:' + Path(argv[0]).name) from error


class Supervisor:
    def __init__(self):
        from lab.state import RunStore
        self.store = RunStore(DATA/'runs')
        self.configuration = json.loads(CONFIG.read_text())
        self.vm_account = pwd.getpwnam('mani-vmlab-vm')
        self.mutation = threading.Lock()
        self.shutdown = threading.Event()
        self.sessions = {}
        self.backend_arm = None
        from evidence import PinnedImage, Firewall
        self.image_pin = PinnedImage(DATA/'bases/noble.qcow2', self.configuration['image_sha256'])
        self.image_pin.verify()
        self.firewall = Firewall()
        self.firewall.start_monitor()
        self.firewall.verify()
        self.workspace_jobs=None
        self.jobs_initialization=threading.Lock()
        from text_chat import TextChat
        self.text_chat=TextChat(self)

    def active_run(self):
        for directory in sorted(self.store.root.iterdir()):
            if directory.is_dir():
                manifest = self.store.read(directory.name)
                if manifest['status'] == 'active':
                    return directory.name
        return None

    def state(self):
        run_id = self.active_run()
        facts = {'protected_supervisor': True, 'signed_base_image': False, 'installed_confinement': False,
                 'owned_fleet_active': False, 'control_transport': False, 'VM_confinement_qualified': False,
                 'network_qualified': False, 'VM_watchdog_qualified': False}
        import window
        facts['inference_window_active'] = window.active()
        import backend
        facts['pinned_model_and_backend_artifacts_current']=backend.artifacts_current()
        facts['host_firewall_qualified'] = self.firewall.current()
        receipt_path = Path('/var/lib/mani-vmlab-setup/VM-watchdog-qualified.json')
        if receipt_path.exists():
            protected(receipt_path)
            receipt = json.loads(receipt_path.read_text())
            facts['VM_watchdog_qualified'] = (receipt.get('all_passed') is True
                and set(receipt.get('policy_files', {})) == set(WATCHDOG_POLICY_FILES)
                and all(hashlib.sha256((INSTALL/name).read_bytes()).hexdigest() == receipt['policy_files'][name]
                        for name in WATCHDOG_POLICY_FILES)
                and receipt.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        facts['signed_base_image'] = self.image_pin.current()
        facts['installed_confinement'] = all((DATA/'runtime-root'/name).is_dir() for name in ('usr', 'vm', 'bases', 'control'))
        if run_id:
            manifest = self.store.read(run_id)
            from lab.process import open_owned
            live = []
            for record in manifest['processes']:
                if record['role'] not in ('controller', 'worker_a', 'worker_b'):
                    continue
                fd = open_owned(record)
                if fd is not None:
                    import select
                    live.append(not bool(select.select([fd], [], [], 0)[0]))
                    os.close(fd)
                else:
                    live.append(False)
            facts['owned_fleet_active'] = len(live) == 3 and all(live)
            facts['control_transport'] = facts['owned_fleet_active'] and manifest.get('control_verified') is True
            # Qualification is tied to this exact still-active inventory, not a guest marker.
            qualification = manifest.get('qualification', {})
            facts['VM_confinement_qualified'] = facts['owned_fleet_active'] and qualification.get('confinement') is True
            facts['network_qualified'] = facts['owned_fleet_active'] and qualification.get('network') is True
            facts['guest_Hermes_installed'] = facts['owned_fleet_active'] and qualification.get('Hermes_installed') is True
            proofs = manifest.get('backend_qualification', {})
            facts['normal_backend_qualified'] = proofs.get('normal', {}).get('confined') is True
            facts['candidate_backend_qualified'] = proofs.get('abliterated', {}).get('confined') is True
            facts['Hermes_routing_qualified'] = manifest.get('Hermes_routing_qualified') is True
        active=facts['inference_window_active']
        manifest=self.store.read(run_id) if run_id else {}
        jobs=manifest.get('workspace_jobs',{})
        current=next((job for job in jobs.values() if job.get('state') in ('starting','running','validating','cancelling')),None)
        return {'status': 'ok', 'broker_version':1, 'observed_facts': facts, 'run_id': run_id,
                'guest_agents_enabled': bool(current) or manifest.get('qualification_fixture_active') is True or manifest.get('Hermes_routing_qualified') is True,
                'runtime_stage': 'protocol_fixture' if manifest.get('qualification_fixture_active') else current['state'] if current else 'qualified' if facts['control_transport'] else 'window_open' if active else 'closed',
                'inference_integration': 'qualified_main' if manifest.get('Hermes_routing_qualified') else 'not_yet_observed_in_current_fleet',
                'window_status': window.state().get('status','closed'),
                'remaining_seconds': max(0,window.state().get('deadline',time.monotonic())-time.monotonic()) if active else 0,
                'status_cost': {'full_image_hashes':self.image_pin.full_hashes,'firewall_inspections':self.firewall.inspections},
                'ledger':'native_root_owned', 'tool_profile':'guest_scoped_v1' if self.configuration.get('workspace_api')==1 else 'not_installed'}

    def credentials(self, run_id, vm_id):
        directory = self.store.directory(run_id)
        private = directory/(vm_id+'.key')
        public = directory/(vm_id+'.key.pub')
        execute(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-C', 'mani-vmlab', '-N', '', '-f', str(private)])
        private.chmod(0o600)
        self.store.register_resource(run_id, private.name)
        self.store.register_resource(run_id, public.name)
        host_key = directory/(vm_id+'-host.key')
        execute(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-C', 'mani-vmlab', '-N', '', '-f', str(host_key)])
        self.store.register_resource(run_id, host_key.name)
        self.store.register_resource(run_id, host_key.name+'.pub')
        return public.read_text().strip(), host_key

    def seed(self, run_id, vm_id):
        directory = self.store.directory(run_id)
        public, host_key = self.credentials(run_id, vm_id)
        # This dedicated guest key and all included code are specific lab artifacts.
        helper = (INSTALL/'guest/qualify.py').read_text()
        ssh = '''PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers lab
AllowAgentForwarding no
AllowTcpForwarding remote
PermitListen 127.0.0.1:18081
AllowStreamLocalForwarding no
X11Forwarding no
PermitTTY no
ForceCommand /usr/bin/python3 -I /opt/mani-vmlab/qualify.py
'''
        document = {'users': [{'name': 'lab', 'lock_passwd': True, 'sudo': False,
                              'ssh_authorized_keys': [public]}], 'disable_root': True, 'ssh_pwauth': False,
                    'ssh_deletekeys': True,
                    'ssh_keys': {'ed25519_private': host_key.read_text(),
                                 'ed25519_public': Path(str(host_key)+'.pub').read_text()},
                    'write_files': [
                        {'path': '/opt/mani-vmlab/qualify.py', 'permissions': '0755', 'owner': 'root:root', 'content': helper},
                        {'path': '/etc/mani-vmlab/guest.json', 'permissions': '0644', 'owner': 'root:root',
                         'content': json.dumps({'role': vm_id, 'agents_enabled': False})},
                        {'path': '/etc/ssh/sshd_config.d/10-mani-vmlab.conf', 'permissions': '0644', 'owner': 'root:root', 'content': ssh}],
                    'runcmd': [['systemctl', 'restart', 'ssh']], 'package_update': False, 'package_upgrade': False}
        if self.configuration.get('runtime_zip_sha256'):
            marker = {'role': vm_id, 'agents_enabled': False,
                      'Hermes_revision': self.configuration['Hermes_revision'],
                      'runtime_zip_sha256': self.configuration['runtime_zip_sha256']}
            if self.configuration.get('compiler_zip_sha256'):
                marker['compiler_zip_sha256']=self.configuration['compiler_zip_sha256']
            document['write_files'][1]['content'] = json.dumps(marker)
            for name in ('bootstrap.py', 'solve.py', 'json_limits.py','workspace_job.py','run_code.py','workspace_contract.py','lifecycle_probe.py','recovery.py'):
                document['write_files'].append({'path': '/opt/mani-vmlab/'+name,
                    'permissions': '0644', 'owner': 'root:root', 'content': (INSTALL/'guest'/name).read_text()})
            document['runcmd'] = [['mkdir', '-p', '/mnt/mani-artifacts'],
                ['mount', '-o', 'ro,nosuid,nodev,noexec', '/dev/vdc', '/mnt/mani-artifacts'],
                ['/usr/bin/python3', '-I', '/opt/mani-vmlab/bootstrap.py'], ['systemctl', 'restart', 'ssh']]
        user_data = directory/(vm_id+'-user-data')
        user_data.write_text('#cloud-config\n'+json.dumps(document))
        user_data.chmod(0o600)
        self.store.register_resource(run_id, user_data.name)
        seed = directory/(vm_id+'.seed')
        execute(['/usr/bin/cloud-localds', str(seed), str(user_data)])
        seed.chmod(0o440)
        os.chown(seed, 0, self.vm_account.pw_gid)
        self.store.register_resource(run_id, seed.name)
        host_public = Path(str(host_key)+'.pub').read_text().strip()
        known = directory/(vm_id+'.known_hosts')
        known.write_text('mani-vmlab-'+vm_id+' '+host_public+'\n')
        known.chmod(0o600)
        self.store.register_resource(run_id, known.name)

    def ssh(self, run_id, vm_id, operation, request=None):
        from lab.transport import bounded_process
        from starter.json_limits import bounded_json
        from vm_service import unit_name
        unit_name(run_id, vm_id)
        directory = self.store.directory(run_id)
        proxy = f'/usr/bin/python3 -I {INSTALL}/proxy.py {directory}/{vm_id}-control/ssh.sock'
        command = ['/usr/bin/ssh', '-F', '/dev/null', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                   '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=mani-vmlab-'+vm_id,
                   '-o', 'UserKnownHostsFile='+str(directory/(vm_id+'.known_hosts')),
                   '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ForwardAgent=no',
                   '-o', 'ClearAllForwardings=yes', '-o', 'ConnectTimeout=3',
                   '-o', 'ProxyCommand='+proxy, '-i', str(directory/(vm_id+'.key')), 'lab@localhost']
        data = {'operation': operation}
        if request is not None:
            data['request'] = request
        seconds=100 if operation=='lifecycle_probe' else 420 if operation=='workspace' else 35 if operation=='validate' else 160 if request is not None else 12
        output = bounded_process(command, json.dumps(data).encode(), seconds)
        return bounded_json(output)

    def provision(self, on_created=None):
        from lab.state import atomic_json
        from lab.process import identity
        from vm_service import VM_IDS, service_text, unit_name
        if self.active_run():
            raise RuntimeError('owned_fleet_already_active')
        self.image_pin.verify()
        self.firewall.verify()
        state = self.state()
        if not state['observed_facts']['signed_base_image'] or not state['observed_facts']['installed_confinement']:
            raise RuntimeError('native_prerequisites_missing')
        if not os.access('/dev/kvm', os.R_OK|os.W_OK):
            raise RuntimeError('KVM_unavailable')
        available = next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        if available < 14*1024**3:
            raise RuntimeError('desktop_memory_reserve_insufficient')
        run_id = self.store.create(ttl=1800, heartbeat_timeout=45, max_calls=48, max_tokens=49152)
        self.store.mutate(run_id, lambda m: m.update(execution_kind='real_no_agent_VM', units=[], vm_uuids={}, unit_files=[], control_dirs=[]))
        try:
            if on_created is not None:
                on_created(run_id)
            for vm_id in VM_IDS:
                directory = self.store.directory(run_id)
                self.seed(run_id, vm_id)
                disk = directory/(vm_id+'.qcow2')
                disk.touch(mode=0o600)
                os.chown(disk, self.vm_account.pw_uid, self.vm_account.pw_gid)
                self.store.register_resource(run_id, disk.name)
                control = directory/(vm_id+'-control')
                control.mkdir(mode=0o770)
                os.chown(control, 0, self.vm_account.pw_gid)
                control.chmod(0o770)
                info = control.stat()
                self.store.mutate(run_id, lambda m: m['control_dirs'].append({'name': control.name, 'device': info.st_dev, 'inode': info.st_ino}))
                vm_uuid = str(uuid.uuid4())
                unit = unit_name(run_id, vm_id)
                text = service_text(run_id, vm_id, vm_uuid, max(1, int(self.store.read(run_id)['deadline']-time.monotonic())),
                                    artifacts=bool(self.configuration.get('runtime_zip_sha256')))
                path = Path('/run/systemd/system')/unit
                if path.exists():
                    raise RuntimeError('preserve_existing_unit')
                path.write_text(text)
                path.chmod(0o644)
                info = path.stat()
                self.store.mutate(run_id, lambda m: m['unit_files'].append({'name': unit, 'device': info.st_dev, 'inode': info.st_ino,
                                                                          'sha256': hashlib.sha256(text.encode()).hexdigest()}))
                self.store.mutate(run_id, lambda m: (m['units'].append(unit), m['vm_uuids'].update({vm_id: vm_uuid})))
                execute(['/usr/bin/systemctl', 'daemon-reload'])
                execute(['/usr/bin/systemctl', 'start', unit], seconds=30)
                pid = int(execute(['/usr/bin/systemctl', 'show', unit, '-p', 'MainPID', '--value']).strip())
                record = {**identity(pid), 'role': vm_id}
                cmdline = Path(f'/proc/{pid}/cmdline').read_bytes()
                if vm_uuid.encode() not in cmdline.split(b'\0'):
                    raise RuntimeError('owned_VM_UUID_not_in_process')
                self.store.mutate(run_id, lambda m: m['processes'].append(record))
                # Pin the control socket before SSH readiness; failed boots must
                # still have registered teardown artifacts.
                for _ in range(40):
                    try:
                        self.register_socket(run_id, vm_id)
                        break
                    except FileNotFoundError:
                        self.shutdown.wait(0.05)
                else:
                    raise RuntimeError('owned_control_socket_missing')
            for vm_id in VM_IDS:
                ready = False
                for _ in range(60):
                    if self.store.mutate(run_id, lambda m: self.store.active(m)):
                        raise RuntimeError('lease_expired_during_boot')
                    self.store.heartbeat(run_id)
                    try:
                        result = self.ssh(run_id, vm_id, 'health')
                        ready = result == {'healthy': True, 'role': vm_id, 'agents_enabled': False}
                    except (OSError, ValueError, RuntimeError, TimeoutError):
                        ready = False
                    if ready:
                        break
                    self.shutdown.wait(0.5)
                if not ready:
                    raise RuntimeError('pinned_guest_control_not_ready:'+vm_id)
                self.register_socket(run_id, vm_id)
            self.store.mutate(run_id, lambda m: m.update(control_verified=True))
            self.sessions[run_id] = time.monotonic()
            return {'status': 'ok', 'run_id': run_id, 'real_VM_boot': True, 'guest_agents_enabled': False,
                    'control_transport': 'pinned_SSH_over_owned_UNIX_socket'}
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.stop(run_id, 'provision_failed')
            cleanup = self.cleanup(run_id)
            return {'status': 'failed', 'run_id': run_id, 'error': str(error), 'cleanup': cleanup,
                    'guest_agents_enabled': False}

    def register_socket(self, run_id, vm_id):
        path = self.store.directory(run_id)/(vm_id+'-control/ssh.sock')
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != self.vm_account.pw_uid:
            raise RuntimeError('unexpected_control_socket_owner_or_type')
        def pin(manifest):
            row = next(row for row in manifest['control_dirs'] if row['name'] == vm_id+'-control')
            parent = path.parent.lstat()
            if (parent.st_dev, parent.st_ino) != (row['device'], row['inode']):
                raise RuntimeError('owned_control_directory_changed')
            if 'socket_inode' in row and (info.st_dev, info.st_ino) != (row['socket_device'], row['socket_inode']):
                raise RuntimeError('pinned_socket_changed')
            row.update(socket_device=info.st_dev, socket_inode=info.st_ino)
        self.store.mutate(run_id, pin)

    @contextmanager
    def lifecycle(self, run_id):
        # Serialize complete stop/cleanup transactions across daemon and outside
        # recovery probes; manifest locks alone cover individual writes only.
        with (self.store.directory(run_id)/'lifecycle.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def stop(self, run_id, reason='operator_stop'):
        with self.lifecycle(run_id):
            return self._stop(run_id, reason)

    def _stop(self, run_id, reason):
        from vm_service import unit_name, VM_IDS
        from lab.process import stop_owned
        self.store.revoke(run_id, reason)
        manifest = self.store.read(run_id)
        if manifest.get('owns_backend'):
            import backend
            backend.stop()
            self.backend_arm = None
        allowed = {unit_name(run_id, vm_id) for vm_id in VM_IDS}
        # Signal exact identities before any system-manager waits or evidence work.
        outcomes = stop_owned(self.store, run_id, grace=0)
        stop_failures = []
        for unit in manifest.get('units', []):
            if unit not in allowed:
                raise RuntimeError('invalid_registered_unit')
            try:
                execute(['/usr/bin/systemctl', 'stop', unit], seconds=5)
            except RuntimeError as error:
                stop_failures.append({'unit': unit, 'error': str(error)})
                # pidfd fallback still targets the recorded exact identity.
        return {'status': 'ok' if all(row['outcome'] != 'termination_unconfirmed' for row in outcomes) else 'failed',
                'reason': self.store.read(run_id)['reason'], 'outcomes': outcomes, 'systemd_stop_failures': stop_failures}

    def recover(self):
        # Reboot/restart never resumes an old lease or model job.
        for directory in self.store.root.iterdir():
            if directory.is_dir():
                self.stop(directory.name, 'supervisor_restart_revoked')

    def cleanup(self, run_id):
        with self.lifecycle(run_id):
            return self._cleanup(run_id)

    def _cleanup(self, run_id):
        from lab.process import stop_owned
        from vm_service import unit_name, VM_IDS
        stopped = self._stop(run_id, 'operator_cleanup')
        if stopped['status'] != 'ok':
            raise RuntimeError('owned_process_termination_unconfirmed')
        manifest = self.store.read(run_id)
        regular = self.store.cleanup(run_id, stop_owned)
        removed, refused = [], list(regular['refused'])
        for record in manifest.get('control_dirs', []):
            if record['name'] not in [vm_id+'-control' for vm_id in VM_IDS]:
                raise ValueError('invalid_registered_control_directory')
            path = self.store.directory(run_id)/record['name']
            if not path.exists():
                continue
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (record['device'], record['inode']):
                refused.append(record['name'])
                continue
            contents = list(path.iterdir())
            if contents:
                socket_path = path/'ssh.sock'
                if contents != [socket_path] or 'socket_inode' not in record:
                    refused.append(record['name'])
                    continue
                socket_info = socket_path.lstat()
                if not stat.S_ISSOCK(socket_info.st_mode) or (socket_info.st_dev, socket_info.st_ino) != (record['socket_device'], record['socket_inode']):
                    refused.append(record['name'])
                    continue
                socket_path.unlink()
            path.rmdir()
            removed.append(record['name'])
        for record in manifest.get('unit_files', []):
            if record['name'] not in [unit_name(run_id, vm_id) for vm_id in VM_IDS]:
                raise ValueError('invalid_registered_unit_file')
            path = Path('/run/systemd/system')/record['name']
            if not path.exists():
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (record['device'], record['inode']) or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                refused.append(record['name'])
                continue
            path.unlink()
            removed.append(record['name'])
        if removed:
            execute(['/usr/bin/systemctl', 'daemon-reload'])
        for unit in manifest.get('units', []):
            if unit not in [unit_name(run_id, vm_id) for vm_id in VM_IDS]:
                raise ValueError('invalid_registered_unit')
            # Remove only this run's failed unit state, never global failures.
            state = execute(['/usr/bin/systemctl', 'show', unit, '-p', 'ActiveState', '--value']).strip()
            if state == b'failed':
                execute(['/usr/bin/systemctl', 'reset-failed', unit])
        return {'status': 'ok' if not refused else 'failed', 'regular_files': regular,
                'removed_native_artifacts': removed, 'refused': refused, 'base_and_reports_preserved': True}

    def qualify(self, run_id):
        from lab.process import identity, open_owned
        from lab.transport import bounded_process, CommandFailure
        from lab.qualification import confinement_supported, network_supported
        from starter.json_limits import bounded_json
        import select
        evidence = {}
        manifest = self.store.read(run_id)
        if self.store.mutate(run_id, lambda m: self.store.active(m)) or not manifest.get('control_verified'):
            raise RuntimeError('active_pinned_control_required')
        for record in list(manifest['processes']):
            vm_id = record['role']
            if vm_id not in ('controller', 'worker_a', 'worker_b'):
                continue
            pid_fd = open_owned(record)
            if pid_fd is None:
                raise RuntimeError('owned_VM_inactive')
            namespace = None
            canary = None
            try:
                if select.select([pid_fd], [], [], 0)[0]:
                    raise RuntimeError('owned_VM_inactive')
                namespace = os.open(f'/proc/{record["pid"]}/ns/net', os.O_RDONLY)
                if identity(record['pid']) != {key: record[key] for key in ('pid', 'start_ticks', 'boot_id')}:
                    raise RuntimeError('owned_VM_identity_changed')
                root = Path(f'/proc/{record["pid"]}/root')
                status = Path(f'/proc/{record["pid"]}/status').read_text()
                values = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in status.splitlines() if ':' in line}
                group = execute(['/usr/bin/systemctl', 'show', f'mani-vmlab-{run_id}-{vm_id}.service', '-p', 'ControlGroup', '--value']).decode().strip()
                cgroup = Path('/sys/fs/cgroup')/group.lstrip('/')
                facts = {
                    'nonroot_dedicated_UID': int(values['Uid'].split()[0]) == self.vm_account.pw_uid != 0,
                    'private_network_namespace': os.fstat(namespace).st_ino != Path('/proc/self/ns/net').stat().st_ino,
                    'private_IPC_namespace': Path(f'/proc/{record["pid"]}/ns/ipc').stat().st_ino != Path('/proc/self/ns/ipc').stat().st_ino,
                    'personal_home_absent': not (root/'home/mani').exists(),
                    'Docker_socket_absent': not (root/'run/docker.sock').exists(),
                    'GPU_devices_absent': not (root/'dev/dri').exists() and not (root/'dev/nvidia0').exists(),
                    'capabilities_empty': int(values['CapEff'], 16) == 0 and values['NoNewPrivs'] == '1',
                    'memory_limit_observed': (cgroup/'memory.max').read_text().strip() != 'max',
                    'PID_limit_observed': (cgroup/'pids.max').read_text().strip() == '64',
                    'UUID_matches': manifest['vm_uuids'][vm_id].encode() in Path(f'/proc/{record["pid"]}/cmdline').read_bytes().split(b'\0'),
                }
                if not confinement_supported(facts):
                    raise RuntimeError('effective_VM_confinement_not_supported')
                nsenter = ['/usr/bin/nsenter', '--net=/proc/self/fd/'+str(namespace)]
                for address in ('198.18.0.1/32', 'fd42:4d41:4e49::1/128'):
                    bounded_process(nsenter+['/usr/bin/ip', 'address', 'replace', address, 'dev', 'lo'], b'', 5, pass_fds=(namespace,))
                canary = subprocess.Popen(nsenter+['/usr/bin/python3', '-I', str(INSTALL/'canary.py'), 'serve'],
                                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                          close_fds=True, pass_fds=(namespace,), env={'PATH': '/usr/bin:/bin'})
                canary_record = {**identity(canary.pid), 'role': vm_id+'_owned_canary'}
                self.store.mutate(run_id, lambda m: m['processes'].append(canary_record))
                if not select.select([canary.stdout], [], [], 3)[0] or canary.stdout.readline(64) != b'ready\n':
                    raise RuntimeError('owned_canary_start_failed')
                def command(operation):
                    return bounded_json(bounded_process(nsenter+['/usr/bin/python3', '-I', str(INSTALL/'canary.py'), operation],
                                                        b'', 8, pass_fds=(namespace,)))
                positive = command('positive')
                command('reset')
                self.store.heartbeat(run_id)
                guest = self.ssh(run_id, vm_id, 'probe')
                boundary = command('counters')
                evidence[vm_id] = {'observed_confinement': facts, 'positive': positive,
                                   'guest_report': guest, 'boundary': boundary,
                                   'network_supported': network_supported(positive, guest, boundary),
                                   'scope': 'owned_private_namespace_canaries_not_physical_LAN_or_WAN'}
            except CommandFailure as error:
                self.store.mutate(run_id, lambda m: m.update(private_qualification_failure={
                    'vm': vm_id, 'command': error.command, 'exit': error.exit_code,
                    'stderr': error.private_stderr}))
                raise
            finally:
                if canary is not None:
                    if canary.poll() is None:
                        canary.terminate()
                    canary.wait(timeout=2)
                    canary.stdout.close()
                if namespace is not None:
                    os.close(namespace)
                os.close(pid_fd)
        passed = len(evidence) == 3 and all(row['network_supported'] for row in evidence.values())
        installations = {}
        if self.configuration.get('runtime_zip_sha256'):
            for role in ('controller', 'worker_a', 'worker_b'):
                installations[role] = self.ssh(run_id, role, 'hermes_health')
        installed = len(installations) == 3 and all(
            item['uid'] != 0 and item['installed']['runtime_zip_sha256'] == self.configuration['runtime_zip_sha256']
            and item['installed']['Hermes_revision'] == self.configuration['Hermes_revision']
            and item['agent_conversation_executed'] is False for item in installations.values())
        self.store.mutate(run_id, lambda m: m.update(qualification={'confinement': len(evidence) == 3,
                                                                    'network': passed, 'watchdog': False,
                                                                    'Hermes_installed': installed,
                                                                    'Hermes_installations': installations,
                                                                    'evidence': evidence}))
        return {'status': 'ok' if passed else 'failed', 'run_id': run_id, 'evidence': evidence,
                'VM_watchdog_kill_tests': 'still_required', 'guest_agents_enabled': False}

    def prepare_model(self, run_id, arm):
        import backend
        from lab.readiness import REQUIREMENTS
        facts = self.state()['observed_facts']
        prerequisites = [key for key in REQUIREMENTS['normal'] if key != 'normal_backend_qualified']
        missing = [key for key in prerequisites if not facts.get(key)]
        if missing or run_id != self.active_run():
            return {'status': 'blocked', 'missing': missing}
        self.store.mutate(run_id, lambda m:m.update(owns_backend=True))
        loaded = backend.start(arm, valid=lambda: not self.store.mutate(run_id, self.store.active))
        self.backend_arm = arm
        proof = backend.qualify(arm)
        self.store.mutate(run_id, lambda m:m.setdefault('backend_qualification', {}).update({arm:proof}))
        return {'status':'ok' if proof['confined'] else 'failed', 'loaded':loaded, 'proof':proof}

    def run_case(self, run_id, case_id, arm):
        from lab.readiness import stage_results
        from lab.relay import Relay
        from lab.transport import CommandFailure
        import backend
        from vm_service import unit_name
        facts = self.state()['observed_facts']
        gate = stage_results(facts)['normal' if arm == 'normal' else 'paired']
        if not gate.ready or run_id != self.active_run():
            return {'status':'blocked', 'missing':list(gate.missing)}
        if self.backend_arm != arm:
            prepared = self.prepare_model(run_id, arm)
            if prepared['status'] != 'ok':
                return prepared
        cases = json.loads((INSTALL/'bench/cases.json').read_text())['cases']
        case = next(item for item in cases if item['case_id'] == case_id)
        relay = Relay(self.store, run_id, backend.ALIAS, 18082, job_seconds=120,
                      connection_factory=lambda seconds:backend.UnixHTTP(timeout=seconds), cancel_backend=backend.stop)
        server = relay.server()
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        directory = self.store.directory(run_id)
        proxy = f'/usr/bin/python3 -I {INSTALL}/proxy.py {directory}/controller-control/ssh.sock'
        tunnel = ['/usr/bin/ssh', '-F', '/dev/null', '-T', '-N', '-o', 'BatchMode=yes',
            '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ForwardAgent=no',
            '-o', 'HostKeyAlias=mani-vmlab-controller', '-o', 'UserKnownHostsFile='+str(directory/'controller.known_hosts'),
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ExitOnForwardFailure=yes', '-o', 'ProxyCommand='+proxy,
            '-i', str(directory/'controller.key'), '-R', f'127.0.0.1:18081:127.0.0.1:{server.server_port}', 'lab@localhost']
        started = time.monotonic()
        process = subprocess.Popen(tunnel, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            time.sleep(0.25)
            if process.poll() is not None:
                raise RuntimeError('fixed_relay_tunnel_not_ready')
            response = self.ssh(run_id, 'controller', 'solve', {'prompt':case['prompt'], 'model':backend.ALIAS,
                                                             'relay_token':self.store.token(run_id)})
            events = list(relay.events)
            completed = [event for event in events if event.get('outcome') == 'completed']
            if not completed or response['Hermes_revision'] != self.configuration['Hermes_revision']:
                raise RuntimeError('trusted_relay_runtime_evidence_missing')
            self.store.mutate(run_id, lambda m:m.update(Hermes_routing_qualified=True))
            event = completed[-1]
            model = json.loads(Path('/usr/local/lib/mani-vmlab-setup/backend-artifacts.lock.json').read_text())['models'][arm]
            return {'status':'ok', 'evidence_kind':'real_guest_Hermes', 'answer':response['answer'],
                'model_sha256':model['sha256'], 'wall_seconds':time.monotonic()-started,
                'ttft_seconds':None, 'prompt_tokens':(event.get('usage') or {}).get('prompt_tokens'),
                'completion_tokens':(event.get('usage') or {}).get('completion_tokens'),
                'finish_reason':event.get('finish_reason'), 'relay_events':events,
                'backend_resources':backend.resources(), 'Hermes_revision':response['Hermes_revision']}
        except CommandFailure as error:
            self.store.mutate(run_id, lambda m:m.setdefault('private_agent_failures', []).append({
                'case_id':case_id, 'arm':arm, 'stderr':error.private_stderr}))
            return {'status':'failed', 'reason':str(error), 'relay_events':list(relay.events)}
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            process.stderr.close()
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

    def watchdog(self):
        last_snapshot=0
        while not self.shutdown.wait(0.25):
            self.text_chat.check()
            if self.workspace_jobs is not None:self.workspace_jobs.check_owners()
            for directory in list(self.store.root.iterdir()):
                if not directory.is_dir():
                    continue
                run_id = directory.name
                manifest = self.store.read(run_id)
                if manifest['status'] != 'active':
                    continue
                reason = self.store.mutate(run_id, lambda m: self.store.active(m))
                if not reason and manifest.get('control_verified'):
                    from lab.process import open_owned
                    import select
                    for record in manifest['processes']:
                        if record['role'] not in ('controller', 'worker_a', 'worker_b'):
                            continue
                        descriptor = open_owned(record)
                        if descriptor is None:
                            reason = 'owned_VM_lost'
                            break
                        try:
                            if select.select([descriptor], [], [], 0)[0]:
                                reason = 'owned_VM_lost'
                                break
                        finally:
                            os.close(descriptor)
                if reason:
                    self.stop(run_id, reason)
                    self.cleanup(run_id)
            notify = os.environ.get('NOTIFY_SOCKET')
            if time.monotonic()-last_snapshot>=3:
                self.publish_status()
                last_snapshot=time.monotonic()
            if notify:
                address = '\0'+notify[1:] if notify.startswith('@') else notify
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
                    channel.sendto(b'WATCHDOG=1', address)

    def publish_status(self):
        from lab.state import atomic_json
        output=Path('/var/lib/mani-vmlab-review/status-public.json')
        state=self.state()
        state.update(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                     observed_monotonic_seconds=time.monotonic(),source_pack_sha256=self.configuration['source_pack_sha256'])
        atomic_json(output,state);output.chmod(0o644)

    def dispatch(self, data, peer_pid=None):
        from lab.native_client import request_schema
        if type(data) is dict and data.get('operation') in ('chat_admit','chat_heartbeat','chat_release','chat_cancel'):
            operation=data['operation']
            if set(data)!=({'operation','job_id','arm'} if operation=='chat_admit' else {'operation','job_id'}):
                raise ValueError('fixed_text_admission_fields_required')
            request_schema(operation,**{k:v for k,v in data.items() if k!='operation'})
            if type(peer_pid) is not int or peer_pid<=0:raise ValueError('native_peer_owner_required')
            if operation=='chat_admit':return self.text_chat.admit(data['job_id'],data['arm'],peer_pid)
            if operation=='chat_heartbeat':return self.text_chat.beat(data['job_id'],peer_pid)
            return self.text_chat.release(data['job_id'],peer_pid,operation=='chat_cancel')
        if type(data) is dict and type(data.get('operation')) is str and data['operation'].startswith('workspace_'):
            fields={'operation','version','payload'} if data['operation']=='workspace_submit' else {'operation','version','job_id'}
            if set(data)!=fields:raise ValueError('fixed_workspace_native_fields_required')
            request_schema(data['operation'],**{key:value for key,value in data.items() if key!='operation'})
            if self.configuration.get('workspace_api')!=1:raise RuntimeError('workspace_API_not_installed')
            from jobs import Jobs
            with self.jobs_initialization:
                if self.workspace_jobs is None:self.workspace_jobs=Jobs(self)
            if data['operation']=='workspace_submit':
                if type(peer_pid) is not int or peer_pid<=0:raise ValueError('native_peer_owner_required')
                return self.workspace_jobs.submit(data['payload'],peer_pid)
            if data['operation']=='workspace_read':return self.workspace_jobs.public(data['job_id'])
            if data['operation']=='workspace_cancel':return self.workspace_jobs.cancel(data['job_id'])
        if type(data) is not dict or set(data)-{'operation', 'run_id', 'vm_id', 'case_id', 'arm'} or 'operation' not in data:
            raise ValueError('invalid_native_schema')
        operation = data['operation']
        request_schema(operation, **{key: value for key, value in data.items() if key != 'operation'})
        if operation in ('provision','prepare_model','run_case','qualify') and self.text_chat.current:
            raise RuntimeError('text_resource_owner_busy')
        if operation == 'status' and set(data) == {'operation'}:
            return self.state()
        if operation == 'provision' and set(data) == {'operation'}:
            with self.mutation:
                return self.provision()
        if operation == 'window_heartbeat' and set(data) == {'operation'}:
            import window
            window.beat()
            return {'status':'ok'}
        if operation == 'prepare_model' and set(data) == {'operation', 'run_id', 'arm'}:
            with self.mutation:
                return self.prepare_model(data['run_id'], data['arm'])
        if operation in ('stop', 'heartbeat', 'cleanup', 'qualify') and set(data) == {'operation', 'run_id'}:
            run_id = data['run_id']
            if operation == 'heartbeat':
                return {'status': 'ok' if self.store.heartbeat(run_id) else 'blocked'}
            if operation == 'stop':
                return self.stop(run_id)
            if operation == 'cleanup':
                return self.cleanup(run_id)
            with self.mutation:
                return self.qualify(run_id)
        if operation == 'run_case':
            if set(data) != {'operation', 'run_id', 'vm_id', 'case_id', 'arm'} or data['vm_id'] != 'controller':
                raise ValueError('fixed_controller_case_contract_required')
            with self.mutation:
                return self.run_case(data['run_id'], data['case_id'], data['arm'])
        raise ValueError('invalid_native_operation_fields')


def send_native_result(connection, result, restore=None):
    """Finish the control reply before recovery can stop its owning daemon."""
    restore_window=result.pop('_restore_window',False)
    try:
        fd=result.pop('_backend_fd',None)
        raw=json.dumps(result).encode()
        if fd is not None:
            import array
            sent=connection.sendmsg([raw],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])
            if sent<len(raw):connection.sendall(raw[sent:])
        else:connection.sendall(raw)
    finally:
        if restore_window:
            if restore is not None:restore()
            else:
                import window
                subprocess.run(['/usr/bin/systemctl','--no-block','stop',window.SERVICE],
                               check=True,timeout=5,capture_output=True)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise SystemExit('fixed_protected_supervisor_only')
    initialize_imports()
    from starter.json_limits import bounded_json
    supervisor = Supervisor()
    supervisor.recover()
    watchdog = threading.Thread(target=supervisor.watchdog, daemon=True)
    watchdog.start()
    SOCKET.parent.mkdir(mode=0o755, exist_ok=True)
    protected(SOCKET.parent)
    activated=os.environ.get('LISTEN_PID')==str(os.getpid()) and os.environ.get('LISTEN_FDS')=='1'
    if SOCKET.exists() and not activated:
        raise RuntimeError('preserve_existing_control_socket')
    with (socket.socket(fileno=3) if activated else socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)) as server:
        if not activated:
            server.bind(str(SOCKET))
            os.chown(SOCKET, 0, pwd.getpwuid(OPERATOR_UID).pw_gid)
            SOCKET.chmod(0o660)
        server.listen(4)
        server.settimeout(0.25)
        slots = threading.BoundedSemaphore(4)
        def handle(connection):
            try:
                with connection:
                    connection.settimeout(2)
                    peer_pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    try:
                        if uid != OPERATOR_UID:
                            raise PermissionError('operator_peer_denied')
                        raw = bytearray()
                        while chunk := connection.recv(8192):
                            raw.extend(chunk)
                            if len(raw) > 65536:
                                raise ValueError('native_request_limit')
                        result = supervisor.dispatch(bounded_json(bytes(raw)),peer_pid=peer_pid)
                    except (OSError, ValueError, RuntimeError) as error:
                        result = {'status':'failed', 'error':str(error)}
                    try:
                        send_native_result(connection,result)
                    except OSError:
                        pass  # Lease/watchdog own recovery when operator transport disappears.
            finally:
                slots.release()
        notify = os.environ.get('NOTIFY_SOCKET')
        if notify:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
                channel.sendto(b'READY=1', '\0'+notify[1:] if notify.startswith('@') else notify)
        try:
            while watchdog.is_alive():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                if not slots.acquire(blocking=False):
                    connection.close()
                    continue
                threading.Thread(target=handle, args=(connection,), daemon=True).start()
        finally:
            supervisor.shutdown.set()
            supervisor.recover()
            supervisor.firewall.close()
            if not activated:SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
