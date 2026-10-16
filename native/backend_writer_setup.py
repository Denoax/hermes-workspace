"""One registered backend writer overlay; base archive and admission stay intact.

Fixed native authentication and source review are required. Only the pinned,
registered production_setup dependency is imported; checkout source is data.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
SELF = Path('/usr/local/lib/mani-vmlab-setup/backend_writer_setup.py')
SETUP = SELF.parent
STATE = Path('/var/lib/mani-vmlab-setup')
INSTALL = Path('/usr/local/lib/mani-vmlab')
DATA = Path('/home/mani-vmlab-data')
SOURCE = INSTALL/'backend.py'
USER_SOURCE = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1/native/backend.py')
DEPENDENCY = SETUP/'production_setup.py'
DEPENDENCY_SHA = '3692bc6b2877f99ae4829aba61164933051068bf47278850eda761499c6eadfd'
BEFORE_SHA = 'be1f398abbe76277497eeb7799aba566eea4af0af862c7f832dd2498d264404f'
AFTER_SHA = 'e52e8ce5c600361764e41b790f1d8a611d1fdce17ee838f013bf6627b6931116'
BASE_PACK = '766142c86543e30b61d7667cc5846ea3c61974a644903ca3ba2b3c0306911d4b'
RUNTIME = SETUP/'runtime-installed.json'
COMPLETE = STATE/'workspace-complete-register.json'
TRANSACTION = STATE/'backend-writer-v6'
BACKEND_UNIT = Path('/run/systemd/system/mani-vmlab-backend.service')
VARIANTS = frozenset(('b7759999d69739d1e7bffc14a5e721efdb362b0912734bc82562f7798925ce51',
                      'a46298d81716912a2c329f5b89f7f736fad65280f4c93d3864c3b044606a35fe'))
X11_HELPER = SETUP/'production_x11_setup.py'
X11_HELPER_SHA = '3c80a7b77e9964d8d799baab7b7cb96c19cdf65ee2c7f5a417b121a69cf70d43'
X11_TRANSACTION = STATE/'production-x11-v6'
APP_UNIT = Path('/etc/systemd/system/hermes-workspace-runtime.service')
APP_BEFORE_SHA = '50fde8247142feebdadefb930a9a05cdeda304f88ad1798f9def431dcaeb1a6c'
SERVICE = 'mani-vmlab-supervisor.service'
SOCKET = 'mani-vmlab-supervisor.socket'
IDENTITY_KEYS = ('path','device','inode','sha256','uid','mode')
RUNTIME_KEYS = ('path','device','inode','sha256')
POLICY = ('supervisor.py','vm_service.py','guest/qualify.py','guest/bootstrap.py','lab/state.py','lab/process.py')
NORMAL_FILES = frozenset(('.config/systemd/user/manibot-llama.service','.config/systemd/user/qwen-local.service',
                          '.local/bin/start-manibot-llama','.hermes/config.yaml'))
ENV = {'PATH':'/usr/bin:/bin','LANG':'C','HOME':'/home/mani','XDG_RUNTIME_DIR':'/run/user/1000',
       'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
TARGETS = {'source':SOURCE,'runtime':RUNTIME,'complete':COMPLETE}
PHASES = frozenset(('preparing','prepared','quiesced','source_written','runtime_written','complete_written','activated','installed',
                    'rollback_prepared','rollback_source','rollback_runtime','rollback_complete','rolled_back'))


def check(value, code):
    if not value: raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value,indent=2)+'\n').encode()


def protected_read(path, maximum=4*1024*1024):
    path=Path(path)
    check(path.is_absolute() and '..' not in path.parts,'fixed_absolute_path_required')
    directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            info=os.fstat(child)
            if info.st_uid!=0 or info.st_mode&0o022:
                os.close(child);raise RuntimeError('protected_parent_required')
            os.close(directory);directory=child
        descriptor=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    finally: os.close(directory)
    with os.fdopen(descriptor,'rb') as stream:
        info=os.fstat(stream.fileno())
        check(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0
              and not info.st_mode&0o022 and info.st_size<=maximum,'bounded_protected_regular_file_required')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
        check(len(raw)<=maximum and (info.st_size,info.st_mtime_ns,info.st_ctime_ns)==
              (after.st_size,after.st_mtime_ns,after.st_ctime_ns),'protected_read_changed')
    return raw,dict(path=str(path),device=info.st_dev,inode=info.st_ino,sha256=sha(raw),uid=info.st_uid,mode=stat.S_IMODE(info.st_mode))


def dependency_row(register, actual):
    rows=inventory(register,'files')
    check(str(DEPENDENCY) in rows and all(rows[str(DEPENDENCY)].get(k)==actual[k] for k in IDENTITY_KEYS)
          and 'allowed_sha256' not in rows[str(DEPENDENCY)],'registered_pinned_dependency_required')


def load_trusted():
    _,own=protected_read(SELF)
    check(own['mode']==0o644,'fixed_helper0644_required')
    raw,dependency=protected_read(DEPENDENCY)
    check(dependency['sha256']==DEPENDENCY_SHA and dependency['mode']==0o644,'pinned_dependency_required')
    register,_=protected_read(COMPLETE);dependency_row(json.loads(register),dependency)
    spec=importlib.util.spec_from_file_location('_registered_production_setup',DEPENDENCY)
    trusted=importlib.util.module_from_spec(spec);spec.loader.exec_module(trusted)
    check(protected_read(DEPENDENCY)[1]==dependency,'dependency_changed_during_import')
    return trusted,own


def inventory(document,key):
    check(isinstance(document,dict) and isinstance(document.get(key),list) and 1<=len(document[key])<=1024,
          'bounded_existing_inventory_required')
    rows=document[key]
    check(all(isinstance(row,dict) and isinstance(row.get('path'),str) and Path(row['path']).is_absolute()
              and '..' not in Path(row['path']).parts for row in rows),'absolute_registered_paths_required')
    result={row['path']:row for row in rows}
    check(len(result)==len(rows),'unique_registration_required')
    return result


def replace_source_row(document,key,item):
    rows=inventory(document,key)
    check(str(SOURCE) in rows,'existing_backend_source_registration_required')
    keys=IDENTITY_KEYS if key=='files' else RUNTIME_KEYS
    replacement={**rows[str(SOURCE)],**{k:item[k] for k in keys}}
    # Preserve any uid/mode fields already carried by the older runtime format.
    for k in ('uid','mode'):
        if k in replacement: replacement[k]=item[k]
    result={**document,key:[replacement if row['path']==str(SOURCE) else dict(row) for row in document[key]]}
    check({k:v for k,v in result.items() if k!=key}=={k:v for k,v in document.items() if k!=key},'registration_metadata_preserved')
    check(all(row==rows[path] for path,row in inventory(result,key).items() if path!=str(SOURCE)),
          'unrelated_registration_preserved')
    return result


def validate_payload(raw):
    check(len(raw)<=65536 and sha(raw)==AFTER_SHA,'frozen_backend_source_required')
    return raw


READ_USER_SOURCE = r'''import os,pathlib,stat,sys
p=pathlib.Path('''+repr(str(USER_SOURCE))+r''')
assert os.getuid()==1000 and os.geteuid()==1000 and not any(q.is_symlink() for q in (p,*p.parents))
f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(f,'rb')as s:
 i=os.fstat(s.fileno());assert stat.S_ISREG(i.st_mode) and i.st_nlink==1 and i.st_uid==1000 and not i.st_mode&0o022 and i.st_size<=65536
 raw=s.read(65537);a=os.fstat(s.fileno());assert (i.st_ino,i.st_size,i.st_mtime_ns,i.st_ctime_ns)==(a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
 sys.stdout.buffer.write(raw)
'''

USER_GUARD = r'''import json,os,pathlib,sqlite3,stat,urllib.request
assert os.getuid()==1000 and os.geteuid()==1000
p=pathlib.Path('/home/mani/HermesLab/catalog.sqlite3')
assert not any(q.is_symlink() for q in (p,*p.parents))
i=p.stat();assert stat.S_ISREG(i.st_mode) and i.st_uid==1000 and i.st_nlink==1 and not i.st_mode&0o077
c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=2)
try:
 c.execute('PRAGMA query_only=ON')
 counts=[c.execute(q).fetchone()[0]for q in ("SELECT COUNT(*) FROM chat_runs WHERE state NOT IN ('completed','cancelled','failed')","SELECT COUNT(*) FROM jobs WHERE state NOT IN ('review_ready','failed','cancelled','blocked')","SELECT COUNT(*) FROM permission_actions WHERE state IN ('allowed','executing','cancelling')")]
finally:c.close()
assert (p.stat().st_dev,p.stat().st_ino)==(i.st_dev,i.st_ino)
o=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with o.open('http://127.0.0.1:8080/slots',timeout=2)as r:s=json.loads(r.read(65537))
assert counts==[0,0,0]and isinstance(s,list)and s and all(isinstance(x,dict)and x.get('is_processing')is False for x in s)
print('idle')
'''

STATUS_PROBE = r'''import json,os,socket,stat,struct
assert os.getuid()==1000 and os.geteuid()==1000
p='/run/mani-vmlab/control.sock';i=os.lstat(p)
assert stat.S_ISSOCK(i.st_mode)and i.st_uid==0
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)as c:
 c.settimeout(8);c.connect(p);pid,uid,gid=struct.unpack('3i',c.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));assert uid==0
 c.sendall(b'{"operation":"status"}\n');c.shutdown(socket.SHUT_WR);raw=bytearray()
 while True:
  block=c.recv(8192)
  if not block:break
  raw.extend(block);assert len(raw)<=262144
v=json.loads(raw);f=v['observed_facts']
assert v['status']=='ok'and v['window_status']=='closed'and f['pinned_model_and_backend_artifacts_current']is True
assert f['inference_window_active']is False and f['owned_fleet_active']is False and v['guest_agents_enabled']is False
print(json.dumps({'peer_uid':uid,'artifact_proof_current':True,'inference_started':False,'VM_started':False,'VM_watchdog_qualified':f['VM_watchdog_qualified']}))
'''


class Native:
    transaction=TRANSACTION
    targets=TARGETS

    def __init__(self,trusted,own): self.trusted,self.own=trusted,own
    def read(self,path): return protected_read(path)
    def same(self,item): return self.trusted.unchanged(item)
    def write(self,path,raw,mode): return self.trusted.write_file(path,raw,mode=mode)
    def run(self,args,timeout=15):
        return subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=timeout,env=ENV).stdout
    def user(self,code):
        return self.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/python3','-I','-c',code])
    def payload(self): return validate_payload(self.user(READ_USER_SOURCE))
    def exists(self,path):
        check(not Path(path).is_symlink(),'preserve_symlink_transaction_or_guard')
        return Path(path).exists()
    def prepare_directory(self):
        self.trusted.protected_directory(STATE)
        self.transaction.mkdir(mode=0o700)
        self.trusted.protected_directory(self.transaction)
    def stage(self,name,target,raw,mode):
        path=self.transaction/name
        if self.exists(path):
            existing,item=self.read(path)
            check(existing==raw and item['mode']==mode and item['uid']==0,'preserve_unknown_prepared_stage')
        else:item=self.write(path,raw,mode)
        return {**item,'path':str(target),'stage':name}
    def commit(self,item):
        stage=self.transaction/item['stage']
        actual=self.read(stage)[1]
        check(all(actual[k]==item[k]for k in IDENTITY_KEYS if k!='path'),'preserve_changed_stage')
        with self.trusted.parent_fd(stage)as(src,sname),self.trusted.parent_fd(Path(item['path']))as(dst,dname):
            os.replace(sname,dname,src_dir_fd=src,dst_dir_fd=dst);os.fsync(dst)
        check(self.same(item),'published_stage_identity_required')
    def unit(self,name,property):
        return self.run(['/usr/bin/systemctl','show',name,'-p',property,'--value']).strip().decode('ascii')
    def pid(self):
        value=int(self.unit(SERVICE,'MainPID')or'0')
        if value:
            p=Path('/proc')/str(value)
            uid=next(line.split()[1:]for line in(p/'status').read_text().splitlines()if line.startswith('Uid:'))
            check(uid==['0']*4 and (p/'cmdline').read_bytes().split(b'\0')[:3]==
                  [b'/usr/bin/python3',b'-I',os.fsencode(INSTALL/'supervisor.py')],'fixed_root_supervisor_process_required')
        return value
    def socket_state(self):
        state=self.unit(SOCKET,'ActiveState')
        check(state in ('active','inactive','failed'),'stable_supervisor_socket_required')
        return state
    def guard(self,allow_x11=False):
        check(allow_x11 or not self.exists(X11_TRANSACTION),'overlay_must_precede_X11_transaction')
        window=json.loads(self.read(DATA/'window/state.json')[0])
        check(window.get('status')=='closed' and window.get('restored_health')is True
              and bool(window.get('configuration_hashes_equal'))and all(window['configuration_hashes_equal'].values()),
              'closed_recovered_window_required')
        for name in ('mani-vmlab-backend.service','mani-vmlab-inference-window.service'):
            check(self.unit(name,'ActiveState')in('inactive','failed')and self.unit(name,'MainPID')=='0','inactive_backend_and_window_required')
        runs=DATA/'runs';info=runs.lstat()
        check(stat.S_ISDIR(info.st_mode)and info.st_uid==0 and not info.st_mode&0o022,'protected_fleet_directory_required')
        paths=list(runs.iterdir());check(len(paths)<=4096,'bounded_fleet_required')
        for path in paths:
            check(path.is_dir()and not path.is_symlink()and re.fullmatch('[a-f0-9]{32}',path.name),'known_fleet_inventory_required')
            check(json.loads(self.read(path/'manifest.json')[0]).get('status')!='active','no_active_fleet_required')
        active=self.run(['/usr/bin/systemctl','list-units','--state=active,activating,deactivating','--no-legend','--plain',
                         'mani-vmlab-*-controller.service','mani-vmlab-*-worker_a.service','mani-vmlab-*-worker_b.service'])
        check(not active.strip()and self.user(USER_GUARD).strip()==b'idle','idle_app_normal_slots_and_VM_units_required')
        normal=json.loads(self.read(SETUP/'normal-profile.lock.json')[0])
        check(set(normal)==NORMAL_FILES and all(re.fullmatch('[a-f0-9]{64}',v)for v in normal.values()),'fixed_normal_profile_pins_required')
        self.trusted.normal_unchanged({'normal_configuration_sha256':normal})
        return {'normal_configuration_sha256':normal,'no_inference':True,'no_VM':True}
    def artifact_proof(self):
        lock_path=SETUP/'backend-artifacts.lock.json';raw,_=self.read(lock_path)
        lock_sha='560a28dbe71b021887a8d6d546a4c128cd02ee99e8bce67a4ace506e5a7e19fa'
        check(sha(raw)==lock_sha,'pinned_artifact_lock_required');lock=json.loads(raw)
        proof=json.loads(self.read(DATA/'artifact-proof.json')[0])
        check(set(lock['models'])=={'normal','abliterated'}and len(lock['backend_files'])==40,'fixed42_artifact_inventory_required')
        expected=[(DATA/'models'/(arm+'.gguf'),row)for arm,row in lock['models'].items()]
        check(all(re.fullmatch('[A-Za-z0-9_.+-]+',row['name'])for row in lock['backend_files']),'fixed_backend_artifact_names_required')
        expected += [(DATA/'backend-b9980'/row['name'],row)for row in lock['backend_files']]
        rows={row['path']:row for row in proof['files']}
        check(len(rows)==len(proof['files'])==42 and set(rows)=={str(p)for p,_ in expected}
              and proof['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
              and proof['lock_sha256']==lock_sha,'current42_artifact_proof_required')
        for path,row in expected:
            i=path.lstat();identity=[i.st_dev,i.st_ino,i.st_size,i.st_mtime_ns,i.st_ctime_ns]
            check(stat.S_ISREG(i.st_mode)and i.st_nlink==1 and i.st_uid==0 and not i.st_mode&0o022
                  and identity==rows[str(path)]['identity']and i.st_size==row['bytes']
                  and rows[str(path)]['sha256']==row['sha256'],'preserve_artifact_identity_drift')
        return {'verified_file_count':42,'full_model_hashes_repeated':False}
    def snapshot(self):
        required=[Path('/etc/mani-vmlab/config.json'),STATE/'runtime-source.zip',SETUP/'runtime-source.sha256',
                  SETUP/'backend-artifacts.lock.json',DATA/'artifact-proof.json',SETUP/'normal-profile.lock.json',
                  Path('/etc/systemd/system')/SERVICE,Path('/etc/systemd/system')/SOCKET,BACKEND_UNIT,
                  *[INSTALL/name for name in POLICY]]
        optional=[STATE/'VM-watchdog-qualified.json',STATE/'workspace-qualified.json']
        proof={str(path):self.read(path)[1]for path in required}
        for path in optional:proof[str(path)]=self.read(path)[1]if self.exists(path)else None
        receipt=proof[str(STATE/'workspace-qualified.json')]
        if receipt:
            path=Path(json.loads(self.read(STATE/'workspace-qualified.json')[0])['report'])
            check(path.parent==Path('/var/lib/mani-vmlab-review')and re.fullmatch('workspace-[0-9]{8}T[0-9]{6}Z.json',path.name),
                  'fixed_qualification_report_scope_required')
            proof[str(path)]=self.read(path)[1]
        config=json.loads(self.read(Path('/etc/mani-vmlab/config.json'))[0])
        check(config.get('source_pack_sha256')==BASE_PACK and config.get('workspace_api')==1
              and config.get('agents_enabled')is False,'fixed_base_workspace_configuration_required')
        check(proof[str(STATE/'runtime-source.zip')]['sha256']==BASE_PACK
              and self.read(SETUP/'runtime-source.sha256')[0].strip().decode()==BASE_PACK,'immutable_base_source_archive_required')
        self.artifact_proof()
        return proof
    def unchanged_snapshot(self,proof):
        for path,item in proof.items():
            check(self.same(item)if item else not self.exists(Path(path)),'preserve_policy_artifact_or_qualification_drift')
        self.artifact_proof()
    def validate_registers(self,documents,source):
        complete=documents['complete'];runtime=documents['runtime']
        check(complete.get('version')==1 and complete.get('source_pack_sha256')==BASE_PACK
              and runtime.get('status')=='installed'and runtime.get('source_pack_sha256')==BASE_PACK,
              'existing_base_installed_registers_required')
        dependency_row(complete,self.read(DEPENDENCY)[1]);self.trusted.inspect_register(complete)
        for key,field in (('complete','files'),('runtime','installed_files')):
            rows=inventory(documents[key],field)
            check(str(SOURCE)in rows and not {str(RUNTIME),str(COMPLETE)}&set(rows),'no_registry_self_or_cross_registration')
            keys=IDENTITY_KEYS if key=='complete'else RUNTIME_KEYS
            check(all(rows[str(SOURCE)].get(k)==source[k]for k in keys),'exact_old_backend_row_required')
            if key=='runtime':
                for row in rows.values():
                    actual=self.trusted.fingerprint(Path(row['path']))
                    check(all(actual[k]==row[k]for k in RUNTIME_KEYS),'preserve_runtime_registration_drift')
        row=inventory(complete,'files').get(str(BACKEND_UNIT));actual=self.read(BACKEND_UNIT)[1]
        check(row and set(row.get('allowed_sha256',()))==VARIANTS and len(row['allowed_sha256'])==2
              and actual['sha256']in VARIANTS and actual['uid']==0 and actual['mode']==0o644,
              'mode_reconciled_original_allowed_unit_required')
    def unchanged_registered(self,journal):
        check(sha(self.read(self.transaction/'source.before')[0])==BEFORE_SHA,'preserve_original_source_backup_drift')
        documents={}
        for role in ('runtime','complete'):
            raw,_=self.read(self.transaction/(role+'.before'))
            check(sha(raw)==journal['before'][role]['sha256'],'preserve_original_registry_backup_drift')
            documents[role]=json.loads(raw)
        complete=documents['complete']
        if journal.get('rollback_chain'):
            chain=journal['rollback_chain']
            check(all(self.same(chain[role])for role in ('helper','journal','unit')),'preserve_recognized_X11_history_drift')
            raw,_=self.read(self.transaction/'complete.after-x11-rollback.before')
            check(sha(raw)==chain['complete']['sha256'],'preserve_X11_chain_register_backup_drift')
            complete=json.loads(raw)
        self.trusted.inspect_register({**complete,'files':[row for row in complete['files']if row['path']!=str(SOURCE)]})
        for row in documents['runtime']['installed_files']:
            if row['path']==str(SOURCE):continue
            actual=self.trusted.fingerprint(Path(row['path']))
            check(all(actual[k]==row[k]for k in RUNTIME_KEYS),'preserve_unrelated_runtime_drift')
    def recognize_x11_rollback(self,journal):
        """One exact later native transaction, never an arbitrary new baseline."""
        if not self.exists(X11_TRANSACTION):return None
        check(journal['phase']=='installed','finish_overlay_before_X11_chain_rollback')
        _,helper=self.read(X11_HELPER)
        check(helper['sha256']==X11_HELPER_SHA and helper['mode']==0o644,'pinned_X11_chain_helper_required')
        raw,history=self.read(X11_TRANSACTION/'journal.json');x11=json.loads(raw)
        check(x11.get('version')==1 and x11.get('repair')=='production_x11_v6'and x11.get('phase')=='rolled_back'
              and x11.get('helper_sha256')==X11_HELPER_SHA,'only_completed_X11_rollback_history_allowed')
        same=lambda left,right:all(left.get(k)==right.get(k)for k in IDENTITY_KEYS)
        check(same(x11['before']['register'],journal['new']['complete']), 'X11_chain_must_start_at_overlay_register')
        _,unit=self.read(APP_UNIT);raw,current=self.read(COMPLETE)
        check(same(unit,x11['rollback']['unit']) and same(current,x11['rollback']['register'])
              and unit['sha256']==APP_BEFORE_SHA and unit['mode']==0o644 and unit['uid']==0,
              'exact_X11_rolled_back_unit_and_register_required')
        baseline_raw,_=self.read(self.transaction/'complete.before')
        check(sha(baseline_raw)==journal['before']['complete']['sha256'],'preserve_overlay_base_register_backup')
        baseline=json.loads(baseline_raw)
        expected=replace_source_row(baseline,'files',journal['new']['source'])
        old=inventory(expected,'files');actual=inventory(json.loads(raw),'files')
        check(str(APP_UNIT)in old and same(old[str(APP_UNIT)],x11['before']['unit']), 'X11_chain_original_app_unit_required')
        expected_row={**old[str(APP_UNIT)],**{k:unit[k]for k in IDENTITY_KEYS}}
        check(set(actual)==set(old)and actual[str(APP_UNIT)]==expected_row
              and all(actual[path]==row for path,row in old.items()if path!=str(APP_UNIT))
              and {k:v for k,v in json.loads(raw).items()if k!='files'}=={k:v for k,v in expected.items()if k!='files'},
              'only_exact_X11_app_unit_registration_may_differ')
        check(self.same(journal['new']['source']) and self.same(journal['new']['runtime']),
              'exact_installed_overlay_source_and_runtime_register_required')
        self.trusted.inspect_register(json.loads(raw))
        check(self.same(helper)and self.same(history)and self.same(unit)and self.same(current),'X11_chain_changed_during_read')
        backup=self.transaction/'complete.after-x11-rollback.before'
        if self.exists(backup):check(self.read(backup)[0]==raw,'preserve_existing_X11_chain_backup')
        else:self.write(backup,raw,0o600)
        return {'helper':helper,'journal':history,'unit':unit,'complete':current}
    def quiesce(self):
        self.run(['/usr/bin/systemctl','stop',SOCKET]);self.run(['/usr/bin/systemctl','stop',SERVICE])
        check(self.socket_state()in('inactive','failed')and self.pid()==0,'supervisor_and_socket_must_be_stopped')
    def activate(self,old_pid):
        self.run(['/usr/bin/systemctl','start',SOCKET]);self.run(['/usr/bin/systemctl','start',SERVICE],timeout=35)
        pid=self.pid();check(pid>1 and pid!=old_pid and self.socket_state()=='active','fresh_supervisor_PID_required')
        proof=json.loads(self.user(STATUS_PROBE))
        check(proof.get('peer_uid')==0 and self.pid()==pid,'fresh_operator_reply_required')
        # Activated listening sockets may report PID1 as their peer credential;
        # tie the fixed unit's fresh MainPID to observations before/after status.
        return {**proof,'pid':pid}
    def restore_states(self,before):
        check(before['socket_state']=='active' and before['pid']>1,'fixed_original_active_units_required')
        return self.activate(before['pid'])


class Overlay:
    """Explicit source/register commit ownership; service operations stay in Native."""
    def __init__(self,native): self.n=native
    def save(self,journal):self.n.write(self.n.transaction/'journal.json',encoded(journal),0o600)
    def load(self):
        journal=json.loads(self.n.read(self.n.transaction/'journal.json')[0])
        check(journal.get('version')==1 and journal.get('kind')=='registered_backend_writer_overlay'
              and journal.get('helper_sha256')==self.n.own['sha256']and journal.get('base_source_pack_sha256')==BASE_PACK
              and journal.get('source_before_sha256')==BEFORE_SHA and journal.get('source_after_sha256')==AFTER_SHA
              and journal.get('phase')in PHASES,'exact_owned_overlay_journal_required')
        check(set(journal['before'])==set(TARGETS) and set(journal['new'])<=set(TARGETS),'exact_owned_target_set_required')
        check(journal['before']['source']['sha256']==BEFORE_SHA and journal['before']['source']['uid']==0
              and journal['before']['source']['mode']==0o644,'exact_journal_source_preimage_required')
        if 'source'in journal['new']:
            check(journal['new']['source']['sha256']==AFTER_SHA and journal['new']['source']['uid']==0
                  and journal['new']['source']['mode']==0o644,'exact_journal_source_postimage_required')
        check(journal['phase']in('preparing','rolled_back')or set(journal['new'])==set(TARGETS),'complete_staged_publication_required')
        chain=journal.get('rollback_chain')
        if chain:
            check(set(chain)=={'helper','journal','unit','complete'}
                  and chain['helper']['path']==str(X11_HELPER)and chain['helper']['sha256']==X11_HELPER_SHA
                  and chain['journal']['path']==str(X11_TRANSACTION/'journal.json')
                  and chain['unit']['path']==str(APP_UNIT)and chain['unit']['sha256']==APP_BEFORE_SHA
                  and chain['complete']['path']==str(COMPLETE),'fixed_recognized_X11_chain_required')
        for stage in ('before','new','rollback'):
            for role,item in journal.get(stage,{}).items():
                check(role in TARGETS and item['path']==str(TARGETS[role]),'fixed_overlay_journal_paths_required')
                if 'stage'in item:check(item['stage']==('new-'if stage=='new'else'rollback-')+role,'fixed_stage_name_required')
        return journal
    def guard(self,journal):
        self.n.guard(allow_x11=bool(journal.get('rollback_chain')))
        self.n.unchanged_snapshot(journal['snapshot']);self.n.unchanged_registered(journal)
    def expect_owned(self,journal):
        for role in TARGETS:
            options=[journal['before'][role]]
            if role in journal['new']:options.append(journal['new'][role])
            if role in journal.get('rollback',{}):options.append(journal['rollback'][role])
            if role=='complete' and journal.get('rollback_chain'):options.append(journal['rollback_chain']['complete'])
            check(any(self.n.same(item)for item in options),'preserve_unowned_source_or_register_drift')
    def prepare(self):
        check(not self.n.exists(self.n.transaction),'review_existing_overlay_transaction_first')
        payload=self.n.payload();self.n.guard();proof=self.n.snapshot()
        originals={role:self.n.read(path)for role,path in TARGETS.items()}
        check(originals['source'][1]['sha256']==BEFORE_SHA and originals['source'][1]['uid']==0
              and originals['source'][1]['mode']==0o644,'exact_protected_old_backend_source_required')
        docs={role:json.loads(originals[role][0])for role in ('runtime','complete')}
        self.n.validate_registers(docs,originals['source'][1])
        before_state={'pid':self.n.pid(),'socket_state':self.n.socket_state()}
        check(before_state['socket_state']=='active' and before_state['pid']>1,'existing_active_supervisor_and_socket_required')
        self.n.prepare_directory()
        journal={'version':1,'kind':'registered_backend_writer_overlay','phase':'preparing','helper_sha256':self.n.own['sha256'],
                 'base_source_pack_sha256':BASE_PACK,'source_before_sha256':BEFORE_SHA,'source_after_sha256':AFTER_SHA,
                 'before':{role:item for role,(_,item)in originals.items()},'new':{},'rollback':{},'snapshot':proof,
                 'before_service':before_state,'effective_source':'immutable base archive plus this exact one-file overlay',
                 'qualifications_rewritten':False,'original_allowlist_preserved':True}
        self.save(journal)
        return self.finish_prepare(journal,payload)
    def finish_prepare(self,journal,payload=None):
        check(all(self.n.same(item)for item in journal['before'].values()),'preserve_original_during_preparation')
        self.n.guard();self.n.unchanged_snapshot(journal['snapshot'])
        payload=self.n.payload()if payload is None else payload
        originals={role:self.n.read(path)for role,path in TARGETS.items()}
        for role,(raw,_)in originals.items():
            backup=self.n.transaction/(role+'.before')
            if self.n.exists(backup):check(self.n.read(backup)[0]==raw,'preserve_preparation_backup_drift')
            else:self.n.write(backup,raw,0o600)
        docs={role:json.loads(originals[role][0])for role in ('runtime','complete')}
        for role in ('source','runtime','complete'):
            if role in journal['new']:
                item=journal['new'][role]
                actual=self.n.read(self.n.transaction/item['stage'])[1]
                check(all(actual[k]==item[k]for k in IDENTITY_KEYS if k!='path'),'preserve_recorded_stage_drift')
                continue
            raw=payload if role=='source'else encoded(replace_source_row(docs[role],
                'installed_files'if role=='runtime'else'files',journal['new']['source']))
            journal['new'][role]=self.n.stage('new-'+role,TARGETS[role],raw,0o644 if role=='source'else 0o600)
            self.save(journal)
        journal['phase']='prepared';self.save(journal)
        return journal
    def apply(self):
        check(not self.n.exists(X11_TRANSACTION),'overlay_apply_must_precede_X11_transaction')
        if self.n.exists(self.n.transaction):
            journal=self.load()
            if journal['phase']=='preparing':journal=self.finish_prepare(journal)
            if journal['phase']=='installed':
                check(all(self.n.same(item)for item in journal['new'].values()),'preserve_installed_overlay_drift')
                self.guard(journal)
                return {'status':'already_installed','source_sha256':AFTER_SHA,'GPU_window_opened':False}
            check(journal['phase']not in('rolled_back','rollback_prepared','rollback_source','rollback_runtime','rollback_complete'),
                  'explicit_rollback_state_requires_review')
        else:journal=self.prepare()
        self.expect_owned(journal);self.guard(journal)
        self.n.quiesce();journal['phase']='quiesced';self.save(journal)
        self.guard(journal);self.expect_owned(journal)
        for role in ('source','runtime','complete'):
            if not self.n.same(journal['new'][role]):
                check(self.n.same(journal['before'][role]),'preserve_commit_target_drift')
                self.n.commit(journal['new'][role])
            journal['phase']=role+'_written';self.save(journal)
        self.guard(journal)
        journal['activation']=self.n.activate(journal['before_service']['pid']);journal['phase']='activated';self.save(journal)
        self.guard(journal)
        check(set(journal['new'])==set(TARGETS)and all(self.n.same(item)for item in journal['new'].values()),'preserve_post_activation_overlay_drift')
        journal['phase']='installed';self.save(journal)
        return {'status':'installed','source_sha256':AFTER_SHA,'base_source_pack_sha256':BASE_PACK,
                'one_file_overlay':True,'fresh_supervisor_pid':journal['activation']['pid'],'GPU_window_opened':False,
                'qualifications_rewritten':False,'original_allowlist_preserved':True}
    def rollback(self):
        journal=self.load()
        if not journal.get('rollback_chain'):
            chain=self.n.recognize_x11_rollback(journal)
            if chain:journal['rollback_chain']=chain;self.save(journal)
        self.expect_owned(journal)
        self.guard(journal)
        if journal['phase']=='rolled_back':
            check(all(self.n.same(item)for item in journal['rollback'].values()),'preserve_rolled_back_overlay_drift')
            return {'status':'already_rolled_back','GPU_window_opened':False}
        self.n.quiesce();self.guard(journal);self.expect_owned(journal)
        # No publication occurred: retain the original source and both original registries.
        if all(self.n.same(item)for item in journal['before'].values()):
            journal['rollback']=journal['before'];journal['restoration']=self.n.restore_states(journal['before_service'])
            journal['phase']='rolled_back';self.save(journal)
            return {'status':'rolled_back','source_write_required':False,'GPU_window_opened':False}
        if not journal['rollback']:
            raw,info=self.n.read(self.n.transaction/'source.before')
            check(sha(raw)==BEFORE_SHA,'preserve_original_source_backup_drift')
            restored=self.n.stage('rollback-source',SOURCE,raw,journal['before']['source']['mode'])
            rollback={'source':restored}
            for role,key in (('runtime','installed_files'),('complete','files')):
                chain=journal.get('rollback_chain')if role=='complete'else None
                path=self.n.transaction/('complete.after-x11-rollback.before'if chain else role+'.before')
                raw,_=self.n.read(path)
                check(sha(raw)==(chain['complete']['sha256']if chain else journal['before'][role]['sha256']),
                      'preserve_registry_backup_drift')
                rollback[role]=self.n.stage('rollback-'+role,TARGETS[role],encoded(replace_source_row(json.loads(raw),key,restored)),0o600)
            journal['rollback']=rollback;journal['phase']='rollback_prepared';self.save(journal)
        for role in ('source','runtime','complete'):
            if not self.n.same(journal['rollback'][role]):
                self.expect_owned(journal);self.n.commit(journal['rollback'][role])
            journal['phase']='rollback_'+role;self.save(journal)
        self.guard(journal)
        journal['restoration']=self.n.restore_states(journal['before_service'])
        self.guard(journal)
        check(all(self.n.same(item)for item in journal['rollback'].values()),'preserve_final_rollback_drift')
        journal['phase']='rolled_back';self.save(journal)
        return {'status':'rolled_back','source_sha256':BEFORE_SHA,'restored_inode_reregistered':True,
                'base_source_pack_sha256':BASE_PACK,'GPU_window_opened':False}


def acquire_lock(path,create):
    flags=os.O_RDWR|os.O_NOFOLLOW|(os.O_CREAT if create else 0)
    fd=os.open(path,flags,0o600)
    try:
        info=os.fstat(fd)
        check(stat.S_ISREG(info.st_mode)and info.st_uid==0 and info.st_nlink==1 and not info.st_mode&0o022,
              'protected_single_link_lock_required')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return fd
    except BaseException:os.close(fd);raise


def main():
    check(os.geteuid()==0 and Path(__file__).absolute()==SELF,'fixed_native_overlay_only')
    check(len(sys.argv)==2 and sys.argv[1]in('apply','rollback'),'apply_or_rollback_required')
    trusted,own=load_trusted();native=Native(trusted,own)
    trusted.protected_directory(STATE);trusted.protected_directory(DATA/'window')
    locks=[]
    def deadline(_signum,_frame):raise TimeoutError('backend_overlay_180_second_deadline')
    previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(180)
    try:
        # Share the established repair/window order before this own transaction
        # lock. A new inference window cannot quiesce normal Qwen mid-commit.
        for path in (STATE/'production-x11-v6.lock',DATA/'window/lock',STATE/'backend-writer-v6.lock'):
            locks.append(acquire_lock(path,path.parent==STATE))
        result=getattr(Overlay(native),sys.argv[1])();print(json.dumps(result),flush=True)
    except Exception as error:
        detail=str(error)
        print(json.dumps({'status':'failed','operation':sys.argv[1],
                          'error_code':detail if re.fullmatch('[A-Za-z0-9_]{1,120}',detail)else'native_boundary_failed',
                          'error_category':type(error).__name__,'GPU_window_opened':False,
                          'recovery':'Preserve the journal; resume only an owned partial apply or explicitly roll back.'}),flush=True)
        raise SystemExit(2)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        for fd in reversed(locks):os.close(fd)


if __name__=='__main__':main()
