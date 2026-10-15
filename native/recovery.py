"""Full registered recovery. Retire verified hooks before referenced code."""
import hashlib
import os
from pathlib import Path
import pwd
import stat
import subprocess
import json
import urllib.request
from contextlib import contextmanager

SYSTEM_UNITS=('mani-vmlab-inference-window.service','mani-vmlab-backend.service','mani-vmlab-supervisor.service')
USER_UNIT='hermes-workspace.service'
USER_FILES={Path('/home/mani/.local/bin/hermes-workspace'),Path('/home/mani/.local/bin/hermes-lab-worker'),
    Path('/home/mani/.local/bin/hermes-worker'),Path('/home/mani/.local/share/applications/hermes-workspace.desktop'),
    Path('/home/mani/.config/systemd/user')/USER_UNIT,Path('/home/mani/.config/quickshell/kona/sidebar/shell.qml')}
ROOTS=(Path('/usr/local/lib/mani-vmlab'),Path('/etc/mani-vmlab'),Path('/home/mani-vmlab-data/runtime-root'),
       Path('/home/mani-vmlab-data/backend-root'))


def permitted(path):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:return False
    return p in USER_FILES or any(p.is_relative_to(root) for root in ROOTS) or p in {
        *(Path('/etc/systemd/system')/unit for unit in SYSTEM_UNITS),
        Path('/run/systemd/system/mani-vmlab-backend.service')}


@contextmanager
def parent_fd(path):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:raise ValueError('absolute_registered_path_required')
    descriptor=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
        yield descriptor,p.name
    finally:os.close(descriptor)


def fingerprint(path):
    p=Path(path)
    with parent_fd(p) as (parent,name):
        info=os.stat(name,dir_fd=parent,follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('registered_regular_single_link_required')
        descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    try:
        actual=os.fstat(descriptor)
        if (actual.st_dev,actual.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('registered_file_changed')
        with os.fdopen(descriptor,'rb',closefd=False) as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    finally:os.close(descriptor)
    return {'path':str(p),'device':info.st_dev,'inode':info.st_ino,'sha256':digest,'uid':info.st_uid,'mode':info.st_mode&0o777}


def namespace_record(path):
    p=Path(path)
    with parent_fd(p) as (parent,name):
        info=os.stat(name,dir_fd=parent,follow_symlinks=False)
        kind='directory' if stat.S_ISDIR(info.st_mode) else 'symlink' if stat.S_ISLNK(info.st_mode) else None
        if kind is None or info.st_uid!=0:raise ValueError('owned_runtime_namespace_required')
        item={'path':str(p),'kind':kind,'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}
        if kind=='directory':
            if info.st_mode&0o022:raise ValueError('protected_runtime_directory_required')
            item['mode']=info.st_mode&0o777
        if kind=='symlink':item['target']=os.readlink(name,dir_fd=parent)
        return item


class NativeServices:
    def command(self,argv):
        return subprocess.check_output(argv,stdin=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=240,
            env={'PATH':'/usr/bin:/bin','LANG':'C','XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'})
    def close_window(self):
        self.command(['/usr/bin/python3','-I','/usr/local/lib/mani-vmlab-setup/inference_window.py','close'])
        import json
        state=json.loads(Path('/home/mani-vmlab-data/window/state.json').read_text())
        if state.get('status')!='closed' or not state.get('restored_health') or not all(state.get('configuration_hashes_equal',{}).values()):
            raise RuntimeError('normal_recovery_not_verified')
        self.verify_normal_profile()
    def verify_normal_profile(self):
        lock=Path('/usr/local/lib/mani-vmlab-setup/normal-profile.lock.json')
        item=fingerprint(lock)
        if item['uid']!=0 or item['mode']&0o022:raise RuntimeError('protected_normal_profile_pin_required')
        pins=json.loads(lock.read_text())
        expected={'.config/systemd/user/manibot-llama.service','.config/systemd/user/qwen-local.service','.local/bin/start-manibot-llama','.hermes/config.yaml'}
        if set(pins)!=expected:raise RuntimeError('four_fixed_normal_profile_pins_required')
        if not all(fingerprint(Path('/home/mani')/relative)['sha256']==digest for relative,digest in pins.items()):raise RuntimeError('preserve_changed_normal_profile')
        with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2) as response:health=json.load(response)
        with urllib.request.urlopen('http://127.0.0.1:8080/props',timeout=2) as response:props=json.load(response)
        if health.get('status')!='ok' or props.get('model_alias')!='qwen3.6-35b-a3b-q4' or props.get('default_generation_settings',{}).get('n_ctx')!=65536:raise RuntimeError('original_normal_alias_context_and_health_required')
        return {'four_configuration_hashes_equal':True,'alias':'qwen3.6-35b-a3b-q4','context':65536,'healthy':True}
    def stop(self,unit,user=False):
        prefix=['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/systemctl','--user'] if user else ['/usr/bin/systemctl']
        if self.command([*prefix,'show',unit,'-p','LoadState','--value']).strip()==b'not-found':return
        self.command([*prefix,'stop',unit])
    def close_workspace_browser(self):
        launcher=Path('/home/mani/.local/bin/hermes-workspace')
        if launcher.exists():self.command(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',str(launcher),'--close'])
    def reload(self):
        self.command(['/usr/bin/systemctl','daemon-reload'])
        self.command(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/systemctl','--user','daemon-reload'])
    def retire_account(self,item):
        if not item['created']:return
        try:account=pwd.getpwnam(item['name'])
        except KeyError:return
        if account.pw_uid!=item['uid'] or account.pw_dir!='/nonexistent' or account.pw_shell not in ('/usr/bin/nologin','/usr/sbin/nologin'):
            raise RuntimeError('preserve_changed_account')
        rows=subprocess.run(['/usr/bin/ps','-u',str(account.pw_uid),'-o','pid='],capture_output=True,timeout=5)
        if rows.stdout.strip():raise RuntimeError('registered_account_has_remaining_processes')
        self.command(['/usr/bin/userdel',item['name']])


class Recovery:
    def __init__(self,register,services,root=Path('/')):
        self.register=register;self.services=services;self.root=Path(root)
        if register.get('version')!=1 or any(not permitted(item['path']) for item in register['files']):
            raise ValueError('fixed_complete_recovery_register_required')
        required={str(Path('/etc/systemd/system')/'mani-vmlab-inference-window.service'),
                  str(Path('/etc/systemd/system')/'mani-vmlab-supervisor.service'),
                  str(Path('/home/mani/.config/systemd/user')/USER_UNIT)}
        if not required<={item['path'] for item in register['files']}:raise ValueError('complete_hook_register_required')
        for item in register['files']:
            if 'allowed_sha256' in item and item['path']!='/run/systemd/system/mani-vmlab-backend.service':
                raise ValueError('only_fixed_generated_backend_hook_can_vary')
            if item.get('action')=='restore':
                backup=Path(item['backup'])
                if not backup.is_relative_to('/home/mani-vmlab-data/workspace-recovery') or '..' in backup.parts:
                    raise ValueError('fixed_private_recovery_backup_required')
        for account in register['accounts']:
            if (account['name'],account['uid']) not in [('mani-vmlab-model',958),('mani-vmlab-vm',959)]:
                raise ValueError('only_recorded_lab_identities_may_retire')
        for item in register.get('namespaces',[]):
            if not any(Path(item['path']).is_relative_to(root) for root in ROOTS) or item['kind'] not in ('directory','symlink'):
                raise ValueError('only_exact_lab_runtime_namespaces_may_retire')

    def physical(self,path):return self.root/str(path).lstrip('/')

    def unchanged(self,item):
        p=self.physical(item['path'])
        if not p.exists() and not p.is_symlink():return True
        actual=fingerprint(p)
        if 'allowed_sha256' in item:
            return actual['uid']==0 and actual['mode']==0o644 and actual['sha256'] in item['allowed_sha256']
        return all(actual[key]==item[key] for key in ('device','inode','sha256','uid'))

    def unlink_registered(self,item):
        p=self.physical(item['path'])
        if not p.exists() and not p.is_symlink():return
        with parent_fd(p) as (parent,name):
            info=os.stat(name,dir_fd=parent,follow_symlinks=False)
            expected=fingerprint(p) if 'allowed_sha256' in item else item
            if (info.st_dev,info.st_ino,info.st_uid)!=(expected['device'],expected['inode'],expected['uid']):
                raise RuntimeError('registered_namespace_drift')
            os.unlink(name,dir_fd=parent)

    def plan(self):
        changed=[item['path'] for item in self.register['files'] if not self.unchanged(item)]
        registered={item['path'] for item in [*self.register['files'],*self.register.get('namespaces',[])]}
        for item in self.register.get('namespaces',[]):
            p=self.physical(item['path'])
            if not p.exists() and not p.is_symlink():continue
            if namespace_record(p)!={**item,'path':str(p)}:changed.append(item['path'])
            if item['kind']=='directory':
                changed.extend(str(child) for child in p.iterdir() if str(Path(item['path'])/child.name) not in registered)
        for item in self.register['files']:
            if item.get('action')=='restore':
                backup=self.physical(item['backup'])
                try:
                    actual=fingerprint(backup)
                    if actual['sha256']!=item['before_sha256']:changed.append(item['backup'])
                except (OSError,ValueError):changed.append(item['backup'])
        return {'ready':not changed,'preserve_changed':changed,
            'ordering':['close_window_verify_normal','stop_user_UI','stop_backend','stop_supervisor',
                        'retire_window_and_service_hooks','reload_managers','remove_verified_runtime_files',
                        'restore_unchanged_desktop_and_router','retire_exact_created_lab_accounts'],
            'retained':self.register['retained']}

    def remove(self):
        plan=self.plan()
        if not plan['ready']:raise RuntimeError('preserve_changed_installation_review_required')
        self.services.close_window()
        self.services.stop(USER_UNIT,user=True)
        self.services.close_workspace_browser()
        for unit in SYSTEM_UNITS:self.services.stop(unit)
        hooks=[item for item in self.register['files'] if Path(item['path']).name in (*SYSTEM_UNITS,USER_UNIT)]
        ordinary=[item for item in self.register['files'] if item not in hooks]
        removed=[];restored=[]
        for item in hooks:
            if not self.unchanged(item):raise RuntimeError('hook_changed_during_removal')
            self.unlink_registered(item);removed.append(item['path'])
        self.services.reload()
        for item in ordinary:
            if not self.unchanged(item):raise RuntimeError('registered_file_changed_during_removal')
            p=self.physical(item['path'])
            if item.get('action')=='restore':
                backup=self.physical(item['backup'])
                data=backup.read_bytes()
                if hashlib.sha256(data).hexdigest()!=item['before_sha256']:raise ValueError('recovery_backup_pin_changed')
                if p.exists():
                    with parent_fd(p) as (parent,name):fd=os.open(name,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
                    try:
                        info=os.fstat(fd)
                        if (info.st_dev,info.st_ino,info.st_uid)!=(item['device'],item['inode'],item['uid']) or info.st_nlink!=1:
                            raise RuntimeError('restore_target_identity_changed')
                        with os.fdopen(fd,'rb',closefd=False) as source:current=hashlib.file_digest(source,'sha256').hexdigest()
                        if current!=item['sha256']:raise RuntimeError('restore_target_bytes_changed')
                        os.lseek(fd,0,os.SEEK_SET)
                        with os.fdopen(fd,'wb',closefd=False) as output:output.write(data);output.flush();os.ftruncate(fd,len(data));os.fchmod(fd,item['before_mode']);os.fsync(fd)
                    finally:os.close(fd)
                    restored.append(item['path'])
            else:self.unlink_registered(item);removed.append(item['path'])
        for item in self.register['accounts']:self.services.retire_account(item)
        for item in sorted(self.register.get('namespaces',[]),key=lambda x:len(Path(x['path']).parts),reverse=True):
            p=self.physical(item['path'])
            if not p.exists() and not p.is_symlink():continue
            if namespace_record(p)!={**item,'path':str(p)}:raise RuntimeError('registered_namespace_changed_during_removal')
            with parent_fd(p) as (parent,name):
                if item['kind']=='directory':os.rmdir(name,dir_fd=parent)
                else:os.unlink(name,dir_fd=parent)
            removed.append(item['path'])
        return {'status':'removed_registered_installation','removed':removed,'restored':restored,
            'retained':self.register['retained'],'production_application':True}
