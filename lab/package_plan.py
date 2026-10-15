"""Fresh Arch transaction planning in an isolated local DB; no host DB changes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

PACKAGES = ('qemu-system-x86', 'qemu-img', 'cloud-image-utils')
MIRROR = 'https://fastly.mirror.pkgbuild.com'


def inventory():
    result = subprocess.run(['/usr/bin/pacman', '-Q'], capture_output=True, check=True, timeout=15)
    return result.stdout


def fresh_plan(directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    database = directory/'db'
    database.mkdir(mode=0o700)
    (database/'sync').mkdir(mode=0o700)
    before = inventory()
    shutil.copytree('/var/lib/pacman/local', database/'local', symlinks=False)
    configured = subprocess.run(['/usr/bin/pacman-conf', '--repo-list'], capture_output=True, check=True, timeout=5).stdout.decode().splitlines()
    if not set(configured) <= {'core', 'extra', 'multilib'} or not {'core', 'extra'} <= set(configured):
        raise RuntimeError('nonstandard_repositories_require_separate_review')
    records = []
    for repository in configured:
        url = f'{MIRROR}/{repository}/os/x86_64/{repository}.db'
        with urllib.request.urlopen(url, timeout=30) as source:
            raw = source.read(64*1024*1024+1)
        if len(raw) > 64*1024*1024:
            raise ValueError('repository_metadata_limit')
        path = database/'sync'/(repository+'.db')
        path.write_bytes(raw)
        records.append({'repository': repository, 'url': url, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'planning_only_TLS_metadata': True})
    command = ['/usr/bin/pacman', '--dbpath', str(database), '--logfile', str(directory/'planning.log'),
               '-Sup', '--print-format', '%n %v %s', *PACKAGES]
    result = subprocess.run(command, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('fresh_full_transaction_resolution_failed:'+result.stderr.decode()[:2000])
    if inventory() != before:
        raise RuntimeError('installed_inventory_changed_during_planning')
    lines = result.stdout.decode().splitlines()
    entries = []
    for line in lines:
        fields = line.split()
        if len(fields) != 3 or not fields[2].isdigit():
            raise ValueError('unexpected_package_plan_output')
        entries.append({'package': fields[0], 'version': fields[1], 'download_bytes': int(fields[2])})
    installed = {line.split()[0]: line.split()[1] for line in before.decode().splitlines()}
    upgrades = [row for row in entries if row['package'] in installed and installed[row['package']] != row['version']]
    record = {'observed_unix_seconds': time.time(), 'host_package_database_changed': False,
              'installed_inventory_sha256': hashlib.sha256(before).hexdigest(), 'repository_records': records,
              'complete_transaction': entries, 'existing_package_upgrades': upgrades,
              'download_bytes': sum(row['download_bytes'] for row in entries),
              'installation_performed': False, 'package_signature_verification_required_at_install': True,
              'native_install_command': ['/usr/bin/pacman', '-Syu', '--needed', *PACKAGES],
              'recovery_review_needed': bool(upgrades)}
    (directory/'plan.json').write_text(json.dumps(record, indent=2)+'\n')
    return record
