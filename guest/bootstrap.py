"""Trusted offline installation only; never imports or runs an agent as root."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import subprocess
import zipfile


def install():
    if os.geteuid() != 0 or sys.version_info[:2] != (3, 12):
        raise RuntimeError('pinned_guest_python_and_root_setup_required')
    marker = json.loads(Path('/etc/mani-vmlab/guest.json').read_text())
    artifact = Path('/mnt/mani-artifacts/runtime.zip')
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != marker['runtime_zip_sha256']:
        raise RuntimeError('guest_runtime_bytes_changed')
    with zipfile.ZipFile(artifact) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or sum(x.file_size for x in entries) > 400*1024*1024:
            raise ValueError('guest_runtime_inventory_limit')
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or path.parts[0] not in ('hermes', 'hermes-deps'):
                raise ValueError('guest_runtime_path_rejected')
            if entry.filename in names or entry.is_dir() or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('guest_runtime_entry_rejected')
            names.add(entry.filename)
            target = Path('/opt') / entry.filename
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(archive.read(entry))
            target.chmod(0o644)
    installed={
        'Hermes_revision': marker['Hermes_revision'],
        'runtime_zip_sha256': marker['runtime_zip_sha256'],
        'python': sys.version.split()[0], 'offline': True}
    compiler=Path('/mnt/mani-artifacts/compiler.zip')
    if marker.get('compiler_zip_sha256'):
        if hashlib.sha256(compiler.read_bytes()).hexdigest()!=marker['compiler_zip_sha256']:
            raise ValueError('offline_compiler_artifact_changed')
        with zipfile.ZipFile(compiler) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            expected={'manifest.json',*(x['file'] for x in manifest['packages'])}
            if set(archive.namelist())!=expected or len(archive.namelist())!=len(expected):raise ValueError('compiler_inventory_changed')
            files=[]
            Path('/tmp/mani-compiler').mkdir(mode=0o700,exist_ok=False)
            for item in manifest['packages']:
                name=item['file']
                if '/' in name or not name.endswith('.deb'):raise ValueError('compiler_package_path')
                raw=archive.read(name)
                if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('compiler_package_pin')
                path=Path('/tmp/mani-compiler')/name;path.write_bytes(raw);files.append(str(path))
            # Only missing compiler/development packages were selected against
            # the signed base's package inventory. Extract their authenticated
            # data without downgrading base runtime packages or running scripts.
            for package in files:
                subprocess.run(['/usr/bin/dpkg-deb','--extract',package,'/'],check=True,capture_output=True,timeout=20)
        subprocess.run(['/usr/sbin/useradd','-u','1001','-U','-M','-d','/nonexistent','-s','/usr/sbin/nologin','mani-candidate'],check=True,capture_output=True)
        path=Path('/etc/sudoers.d/mani-code')
        path.write_text('lab ALL=(root) NOPASSWD: /usr/bin/python3 -I /opt/mani-vmlab/run_code.py\nlab ALL=(root) NOPASSWD: /usr/bin/python3 -I /opt/mani-vmlab/lifecycle_probe.py\n');path.chmod(0o440)
        subprocess.run(['/usr/sbin/visudo','-cf',str(path)],check=True,capture_output=True)
        version=subprocess.check_output(['/usr/bin/g++','--version'],timeout=5).decode().splitlines()[0]
        installed.update(compiler_zip_sha256=marker['compiler_zip_sha256'],compiler=version,candidate_uid=1001,
                         compiler_installation='signed_missing_package_data_extract')
    Path('/etc/mani-vmlab/installed.json').write_text(json.dumps(installed))


if __name__ == '__main__':
    install()
