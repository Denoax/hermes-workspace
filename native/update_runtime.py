#!/usr/bin/python3
"""Fixed protected runtime update, only after recorded fleet teardown.

Freeze/inspect an exact source pack and lock before installing this helper.
Previous source bytes and the installation register are retained for recovery.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

SELF = Path('/usr/local/lib/mani-vmlab-setup/update_runtime.py')
INSTALL = Path('/usr/local/lib/mani-vmlab')
REGISTER = SELF.with_name('runtime-installed.json')
PACK = Path('/var/lib/mani-vmlab-setup/runtime-source.zip')
LOCK = SELF.with_name('runtime-source.sha256')
DATA = Path('/home/mani-vmlab-data')
UNIT = 'mani-vmlab-supervisor.service'


def trusted(path):
    info = path.lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
        raise PermissionError('root_protected_update_required')


def run(argv):
    subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30,
                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})


def recover_no_agent_socket(control, run_id):
    """Adopt only a stopped failed-boot socket in its recorded owned directory.

    Older source pinned sockets after SSH health. Never adopt agent-run artifacts,
    extra files, changed directories, symlinks, or artifacts of live units.
    """
    manifest = control.store.read(run_id)
    if manifest['status'] != 'revoked' or manifest.get('control_verified') or manifest.get('execution_kind') != 'real_no_agent_VM':
        return
    for unit in manifest.get('units', []):
        if unit not in [f'mani-vmlab-{run_id}-{role}.service' for role in ('controller', 'worker_a', 'worker_b')]:
            raise ValueError('unregistered_recovery_unit')
        pid = subprocess.check_output(['/usr/bin/systemctl', 'show', unit, '-p', 'MainPID', '--value'], timeout=5)
        if int(pid.strip() or b'0') != 0:
            raise RuntimeError('preserve_live_unit_artifacts')
    for entry in manifest.get('control_dirs', []):
        if 'socket_inode' in entry:
            continue
        if entry['name'] not in ('controller-control', 'worker_a-control', 'worker_b-control'):
            raise ValueError('invalid_recorded_recovery_directory')
        directory = control.store.directory(run_id)/entry['name']
        if not directory.exists():
            continue
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (entry['device'], entry['inode']):
            raise RuntimeError('preserve_changed_control_directory')
        socket_path = directory/'ssh.sock'
        contents = list(directory.iterdir())
        if not contents:
            continue
        info = socket_path.lstat()
        if contents != [socket_path] or not stat.S_ISSOCK(info.st_mode) or info.st_uid != control.vm_account.pw_uid:
            raise RuntimeError('preserve_unknown_failed_boot_artifact')
        def record_socket(m):
            row = next(row for row in m['control_dirs'] if row['name'] == entry['name'])
            row.update(socket_device=info.st_dev, socket_inode=info.st_ino, recovered_after_failed_no_agent_boot=True)
        control.store.mutate(run_id, record_socket)


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_protected_update_only')
    for path in (SELF, SELF.parent, REGISTER, INSTALL, PACK, LOCK):
        trusted(path)
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['apply', 'resume', 'diagnose'])
    operation = parser.parse_args().operation
    if operation == 'diagnose':
        diagnostics = []
        for directory in sorted((DATA/'runs').iterdir(), key=lambda p: p.stat().st_mtime_ns)[-3:]:
            if directory.is_dir() and len(directory.name) == 32 and all(c in '0123456789abcdef' for c in directory.name):
                record = json.loads((directory/'manifest.json').read_text())
                diagnostics.append({'run': directory.name, 'status': record['status'],
                                    'private_qualification_failure': record.get('private_qualification_failure')})
        changed = []
        for item in json.loads(REGISTER.read_text())['installed_files']:
            path = Path(item['path'])
            info = path.stat()
            if (info.st_dev, info.st_ino) != (item['device'], item['inode']) or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                changed.append(str(path))
        print(json.dumps({'diagnostics': diagnostics, 'changed_registered_files':changed}))
        return
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SELF.parent))
    from install_runtime import validated_pack, checkpoint, sha256, supervisor_service_text, EXPECTED_FILES
    expected = LOCK.read_text().strip()
    payload = validated_pack(PACK, expected)
    record = json.loads(REGISTER.read_text())
    resume = operation == 'resume'
    if record['status'] != ('failed_partial_update' if resume else 'installed'):
        raise RuntimeError('recover_partial_install_before_update')
    if resume:
        if record.get('pending_source_pack_sha256', expected) != expected:
            raise RuntimeError('resume_requires_same_frozen_source_pack')
        config = json.loads(Path('/etc/mani-vmlab/config.json').read_text())
        if config['source_pack_sha256'] not in (record['source_pack_sha256'],expected):
            raise RuntimeError('partial_configuration_requires_separate_recovery')
        if int(subprocess.check_output(['/usr/bin/systemctl','show',UNIT,'-p','MainPID','--value'],timeout=5).strip() or b'0') != 0:
            raise RuntimeError('preserve_live_partial_runtime')
    generated = []
    for item in record['installed_files']:
        path = Path(item['path'])
        trusted(path)
        if path.suffix == '.pyc' and path.parent.name == '__pycache__' and path.is_relative_to(INSTALL):
            source = Path(importlib.util.source_from_cache(str(path)))
            if str(source.relative_to(INSTALL)) not in EXPECTED_FILES:
                raise RuntimeError('preserve_unknown_generated_cache')
            generated.append(path)
            continue
        info = path.stat()
        if (info.st_dev, info.st_ino) != (item['device'], item['inode']) or sha256(path) != item['sha256']:
            raise RuntimeError('preserve_changed_installation_before_update')
    # Root helper imports generated these caches; they are not installed source.
    # Preserve exact bytes outside the import path before loading trusted code.
    if generated:
        quarantine = DATA/'runtime-versions'/('generated-bytecode-'+hashlib.sha256(REGISTER.read_bytes()).hexdigest())
        quarantine.mkdir(mode=0o700, exist_ok=False)
        for path in generated:
            target = quarantine/path.relative_to(INSTALL)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if sha256(target) != sha256(path):
                raise RuntimeError('generated_bytecode_preservation_failed')
            path.unlink()
        record['generated_bytecode_quarantine'] = str(quarantine)
        checkpoint(record)
    # Teardown uses the current immutable trusted installation, before replacing
    # any imported code. The operator/model never supplies a PID, unit or path.
    sys.path.insert(0, str(INSTALL))
    import supervisor
    supervisor.initialize_imports()
    control = supervisor.Supervisor()
    for directory in control.store.root.iterdir():
        if directory.is_dir():
            control.stop(directory.name, 'source_update_teardown')
            recover_no_agent_socket(control, directory.name)
            if control.cleanup(directory.name)['status'] != 'ok':
                raise RuntimeError('owned_fleet_cleanup_incomplete')
    versions = DATA/'runtime-versions'
    versions.mkdir(mode=0o700, exist_ok=True)
    trusted(versions)
    backup = versions/(record['source_pack_sha256']+'-'+hashlib.sha256(REGISTER.read_bytes()).hexdigest()[:16])
    if resume:
        backups = [p for p in versions.iterdir() if p.name.startswith(record['source_pack_sha256']+'-')]
        if not backups or not all(json.loads((p/'runtime-installed.json').read_text())['status']=='installed' for p in backups):
            raise RuntimeError('verified_prior_installation_backup_required')
    else:
        backup.mkdir(mode=0o700, exist_ok=False)
        shutil.copytree(INSTALL, backup/'source', symlinks=False)
        shutil.copy2(REGISTER, backup/'runtime-installed.json')
        shutil.copy2('/etc/mani-vmlab/config.json', backup/'config.json')
        shutil.copy2('/etc/systemd/system/mani-vmlab-supervisor.service', backup/'supervisor.service')
    run(['/usr/bin/systemctl', 'stop', UNIT])
    record['status'] = 'updating'
    record['pending_source_pack_sha256'] = expected
    checkpoint(record)
    try:
        for name, raw in sorted(payload.items()):
            target = INSTALL/name
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            trusted(target.parent)
            temporary = target.with_name(target.name+'.new')
            with temporary.open('xb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o644)
            temporary.replace(target)
            checkpoint(record)
        config_path = Path('/etc/mani-vmlab/config.json')
        config = json.loads(config_path.read_text())
        config['source_pack_sha256'] = expected
        config_path.write_text(json.dumps(config))
        unit_path = Path('/etc/systemd/system')/UNIT
        unit_path.write_text(supervisor_service_text())
        run(['/usr/bin/systemd-analyze', 'verify', str(unit_path)])
        run(['/usr/bin/systemctl', 'daemon-reload'])
        record['source_pack_sha256'] = expected
        record['status'] = 'installed'
        record.pop('pending_source_pack_sha256', None)
        checkpoint(record)
        run(['/usr/bin/systemctl', 'start', UNIT])
    except BaseException:
        record['status'] = 'failed_partial_update'
        checkpoint(record)
        raise
    print(json.dumps({'status': 'updated', 'source_pack_sha256': expected, 'previous_source_retained': True,
                      'normal_services_changed': False, 'firewall_changed': False}))


if __name__ == '__main__':
    main()
