#!/usr/bin/python3
"""Fixed same-source Quickshell repair for the measured Qt upgrade mismatch.

Frozen package bytes only, no arbitrary package/path/command arguments. Preserve
the original AUR archive and install reason. No desktop or model service restart.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

SELF = Path('/usr/local/lib/mani-vmlab-setup/recover_desktop.py')
RECOVERY = Path('/home/mani-vmlab-data/maintenance-recovery')
STATE = Path('/var/lib/mani-vmlab-setup')
OLD = Path('/home/mani/.cache/yay/quickshell-git/quickshell-git-0.3.1.r14.gc6a5160-1-x86_64.pkg.tar.zst')
NEW = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/private-artifacts/desktop-recovery/packaging/quickshell-git-0.3.1.r14.gc6a5160-2-x86_64.pkg.tar.zst')
OLD_SHA = 'e6ec6b347f40062c28157368eab1e98f136fc4f8ae51ddf1e47dbe13644d560b'
NEW_SHA = 'acd561b7ed5896eb383871072722c3a1672a53f1520439ab975307a97e3b842e'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def checked(argv, timeout=30):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, env=ENV)
    if result.returncode:
        raise RuntimeError('fixed_desktop_operation_failed:'+Path(argv[0]).name+':'+result.stderr.decode(errors='replace')[-1200:])
    return result.stdout.decode().strip()


def preserve(source, expected):
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    target = RECOVERY/source.name
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 256*1024**2:
            raise ValueError('frozen_package_shape_required')
        with os.fdopen(fd, 'rb') as package:
            fd = None
            raw = package.read(256*1024**2+1)
            after = os.fstat(package.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError('source_package_changed')
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError('frozen_package_digest_mismatch')
        if target.exists():
            info = target.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):
                raise PermissionError('protected_recovery_archive_required')
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise RuntimeError('preserve_conflicting_recovery_archive')
        else:
            with target.open('xb') as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
        return target
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_protected_desktop_repair_only')
    for path in (SELF, SELF.parent, SELF.with_name('setup.py')):
        info = path.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise PermissionError('protected_repair_source_required')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SELF.parent))
    from setup import safe_directory, atomic_record
    os.close(safe_directory(RECOVERY))
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['apply', 'status'])
    operation = parser.parse_args().operation
    if operation == 'status':
        path = STATE/'desktop-repair.json'
        print(path.read_text() if path.exists() else json.dumps({'status': 'not_applied'}))
        return
    os.umask(0o077)
    current = checked(['/usr/bin/pacman', '-Q', 'quickshell-git'])
    if current != 'quickshell-git 0.3.1.r14.gc6a5160-1':
        raise RuntimeError('preserve_changed_desktop_package')
    if checked(['/usr/bin/pacman', '-Q', 'qt6-base']).split()[1] != '6.12.0-2':
        raise RuntimeError('Qt_version_drift_rebuild_again')
    old = preserve(OLD, OLD_SHA)
    new = preserve(NEW, NEW_SHA)
    if checked(['/usr/bin/pacman', '-Qp', str(new)]) != 'quickshell-git 0.3.1.r14.gc6a5160-2':
        raise RuntimeError('frozen_package_metadata_mismatch')
    atomic_record(STATE/'desktop-repair-prepared.json', {'old_archive': str(old), 'old_sha256': OLD_SHA,
                  'new_archive': str(new), 'new_sha256': NEW_SHA,
                  'source_commit': 'c6a516096dd84d5255b409482eb4bf740b952f88',
                  'local_Qt_moc_compatibility_patch': True, 'original_hardening_and_LTO': True})
    # Pacman must finish an in-flight transaction; no timeout/kill after install.
    with (RECOVERY/'desktop-install.log').open('xb') as output:
        outcome = subprocess.run(['/usr/bin/pacman', '-U', '--asdeps', '--noconfirm', str(new)],
                                 stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, env=ENV)
    if outcome.returncode:
        raise RuntimeError('desktop_package_transaction_failed_review_private_log')
    compatibility = checked(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--clear-groups',
                             '--no-new-privs', '/usr/bin/quickshell', '--private-check-compat'])
    result = {'status': 'installed', 'package': checked(['/usr/bin/pacman', '-Q', 'quickshell-git']),
              'Qt_compatibility_exit': 0, 'compatibility_output': compatibility,
              'source_commit': 'c6a516096dd84d5255b409482eb4bf740b952f88',
              'new_package_sha256': NEW_SHA, 'old_package_retained_sha256': OLD_SHA,
              'desktop_or_model_services_restarted': False, 'configuration_changed': False,
              'physical_desktop_and_reboot_unverified': True}
    atomic_record(STATE/'desktop-repair.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
