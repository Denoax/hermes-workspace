"""One reviewed hash-frozen native update, without opening a GPU window."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import time
import tempfile
import zipfile
import io
sys.dont_write_bytecode=True

SELF=Path('/usr/local/lib/mani-vmlab-setup/workspace_setup.py')
INPUT=Path('/home/mani/mani-hermes-workspace-gi95k3xk/private-state/workspace-setup-input.json')
INPUT_SHA='1478aaea6f51d89369e6e97a6869fa0721bd6936f810623b1298b3790d7bd243'
PREVIOUS_PACK='4d1bb05cbf874df1b5aff8f9b96d060833bfe0f425c7a9e80f318921b04f7fcb'
SETUP=SELF.parent
STATE=Path('/var/lib/mani-vmlab-setup')
DATA=Path('/home/mani-vmlab-data')
INSTALL=Path('/usr/local/lib/mani-vmlab')
CONFIG=Path('/etc/mani-vmlab/config.json')
TARGETS={'installer':SETUP/'install_runtime.py','updater':SETUP/'update_runtime.py',
         'recovery':SETUP/'recovery.py','recovery_entry':SETUP/'workspace_recovery.py',
         'acceptance':SETUP/'workspace_acceptance.py','watchdogs':SETUP/'watchdog_probe.py','protocol':SETUP/'protocol_probe.py',
         'normal_profile':SETUP/'normal-profile.lock.json'}


def read_pinned(path,digest,maximum):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:raise ValueError('bounded_frozen_setup_file_required')
        with os.fdopen(fd,'rb',closefd=False) as source:data=source.read(maximum+1)
        if len(data)>maximum or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('prepared_setup_digest_changed')
        return data
    finally:os.close(fd)


def command(argv):return subprocess.check_output(argv,stdin=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=240)


def write(path,data,mode=0o644):
    descriptor,name=tempfile.mkstemp(prefix=path.name+'.workspace-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as out:os.fchmod(out.fileno(),mode);out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:raise SystemExit('fixed_protected_workspace_setup_only')
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['apply']);parser.parse_args()
    for path in [SELF,SELF.parent,STATE,DATA,INSTALL,CONFIG]:
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):raise PermissionError('protected_existing_installation_required')
    plan=json.loads(read_pinned(INPUT,INPUT_SHA,65536))
    if set(plan)!={'files','source_pack_sha256','compiler_zip_sha256','runtime_iso_sha256','pin_before_sha256','router_before_sha256','pin_before_mode','router_before_mode'}:
        raise ValueError('fixed_prepared_update_inventory_required')
    expected={*TARGETS,'source_pack','runtime_iso','pin_backup','router_backup'}
    if set(plan['files'])!=expected:raise ValueError('fixed_setup_file_roles_required')
    payload={key:read_pinned(item['path'],item['sha256'],130*1024*1024 if key=='runtime_iso' else 1024*1024) for key,item in plan['files'].items()}
    config=json.loads(CONFIG.read_text())
    journal=STATE/'workspace-update.json'
    progress=json.loads(journal.read_text()) if journal.exists() else None
    if progress is not None and (progress.get('input_sha256')!=INPUT_SHA or progress.get('new_pack')!=plan['source_pack_sha256']):
        if progress.get('phase')!='installed' or config['source_pack_sha256']!=PREVIOUS_PACK:raise RuntimeError('preserve_other_or_changed_partial_update_transaction')
        previous=STATE/('workspace-update-'+progress['input_sha256']+'.json')
        if not previous.exists():write(previous,journal.read_bytes(),0o600)
        progress=None
    if config['source_pack_sha256'] not in (PREVIOUS_PACK,plan['source_pack_sha256']):raise RuntimeError('preserve_later_native_runtime')
    if config['source_pack_sha256']!=PREVIOUS_PACK and progress is None:raise RuntimeError('unregistered_partial_update')
    if progress is not None and progress.get('phase')=='installed':
        with zipfile.ZipFile(io.BytesIO(payload['source_pack'])) as archive:
            for name in archive.namelist():
                if (INSTALL/name).read_bytes()!=archive.read(name):raise RuntimeError('installed_source_drift_review_required')
        print(json.dumps({'status':'already_installed','source_pack_sha256':plan['source_pack_sha256']}));return
    window=DATA/'window/state.json'
    if window.exists() and json.loads(window.read_text()).get('status') not in ('closed',None):raise RuntimeError('close_and_verify_existing_window_before_setup')
    for directory in (DATA/'runs').iterdir():
        if directory.is_dir() and json.loads((directory/'manifest.json').read_text())['status']=='active':raise RuntimeError('preserve_active_registered_fleet')
    backup=DATA/'workspace-recovery';backup.mkdir(mode=0o700,exist_ok=True)
    if progress is None:
        checkpoint=backup/('before-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));checkpoint.mkdir(mode=0o700)
        for key,target in TARGETS.items():
            if target.exists():shutil.copy2(target,checkpoint/(key+'.py'))
        shutil.copy2(CONFIG,checkpoint/'config.json');shutil.copy2(DATA/'artifacts/runtime.iso',checkpoint/'runtime.iso')
        shutil.copytree(INSTALL,checkpoint/'source',symlinks=True)
        for name in ['runtime-installed.json','runtime-source.sha256']:
            shutil.copy2(SETUP/name,checkpoint/name)
        shutil.copy2(STATE/'runtime-source.zip',checkpoint/'runtime-source.zip')
        shutil.copy2('/etc/systemd/system/mani-vmlab-supervisor.service',checkpoint/'supervisor.service')
        progress={'input_sha256':INPUT_SHA,'new_pack':plan['source_pack_sha256'],'previous_pack':PREVIOUS_PACK,'backup':str(checkpoint),'phase':'prepared'}
    def advance(phase):
        progress['phase']=phase;write(journal,(json.dumps(progress,indent=2)+'\n').encode(),0o600)
    advance(progress['phase'])
    write(backup/'pin-before',payload['pin_backup'],0o600);write(backup/'router-before',payload['router_backup'],0o600)
    for key,target in TARGETS.items():write(target,payload[key])
    command(['/usr/bin/systemctl','stop','mani-vmlab-supervisor.service'])
    for directory,mode in [(DATA/'workspace-jobs',0o700),(Path('/var/lib/mani-vmlab-review'),0o755)]:
        directory.mkdir(mode=mode,exist_ok=True)
        info=directory.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or not stat.S_ISDIR(info.st_mode):raise RuntimeError('protected_workspace_ledger_required')
    write(STATE/'runtime-source.zip',payload['source_pack'],0o600)
    write(SETUP/'runtime-source.sha256',(plan['source_pack_sha256']+'\n').encode(),0o600)
    # Source updater expects its frozen files in the root-private setup ledger.
    current=json.loads((SETUP/'runtime-installed.json').read_text())
    if config['source_pack_sha256']==PREVIOUS_PACK or current.get('status')=='failed_partial_update':
        operation='resume' if current.get('status')=='failed_partial_update' else 'apply'
        command(['/usr/bin/python3','-I',str(SETUP/'update_runtime.py'),operation])
    current=json.loads((SETUP/'runtime-installed.json').read_text())
    if current.get('status')!='installed' or current.get('source_pack_sha256')!=plan['source_pack_sha256']:raise RuntimeError('runtime_update_commit_not_verified')
    with zipfile.ZipFile(io.BytesIO(payload['source_pack'])) as archive:
        for name in archive.namelist():
            if (INSTALL/name).read_bytes()!=archive.read(name):raise RuntimeError('partial_source_update_requires_recovery')
    advance('runtime_updated')
    command(['/usr/bin/systemctl','stop','mani-vmlab-supervisor.service'])
    write(DATA/'artifacts/runtime.iso',payload['runtime_iso'],0o440)
    os.chown(DATA/'artifacts/runtime.iso',0,pwd.getpwnam('mani-vmlab-vm').pw_gid)
    config=json.loads(CONFIG.read_text());config.update(workspace_api=1,compiler_zip_sha256=plan['compiler_zip_sha256'],runtime_iso_sha256=plan['runtime_iso_sha256'])
    write(CONFIG,(json.dumps(config,indent=2)+'\n').encode(),0o640)
    advance('media_and_configuration_updated')
    sys.path.insert(0,str(SETUP))
    from install_runtime import checkpoint as register_runtime
    installed=json.loads((SETUP/'runtime-installed.json').read_text());register_runtime(installed)
    from recovery import fingerprint,namespace_record,ROOTS
    files=list(installed['installed_files'])
    for root in [DATA/'backend-root']:
        if root.exists():
            for path in root.rglob('*'):
                if path.is_file() and not path.is_symlink():files.append(fingerprint(path))
    for path in [Path('/etc/systemd/system/mani-vmlab-inference-window.service'),Path('/run/systemd/system/mani-vmlab-backend.service')]:
        if path.exists() or path.name=='mani-vmlab-backend.service':
            item=fingerprint(path) if path.exists() else {'path':str(path),'uid':0,'mode':0o644,'device':None,'inode':None,'sha256':None}
            if path.name=='mani-vmlab-backend.service':
                sys.path.insert(0,str(INSTALL));import backend
                item['allowed_sha256']=[hashlib.sha256(backend.unit_text(arm).encode()).hexdigest() for arm in ('normal','abliterated')]
            files.append(item)
    user_paths=['.local/bin/hermes-workspace','.local/bin/hermes-lab-worker','.local/bin/hermes-worker',
                '.local/share/applications/hermes-workspace.desktop','.config/systemd/user/hermes-workspace.service',
                '.config/quickshell/kona/sidebar/shell.qml']
    for relative in user_paths:
        item=fingerprint(Path('/home/mani')/relative)
        if relative.endswith('shell.qml'):item.update(action='restore',backup=str(backup/'pin-before'),before_sha256=plan['pin_before_sha256'],before_mode=plan['pin_before_mode'])
        if relative.endswith('/hermes-worker'):item.update(action='restore',backup=str(backup/'router-before'),before_sha256=plan['router_before_sha256'],before_mode=plan['router_before_mode'])
        files.append(item)
    for item in files:
        if 'uid' not in item:item.update(uid=Path(item['path']).stat().st_uid,mode=Path(item['path']).stat().st_mode&0o777)
    files=list({item['path']:item for item in files}.values())
    inference=json.loads((STATE/'inference-preparation.json').read_text())
    namespaces=[]
    for root in ROOTS:
        if root.exists():
            for path in [root,*root.rglob('*')]:
                if path.is_symlink() or path.is_dir():namespaces.append(namespace_record(path))
    register={'version':1,'files':files,'namespaces':namespaces,'accounts':[{'name':'mani-vmlab-vm','uid':959,'created':installed['account_created']},
        {'name':'mani-vmlab-model','uid':958,'created':inference['model_account']['created']}],
        'retained':['original model/profile files','copied weights and backend binaries','signed package/cache/database recovery',
                    'base images','run/job evidence','private UI catalog and browser profile','source and version backups','fixed setup/recovery helpers'],
        'source_pack_sha256':plan['source_pack_sha256'],'production_uninstall_applied':False}
    write(STATE/'workspace-complete-register.json',(json.dumps(register,indent=2)+'\n').encode(),0o600)
    command(['/usr/bin/systemctl','start','mani-vmlab-supervisor.service'])
    advance('installed')
    print(json.dumps({'status':'installed','source_pack_sha256':plan['source_pack_sha256'],'registered_files':len(files),
                      'GPU_window_opened':False,'host_packages_changed':False,'recovery_register_complete':True}))


if __name__=='__main__':main()
