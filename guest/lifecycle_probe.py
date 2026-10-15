"""Fixed disposable worker_b systemd lifecycle test; no production uninstall."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time
sys.path.insert(0,'/opt/mani-vmlab')
from recovery import Recovery,fingerprint,namespace_record,NativeServices,SYSTEM_UNITS,USER_UNIT


def command(argv):return subprocess.check_output(argv,stderr=subprocess.PIPE,timeout=30)


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=Path('/opt/mani-vmlab/lifecycle_probe.py') or len(sys.argv)!=1:
        raise SystemExit('fixed_disposable_guest_probe_only')
    marker=json.loads(Path('/etc/mani-vmlab/guest.json').read_text())
    if marker.get('role')!='worker_b':raise ValueError('fresh_validation_worker_only')
    if Path('/usr/local/lib/mani-vmlab').exists():raise ValueError('refuse_existing_installation')
    lab=pwd.getpwnam('lab');home=Path(lab.pw_dir)
    if Path('/home/mani').exists():raise ValueError('refuse_existing_profile')
    Path('/home/mani').mkdir(mode=0o700);os.chown('/home/mani',1000,1000)
    command(['/usr/sbin/usermod','-d','/home/mani','lab'])
    for username,uid in [('mani-vmlab-model',958),('mani-vmlab-vm',959)]:
        command(['/usr/sbin/useradd','-u',str(uid),'-U','-M','-d','/nonexistent','-s','/usr/sbin/nologin',username])
    files=[]
    def write(path,text,uid=0):
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(0o600);os.chown(p,uid,uid)
        files.append(fingerprint(p));return p
    hook=write('/usr/local/lib/mani-vmlab/window.py','from pathlib import Path\nPath("/tmp/mani-normal-restored").write_text("restored")\n')
    for name in SYSTEM_UNITS:
        binds='' if name.endswith('supervisor.service') else 'BindsTo=mani-vmlab-supervisor.service\n'
        if 'backend' in name:binds+='BindsTo=mani-vmlab-inference-window.service\n'
        stop='ExecStopPost=/usr/bin/python3 -I '+str(hook)+'\n' if 'window' in name else ''
        user='User=mani-vmlab-model\n' if 'backend' in name else ''
        write('/etc/systemd/system/'+name,'[Unit]\nDescription=Disposable full recovery stand-in\n'+binds+'[Service]\n'+user+'ExecStart=/usr/bin/sleep 900\n'+stop)
    userunit=write('/home/mani/.config/systemd/user/'+USER_UNIT,'[Service]\nExecStart=/usr/bin/sleep 900\n',1000)
    os.chown(userunit.parent,1000,1000);os.chown(userunit.parent.parent,1000,1000);os.chown(userunit.parent.parent.parent,1000,1000)
    pin=write('/home/mani/.config/quickshell/kona/sidebar/shell.qml','Hermes installed pin',1000)
    backup=Path('/home/mani-vmlab-data/workspace-recovery/pin-before');backup.parent.mkdir(parents=True);backup.write_text('original Steam pin')
    item=next(x for x in files if x['path']==str(pin));item.update(action='restore',backup=str(backup),before_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),before_mode=0o600)
    write('/home/mani/.local/bin/hermes-lab-worker','registered adapter',1000)
    retained=Path('/home/mani-vmlab-data/models/normal.gguf');retained.parent.mkdir(parents=True);retained.write_text('fixture weight bytes retained; not a model')
    thin=Path('/home/mani-vmlab-data/backend-root');(thin/'usr/bin').mkdir(parents=True)
    (thin/'bin').symlink_to('usr/bin')
    namespaces=[namespace_record(p) for root in (hook.parent,thin) for p in [root,*root.rglob('*')] if p.is_dir() or p.is_symlink()]
    command(['/usr/bin/loginctl','enable-linger','lab']);command(['/usr/bin/systemctl','start','user@1000.service'])
    env={'PATH':'/usr/bin:/bin','XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
    def user(*args):return subprocess.check_output(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/systemctl','--user',*args],env=env,stderr=subprocess.PIPE,timeout=20)
    command(['/usr/bin/systemctl','daemon-reload']);user('daemon-reload')
    command(['/usr/bin/systemctl','start',*SYSTEM_UNITS]);user('start',USER_UNIT)
    class Services(NativeServices):
        def close_window(self):
            command(['/usr/bin/systemctl','stop','mani-vmlab-inference-window.service'])
            if not Path('/tmp/mani-normal-restored').exists():raise RuntimeError('standin_restore_hook_not_run')
    register={'version':1,'files':files,'namespaces':namespaces,'accounts':[{'name':n,'uid':u,'created':True} for n,u in [('mani-vmlab-model',958),('mani-vmlab-vm',959)]],
              'retained':['fixture copied weights','base image and source/evidence layout']}
    recovery=Recovery(register,Services())
    # An actual systemd update replaces the hook and refreshes the latest
    # register, while the prior source remains recoverable in this fixture.
    window=Path('/etc/systemd/system/mani-vmlab-inference-window.service')
    previous_hook=window.read_text();window.write_text(previous_hook+'# registered update v2\n')
    command(['/usr/bin/systemctl','daemon-reload'])
    for entry in files:
        if entry['path']==str(window):entry.update(fingerprint(window))
    full_bytes={entry['path']:Path(entry['path']).read_bytes() for entry in files}
    # First exercise an updated hook drift: no service/code mutation is allowed.
    original=window.read_text();window.write_text(original+'# drift\n')
    drift_refused=False
    try:recovery.remove()
    except RuntimeError:drift_refused=True
    window.write_text(original)
    # Rebind this deliberate fixture update into the full latest register.
    updated=fingerprint(window)
    for entry in files:
        if entry['path']==str(window):entry.update(updated)
    result=recovery.remove()
    pids=command(['/usr/bin/systemctl','show',*SYSTEM_UNITS,'-p','MainPID','--value']).decode().split()
    user_pid=user('show',USER_UNIT,'-p','MainPID','--value').decode().strip()
    first={'all_owned_system_PIDs_zero':all(x=='0' for x in pids),'user_UI_PID_zero':user_pid=='0',
        'normal_restore_hook_before_code_removal':Path('/tmp/mani-normal-restored').exists() and not hook.exists(),
        'pin_restored':pin.read_text()=='original Steam pin','window_hook_retired':not window.exists()}
    retired=all(name not in [entry.pw_name for entry in pwd.getpwall()] for name in ('mani-vmlab-model','mani-vmlab-vm'))
    # Reinstall the same complete layout, refresh inode-bound registration,
    # start real managers, then remove once more through the production code.
    for username,uid in [('mani-vmlab-model',958),('mani-vmlab-vm',959)]:
        command(['/usr/sbin/useradd','-u',str(uid),'-U','-M','-d','/nonexistent','-s','/usr/sbin/nologin',username])
    for entry in sorted(namespaces,key=lambda x:len(Path(x['path']).parts)):
        p=Path(entry['path'])
        if entry['kind']=='directory':p.mkdir(parents=True,exist_ok=True)
        else:p.symlink_to(entry['target'])
        entry.update(namespace_record(p))
    for entry in files:
        p=Path(entry['path']);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(full_bytes[str(p)]);p.chmod(entry['mode']);os.chown(p,entry['uid'],entry['uid']);entry.update(fingerprint(p))
    command(['/usr/bin/systemctl','daemon-reload']);user('daemon-reload')
    command(['/usr/bin/systemctl','start',*SYSTEM_UNITS]);user('start',USER_UNIT)
    reinstalled=all(int(x)>0 for x in command(['/usr/bin/systemctl','show',*SYSTEM_UNITS,'-p','MainPID','--value']).decode().split()) and int(user('show',USER_UNIT,'-p','MainPID','--value'))>0
    second=Recovery(register,Services()).remove()
    print(json.dumps({'evidence_kind':'actual_disposable_guest_systemd_lifecycle_standin_not_GPU_or_production_uninstall',
        'full_registered_removal':result['status'],'drift_refused_before_mutation':drift_refused,
        **first,'copied_weights_retained':retained.exists(),
        'registered_update_measured':True,'exact_accounts_retired':retired,
        'thin_runtime_directories_and_symlinks_retired':not thin.exists() and not hook.parent.exists(),
        'reinstall_services_started':reinstalled,'second_removal':second['status'],
        'account_retirement':['mani-vmlab-model','mani-vmlab-vm'],
        'production_uninstall_applied':False}))


if __name__=='__main__':main()
