"""One-time fixed, hash-frozen native text admission setup. No model load."""
import hashlib,json,os,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
sys.dont_write_bytecode=True

SELF=Path('/usr/local/lib/mani-vmlab-setup/local_chat_setup.py')
PLAN=Path('/home/mani/mani-hermes-local-chat-v3-ee548ych/private-state/local-chat-setup-plan.json')
PLAN_SHA='6b3eac44795472bf5a016b85ecf186be14490b934328127d7885bf470c76693b'
SETUP=SELF.parent
UNIT=Path('/etc/systemd/system/mani-vmlab-supervisor.service')
SOCKET_UNIT=Path('/etc/systemd/system/mani-vmlab-supervisor.socket')
WINDOW_UNIT=Path('/etc/systemd/system/mani-vmlab-inference-window.service')
SOCKET_TEXT='''[Unit]
Description=Operator-only Mani local model admission socket
[Socket]
ListenStream=/run/mani-vmlab/control.sock
SocketUser=root
SocketGroup=mani
SocketMode=0660
DirectoryMode=0755
Service=mani-vmlab-supervisor.service
RemoveOnStop=yes
[Install]
WantedBy=sockets.target
'''


def read_pinned(path,digest,maximum=1024*1024):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:raise ValueError('bounded_frozen_setup_file_required')
        raw=source.read(maximum+1)
        if len(raw)>maximum or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('prepared_source_changed')
        return raw


def write(path,raw,mode=0o644):
    fd,name=tempfile.mkstemp(prefix=path.name+'.chat-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:os.fchmod(out.fileno(),mode);out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def command(argv,seconds=180):
    return subprocess.run(argv,check=True,timeout=seconds,capture_output=True,env={'PATH':'/usr/bin:/bin','LANG':'C'})


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF or sys.argv[1:]!=['apply']:raise SystemExit('fixed_native_setup_apply_only')
    for path in (SELF,SETUP,UNIT):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):raise PermissionError('protected_native_target_required')
    plan=json.loads(read_pinned(PLAN,PLAN_SHA))
    if set(plan)!={'workspace_setup','normal_configuration_sha256','source_pack_sha256','window_unit_before_sha256','window_unit_after_sha256'}:raise ValueError('fixed_native_setup_plan_required')
    window_digest=hashlib.sha256(WINDOW_UNIT.read_bytes()).hexdigest()
    if window_digest not in (plan['window_unit_before_sha256'],plan['window_unit_after_sha256']):raise RuntimeError('preserve_changed_window_unit')
    read_pinned(WINDOW_UNIT,window_digest)
    before={name:hashlib.sha256((Path('/home/mani')/name).read_bytes()).hexdigest() for name in plan['normal_configuration_sha256']}
    if before!=plan['normal_configuration_sha256']:raise RuntimeError('preserve_changed_normal_configuration')
    helper=plan['workspace_setup'];raw=read_pinned(Path(helper['path']),helper['sha256'])
    if SOCKET_UNIT.exists() and SOCKET_UNIT.read_text()!=SOCKET_TEXT:raise RuntimeError('preserve_other_socket_unit')
    backup=Path('/home/mani-vmlab-data')/('text-chat-before-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));backup.mkdir(mode=0o700)
    shutil.copy2(UNIT,backup/'supervisor.service')
    shutil.copy2(WINDOW_UNIT,backup/'inference-window.service')
    shutil.copy2(SETUP/'runtime-installed.json',backup/'runtime-installed.json')
    if SOCKET_UNIT.exists():shutil.copy2(SOCKET_UNIT,backup/'supervisor.socket')
    # The first text setup added socket preservation after the older updater
    # recorded the generated unit. Reconcile only that exact known change;
    # every other installed byte/inode must still match the protected ledger.
    sys.path.insert(0,str(SETUP))
    from install_runtime import checkpoint,supervisor_service_text,trusted
    registered_runtime=json.loads((SETUP/'runtime-installed.json').read_text())
    changed=[]
    base=supervisor_service_text()
    preserved=base.replace('RuntimeDirectoryMode=0755','RuntimeDirectoryMode=0755\nRuntimeDirectoryPreserve=yes')
    for item in registered_runtime['installed_files']:
        path=Path(item['path']);trusted(path);info=path.stat();actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if (info.st_dev,info.st_ino,actual)!=(item['device'],item['inode'],item['sha256']):
            if path!=UNIT or path.read_text()!=preserved or item['sha256']!=hashlib.sha256(base.encode()).hexdigest():
                raise RuntimeError('Preserve unexpected registered change: '+str(path))
            changed.append(path)
    if changed:
        print('Reconciled the exact previously added socket-preservation unit; all other registered files match.',flush=True)
        checkpoint(registered_runtime)
    print('Installing the frozen no-GPU workspace/runtime update.',flush=True)
    write(SETUP/'workspace_setup.py',raw)
    subprocess.run(['/usr/bin/python3','-I',str(SETUP/'workspace_setup.py'),'apply'],check=True,timeout=300)
    command(['/usr/bin/systemctl','stop','mani-vmlab-supervisor.service'])
    # The updater temporarily writes the base service without Preserve. Its
    # stop can unlink the old listener directory while the socket unit remains
    # active. Rebind the owned socket after all runtime-directory updates.
    command(['/usr/bin/systemctl','stop','mani-vmlab-supervisor.socket'])
    current=UNIT.read_text()
    if 'RuntimeDirectoryPreserve=yes' not in current:current=current.replace('RuntimeDirectoryMode=0755','RuntimeDirectoryMode=0755\nRuntimeDirectoryPreserve=yes')
    write(UNIT,current.encode());write(SOCKET_UNIT,SOCKET_TEXT.encode())
    # Use only the installed, digest-checked source to refresh this lab-owned
    # unit. The narrow receipt directory is required for recovery publication.
    code="import sys;sys.path.insert(0,'/usr/local/lib/mani-vmlab');import window;print(window.unit_text(),end='')"
    window_text=command(['/usr/bin/python3','-I','-c',code]).stdout
    write(WINDOW_UNIT,window_text)
    print('Reverifying the installed model/backend copies; no inference is started.',flush=True)
    code="import sys;sys.path.insert(0,'/usr/local/lib/mani-vmlab');import backend;print(backend.verify_artifacts())"
    verified=command(['/usr/bin/python3','-B','-I','-c',code],seconds=180)
    print(verified.stdout.decode().strip(),flush=True)
    command(['/usr/bin/systemctl','daemon-reload']);command(['/usr/bin/systemctl','enable','--now','mani-vmlab-supervisor.socket'])
    # Keep the existing scoped uninstall ledger consistent with these exact
    # lab unit changes; preserve all other registrations and recovery backups.
    sys.path.insert(0,str(SETUP))
    from install_runtime import checkpoint
    installed=json.loads((SETUP/'runtime-installed.json').read_text());checkpoint(installed)
    from recovery import fingerprint
    ledger=Path('/var/lib/mani-vmlab-setup/workspace-complete-register.json')
    registered=json.loads(ledger.read_text());changed={str(p):fingerprint(p) for p in (UNIT,SOCKET_UNIT,WINDOW_UNIT)}
    registered['files']=[item for item in registered['files'] if item['path'] not in changed]+list(changed.values())
    write(ledger,(json.dumps(registered,indent=2)+'\n').encode(),0o600)
    after={name:hashlib.sha256((Path('/home/mani')/name).read_bytes()).hexdigest() for name in before}
    if after!=before:raise RuntimeError('normal_configuration_drift_during_setup')
    receipt={'status':'installed','source_pack_sha256':plan['source_pack_sha256'],'GPU_window_opened':False,'normal_configuration_hashes_unchanged':True,'socket_activation':True,'backup':str(backup)}
    write(SETUP/'text-chat-installed.json',(json.dumps(receipt,indent=2)+'\n').encode(),0o600)
    public={k:v for k,v in receipt.items() if k!='backup'};directory=Path('/var/lib/mani-vmlab-review');directory.mkdir(mode=0o755,exist_ok=True);write(directory/'text-chat-installed.json',(json.dumps(public,indent=2)+'\n').encode())
    print(json.dumps(public),flush=True)

if __name__=='__main__':main()
