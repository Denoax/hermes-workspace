"""Remove only a recorded installation; retain bases, cache backups and evidence."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

SELF = Path('/usr/local/lib/mani-vmlab-setup/rollback_runtime.py')
REGISTER = SELF.with_name('runtime-installed.json')
INSTALL = Path('/usr/local/lib/mani-vmlab')
CONFIG = Path('/etc/mani-vmlab')
RUNTIME_ROOT = Path('/home/mani-vmlab-data/runtime-root')
UNIT = Path('/etc/systemd/system/mani-vmlab-supervisor.service')


def permitted_file(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        return False
    return path == UNIT or any(path.is_relative_to(root) for root in (INSTALL, CONFIG, RUNTIME_ROOT))


def run(command):
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
    if result.returncode:
        raise RuntimeError('native_rollback_operation_failed:'+Path(command[0]).name)
    return result.stdout


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF or sys.argv[1:] not in ([], ['--apply']):
        raise SystemExit('fixed_protected_rollback_only')
    for path in (SELF, REGISTER):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('protected_rollback_record_required')
    record = json.loads(REGISTER.read_text())
    files = record['installed_files']
    if any(not permitted_file(item['path']) for item in files):
        raise ValueError('unregistered_rollback_target')
    for item in files:
        path = Path(item['path'])
        if not path.exists():
            continue
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (item['device'], item['inode']) or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('preserve_changed_installed_file:'+path.name)
    if not sys.argv[1:]:
        print(json.dumps({'dry_run': True, 'files': [item['path'] for item in files],
                          'remove_created_account': record['account_created'],
                          'retain': ['cache backups', 'base image', 'run evidence', 'setup helper records']}))
        return
    loaded = run(['/usr/bin/systemctl', 'show', UNIT.name, '-p', 'LoadState', '--value']).decode().strip()
    if loaded != 'not-found':
        run(['/usr/bin/systemctl', 'stop', UNIT.name])
    # Import only the installed hash-checked trusted supervisor to stop/clean exact
    # recorded runs. Never recursively remove a caller-selected directory.
    runs = Path('/home/mani-vmlab-data/runs')
    if runs.exists() and any(path.is_dir() for path in runs.iterdir()):
        # A partial installation with no runs needs no runtime imports. Existing
        # runs require the complete recorded supervisor, or recovery fails closed.
        sys.path.insert(0, str(INSTALL))
        import supervisor
        supervisor.initialize_imports()
        control = supervisor.Supervisor()
        for directory in control.store.root.iterdir():
            if directory.is_dir():
                result = control.cleanup(directory.name)
                if result['status'] != 'ok':
                    raise RuntimeError('registered_run_cleanup_not_complete')
    for item in files:
        Path(item['path']).unlink(missing_ok=True)
    # Only fixed installed-root symlinks and now-empty directories are retired.
    for name, target in [('bin', 'usr/bin'), ('sbin', 'usr/bin'), ('lib', 'usr/lib'), ('lib64', 'usr/lib')]:
        path = RUNTIME_ROOT/name
        if path.is_symlink() and os.readlink(path) == target:
            path.unlink()
    for root in (INSTALL, CONFIG, RUNTIME_ROOT):
        if not root.exists():
            continue
        directories = sorted((path for path in root.rglob('*') if path.is_dir() and not path.is_symlink()),
                             key=lambda path: len(path.parts), reverse=True)
        for directory in directories:
            directory.rmdir()
        root.rmdir()
    run(['/usr/bin/systemctl', 'daemon-reload'])
    if record['account_created']:
        try:
            account = pwd.getpwnam('mani-vmlab-vm')
        except KeyError:
            account = None
        if account is not None:
            if account.pw_uid != record['account_uid'] or account.pw_dir != '/nonexistent' or account.pw_shell != '/usr/bin/nologin':
                raise RuntimeError('preserve_changed_account')
            processes = subprocess.run(['/usr/bin/ps', '-u', str(account.pw_uid), '-o', 'pid='],
                                       capture_output=True, timeout=5, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            if processes.returncode not in (0, 1):
                raise RuntimeError('cannot_verify_account_process_exit')
            if processes.stdout.strip():
                raise RuntimeError('account_has_remaining_processes')
            run(['/usr/bin/userdel', 'mani-vmlab-vm'])
    record['status'] = 'removed_recorded_runtime'
    REGISTER.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'status': 'removed_recorded_runtime', 'bases_cache_and_evidence_retained': True,
                      'normal_services_changed': False}))


if __name__ == '__main__':
    main()
