#!/usr/bin/python3
"""Fixed native setup operations. Run only an inspected root-owned copy with -I.

No shell, password handling, arbitrary paths, command arguments or model inputs.
Cache relocation preserves every selected archive/signature before releasing root
space. Package installation and firewall mutation are deliberately separate.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import sys
import time

DATA = Path('/home/mani-vmlab-data')
STATE = Path('/var/lib/mani-vmlab-setup')
CACHE = Path('/var/cache/pacman/pkg')
DB_LOCK = Path('/var/lib/pacman/db.lck')
SELF = Path('/usr/local/lib/mani-vmlab-setup/setup.py')
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'SYSTEMD_PAGER': 'cat', 'SYSTEMD_COLORS': '0'}
PACKAGE_FILE = re.compile(r'[A-Za-z0-9+_.:@-]+\.pkg\.tar\.(?:zst|xz|gz)(?:\.sig)?\Z')


def safe_directory(path, create=False, mode=0o700):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('invalid_fixed_directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, part in enumerate(path.parts[1:]):
            if create and index == len(path.parts) - 2:
                try:
                    os.mkdir(part, mode, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise PermissionError('directory_must_be_root_owned_and_protected')
        return fd
    except BaseException:
        os.close(fd)
        raise


def atomic_record(path, value):
    parent = safe_directory(path.parent)
    temporary = path.name + '.tmp'
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'w') as output:
            fd = None
            json.dump(value, output, sort_keys=True, allow_nan=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.rename(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def observed(argv, seconds=30, limit=262144):
    executable = Path('/usr/bin') / argv[0]
    resolved = executable.resolve(strict=True)
    info = resolved.stat()
    if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise PermissionError('untrusted_native_binary')
    process = subprocess.Popen([str(executable), *argv[1:]], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV, close_fds=True)
    outputs = {'out': bytearray(), 'error': bytearray()}
    deadline = time.monotonic() + seconds
    try:
        with selectors.DefaultSelector() as selector:
            for label, stream in [('out', process.stdout), ('error', process.stderr)]:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise TimeoutError('native_observation_timeout')
                for key, _ in selector.select(min(0.1, deadline - time.monotonic())):
                    chunk = os.read(key.fileobj.fileno(), 16384)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        outputs[key.data].extend(chunk)
                        if len(outputs[key.data]) > limit:
                            raise ValueError('native_output_limit')
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return {'exit': code, **{label: data.decode(errors='replace') for label, data in outputs.items()}}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()


def file_record(directory_fd, name):
    if not PACKAGE_FILE.fullmatch(name):
        raise ValueError('not_a_package_archive_or_signature')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('cache_entry_must_be_regular_unlinked_file')
        checksum = hashlib.sha256()
        while chunk := os.read(fd, 4 * 1024 * 1024):
            checksum.update(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('cache_entry_changed_during_hash')
        return {'name': name, 'device': after.st_dev, 'inode': after.st_ino, 'bytes': after.st_size,
                'mtime_ns': after.st_mtime_ns, 'sha256': checksum.hexdigest()}
    finally:
        os.close(fd)


@contextmanager
def package_lock():
    parent = safe_directory(DB_LOCK.parent)
    fd = None
    try:
        fd = os.open(DB_LOCK.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        identity = os.fstat(fd)
        os.write(fd, b'mani-vmlab-cache-relocation\n')
        os.fsync(fd)
        yield
    finally:
        if fd is not None:
            current = os.stat(DB_LOCK.name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise RuntimeError('package_lock_replaced_do_not_remove')
            os.unlink(DB_LOCK.name, dir_fd=parent)
            os.close(fd)
        os.close(parent)


def audit():
    checks = {}
    for label, argv in {
        'var': ['du', '-x', '-B1', '--max-depth=1', '/var'],
        'var_lib': ['du', '-x', '-B1', '--max-depth=1', '/var/lib'],
        'cache': ['du', '-x', '-B1', '--max-depth=1', '/var/cache'],
        'disk': ['df', '-B1', '/', '/home'],
        'journal_bytes': ['journalctl', '--disk-usage'],
        'pending_jobs': ['systemctl', 'list-jobs', '--no-pager', '--no-legend'],
        'cached_package_plan': ['pacman', '-Sp', '--print-format', '%n %v %s', 'qemu-system-x86', 'qemu-img', 'cloud-image-utils'],
        'cached_upgrades': ['pacman', '-Qu'],
        'nft_rules': ['nft', '-j', 'list', 'ruleset'],
    }.items():
        try:
            checks[label] = observed(argv)
        except (OSError, ValueError, TimeoutError) as error:
            checks[label] = {'exit': None, 'error': type(error).__name__}
    record = {'utc': datetime.now(timezone.utc).isoformat(), 'host_configuration_changed': False,
              'db_locked': DB_LOCK.exists(), 'checks': checks}
    atomic_record(STATE / 'audit.json', record)
    summary = {k: v for k, v in checks.items() if k != 'nft_rules'}
    nft = checks['nft_rules']
    summary['nft_rules_readable'] = nft['exit'] == 0
    if nft['exit'] == 0:
        chains = [item['chain'] for item in json.loads(nft['out']).get('nftables', []) if 'chain' in item]
        summary['input_base_policies'] = [{'family': chain.get('family'), 'policy': chain.get('policy')}
                                          for chain in chains if chain.get('hook') == 'input']
    return {'utc': record['utc'], 'db_locked': record['db_locked'], 'observations': summary,
            'raw_root_private_audit': str(STATE / 'audit.json')}


def cache_plan():
    if DB_LOCK.exists():
        raise RuntimeError('package_transaction_active')
    directory = safe_directory(CACHE)
    try:
        records = [file_record(directory, name) for name in sorted(os.listdir(directory)) if PACKAGE_FILE.fullmatch(name)]
    finally:
        os.close(directory)
    plan = {'operation': 'preserve_all_cached_archives_and_signatures', 'entries': records,
            'bytes': sum(item['bytes'] for item in records), 'target': str(DATA / 'package-cache'),
            'excluded': 'partial downloads, subdirectories, journals, flatpak, Docker and all unrelated data'}
    atomic_record(STATE / 'cache-plan.json', plan)
    return {'archive_and_signature_files': len(records), 'bytes': plan['bytes'], 'target': plan['target'],
            'source_deleted': False, 'retained_versions': 'all', 'plan_sha256': hashlib.sha256((STATE/'cache-plan.json').read_bytes()).hexdigest()}


def copy_exact(source_fd, destination_fd, record):
    name = record['name']
    actual = file_record(source_fd, name)
    if actual != record:
        raise RuntimeError('planned_source_identity_changed')
    try:
        existing = file_record(destination_fd, name)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing['sha256'] != record['sha256'] or existing['bytes'] != record['bytes']:
            raise RuntimeError('preserve_conflicting_destination')
        return
    input_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source_fd)
    output_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=destination_fd)
    try:
        with os.fdopen(input_fd, 'rb') as source, os.fdopen(output_fd, 'wb') as output:
            shutil.copyfileobj(source, output, 4 * 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        # Incomplete destination remains for inspection; no source is deleted.
        raise
    copy = file_record(destination_fd, name)
    if copy['sha256'] != record['sha256'] or copy['bytes'] != record['bytes']:
        raise RuntimeError('copied_archive_integrity_failed')


def relocate_cache(commit=False):
    plan = json.loads((STATE / 'cache-plan.json').read_text())
    if shutil.disk_usage('/home').free < plan['bytes'] + 2 * 1024**3:
        raise RuntimeError('home_reserve_insufficient')
    os.close(safe_directory(DATA, create=True))
    destination = safe_directory(DATA / 'package-cache', create=True)
    source = safe_directory(CACHE)
    try:
        with package_lock():
            for record in plan['entries']:
                try:
                    actual = file_record(source, record['name'])
                except FileNotFoundError:
                    if not commit:
                        raise
                    copy = file_record(destination, record['name'])
                    if copy['sha256'] != record['sha256']:
                        raise RuntimeError('missing_source_and_backup_mismatch')
                    continue
                if actual != record:
                    raise RuntimeError('cache_plan_stale')
                copy_exact(source, destination, record)
            os.fsync(destination)
            if commit:
                # Every entry has been copied and independently hashed before any unlink.
                removed = 0
                for record in plan['entries']:
                    try:
                        actual = file_record(source, record['name'])
                    except FileNotFoundError:
                        continue
                    copy = file_record(destination, record['name'])
                    if actual != record or copy['sha256'] != record['sha256']:
                        raise RuntimeError('refuse_changed_source_or_backup')
                    os.unlink(record['name'], dir_fd=source)
                    removed += record['bytes']
                os.fsync(source)
                atomic_record(STATE / 'cache-relocated.json', {'bytes_released': removed, 'all_versions_retained': True})
                return {'bytes_released': removed, 'all_versions_retained': True}
            return {'copied_and_verified': len(plan['entries']), 'source_deleted': False}
    finally:
        os.close(source)
        os.close(destination)


def restore_cache():
    plan = json.loads((STATE / 'cache-plan.json').read_text())
    if shutil.disk_usage('/').free < plan['bytes'] + 512 * 1024**2:
        raise RuntimeError('root_space_insufficient_for_full_cache_restore')
    backup = safe_directory(DATA / 'package-cache')
    original = safe_directory(CACHE)
    try:
        with package_lock():
            for planned in plan['entries']:
                saved = file_record(backup, planned['name'])
                if (saved['sha256'], saved['bytes']) != (planned['sha256'], planned['bytes']):
                    raise RuntimeError('cache_backup_changed')
                copy_exact(backup, original, saved)
            os.fsync(original)
        return {'restored_entries': len(plan['entries']), 'backups_retained': True,
                'installed_packages_changed': False}
    finally:
        os.close(backup)
        os.close(original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['audit', 'cache-plan', 'cache-copy', 'cache-commit', 'cache-restore'])
    operation = parser.parse_args().operation
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('Use the exact protected native setup copy, never a root agent.')
    parent = safe_directory(SELF.parent)
    info = os.stat(SELF.name, dir_fd=parent, follow_symlinks=False)
    os.close(parent)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit('Setup copy must be root-owned and immutable to operators.')
    os.umask(0o077)
    os.chdir('/')
    os.close(safe_directory(STATE, create=True))
    lock = os.open(STATE/'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if operation == 'audit':
            result = audit()
        elif operation == 'cache-plan':
            result = cache_plan()
        elif operation == 'cache-restore':
            result = restore_cache()
        else:
            result = relocate_cache(operation == 'cache-commit')
        print(json.dumps(result, indent=2))
    finally:
        os.close(lock)


if __name__ == '__main__':
    main()
