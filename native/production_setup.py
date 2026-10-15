"""Fixed, hash-frozen socket activation repair. Never loads a model or alters chat data."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
from contextlib import contextmanager

sys.dont_write_bytecode = True
SELF = Path('/usr/local/lib/mani-vmlab-setup/production_setup.py')
PLAN = Path('/home/mani/mani-hermes-v4-d1wzr5kx/private-state/production-setup/production-plan.json')
PLAN_SHA = '2ebe54fafd32cad8ff38c482ff58171e01cb97fffbf5192e874ab8f3705ababe'
ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
SETUP = SELF.parent
STATE = Path('/var/lib/mani-vmlab-setup')
RECOVERY = SETUP / 'recovery.py'
REGISTER = STATE / 'workspace-complete-register.json'
TRANSACTION = STATE / 'production-v4'
USER_UNIT = Path('/home/mani/.config/systemd/user/hermes-workspace.service')
SERVICE = Path('/etc/systemd/system/hermes-workspace-runtime.service')
SOCKET = Path('/etc/systemd/system/hermes-workspace-runtime.socket')
ENABLE_LINK = Path('/etc/systemd/system/sockets.target.wants/hermes-workspace-runtime.socket')
NORMAL_FILES = frozenset(('.config/systemd/user/manibot-llama.service', '.config/systemd/user/qwen-local.service', '.local/bin/start-manibot-llama', '.hermes/config.yaml'))
USER_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': '/home/mani', 'XDG_RUNTIME_DIR': '/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'}
USER_CTL = ['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--init-groups', '/usr/bin/systemctl', '--user']


def unit_texts():
    return {
        'socket': '[Unit]\nDescription=Loopback Hermes workspace listener\n[Socket]\nListenStream=127.0.0.1:18791\nService=hermes-workspace-runtime.service\nNoDelay=yes\n[Install]\nWantedBy=sockets.target\n',
        'service': '[Unit]\nDescription=Local Hermes workspace data runtime\nAfter=user@1000.service\nRequires=user@1000.service\n[Service]\nUser=mani\nGroup=mani\nWorkingDirectory=' + str(ROOT) + '\nExecStart=/usr/bin/python3 -I ' + str(ROOT / 'workspace/server.py') + '\nEnvironment=HOME=/home/mani\nEnvironment=XDG_RUNTIME_DIR=/run/user/1000\nEnvironment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus\nUMask=0077\nPrivateTmp=yes\nPrivateUsers=no\nNoNewPrivileges=yes\nCapabilityBoundingSet=\nAmbientCapabilities=\nRestart=on-failure\nRestartSec=3\nTimeoutStopSec=20\n',
        'user': '[Unit]\nDescription=Local Hermes workspace launcher lifecycle\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/python3 -I ' + str(ROOT / 'workspace/production_client.py') + ' start\nExecStop=/usr/bin/python3 -I ' + str(ROOT / 'workspace/production_client.py') + ' stop\nUMask=0077\nPrivateTmp=no\nNoNewPrivileges=yes\n[Install]\nWantedBy=default.target\n',
    }


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def parent_fd(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute_fixed_path_required')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, path.name
    finally:
        os.close(descriptor)


def read_file(path, maximum=1024 * 1024, owner=None, protected=False):
    with parent_fd(path) as (parent, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
            raise ValueError('bounded_single_link_regular_file_required')
        if owner is not None and info.st_uid != owner:
            raise PermissionError('unexpected_file_owner')
        if protected and info.st_mode & 0o022:
            raise PermissionError('protected_file_required')
        raw = source.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError('file_size_limit')
        return raw, {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino, 'sha256': sha(raw), 'uid': info.st_uid, 'mode': stat.S_IMODE(info.st_mode)}


def read_pinned(path, digest, **kwargs):
    raw, info = read_file(path, **kwargs)
    if info['sha256'] != digest:
        raise RuntimeError('frozen_file_drift:' + str(path))
    return raw


def write_file(path, raw, mode=0o644, uid=0, gid=0):
    with parent_fd(path) as (parent, name):
        temporary = '.' + name + '.production-' + secrets.token_hex(8)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                os.fchmod(output.fileno(), mode)
                os.fchown(output.fileno(), uid, gid)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    return read_file(path, owner=uid)[1]


def command(argv, timeout=40):
    return subprocess.run(argv, check=True, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, env=USER_ENV)


def protected_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise PermissionError('protected_directory_required:' + str(path))
    with parent_fd(path / 'unused'):
        pass


def normal_unchanged(plan):
    if set(plan['normal_configuration_sha256']) != NORMAL_FILES:
        raise ValueError('four_fixed_normal_configuration_pins_required')
    for relative, digest in plan['normal_configuration_sha256'].items():
        read_pinned(Path('/home/mani') / relative, digest, owner=1000)


def validate_plan(plan):
    if set(plan) != {'version', 'units', 'old_user_unit_sha256', 'recovery_before_sha256', 'recovery_source', 'normal_configuration_sha256', 'application_sources'} or plan['version'] != 1:
        raise ValueError('fixed_production_plan_required')
    if plan['units'] != unit_texts():
        raise ValueError('fixed_production_unit_texts_required')
    if set(plan['normal_configuration_sha256']) != NORMAL_FILES:
        raise ValueError('four_fixed_normal_configuration_pins_required')
    if set(plan['recovery_source']) != {'path', 'sha256'} or plan['recovery_source']['path'] != str(ROOT / 'native/recovery.py'):
        raise ValueError('fixed_recovery_source_required')
    expected = {str(ROOT / 'workspace/server.py'), str(ROOT / 'workspace/production_client.py')}
    if set(plan['application_sources']) != expected:
        raise ValueError('fixed_unprivileged_application_sources_required')
    for digest in [plan['old_user_unit_sha256'], plan['recovery_before_sha256'], plan['recovery_source']['sha256'], *plan['normal_configuration_sha256'].values(), *plan['application_sources'].values()]:
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('sha256_digest_required')
    return plan


PROOF_CODE = r'''from pathlib import Path
import json,os,socket,stat,struct,subprocess
r={"uid":os.getuid(),"gid":os.getgid(),"user_namespace":os.readlink("/proc/self/ns/user"),"mount_namespace":os.readlink("/proc/self/ns/mnt")}
s={line.split(":",1)[0]:line.split(":",1)[1].strip()for line in Path("/proc/self/status").read_text().splitlines()if ":"in line}
r.update(no_new_privileges=s["NoNewPrivs"],effective_capabilities=s["CapEff"])
p=Path("/run/mani-vmlab/control.sock");i=p.lstat();j=p.parent.lstat();r.update(socket_uid=i.st_uid,parent_uid=j.st_uid,parent_mode=stat.S_IMODE(j.st_mode),is_socket=stat.S_ISSOCK(i.st_mode))
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)as c:
 c.settimeout(3);c.connect(str(p));_,uid,gid=struct.unpack("3i",c.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));r["root_peer_uid"]=uid;c.shutdown(socket.SHUT_WR)
pid=int(subprocess.check_output(["/usr/bin/systemctl","--user","show","manibot-llama.service","--property=MainPID","--value"],timeout=5).strip());r["normal_pid"]=pid
r["normal_executable"]=os.readlink("/proc/"+str(pid)+"/exe");r["normal_command_readable"]=bool(Path("/proc/"+str(pid)+"/cmdline").read_bytes())
print(json.dumps(r))
'''


def validate_proof(proof, user_namespace, mount_namespace):
    if (proof.get('uid'), proof.get('gid'), proof.get('root_peer_uid'), proof.get('socket_uid'), proof.get('parent_uid')) != (1000, 1000, 0, 0, 0):
        raise RuntimeError('same_uid_and_real_root_peer_required')
    if not proof.get('is_socket') or proof.get('parent_mode', 0o777) & 0o022:
        raise RuntimeError('protected_native_socket_required')
    if proof.get('user_namespace') != user_namespace or proof.get('mount_namespace') == mount_namespace:
        raise RuntimeError('initial_user_namespace_and_private_mount_namespace_required')
    if proof.get('no_new_privileges') != '1' or int(proof.get('effective_capabilities', '1'), 16) != 0:
        raise RuntimeError('unprivileged_runtime_required')
    if type(proof.get('normal_pid')) is not int or proof['normal_pid'] <= 1 or not proof.get('normal_executable') or not proof.get('normal_command_readable'):
        raise RuntimeError('normal_process_identity_must_remain_readable')
    return proof


def namespace_proof():
    unit = 'hermes-v4-production-proof-' + secrets.token_hex(8) + '.service'
    properties = ['User=mani', 'Group=mani', 'PrivateTmp=yes', 'PrivateUsers=no', 'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'AmbientCapabilities=', 'RuntimeMaxSec=20', 'Environment=HOME=/home/mani', 'Environment=XDG_RUNTIME_DIR=/run/user/1000', 'Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus']
    args = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit=' + unit]
    args += ['--property=' + value for value in properties]
    try:
        raw = command([*args, '/usr/bin/python3', '-I', '-c', PROOF_CODE], timeout=25).stdout
        if len(raw) > 8192:
            raise ValueError('bounded_namespace_proof_required')
        proof = validate_proof(json.loads(raw), os.readlink('/proc/self/ns/user'), os.readlink('/proc/self/ns/mnt'))
    finally:
        loaded = command(['/usr/bin/systemctl', 'show', unit, '--property=LoadState', '--value']).stdout.strip()
        if loaded != b'not-found':
            command(['/usr/bin/systemctl', 'stop', unit])
    proof['disposable_unit'] = unit
    return proof


def fingerprint(path):
    # Existing recovery registrations include backend binaries; hash them as a
    # stream rather than turning a trusted file inventory into a RAM allocation.
    with parent_fd(path) as (parent, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('registered_single_link_regular_file_required')
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
        after = os.fstat(source.fileno())
        if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise RuntimeError('registered_file_changed_during_verification')
    return {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino, 'sha256': digest, 'uid': info.st_uid, 'mode': stat.S_IMODE(info.st_mode)}


def unchanged(item):
    try:
        actual = fingerprint(Path(item['path']))
    except FileNotFoundError:
        return False
    return all(actual[k] == item[k] for k in ('device', 'inode', 'sha256', 'uid', 'mode'))


def inspect_register(register):
    if register.get('version') != 1 or type(register.get('files')) is not list:
        raise ValueError('existing_complete_recovery_register_required')
    paths = [item['path'] for item in register['files']]
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate_existing_recovery_registration')
    for item in register['files']:
        path = Path(item['path'])
        if not path.exists() and not path.is_symlink():
            continue
        if item.get('allowed_sha256') and str(path) == '/run/systemd/system/mani-vmlab-backend.service':
            actual = fingerprint(path)
            if actual['uid'] != 0 or actual['mode'] != 0o644 or actual['sha256'] not in item['allowed_sha256']:
                raise RuntimeError('preserve_registered_backend_drift')
        elif not unchanged(item):
            raise RuntimeError('preserve_registered_file_drift:' + str(path))


def save_journal(journal):
    write_file(TRANSACTION / 'journal.json', (json.dumps(journal, indent=2) + '\n').encode(), mode=0o600)


def backup(plan, register_digest):
    TRANSACTION.mkdir(mode=0o700)
    protected_directory(TRANSACTION)
    paths = {'user': USER_UNIT, 'recovery': RECOVERY, 'register': REGISTER}
    records = {}
    for role, path in paths.items():
        raw, info = read_file(path, maximum=4 * 1024 * 1024, owner=1000 if role == 'user' else 0, protected=role != 'user')
        expected = {'user': plan['old_user_unit_sha256'], 'recovery': plan['recovery_before_sha256'], 'register': register_digest}[role]
        if info['sha256'] != expected:
            raise RuntimeError('preserve_change_during_production_preflight:' + role)
        write_file(TRANSACTION / (role + '.before'), raw, mode=0o600)
        records[role] = {'before': info, 'backup_sha256': sha(raw)}
    active = command([*USER_CTL, 'show', USER_UNIT.name, '--property=ActiveState', '--value']).stdout.strip() == b'active'
    journal = {'plan_sha256': PLAN_SHA, 'phase': 'prepared', 'files': records, 'installed': {}, 'user_was_active': active}
    save_journal(journal)
    return journal


def record_files(register, changed):
    current = {item['path']: dict(item) for item in register['files']}
    for item in changed:
        current[item['path']] = {**current.get(item['path'], {}), **item}
    return {**register, 'files': list(current.values())}


def link_record():
    info = ENABLE_LINK.lstat()
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or os.readlink(ENABLE_LINK) != str(SOCKET):
        raise RuntimeError('preserve_other_socket_enable_link')
    return {'path': str(ENABLE_LINK), 'kind': 'symlink', 'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid, 'target': str(SOCKET)}


def apply(plan):
    normal_unchanged(plan)
    for path, digest in plan['application_sources'].items():
        read_pinned(Path(path), digest, owner=1000)
    recovery_raw = read_pinned(Path(plan['recovery_source']['path']), plan['recovery_source']['sha256'], owner=1000)
    if TRANSACTION.exists():
        journal = json.loads(read_file(TRANSACTION / 'journal.json', owner=0, protected=True)[0])
        if journal.get('plan_sha256') != PLAN_SHA:
            raise RuntimeError('preserve_other_production_transaction')
        if journal['phase'] == 'installed':
            for item in journal['installed'].values():
                if not unchanged(item):
                    raise RuntimeError('preserve_changed_installed_production_files')
            if link_record() != journal['enable_link']:
                raise RuntimeError('preserve_changed_installed_socket_link')
            inspect_register(json.loads(read_file(REGISTER, owner=0, protected=True)[0]))
            command(['/usr/bin/systemctl','start',SOCKET.name])
            print(json.dumps({'status': 'already_installed', 'GPU_window_opened': False}));return
        raise RuntimeError('partial_production_transaction_requires_rollback')
    read_pinned(USER_UNIT, plan['old_user_unit_sha256'], owner=1000)
    read_pinned(RECOVERY, plan['recovery_before_sha256'], owner=0, protected=True)
    for path in (SERVICE, SOCKET, ENABLE_LINK):
        if path.exists() or path.is_symlink():
            raise RuntimeError('preserve_other_production_unit:' + str(path))
    register_raw, register_info = read_file(REGISTER, maximum=4 * 1024 * 1024, owner=0, protected=True)
    register = json.loads(register_raw)
    inspect_register(register)
    proof = namespace_proof()
    journal = backup(plan, register_info['sha256'])
    journal['namespace_proof'] = proof
    save_journal(journal)
    try:
        command([*USER_CTL, 'stop', USER_UNIT.name])
        for role, path, raw, uid, gid in [('service', SERVICE, plan['units']['service'].encode(), 0, 0), ('socket', SOCKET, plan['units']['socket'].encode(), 0, 0), ('user', USER_UNIT, plan['units']['user'].encode(), 1000, 1000), ('recovery', RECOVERY, recovery_raw, 0, 0)]:
            if role in ('user', 'recovery') and not unchanged(journal['files'][role]['before']):
                raise RuntimeError('target_changed_during_setup:' + role)
            if role in ('service', 'socket') and (path.exists() or path.is_symlink()):
                raise RuntimeError('new_unit_appeared_during_setup')
            journal['installed'][role] = write_file(path, raw, uid=uid, gid=gid)
            save_journal(journal)
        protected_directory(ENABLE_LINK.parent)
        with parent_fd(ENABLE_LINK) as (parent, name):
            os.symlink(str(SOCKET), name, dir_fd=parent)
        journal['enable_link'] = link_record()
        save_journal(journal)
        updated = record_files(register, [item for role,item in journal['installed'].items() if role!='recovery'] + [fingerprint(SELF)])
        updated['namespaces'] = [item for item in updated.get('namespaces', []) if item['path'] != str(ENABLE_LINK)] + [journal['enable_link']]
        if not unchanged(journal['files']['register']['before']):
            raise RuntimeError('preserve_concurrent_recovery_register_change')
        journal['installed']['register'] = write_file(REGISTER, (json.dumps(updated, indent=2) + '\n').encode(), mode=0o600)
        save_journal(journal)
        command(['/usr/bin/systemctl', 'daemon-reload'])
        command([*USER_CTL, 'daemon-reload'])
        command(['/usr/bin/systemctl', 'start', SOCKET.name])
        normal_unchanged(plan)
        journal['phase'] = 'installed'
        save_journal(journal)
        receipt = {'status': 'installed', 'plan_sha256': PLAN_SHA, 'GPU_window_opened': False, 'normal_configuration_hashes_unchanged': True, 'conversations_touched': False, 'namespace_proof': proof, 'socket_activation': True}
        directory = Path('/var/lib/mani-vmlab-review');protected_directory(directory)
        write_file(directory / 'production-installed.json', (json.dumps(receipt, indent=2) + '\n').encode())
        print(json.dumps(receipt))
    except BaseException:
        rollback(plan)
        raise


def rollback(plan):
    normal_unchanged(plan)
    protected_directory(TRANSACTION)
    journal = json.loads(read_file(TRANSACTION / 'journal.json', owner=0, protected=True)[0])
    if journal.get('plan_sha256') != PLAN_SHA:
        raise RuntimeError('preserve_other_production_transaction')
    if journal['phase'] == 'rolled_back':
        print(json.dumps({'status': 'already_rolled_back', 'GPU_window_opened': False}));return
    for item in journal['installed'].values():
        if not unchanged(item):
            raise RuntimeError('preserve_drift_before_production_rollback:' + item['path'])
    if 'enable_link' in journal and link_record() != journal['enable_link']:
        raise RuntimeError('preserve_changed_socket_enable_link')
    originals = {role: read_pinned(TRANSACTION / (role + '.before'), item['backup_sha256'], owner=0, protected=True, maximum=4 * 1024 * 1024) for role, item in journal['files'].items()}
    for unit in (SOCKET.name,SERVICE.name):
        if command(['/usr/bin/systemctl','show',unit,'--property=LoadState','--value']).stdout.strip()!=b'not-found':
            command(['/usr/bin/systemctl','stop',unit])
    command([*USER_CTL, 'stop', USER_UNIT.name])
    if 'enable_link' in journal:
        with parent_fd(ENABLE_LINK) as (parent, name):os.unlink(name, dir_fd=parent)
    for role, path in [('socket', SOCKET), ('service', SERVICE)]:
        if role in journal['installed']:
            with parent_fd(path) as (parent, name):os.unlink(name, dir_fd=parent)
    restored = []
    for role, path in [('user', USER_UNIT), ('recovery', RECOVERY)]:
        if role in journal['installed']:
            item = journal['files'][role]['before']
            restored.append(write_file(path, originals[role], mode=item['mode'], uid=item['uid'], gid=1000 if role == 'user' else 0))
    register = json.loads(originals['register'])
    register = record_files(register, [item for item in restored if any(old['path'] == item['path'] for old in register['files'])])
    write_file(REGISTER, (json.dumps(register, indent=2) + '\n').encode(), mode=0o600)
    command(['/usr/bin/systemctl', 'daemon-reload'])
    command([*USER_CTL, 'daemon-reload'])
    if journal['user_was_active']:
        command([*USER_CTL, 'start', USER_UNIT.name])
    normal_unchanged(plan)
    journal['phase'] = 'rolled_back';save_journal(journal)
    print(json.dumps({'status': 'rolled_back', 'normal_configuration_hashes_unchanged': True, 'conversations_touched': False, 'GPU_window_opened': False}))


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF or sys.argv[1:] not in (['apply'], ['rollback']):
        raise SystemExit('fixed_protected_production_setup_only')
    for directory in (SETUP, STATE, Path('/etc/systemd/system')):
        protected_directory(directory)
    read_file(SELF, owner=0, protected=True)
    plan = validate_plan(json.loads(read_pinned(PLAN, PLAN_SHA)))
    (apply if sys.argv[1] == 'apply' else rollback)(plan)


if __name__ == '__main__':
    main()
