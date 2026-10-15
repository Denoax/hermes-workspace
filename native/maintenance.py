#!/usr/bin/python3
"""Fixed full Arch maintenance; preserve signed downgrade artifacts first.

Run an inspected root-owned copy with -I. There is no arbitrary command/path
interface and no model input. A failed download/plan check never starts install.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from urllib.parse import quote

SELF = Path('/usr/local/lib/mani-vmlab-setup/maintenance.py')
STATE = Path('/var/lib/mani-vmlab-setup')
DATA = Path('/home/mani-vmlab-data')
CACHE = DATA/'package-cache'
DOWNLOAD_CACHE = Path('/home/mani-vmlab-package-downloads')
RECOVERY = DATA/'maintenance-recovery'
PLAN = STATE/'maintenance-plan.json'
PLAN_SHA = '9b9db0ac8c7d03b539c157cefaaa2d11b6db4cf3c33b23076caa3b80afcb613b'
TARGETS = ('qemu-system-x86', 'qemu-img', 'cloud-image-utils')
TOKEN = re.compile(r'[A-Za-z0-9+_.:@-]+\Z')
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'SYSTEMD_PAGER': 'cat'}


def checked(argv, seconds=60, limit=1048576):
    result = observed([Path(argv[0]).name, *argv[1:]], seconds=seconds, limit=limit)
    if result['exit']:
        raise RuntimeError('native_command_failed:'+Path(argv[0]).name+':'+result['error'][-1500:])
    return result['out']


def installed():
    return checked(['/usr/bin/pacman', '-Q']).encode()


def plan():
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA:
        raise RuntimeError('reviewed_plan_digest_mismatch')
    result = json.loads(raw)
    for row in result['complete_transaction']:
        if not TOKEN.fullmatch(row['package']) or not TOKEN.fullmatch(row['version']):
            raise ValueError('invalid_package_plan')
    if hashlib.sha256(installed()).hexdigest() != result['installed_inventory_sha256']:
        raise RuntimeError('installed_inventory_changed_replan_before_maintenance')
    return result


def download(url, destination, maximum=2*1024**3):
    # Only caller-built official archive URLs, never caller/model URLs.
    temporary = destination.with_name(destination.name+'.download')
    if temporary.exists():
        raise RuntimeError('preserve_previous_partial_recovery_download')
    with urllib.request.urlopen(url, timeout=30) as source, temporary.open('xb') as output:
        deadline = time.monotonic()+600
        size = 0
        while chunk := source.read(1024*1024):
            size += len(chunk)
            if size > maximum or time.monotonic() > deadline:
                raise RuntimeError('recovery_download_limit')
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    temporary.rename(destination)


def archive_names(name, version):
    if not TOKEN.fullmatch(name) or not TOKEN.fullmatch(version):
        raise ValueError('invalid_package_identity')
    # Arch repository FILENAME preserves the epoch (e.g. docker-1:29.8.2-1).
    return [name+'-'+version+'-'+arch+'.pkg.tar.zst' for arch in ('x86_64', 'any')]


def recovery_archive(name, version):
    prefix = name+'-'+version+'-'
    candidates = sorted(p for p in CACHE.iterdir() if p.name.startswith(prefix)
                        and re.fullmatch(re.escape(prefix)+r'(?:x86_64|any)\.pkg\.tar\.(?:zst|xz)', p.name))
    if not candidates:
        for filename in archive_names(name, version):
            target = CACHE/filename
            url = 'https://archive.archlinux.org/packages/'+name[0]+'/'+name+'/'+quote(filename, safe='')
            try:
                download(url, target)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    continue
                raise
            candidates = [target]
            break
    if not candidates:
        raise RuntimeError('old_installed_package_unavailable:'+name)
    for target in candidates:
        fd = safe_directory(CACHE)
        try:
            record = file_record(fd, target.name)
        finally:
            os.close(fd)
        signature = target.with_name(target.name+'.sig')
        if not signature.exists():
            download('https://archive.archlinux.org/packages/'+name[0]+'/'+name+'/'+quote(signature.name, safe=''),
                     signature, maximum=65536)
        fd = safe_directory(CACHE)
        try:
            sig_record = file_record(fd, signature.name)
        finally:
            os.close(fd)
        checked(['/usr/bin/pacman-key', '--verify', str(signature), str(target)], seconds=30)
        metadata = checked(['/usr/bin/pacman', '-Qp', str(target)]).strip().split()
        if metadata == [name, version]:
            return {'package': name, 'version': version, 'archive': record,
                    'signature': sig_record, 'signature_verified': True}
    raise RuntimeError('old_package_metadata_mismatch:'+name)


def prepare():
    expected = plan()
    if Path('/var/lib/pacman/db.lck').exists():
        raise RuntimeError('package_transaction_active')
    safe = safe_directory(RECOVERY, create=True)
    os.close(safe)
    # Pacman's unprivileged DownloadUser needs a traversable, separate cache.
    # Public signed packages go here; private backups remain under DATA (0700).
    download_fd = safe_directory(DOWNLOAD_CACHE, create=True, mode=0o755)
    try:
        os.fchmod(download_fd, 0o755)
    finally:
        os.close(download_fd)
    database = RECOVERY/'package-db.tar'
    inventory = installed()
    current = dict(line.split() for line in inventory.decode().splitlines())
    if not database.exists():
        with package_lock():
            checked(['/usr/bin/tar', '-cpf', str(database), '-C', '/var/lib/pacman', 'local', 'sync',
                     '-C', '/etc', 'pacman.conf', 'pacman.d'], seconds=120)
            atomic_record(RECOVERY/'inventory.json', {'inventory': inventory.decode(),
                          'sha256': hashlib.sha256(inventory).hexdigest()})
    recorded_inventory = json.loads((RECOVERY/'inventory.json').read_text())
    if recorded_inventory['sha256'] != expected['installed_inventory_sha256']:
        raise RuntimeError('preserve_recovery_for_other_inventory')
    recovery = []
    for row in expected['existing_package_upgrades']:
        recovery.append(recovery_archive(row['package'], current[row['package']]))
        atomic_record(STATE/'maintenance-preparation-progress.json', {'signed_old_packages': len(recovery),
                      'required': len(expected['existing_package_upgrades'])})
        print(json.dumps({'recovery_progress': len(recovery), 'required': len(expected['existing_package_upgrades'])}), flush=True)
    record = {'schema_version': 1, 'prepared_unix': time.time(), 'reviewed_plan_sha256': PLAN_SHA,
              'inventory_sha256': hashlib.sha256(inventory).hexdigest(), 'database_backup': str(database),
              'database_backup_sha256': sha256(database), 'signed_old_packages': recovery,
              'new_packages': [r['package'] for r in expected['complete_transaction'] if r['package'] not in current],
              'installation_performed': False, 'automatic_reboot': False,
              'rollback_requires_native_console_and_coherent_pacman_U': True}
    atomic_record(STATE/'maintenance-prepared.json', record)
    return {'status': 'prepared', 'signed_old_packages': len(recovery), 'all_upgrades_covered': True,
            'database_backup_sha256': record['database_backup_sha256'], 'plan_sha256': PLAN_SHA}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(4*1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def transaction(argv, log):
    # Never kill pacman on a timeout: an in-flight package transaction must finish.
    # This fixed native process owns only pacman; it is not an interactive root agent.
    log = log.with_name(log.stem+'-'+str(time.time_ns())+'.log')
    with log.open('xb') as output:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                env=ENV, close_fds=True)
        output.flush()
        os.fsync(output.fileno())
    if result.returncode:
        raise RuntimeError('pacman_failed_log:'+str(log))


def apply():
    expected = plan()
    prepared = json.loads((STATE/'maintenance-prepared.json').read_text())
    if prepared['reviewed_plan_sha256'] != PLAN_SHA:
        raise RuntimeError('prepare_matching_rollback_first')
    for row in prepared['signed_old_packages']:
        for key in ('archive', 'signature'):
            if sha256(CACHE/row[key]['name']) != row[key]['sha256']:
                raise RuntimeError('recovery_bytes_changed')
    if len(prepared['signed_old_packages']) != len(expected['existing_package_upgrades']):
        raise RuntimeError('incomplete_rollback_coverage')
    if shutil.disk_usage('/').free < 4*1024**3 or Path('/var/lib/pacman/db.lck').exists():
        raise RuntimeError('root_storage_or_package_lock_not_ready')
    # Download/sync does not install any package. Resolve the complete full upgrade
    # against those actual databases before installing; repository drift fails closed.
    transaction(['/usr/bin/pacman', '--cachedir', str(DOWNLOAD_CACHE), '-Syuw', '--needed', '--noconfirm', *TARGETS],
                RECOVERY/'download.log')
    actual = checked(['/usr/bin/pacman', '-Sup', '--print-format', '%n %v', *TARGETS])
    actual_set = set(tuple(line.split()) for line in actual.splitlines())
    expected_set = {(r['package'], r['version']) for r in expected['complete_transaction']}
    if actual_set != expected_set:
        atomic_record(STATE/'maintenance-drift.json', {'actual': sorted(actual_set), 'expected': sorted(expected_set),
                      'installation_performed': False})
        raise RuntimeError('repository_transaction_drift_replan_before_any_install')
    if hashlib.sha256(installed()).hexdigest() != prepared['inventory_sha256']:
        raise RuntimeError('installed_inventory_drift')
    atomic_record(STATE/'maintenance-started.json', {'plan_sha256': PLAN_SHA, 'unix': time.time()})
    transaction(['/usr/bin/pacman', '--cachedir', str(DOWNLOAD_CACHE), '-Su', '--needed', '--noconfirm', *TARGETS],
                RECOVERY/'install.log')
    after = installed().decode()
    current = dict(line.split() for line in after.splitlines())
    if any(current.get(r['package']) != r['version'] for r in expected['complete_transaction']):
        raise RuntimeError('installed_transaction_not_matching_plan')
    record = {'status': 'installed', 'plan_sha256': PLAN_SHA, 'unix': time.time(),
              'complete_transaction': expected['complete_transaction'], 'existing_upgrades': len(expected['existing_package_upgrades']),
              'normal_service_configuration_changed_by_helper': False, 'automatic_reboot': False,
              'post_inventory_sha256': hashlib.sha256(after.encode()).hexdigest()}
    atomic_record(STATE/'maintenance-completed.json', record)
    return record


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_protected_helper_only')
    sys.path.insert(0, str(SELF.parent))
    global safe_directory, atomic_record, observed, file_record, package_lock
    from setup import safe_directory, atomic_record, observed, file_record, package_lock
    for path in (SELF.parent, STATE, CACHE):
        os.close(safe_directory(path))
    for path in (SELF, SELF.with_name('setup.py'), PLAN):
        info = path.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or not path.is_file() or path.is_symlink():
            raise PermissionError('protected_source_and_plan_required')
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['prepare', 'apply', 'status'])
    operation = parser.parse_args().operation
    if operation == 'status':
        result = {}
        for name in ('prepared', 'completed', 'drift'):
            path = STATE/('maintenance-'+name+'.json')
            if path.exists():
                value = json.loads(path.read_text())
                if name == 'prepared':
                    value['signed_old_packages'] = len(value['signed_old_packages'])
                result[name] = value
        result['logs'] = []
        for path in sorted(RECOVERY.glob('*.log'), key=lambda p: p.stat().st_mtime_ns)[-3:]:
            with path.open('rb') as source:
                source.seek(max(0, path.stat().st_size-6000))
                tail = source.read(6000).decode(errors='replace')
            result['logs'].append({'name': path.name, 'tail': tail})
    else:
        result = prepare() if operation == 'prepare' else apply()
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
