#!/usr/bin/python3
"""Frozen correction transaction then fixed smoke; no caller paths or commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
sys.dont_write_bytecode=True

SELF=Path('/usr/local/lib/mani-vmlab-setup/resume_smoke.py')
ROOT=Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
PACK=ROOT.parent/'private-state/runtime-update-mask/runtime-source.zip'
PACK_SHA='7dd20b4588af216d0b3bf8cdee2629a1b3f28f45cf5efaab47e1e499d84069c8'
HELPER_SHA='92d92e4dd651c99eca98b0c3f08254952d0b9eca6ace494d16ad58da9f90cb7f'
PROBE_SHA='2ceed00e6aab703596caa5fe4bad1278449dc6e0f2d17a28178d35e6bc1d0271'
OLD_UNIT_SHA='dceb1098a9ce324405b59c8202332d95755d665c57e5ba657f6a4e2d5b339e37'
NEW_UNIT_SHA='45f4ddf599338e962b8296f63c71c97ba90924c8d755a0403c03427ec09db235'


def frozen(path,expected,limit):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('frozen_file_limit')
        raw=source.read(limit+1)
    if hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError('frozen_correction_bytes_changed')
    return raw


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:raise SystemExit('installed_protected_resume_only')
    sys.path.insert(0,str(SELF.parent))
    from install_runtime import trusted
    for p in (SELF,SELF.parent,SELF.with_name('install_runtime.py'),SELF.with_name('update_runtime.py')):trusted(p)
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=('run','run-new-window'))
    operation=parser.parse_args().operation
    state=Path('/home/mani-vmlab-data/window/state.json')
    if state.exists() and json.loads(state.read_text()).get('status') in ('opening','active','restoring'):
        raise RuntimeError('recover_existing_window_before_correction')
    raw=frozen(PACK,PACK_SHA,512*1024)
    helper=frozen(ROOT/'native/run_smoke.py',HELPER_SHA,65536)
    probe=frozen(ROOT/'native/model_probe.py',PROBE_SHA,65536)
    unit=Path('/etc/systemd/system/mani-vmlab-inference-window.service')
    trusted(unit)
    old=unit.read_bytes()
    old_hash=hashlib.sha256(old).hexdigest()
    if old_hash not in (OLD_UNIT_SHA,NEW_UNIT_SHA):raise RuntimeError('preserve_changed_window_unit')
    backup=Path('/home/mani-vmlab-data/runtime-versions')/('window-'+OLD_UNIT_SHA+'.service')
    if old_hash==OLD_UNIT_SHA and not backup.exists():backup.write_bytes(old);backup.chmod(0o600)
    target=Path('/var/lib/mani-vmlab-setup/runtime-source.zip')
    target.write_bytes(raw);target.chmod(0o600)
    lock=SELF.with_name('runtime-source.sha256');lock.write_text(PACK_SHA+'\n');lock.chmod(0o600)
    target=SELF.with_name('run_smoke.py');target.write_bytes(helper);target.chmod(0o644)
    target=SELF.with_name('model_probe.py');target.write_bytes(probe);target.chmod(0o644)
    subprocess.run(['/usr/bin/python3','-I',str(SELF.with_name('update_runtime.py')),'apply'],check=True)
    # Create only missing runtime directories, never replace a user-owned entry.
    parent=Path('/run/user/1000')
    for name in ('systemd','user.control'):
        parent=parent/name
        if not parent.exists():parent.mkdir(mode=0o700);os.chown(parent,1000,1000)
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=1000 or info.st_mode&0o022:
            raise RuntimeError('preserve_changed_user_runtime_directory')
    sys.path.insert(0,'/usr/local/lib/mani-vmlab')
    import window
    text=window.unit_text()
    if hashlib.sha256(text.encode()).hexdigest()!=NEW_UNIT_SHA:raise RuntimeError('frozen_window_unit_changed')
    unit.write_text(text);unit.chmod(0o644)
    subprocess.run(['/usr/bin/systemd-analyze','verify',str(unit)],check=True)
    subprocess.run(['/usr/bin/systemctl','daemon-reload'],check=True)
    result=subprocess.run(['/usr/bin/python3','-I',str(SELF.with_name('run_smoke.py')),operation])
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
