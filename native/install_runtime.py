#!/usr/bin/python3
"""Fixed root-owned runtime installer. Source pack digest is frozen at preparation.

No package installation, network-policy change or model load occurs here.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import stat
import subprocess
import sys
import zipfile

SELF = Path('/usr/local/lib/mani-vmlab-setup/install_runtime.py')
PACK = Path('/var/lib/mani-vmlab-setup/runtime-source.zip')
INSTALL = Path('/usr/local/lib/mani-vmlab')
DATA = Path('/home/mani-vmlab-data')
CONFIG = Path('/etc/mani-vmlab')
UNIT = Path('/etc/systemd/system/mani-vmlab-supervisor.service')
IMAGE = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/private-artifacts/guest-image/ubuntu-24.04-server-cloudimg-amd64.img')
IMAGE_SHA = '6a81c37564db9b1ee84e141922625e1d7c5b389b99bb3c572e0243607d5bb4d2'
EXPECTED_FILES = frozenset({'supervisor.py', 'vm_service.py', 'proxy.py', 'canary.py', 'nft_monitor.py', 'guest/qualify.py',
                           'backend.py', 'window.py', 'lab/relay.py', 'bench/cases.json',
                           'guest/bootstrap.py', 'guest/solve.py', 'guest/json_limits.py',
                           'lab/__init__.py', 'lab/state.py', 'lab/process.py', 'lab/doctor.py', 'lab/transport.py',
                           'lab/native_client.py', 'lab/readiness.py', 'lab/qualification.py', 'starter/__init__.py', 'starter/json_limits.py',
                           'evidence.py','jobs.py','lab/workspace_contract.py','guest/workspace_job.py','guest/run_code.py','guest/workspace_contract.py',
                           'guest/lifecycle_probe.py','guest/recovery.py'})


def sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(4*1024*1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def trusted(path, directory=False):
    info = Path(path).lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
        raise PermissionError('root_owned_protected_path_required')
    if directory and not stat.S_ISDIR(info.st_mode):
        raise ValueError('directory_required')


def run(argv):
    subprocess.run(argv, stdin=subprocess.DEVNULL, check=True, timeout=30,
                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C'}, capture_output=True)


def validated_pack(path, expected):
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected) or sha256(path) != expected:
        raise ValueError('native_source_pack_digest_mismatch')
    payload = {}
    with zipfile.ZipFile(path) as archive:
        if set(archive.namelist()) != EXPECTED_FILES or len(archive.namelist()) != len(EXPECTED_FILES):
            raise ValueError('exact_native_source_inventory_required')
        for name in EXPECTED_FILES:
            info = archive.getinfo(name)
            if info.file_size > 131072 or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('native_pack_member_limit')
            payload[name] = archive.read(name)
    return payload


def checkpoint(register):
    """Journal only our initially absent installation roots, including partial writes."""
    files = []
    roots = (INSTALL, CONFIG, DATA/'runtime-root')
    for root in roots:
        if root.exists():
            for path in root.rglob('*'):
                if '__pycache__' in path.parts or path.suffix == '.pyc':
                    continue
                if path.is_file() and not path.is_symlink():
                    info = path.stat()
                    files.append({'path': str(path), 'device': info.st_dev, 'inode': info.st_ino,
                                  'sha256': sha256(path)})
    unit = UNIT
    if unit.exists():
        info = unit.stat()
        files.append({'path': str(unit), 'device': info.st_dev, 'inode': info.st_ino, 'sha256': sha256(unit)})
    register['installed_files'] = files
    path = SELF.parent/'runtime-installed.json'
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('x') as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(register, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def supervisor_service_text():
    return '''[Unit]
Description=Fixed Mani VM lab supervisor (no-agent qualification)
After=local-fs.target

[Service]
Type=notify
ExecStart=/usr/bin/python3 -I /usr/local/lib/mani-vmlab/supervisor.py
WatchdogSec=10
NotifyAccess=main
RuntimeDirectory=mani-vmlab
RuntimeDirectoryMode=0755
PrivateTmp=yes
NoNewPrivileges=yes
ProtectHome=read-only
InaccessiblePaths=/root /home/mani /etc/shadow /etc/gshadow /run/docker.sock /run/user/1000
ProtectSystem=strict
ReadWritePaths=/run/mani-vmlab /run/systemd/system /home/mani-vmlab-data/runs /home/mani-vmlab-data/window /home/mani-vmlab-data/backend-control /home/mani-vmlab-data/workspace-jobs /var/lib/mani-vmlab-review
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
MemoryMax=256M
TasksMax=64
LimitCORE=0
TimeoutStopSec=5
KillMode=control-group
Restart=no
UMask=0077
'''


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF or len(sys.argv) != 1:
        raise SystemExit('Use the fixed protected installer, not a root agent.')
    trusted(SELF)
    trusted(SELF.parent, directory=True)
    trusted(PACK)
    # The independently prepared pack lock is installed and hash-reviewed with this helper.
    lock = SELF.with_name('runtime-source.sha256')
    trusted(lock)
    expected = lock.read_text().strip()
    payload = validated_pack(PACK, expected)
    for name in ('qemu-system-x86_64', 'qemu-img', 'cloud-localds'):
        path = Path('/usr/bin')/name
        if not path.is_file():
            raise RuntimeError('required_native_package_missing:'+name)
        trusted(path.resolve())
    if not os.access('/dev/kvm', os.R_OK|os.W_OK):
        raise RuntimeError('KVM_access_missing')
    if sha256(IMAGE) != IMAGE_SHA or IMAGE.is_symlink():
        raise ValueError('pinned_signed_image_mismatch')
    if (DATA/'runtime-root').exists() or (SELF.parent/'runtime-installed.json').exists():
        raise RuntimeError('preserve_prior_or_partial_installation_use_recorded_rollback')
    if INSTALL.exists():
        raise RuntimeError('preserve_existing_runtime_installation_use_reviewed_update')
    if CONFIG.exists() or UNIT.exists():
        raise RuntimeError('preserve_existing_native_configuration')
    register = {'source_pack_sha256': expected, 'image_sha256': IMAGE_SHA,
                'new_account': 'mani-vmlab-vm', 'new_unit': 'mani-vmlab-supervisor.service',
                'account_created': False, 'account_uid': None, 'installed_files': [],
                'installed_code': str(INSTALL), 'data': str(DATA), 'status': 'installing',
                'firewall_changed': False, 'packages_changed_by_this_installer': False,
                'normal_services_changed': False}
    checkpoint(register)
    try:
        install_files(payload, expected, register)
        register['status'] = 'installed'
    except BaseException:
        register['status'] = 'failed_partial_installation'
        raise
    finally:
        checkpoint(register)
    print(json.dumps(register, indent=2))


def install_files(payload, expected, register):
    os.umask(0o077)
    DATA.mkdir(mode=0o700, exist_ok=True)
    trusted(DATA, directory=True)
    (DATA/'bases').mkdir(mode=0o700, exist_ok=True)
    (DATA/'runs').mkdir(mode=0o700, exist_ok=True)
    for folder in (DATA/'bases', DATA/'runs'):
        trusted(folder, directory=True)
    try:
        account = pwd.getpwnam('mani-vmlab-vm')
        created_account = False
        if account.pw_uid in (0, 1000) or account.pw_dir != '/nonexistent' or account.pw_shell != '/usr/bin/nologin':
            raise RuntimeError('preserve_incompatible_existing_account')
    except KeyError:
        register['account_create_intent'] = True
        checkpoint(register)
        try:
            run(['/usr/bin/useradd', '--system', '--no-create-home', '--home-dir', '/nonexistent',
                 '--shell', '/usr/bin/nologin', '--user-group', 'mani-vmlab-vm'])
        finally:
            try:
                account = pwd.getpwnam('mani-vmlab-vm')
            except KeyError:
                account = None
            if account is not None:
                register.update(account_created=True, account_uid=account.pw_uid)
                checkpoint(register)
        account = pwd.getpwnam('mani-vmlab-vm')
        created_account = True
    register.update(account_created=created_account, account_uid=account.pw_uid)
    checkpoint(register)
    for directory,mode in [(DATA/'workspace-jobs',0o700),(Path('/var/lib/mani-vmlab-review'),0o755)]:
        directory.mkdir(mode=mode,exist_ok=True);trusted(directory,directory=True)
    INSTALL.mkdir(mode=0o755)
    for name in sorted(EXPECTED_FILES):
        target = INSTALL/name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        target.write_bytes(payload[name])
        target.chmod(0o644)
        checkpoint(register)
    base = DATA/'bases/noble.qcow2'
    if base.exists():
        if base.is_symlink() or sha256(base) != IMAGE_SHA:
            raise ValueError('preserve_existing_base_image')
    else:
        with IMAGE.open('rb') as source, base.open('xb') as output:
            shutil.copyfileobj(source, output, 4*1024*1024)
            output.flush()
            os.fsync(output.fileno())
        if sha256(base) != IMAGE_SHA:
            raise ValueError('installed_base_image_hash_mismatch')
    os.chown(base, 0, account.pw_gid)
    base.chmod(0o440)
    runtime_root = DATA/'runtime-root'
    runtime_root.mkdir(mode=0o755, exist_ok=False)
    runtime_root.chmod(0o755)
    trusted(runtime_root, directory=True)
    for name in ('usr', 'vm', 'bases', 'control', 'dev', 'proc', 'sys', 'run', 'tmp', 'etc'):
        (runtime_root/name).mkdir(mode=0o755, exist_ok=True)
        (runtime_root/name).chmod(0o755)
    for name, target in [('bin', 'usr/bin'), ('sbin', 'usr/bin'), ('lib', 'usr/lib'), ('lib64', 'usr/lib')]:
        path = runtime_root/name
        if not path.exists():
            path.symlink_to(target)
    for name in ('disk.qcow2', 'seed'):
        (runtime_root/'vm'/name).touch(mode=0o600)
    (runtime_root/'bases/noble.qcow2').touch(mode=0o400)
    (runtime_root/'etc/passwd').write_text(f'mani-vmlab-vm:x:{account.pw_uid}:{account.pw_gid}:Dedicated lab VM:/nonexistent:/usr/bin/nologin\n')
    checkpoint(register)
    (runtime_root/'etc/group').write_text(f'mani-vmlab-vm:x:{account.pw_gid}:\n')
    config_dir = CONFIG
    config_dir.mkdir(mode=0o755, exist_ok=False)
    (config_dir/'config.json').write_text(json.dumps({'schema_version': 1, 'image_sha256': IMAGE_SHA,
                                                   'source_pack_sha256': expected, 'agents_enabled': False}))
    (config_dir/'config.json').chmod(0o644)
    unit = UNIT
    if unit.exists():
        raise RuntimeError('preserve_existing_supervisor_unit')
    unit.write_text(supervisor_service_text())
    unit.chmod(0o644)
    checkpoint(register)
    run(['/usr/bin/systemd-analyze', 'verify', str(unit)])
    run(['/usr/bin/systemctl', 'daemon-reload'])
    run(['/usr/bin/systemctl', 'start', unit.name])



if __name__ == '__main__':
    main()
