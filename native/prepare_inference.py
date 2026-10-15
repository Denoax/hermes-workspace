#!/usr/bin/python3
"""Preserve pinned model/runtime bytes in isolated lab storage, without loading."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
sys.dont_write_bytecode = True
import time

SELF = Path('/usr/local/lib/mani-vmlab-setup/prepare_inference.py')
DATA = Path('/home/mani-vmlab-data')
LOCK_SHA = '560a28dbe71b021887a8d6d546a4c128cd02ee99e8bce67a4ace506e5a7e19fa'


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(4*1024*1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def preserve(source, target, expected, mode, group):
    if target.exists():
        info = target.lstat()
        if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or digest(target) != expected['sha256']:
            raise RuntimeError('preserve_changed_lab_artifact:'+target.name)
        return
    descriptor = os.open(source, os.O_RDONLY|os.O_NOFOLLOW)
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size != expected['bytes']:
        os.close(descriptor)
        raise RuntimeError('frozen_artifact_size_mismatch')
    temporary = target.with_suffix(target.suffix+'.prepared')
    checksum = hashlib.sha256()
    started = time.monotonic()
    copied = 0
    with os.fdopen(descriptor, 'rb') as input_file, temporary.open('xb') as output:
        while chunk := input_file.read(4*1024*1024):
            output.write(chunk)
            checksum.update(chunk)
            copied += len(chunk)
            time.sleep(max(0, copied/(128*1024*1024)-(time.monotonic()-started)))
        after = os.fstat(input_file.fileno())
        output.flush()
        os.fsync(output.fileno())
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or checksum.hexdigest()!=expected['sha256']:
        temporary.unlink()
        raise RuntimeError('frozen_artifact_changed_during_copy')
    os.chown(temporary, 0, group)
    temporary.chmod(mode)
    temporary.replace(target)


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:
        raise SystemExit('fixed_native_artifact_preparation_only')
    sys.path.insert(0, str(SELF.parent))
    from install_runtime import trusted
    for path in (SELF, SELF.parent, SELF.with_name('install_runtime.py')):
        trusted(path)
    lock = SELF.with_name('backend-artifacts.lock.json')
    trusted(lock)
    if digest(lock)!=LOCK_SHA:
        raise RuntimeError('frozen_backend_inventory_changed')
    parser=argparse.ArgumentParser()
    parser.add_argument('operation', choices=('prepare','finalize','status'))
    operation=parser.parse_args().operation
    spec=json.loads(lock.read_text())
    group=pwd.getpwnam('mani-vmlab-vm').pw_gid
    record_path=Path('/var/lib/mani-vmlab-setup/inference-preparation.json')
    if operation=='prepare':
        for name in ('models','backend-b9980','backend-root','backend-control','window'):
            directory=DATA/name
            directory.mkdir(mode=0o700,exist_ok=True)
            trusted(directory,directory=True)
        (DATA/'backend-b9980').chmod(0o755)
        (DATA/'backend-root').chmod(0o755)
        os.chown(DATA/'backend-control',0,group)
        (DATA/'backend-control').chmod(0o770)
        for arm in ('normal','abliterated'):
            print('Preserving and hashing '+arm+' weights',flush=True)
            preserve(Path(spec['models'][arm]['source']),DATA/'models'/(arm+'.gguf'),spec['models'][arm],0o440,group)
        directory=Path(spec['backend_directory'])
        if directory!=Path('/home/mani/.local/lib/llama.cpp-b9980-vulkan'):
            raise ValueError('fixed_backend_directory_required')
        for item in spec['backend_files']:
            if '/' in item['name'] or item['name'] in ('.','..'):
                raise ValueError('fixed_backend_filename_required')
            source=(directory/item['name']).resolve()
            if source.parent!=directory:
                raise ValueError('backend_source_outside_pin')
            preserve(source,DATA/'backend-b9980'/item['name'],item,0o755 if item['name']=='llama-server' else 0o644,0)
        root=DATA/'backend-root'
        for name in ('usr','dev','proc','tmp','model','backend','control','etc'):
            (root/name).mkdir(mode=0o755,exist_ok=True)
        for name,target in (('lib','usr/lib'),('lib64','usr/lib'),('bin','usr/bin'),('sbin','usr/bin')):
            p=root/name
            if not p.exists() and not p.is_symlink():p.symlink_to(target)
            if not p.is_symlink() or os.readlink(p)!=target:raise RuntimeError('preserve_changed_backend_root')
        (root/'model/weights.gguf').touch(mode=0o600,exist_ok=True)
        record_path.write_text(json.dumps({'status':'prepared','models':{k:{'sha256':v['sha256'],'bytes':v['bytes']} for k,v in spec['models'].items()},'lock_sha256':LOCK_SHA,'model_loads':0}))
        record_path.chmod(0o600)
    if operation=='finalize':
        record=json.loads(record_path.read_text())
        try:
            account=pwd.getpwnam('mani-vmlab-model')
            if record.get('model_account',{}).get('UID')!=account.pw_uid:
                raise RuntimeError('preserve_preexisting_model_account')
        except KeyError:
            subprocess.run(['/usr/bin/useradd','--system','--user-group','--home-dir','/nonexistent',
                            '--shell','/usr/bin/nologin','mani-vmlab-model'],check=True,timeout=10)
            account=pwd.getpwnam('mani-vmlab-model')
            record['model_account']={'UID':account.pw_uid,'GID':account.pw_gid,'created':True}
            record_path.write_text(json.dumps(record))
        for arm in ('normal','abliterated'):
            path=DATA/'models'/(arm+'.gguf')
            os.chown(path,0,account.pw_gid)
        os.chown(DATA/'backend-control',0,account.pw_gid)
        sys.path.insert(0,'/usr/local/lib/mani-vmlab')
        import window
        unit=Path('/etc/systemd/system')/window.SERVICE
        text=window.unit_text()
        if unit.exists() and unit.read_text()!=text:
            raise RuntimeError('preserve_existing_window_unit')
        unit.write_text(text)
        unit.chmod(0o644)
        subprocess.run(['/usr/bin/systemd-analyze','verify',str(unit)],check=True,timeout=20)
        subprocess.run(['/usr/bin/systemctl','daemon-reload'],check=True,timeout=20)
    print(record_path.read_text())


if __name__=='__main__':
    main()
