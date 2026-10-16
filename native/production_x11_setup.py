"""Fixed one-line app mount repair. No model inference or lab/Qwen mutations.

Install only after source review and fresh native authentication. Root never
imports checkout code; the sole Python dependency is pinned, protected and
already fingerprinted in the existing complete recovery register.
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
import time

sys.dont_write_bytecode = True
SELF = Path('/usr/local/lib/mani-vmlab-setup/production_x11_setup.py')
SETUP = SELF.parent
DEPENDENCY = SETUP / 'production_setup.py'
DEPENDENCY_SHA = '3692bc6b2877f99ae4829aba61164933051068bf47278850eda761499c6eadfd'
STATE = Path('/var/lib/mani-vmlab-setup')
REGISTER = STATE / 'workspace-complete-register.json'
TRANSACTION = STATE / 'production-x11-v6'
UNIT = Path('/etc/systemd/system/hermes-workspace-runtime.service')
UNIT_NAME = UNIT.name
ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
BEFORE_SHA = '50fde8247142feebdadefb930a9a05cdeda304f88ad1798f9def431dcaeb1a6c'
AFTER_SHA = 'c298fd0222252480418520c4c5c975794c1570687dcbb91a20ad71b5d208f7af'
BIND_LINE = b'BindReadOnlyPaths=/tmp/.X11-unix:/tmp/.X11-unix:norbind\n'
NORMAL_FILES = frozenset(('.config/systemd/user/manibot-llama.service', '.config/systemd/user/qwen-local.service',
                          '.local/bin/start-manibot-llama', '.hermes/config.yaml'))
ENV = {'PATH':'/usr/bin:/bin','LANG':'C','HOME':'/home/mani','XDG_RUNTIME_DIR':'/run/user/1000',
       'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
IDENTITY_KEYS = ('path','device','inode','sha256','uid','mode')
BACKEND_UNIT = Path('/run/systemd/system/mani-vmlab-backend.service')
BACKEND_SOURCE = Path('/usr/local/lib/mani-vmlab/backend.py')
BACKEND_SOURCE_SHA = 'be1f398abbe76277497eeb7799aba566eea4af0af862c7f832dd2498d264404f'
MODE_TRANSACTION = STATE / 'backend-mode-v6'
BACKEND_VARIANTS = {
    'normal':'b7759999d69739d1e7bffc14a5e721efdb362b0912734bc82562f7798925ce51',
    'abliterated':'a46298d81716912a2c329f5b89f7f736fad65280f4c93d3864c3b044606a35fe',
}
PHASES = frozenset(('prepared','unit_written','registered','reloaded','restarting','installed',
                    'rollback_unit','rollback_registered','rolled_back'))


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def protected_read(path, maximum=4*1024*1024):
    """Bootstrap trust before importing any non-standard-library code."""
    path = Path(path)
    check(path.is_absolute() and '..' not in path.parts, 'fixed_absolute_path_required')
    descriptor = os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            info = os.fstat(child)
            if info.st_uid != 0 or info.st_mode & 0o022:
                os.close(child)
                raise RuntimeError('protected_parent_required')
            os.close(descriptor); descriptor = child
        source = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=descriptor)
    finally:
        os.close(descriptor)
    with os.fdopen(source,'rb') as stream:
        info = os.fstat(stream.fileno())
        check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0
              and not info.st_mode & 0o022 and info.st_size <= maximum, 'protected_regular_input_required')
        raw = stream.read(maximum+1)
        check(len(raw)<=maximum,'bounded_protected_input_required')
        after = os.fstat(stream.fileno())
        check((info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),
              'protected_input_changed_during_read')
    return raw, {'path':str(path),'device':info.st_dev,'inode':info.st_ino,'sha256':digest(raw),
                 'uid':info.st_uid,'mode':stat.S_IMODE(info.st_mode)}


def registered_dependency(register, actual):
    check(isinstance(register,dict) and register.get('version')==1 and isinstance(register.get('files'),list),
          'existing_complete_register_required')
    paths = [item.get('path') for item in register['files'] if isinstance(item,dict)]
    check(len(paths)==len(register['files']) and len(paths)==len(set(paths)), 'unique_complete_register_required')
    matches = [item for item in register['files'] if item['path']==str(DEPENDENCY)]
    check(len(matches)==1 and 'allowed_sha256' not in matches[0]
          and all(matches[0].get(key)==actual[key] for key in IDENTITY_KEYS), 'registered_trusted_dependency_required')


def load_trusted_dependency():
    own_raw, own = protected_read(SELF)
    check(own['mode']==0o644,'fixed_root_helper_mode_required')
    raw, dependency = protected_read(DEPENDENCY)
    check(dependency['sha256']==DEPENDENCY_SHA and dependency['mode']==0o644,'pinned_root_dependency_required')
    register_raw, _ = protected_read(REGISTER)
    registered_dependency(json.loads(register_raw),dependency)
    # Only this protected source is imported. Its module top level has no
    # installer action and its imports are Python's standard library.
    spec = importlib.util.spec_from_file_location('_root_trusted_production_setup',DEPENDENCY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    check(protected_read(DEPENDENCY)[1]==dependency,'trusted_dependency_changed_during_import')
    return module, own


def audit(trusted):
    """Read-only fixed-unit classification; never an apply admission override."""
    register_raw, register_info = protected_read(REGISTER)
    register = json.loads(register_raw)
    registered_dependency(register,protected_read(DEPENDENCY)[1])
    rows = [row for row in register['files'] if row['path']==str(BACKEND_UNIT)]
    check(len(rows)==1,'audit_fixed_backend_registration_required')
    entry = rows[0]
    allowed = entry.get('allowed_sha256')
    check(isinstance(allowed,list) and 0<len(allowed)<=16
          and all(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) for value in allowed)
          and len(set(allowed))==len(allowed),'audit_bounded_existing_backend_allowlist_required')
    check(type(entry.get('uid')) is int and entry['uid']==0
          and type(entry.get('mode')) is int and 0<=entry['mode']<=0o7777,
          'audit_fixed_backend_metadata_required')
    unit_raw, unit_info = protected_read(BACKEND_UNIT,maximum=8192)
    source_raw, source_info = protected_read(BACKEND_SOURCE,maximum=1024*1024)
    sources = [row for row in register['files'] if row['path']==str(BACKEND_SOURCE)]
    source_registered = len(sources)==1 and all(sources[0].get(key)==source_info[key] for key in IDENTITY_KEYS)
    # This copied inventory is solely a diagnostic: apply still inspects the
    # unmodified complete register, including the fixed generated backend unit.
    other_entries = {**register,'files':[row for row in register['files'] if row['path']!=str(BACKEND_UNIT)]}
    try:
        trusted.inspect_register(other_entries)
        other_status = {'status':'PASS'}
    except (OSError,ValueError,RuntimeError):
        other_status = {'status':'FAIL','error_code':'other_registered_entry_mismatch'}
    check(protected_read(REGISTER)[1]==register_info,'audit_register_changed')
    check(protected_read(BACKEND_UNIT,maximum=8192)[1]==unit_info
          and protected_read(BACKEND_SOURCE,maximum=1024*1024)[1]==source_info,
          'audit_backend_input_changed')
    allowed_hash = unit_info['sha256'] in allowed
    return {'operation':'audit','status':'audited_read_only','GPU_window_opened':False,
            'writes_performed':False,'service_commands_performed':False,'admission_changed':False,
            'backend_unit':{'uid':unit_info['uid'],'mode':unit_info['mode'],'sha256':unit_info['sha256'],
                'bytes':len(unit_raw),'existing_registered_uid':entry['uid'],'existing_registered_mode':entry['mode'],
                'admission_required_mode':0o644,'mode_satisfies_generated_unit_admission':unit_info['mode']==0o644,
                'existing_allowed_sha256':list(allowed),'hash_in_existing_allowlist':allowed_hash,
                'mode_matches_registration':unit_info['mode']==entry['mode'],
                'matches_fixed_generator_variants':{arm:unit_info['sha256']==value for arm,value in BACKEND_VARIANTS.items()}},
            'installed_backend_source':{'sha256':source_info['sha256'],'bytes':len(source_raw),
                'registered_fingerprint_matches':source_registered,
                'matches_reviewed_source':source_info['sha256']==BACKEND_SOURCE_SHA},
            'all_other_registered_entries':other_status,
            'other_entry_check_scope':'existing_inspect_register_policy_skips_absent_paths'}


def amended_unit(raw):
    check(digest(raw)==BEFORE_SHA and raw.count(b'PrivateTmp=yes\n')==1
          and b'BindReadOnlyPaths=' not in raw and b'BindPaths=' not in raw,'exact_original_app_unit_required')
    result = raw.replace(b'PrivateTmp=yes\n',b'PrivateTmp=yes\n'+BIND_LINE)
    check(digest(result)==AFTER_SHA and len(result)-len(raw)==len(BIND_LINE),'fixed_one_line_amendment_required')
    return result


def merge_unit(register, item, merge):
    matches = [row for row in register['files'] if row['path']==item['path']]
    check(len(matches)==1,'existing_registered_app_unit_required')
    updated = merge(register,[item])
    check({k:v for k,v in updated.items() if k!='files'}=={k:v for k,v in register.items() if k!='files'},
          'unrelated_register_fields_must_survive')
    original = {row['path']:row for row in register['files']}
    current = {row['path']:row for row in updated['files']}
    check(set(original)==set(current) and all(current[k]==v for k,v in original.items() if k!=item['path']),
          'only_registered_app_unit_may_change')
    check(all(current[item['path']].get(k)==v for k,v in matches[0].items() if k not in IDENTITY_KEYS),
          'existing_unit_restore_metadata_must_survive')
    return updated


USER_GUARD = r'''import json,os,pathlib,sqlite3,stat,urllib.request
assert os.getuid()==1000 and os.geteuid()==1000
p=pathlib.Path('/home/mani/HermesLab/catalog.sqlite3')
assert not any(q.is_symlink() for q in (p,*p.parents))
i=p.stat();assert stat.S_ISREG(i.st_mode) and i.st_uid==1000 and i.st_nlink==1 and not i.st_mode&0o077
c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=2)
try:
 c.execute('PRAGMA query_only=ON')
 chats=c.execute("SELECT COUNT(*) FROM chat_runs WHERE state NOT IN ('completed','cancelled','failed')").fetchone()[0]
 jobs=c.execute("SELECT COUNT(*) FROM jobs WHERE state NOT IN ('review_ready','failed','cancelled','blocked')").fetchone()[0]
 actions=c.execute("SELECT COUNT(*) FROM permission_actions WHERE state IN ('allowed','executing','cancelling')").fetchone()[0]
finally:c.close()
assert (p.stat().st_dev,p.stat().st_ino)==(i.st_dev,i.st_ino)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:8080/slots',timeout=2)as r: slots=json.loads(r.read(65537))
assert isinstance(slots,list) and slots and all(isinstance(s,dict) and s.get('is_processing') is False for s in slots)
assert chats==0 and jobs==0 and actions==0
print(json.dumps({'active_chats':chats,'active_jobs':jobs,'active_actions':actions,'normal_slots_idle':True,'uid':os.getuid()}))
'''

HEALTH_GUARD = r'''import json,os,time,urllib.request
assert os.getuid()==1000 and os.geteuid()==1000
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));end=time.monotonic()+8
while True:
 try:
  with opener.open('http://127.0.0.1:18791/health',timeout=1)as r: health=json.loads(r.read(65537))
  assert health.get('application')=='hermes-workspace'
  print('ready');break
 except OSError:
  if time.monotonic()>=end:raise
  time.sleep(.2)
'''


class Native:
    unit, register, transaction = UNIT, REGISTER, TRANSACTION

    def __init__(self, trusted, own):
        self.trusted, self.own = trusted, own

    def read(self,path):
        return protected_read(path)

    def write(self,path,raw,mode):
        return self.trusted.write_file(path,raw,mode=mode)

    def same(self,item):
        return self.trusted.unchanged(item)

    def fingerprint(self,path):
        return self.trusted.fingerprint(path)

    def merge(self,register,item):
        return merge_unit(register,item,self.trusted.record_files)

    def validate_register(self,register):
        registered_dependency(register,protected_read(DEPENDENCY)[1])
        self.trusted.inspect_register(register)
        matches = [row for row in register['files'] if row['path']==str(self.unit)]
        check(len(matches)==1 and self.same(matches[0]),'matching_existing_app_unit_register_required')

    def mode_journal_exists(self):
        check(not MODE_TRANSACTION.is_symlink(),'protected_backend_mode_transaction_required')
        if not MODE_TRANSACTION.exists():return False
        self.trusted.protected_directory(MODE_TRANSACTION)
        return True

    def prepare_mode(self):
        self.trusted.protected_directory(STATE)
        MODE_TRANSACTION.mkdir(mode=0o700)
        self.trusted.protected_directory(MODE_TRANSACTION)

    def chmod_backend_mode(self,expected,target_mode,register,source):
        check(expected['path']==str(BACKEND_UNIT) and target_mode in (0o600,0o644)
              and expected['mode'] in (0o600,0o644) and expected['mode']!=target_mode,
              'fixed_backend_mode_transition_required')
        descriptor=os.open(BACKEND_UNIT,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'rb') as stream:
            info=os.fstat(stream.fileno())
            check(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0
                  and info.st_nlink==1 and info.st_size<=8192,'protected_single_backend_unit_required')
            raw=stream.read(8193)
            actual={'path':str(BACKEND_UNIT),'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,
                    'mode':stat.S_IMODE(info.st_mode),'sha256':digest(raw)}
            check(len(raw)<=8192 and actual==expected,'backend_mode_descriptor_identity_changed')
            check(self.read(REGISTER)[1]==register and self.read(BACKEND_SOURCE)[1]==source,
                  'backend_mode_register_or_source_changed')
            current=os.fstat(stream.fileno())
            check((info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(current.st_size,current.st_mtime_ns,current.st_ctime_ns)
                  and self.read(BACKEND_UNIT)[1]==expected,'backend_mode_descriptor_changed_before_chmod')
            os.fchmod(stream.fileno(),target_mode)
            after=self.read(BACKEND_UNIT)[1]
            check(after=={**expected,'mode':target_mode},'backend_mode_identity_or_bytes_changed_after_chmod')
            check(self.read(REGISTER)[1]==register and self.read(BACKEND_SOURCE)[1]==source,
                  'backend_mode_register_or_source_changed_after_chmod')
            return after

    def journal_exists(self):
        if self.transaction.is_symlink():raise RuntimeError('protected_transaction_required')
        return self.transaction.exists()

    def prepare(self,unit_raw,register_raw):
        self.trusted.protected_directory(STATE)
        self.transaction.mkdir(mode=0o700)
        self.trusted.protected_directory(self.transaction)
        self.write(self.transaction/'unit.before',unit_raw,0o600)
        self.write(self.transaction/'register.before',register_raw,0o600)

    def run(self,argv,timeout=10):
        return subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=timeout,env=ENV).stdout

    def normal_pins(self):
        raw,_ = protected_read(SETUP/'normal-profile.lock.json')
        pins = json.loads(raw)
        check(set(pins)==NORMAL_FILES and all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in pins.values()),
              'four_fixed_normal_pins_required')
        return pins

    def normal_unchanged(self,pins):
        self.trusted.normal_unchanged({'normal_configuration_sha256':pins})

    def service_pid(self):
        raw = self.run(['/usr/bin/systemctl','show',UNIT_NAME,'-p','MainPID','--value'])
        pid = int(raw.strip()); check(pid>1,'existing_active_app_required')
        proc = Path('/proc')/str(pid)
        values = {line.split(':',1)[0]:line.split(':',1)[1].strip() for line in (proc/'status').read_text().splitlines() if ':' in line}
        argv = (proc/'cmdline').read_bytes().split(b'\0')
        check(values.get('Uid','').split()==['1000']*4 and values.get('Gid','').split()==['1000']*4
              and values.get('NoNewPrivs')=='1' and int(values.get('CapEff','1'),16)==0
              and argv[:3]==[b'/usr/bin/python3',b'-I',os.fsencode(ROOT/'workspace/server.py')],
              'exact_unprivileged_app_process_required')
        return pid

    def guard(self):
        raw,_ = protected_read(Path('/home/mani-vmlab-data/window/state.json'))
        window = json.loads(raw)
        check(window.get('status')=='closed' and window.get('restored_health') is True
              and bool(window.get('configuration_hashes_equal')) and all(window['configuration_hashes_equal'].values()),
              'closed_recovered_inference_window_required')
        for name in ('mani-vmlab-backend.service','mani-vmlab-inference-window.service'):
            state = self.run(['/usr/bin/systemctl','show',name,'-p','ActiveState','--value']).strip()
            check(state in (b'inactive',b'failed'),'no_candidate_backend_or_window_may_be_active')
        runs = Path('/home/mani-vmlab-data/runs')
        check(runs.is_dir() and not runs.is_symlink(),'tracked_fleet_directory_required')
        directories = list(runs.iterdir()); check(len(directories)<=4096,'bounded_fleet_inventory_required')
        for path in directories:
            if not path.is_dir() or not re.fullmatch('[0-9a-f]{32}',path.name):
                raise RuntimeError('unexpected_fleet_inventory_preserved')
            manifest = json.loads(protected_read(path/'manifest.json')[0])
            check(manifest.get('status')!='active','no_active_fleet_may_be_restarted')
        active = self.run(['/usr/bin/systemctl','list-units','--state=active,activating,deactivating','--no-legend','--plain',
                           'mani-vmlab-*-controller.service','mani-vmlab-*-worker_a.service','mani-vmlab-*-worker_b.service'])
        check(not active.strip(),'no_actual_VM_unit_may_be_active')
        user = self.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
                         '/usr/bin/python3','-I','-c',USER_GUARD],timeout=12)
        check(len(user)<=4096,'bounded_unprivileged_guard_required')
        observation = json.loads(user)
        check(observation=={'active_chats':0,'active_jobs':0,'active_actions':0,'normal_slots_idle':True,'uid':1000},'idle_app_and_normal_slots_required')
        return {**observation,'inference_window_closed':True,'fleet_inactive':True,'app_pid':self.service_pid()}

    def source_directory(self):
        for path in (Path('/tmp'),Path('/tmp/.X11-unix')):
            info = path.lstat()
            check(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o1777,
                  'real_root_sticky_X11_socket_directory_required')

    def reload(self):
        self.run(['/usr/bin/systemctl','daemon-reload'],timeout=15)

    def runtime_state(self):
        pid = self.service_pid()
        mounts = Path(f'/proc/{pid}/mountinfo').read_text().splitlines()
        check(bool(mounts) and all(len(row.split())>=10 for row in mounts),'actual_app_mountinfo_required')
        present = any(row.split()[4]=='/tmp/.X11-unix' for row in mounts)
        check(self.service_pid()==pid,'app_changed_during_runtime_mount_observation')
        return {'app_pid':pid,'X11_bind_present':present}

    def restart(self,old_pid,expected_bind):
        # No other service name reaches a mutating system-manager command.
        self.run(['/usr/bin/systemctl','restart',UNIT_NAME],timeout=35)
        pid = self.service_pid(); check(pid!=old_pid,'fresh_app_pid_required')
        private = self.run(['/usr/bin/systemctl','show',UNIT_NAME,'-p','PrivateTmp','--value']).strip()
        check(private==b'yes','PrivateTmp_must_remain_enabled')
        check(os.readlink(f'/proc/{pid}/ns/mnt')!=os.readlink('/proc/self/ns/mnt'),'private_mount_namespace_required')
        check(os.readlink(f'/proc/{pid}/ns/user')==os.readlink('/proc/self/ns/user'),'existing_user_namespace_must_survive')
        mounts = Path(f'/proc/{pid}/mountinfo').read_text().splitlines()
        binds = [row.split() for row in mounts if row.split()[4]=='/tmp/.X11-unix']
        if expected_bind:
            check(len(binds)==1 and 'ro' in binds[0][5].split(','),'read_only_X11_bind_required')
            host = Path('/tmp/.X11-unix').stat(); child = Path(f'/proc/{pid}/root/tmp/.X11-unix').stat()
            check((host.st_dev,host.st_ino)==(child.st_dev,child.st_ino),'actual_host_socket_directory_bind_required')
        else:
            check(not binds,'restored_original_unit_must_not_keep_X11_bind')
        healthy = self.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
                            '/usr/bin/python3','-I','-c',HEALTH_GUARD],timeout=10)
        check(healthy.strip()==b'ready' and self.service_pid()==pid,'fresh_production_app_health_required')
        return {'pid':pid,'uid':1000,'capabilities_zero':True,'no_new_privileges':True,
                'PrivateTmp':True,'private_mount_namespace':True,'read_only_X11_bind':expected_bind,'production_health':True}


class Repair:
    def __init__(self,native):
        self.n = native

    def save(self,journal):
        self.n.write(self.n.transaction/'journal.json',(json.dumps(journal,indent=2)+'\n').encode(),0o600)

    def load(self):
        journal = json.loads(self.n.read(self.n.transaction/'journal.json')[0])
        check(journal.get('version')==1 and journal.get('repair')=='production_x11_v6' and journal.get('phase') in PHASES
              and journal.get('helper_sha256')==self.n.own['sha256'],'exact_own_repair_journal_required')
        for role,path in (('unit',self.n.unit),('register',self.n.register)):
            check(journal['before'][role]['path']==str(path),'fixed_journal_paths_required')
            for item in (journal.get('installed',{}).get(role),journal.get('rollback',{}).get(role)):
                if item:check(item['path']==str(path),'fixed_journal_paths_required')
        check(journal['before']['unit']['sha256']==BEFORE_SHA,'original_unit_backup_pin_required')
        return journal

    def apply(self):
        if self.n.journal_exists():
            journal = self.load()
            check(journal['phase']=='installed','partial_or_rolled_back_repair_requires_explicit_review')
            check(all(self.n.same(journal['installed'][role]) for role in ('unit','register')),'preserve_changed_installed_repair')
            self.n.normal_unchanged(journal['normal_pins'])
            return {'status':'already_installed','GPU_window_opened':False,'only_app_unit_changed':True}
        unit_raw, unit = self.n.read(self.n.unit)
        check(unit['uid']==0 and unit['mode']==0o644,'root_owned_app_unit_required')
        amended = amended_unit(unit_raw)
        register_raw, register = self.n.read(self.n.register)
        check(register['mode']==0o600,'owner_only_complete_register_required')
        original = json.loads(register_raw); self.n.validate_register(original)
        pins = self.n.normal_pins(); self.n.normal_unchanged(pins)
        self.n.source_directory(); before = self.n.guard()
        check(self.n.same(unit) and self.n.same(register),'preserve_concurrent_preflight_change')
        self.n.prepare(unit_raw,register_raw)
        journal = {'version':1,'repair':'production_x11_v6','phase':'prepared','helper_sha256':self.n.own['sha256'],
                   'before':{'unit':unit,'register':register},'normal_pins':pins,'guard_before':before,
                   'installed':{},'rollback':{},'restart_attempted':False}
        self.save(journal)
        check(self.n.same(unit) and self.n.same(register),'preserve_concurrent_unit_or_register_change')
        journal['installed']['unit'] = self.n.write(self.n.unit,amended,0o644)
        journal['phase']='unit_written'; self.save(journal)
        check(self.n.same(register) and self.n.same(journal['installed']['unit']),'preserve_concurrent_register_or_unit_change')
        updated = self.n.merge(original,journal['installed']['unit'])
        journal['installed']['register'] = self.n.write(self.n.register,(json.dumps(updated,indent=2)+'\n').encode(),0o600)
        journal['phase']='registered'; self.save(journal)
        self.n.reload(); journal['phase']='reloaded'; self.save(journal)
        self.n.normal_unchanged(pins); idle = self.n.guard()
        check(idle['app_pid']==before['app_pid'],'preserve_changed_app_process_before_restart')
        check(all(self.n.same(journal['installed'][role]) for role in ('unit','register')),'preserve_changed_repair_before_restart')
        journal['restart_attempted']=True; journal['phase']='restarting'; self.save(journal)
        proof = self.n.restart(idle['app_pid'],True)
        self.n.normal_unchanged(pins); after = self.n.guard()
        check(after['app_pid']==proof['pid'],'fresh_app_proof_changed')
        journal['proof']=proof; journal['guard_after']=after; journal['phase']='installed'; self.save(journal)
        return {'status':'installed','unit_before_sha256':BEFORE_SHA,'unit_after_sha256':AFTER_SHA,
                'only_app_unit_changed':True,'register_only_existing_app_unit_fingerprint_changed':True,
                'normal_configuration_hashes_unchanged':True,'GPU_window_opened':False,'inference_started':False,
                'conversations_touched':False,'proof':proof}

    def recover_exact_write_gap(self,journal,unit_raw,register_raw):
        """Recover only exact known commit bytes after write-before-journal loss.

        Unknown bytes or another register revision are never reconciled. A
        matching fixed transition may be fingerprinted because atomic writes
        allocate their inode before the journal can record that new identity.
        """
        original = json.loads(register_raw)
        if journal['phase']=='prepared' and not self.n.same(journal['before']['unit']):
            raw, item = self.n.read(self.n.unit)
            check(digest(raw)==AFTER_SHA and item['uid']==0 and item['mode']==0o644
                  and self.n.same(journal['before']['register']),'unknown_unit_commit_gap_preserved')
            journal['installed']['unit']=item; journal['phase']='unit_written'; self.save(journal)
        if journal['installed'].get('unit') and not journal['rollback'].get('unit') and not self.n.same(journal['installed']['unit']):
            raw, item = self.n.read(self.n.unit)
            register = journal['installed'].get('register') or journal['before']['register']
            check(raw==unit_raw and item['uid']==0 and item['mode']==journal['before']['unit']['mode']
                  and self.n.same(register),'unknown_rollback_unit_gap_preserved')
            journal['rollback']['unit']=item; journal['phase']='rollback_unit'; self.save(journal)
        if journal['phase']=='unit_written' and not self.n.same(journal['before']['register']):
            raw, item = self.n.read(self.n.register)
            expected = (json.dumps(self.n.merge(original,journal['installed']['unit']),indent=2)+'\n').encode()
            check(raw==expected and item['uid']==0 and item['mode']==0o600
                  and self.n.same(journal['installed']['unit']),'unknown_register_commit_gap_preserved')
            journal['installed']['register']=item; journal['phase']='registered'; self.save(journal)
        expected_register = journal['installed'].get('register') or journal['before']['register']
        if journal['rollback'].get('unit') and not journal['rollback'].get('register') and not self.n.same(expected_register):
            raw, item = self.n.read(self.n.register)
            expected = (json.dumps(self.n.merge(original,journal['rollback']['unit']),indent=2)+'\n').encode()
            check(raw==expected and item['uid']==0 and item['mode']==0o600
                  and self.n.same(journal['rollback']['unit']),'unknown_rollback_register_gap_preserved')
            journal['rollback']['register']=item; journal['phase']='rollback_registered'; self.save(journal)

    def rollback(self):
        check(self.n.journal_exists(),'own_repair_journal_required')
        journal = self.load()
        if journal['phase']=='rolled_back':
            check(all(self.n.same(journal['rollback'][role]) for role in ('unit','register')),'preserve_changed_rolled_back_repair')
            return {'status':'already_rolled_back','GPU_window_opened':False}
        unit_raw, _ = self.n.read(self.n.transaction/'unit.before')
        register_raw, _ = self.n.read(self.n.transaction/'register.before')
        check(digest(unit_raw)==journal['before']['unit']['sha256']
              and digest(register_raw)==journal['before']['register']['sha256'],'private_repair_backup_pin_changed')
        original = json.loads(register_raw)
        self.recover_exact_write_gap(journal,unit_raw,register_raw)
        expected_unit = journal['rollback'].get('unit') or journal['installed'].get('unit') or journal['before']['unit']
        expected_register = journal['rollback'].get('register') or journal['installed'].get('register') or journal['before']['register']
        check(self.n.same(expected_unit) and self.n.same(expected_register),'preserve_drift_before_amendment_rollback')
        self.n.normal_unchanged(journal['normal_pins']); idle = self.n.guard()
        if journal['phase']=='prepared':
            journal['rollback']={'unit':expected_unit,'register':expected_register}
            journal['phase']='rolled_back'; self.save(journal)
            return {'status':'rolled_back_without_unit_mutation','GPU_window_opened':False}
        if 'unit' not in journal['rollback']:
            check(self.n.same(expected_unit) and self.n.same(expected_register),'preserve_concurrent_rollback_change')
            journal['rollback']['unit']=self.n.write(self.n.unit,unit_raw,journal['before']['unit']['mode'])
            journal['phase']='rollback_unit'; self.save(journal)
        if 'register' not in journal['rollback']:
            check(self.n.same(expected_register) and self.n.same(journal['rollback']['unit']),'preserve_register_change_during_rollback')
            restored = self.n.merge(original,journal['rollback']['unit'])
            journal['rollback']['register']=self.n.write(self.n.register,(json.dumps(restored,indent=2)+'\n').encode(),0o600)
            journal['phase']='rollback_registered'; self.save(journal)
        self.n.reload()
        self.n.normal_unchanged(journal['normal_pins']); idle_now = self.n.guard()
        check(idle_now['app_pid']==idle['app_pid'],'preserve_changed_app_process_before_rollback_restart')
        runtime = self.n.runtime_state()
        check(runtime['app_pid']==idle_now['app_pid'],'app_changed_before_rollback_runtime_decision')
        # Restart=on-failure can launch the amended unit after daemon-reload,
        # before apply reaches its explicit restart. Observe reality rather
        # than assuming restart_attempted describes every possible new process.
        must_restart = (journal['restart_attempted'] or runtime['X11_bind_present']
                        or runtime['app_pid']!=journal['guard_before']['app_pid'])
        if must_restart:
            journal['rollback_proof']=self.n.restart(runtime['app_pid'],False)
        else:
            journal['rollback_proof']={'pid':runtime['app_pid'],'original_runtime_preserved':True}
        self.n.normal_unchanged(journal['normal_pins']); after = self.n.guard()
        final = self.n.runtime_state()
        check(final['app_pid']==after['app_pid']==journal['rollback_proof']['pid']
              and final['X11_bind_present'] is False,'actual_original_runtime_without_X11_bind_required')
        journal['rollback_proof']['X11_bind_absence_observed']=True
        journal['phase']='rolled_back'; self.save(journal)
        return {'status':'rolled_back','normal_configuration_hashes_unchanged':True,'conversations_touched':False,
                'GPU_window_opened':False,'old_v4_journals_untouched':True,'restored_unit_fingerprint_reregistered':True}


class BackendModeRepair:
    """One explicit metadata-only repair; no register/source/service changes."""
    def __init__(self,native):
        self.n=native
        self.journal_path=MODE_TRANSACTION/'journal.json'

    def inputs(self,mode):
        check(mode in (0o600,0o644),'fixed_backend_mode_snapshot_required')
        register_raw,register_info=self.n.read(REGISTER)
        register=json.loads(register_raw)
        registered_dependency(register,self.n.read(DEPENDENCY)[1])
        entries=[row for row in register['files'] if row['path']==str(BACKEND_UNIT)]
        check(len(entries)==1,'fixed_existing_backend_mode_registration_required')
        entry=entries[0];allowed=entry.get('allowed_sha256')
        check(isinstance(allowed,list) and len(allowed)==2 and all(isinstance(value,str) for value in allowed)
              and set(allowed)==set(BACKEND_VARIANTS.values()) and entry.get('uid')==0 and entry.get('mode')==0o644,
              'unchanged_fixed_backend_mode_allowlist_required')
        _,unit=self.n.read(BACKEND_UNIT)
        _,source=self.n.read(BACKEND_SOURCE)
        check(unit['uid']==0 and unit['mode']==mode and unit['sha256'] in allowed,
              'exact_allowlisted_backend_mode_input_required')
        sources=[row for row in register['files'] if row['path']==str(BACKEND_SOURCE)]
        check(len(sources)==1 and 'allowed_sha256' not in sources[0]
              and source['sha256']==BACKEND_SOURCE_SHA and source['mode']==0o644
              and all(sources[0].get(key)==source[key] for key in IDENTITY_KEYS),
              'exact_registered_backend_mode_source_required')
        inspected=register if mode==0o644 else {**register,'files':[row for row in register['files'] if row['path']!=str(BACKEND_UNIT)]}
        self.n.trusted.inspect_register(inspected)
        check(self.n.read(REGISTER)[1]==register_info and self.n.read(BACKEND_SOURCE)[1]==source
              and self.n.read(BACKEND_UNIT)[1]==unit,'backend_mode_inputs_changed')
        return {'register':register_info,'source':source,'unit':unit}

    def save(self,journal):
        self.n.write(self.journal_path,(json.dumps(journal,indent=2)+'\n').encode(),0o600)

    def load(self):
        journal=json.loads(self.n.read(self.journal_path)[0])
        check(journal.get('version')==1 and journal.get('helper_sha256')==self.n.own['sha256']
              and journal.get('phase') in ('prepared','applied','rolled_back'),
              'own_backend_mode_journal_required')
        before=journal.get('before',{})
        check(set(before)=={'register','source','unit'} and before['unit'].get('path')==str(BACKEND_UNIT)
              and before['unit'].get('mode')==0o600 and before['unit'].get('sha256') in BACKEND_VARIANTS.values()
              and before['register'].get('path')==str(REGISTER)
              and before['source'].get('path')==str(BACKEND_SOURCE)
              and before['source'].get('sha256')==BACKEND_SOURCE_SHA,
              'fixed_backend_mode_journal_inputs_required')
        check(journal.get('after') in (None,{**before['unit'],'mode':0o644})
              and (journal['phase']!='applied' or journal.get('after') is not None),
              'fixed_backend_mode_journal_transition_required')
        return journal

    def state(self,journal):
        mode=self.n.read(BACKEND_UNIT)[1]['mode']
        check(mode in (0o600,0o644),'preserve_other_backend_unit_mode')
        current=self.inputs(mode)
        check(current['register']==journal['before']['register'] and current['source']==journal['before']['source']
              and current['unit']=={**journal['before']['unit'],'mode':mode},
              'preserve_backend_mode_transaction_drift')
        return mode

    @staticmethod
    def result(status,mode):
        return {'status':status,'backend_mode':mode,'register_bytes_unchanged':True,'source_pack_unchanged':True,
                'installed_source_unchanged':True,'services_changed':False,'GPU_window_opened':False,
                'generated_unit_admission_mode_satisfied':mode==0o644}

    def apply(self):
        if self.n.mode_journal_exists():
            journal=self.load()
            check(journal['phase']!='rolled_back','backend_mode_rolled_back_requires_new_review')
        else:
            before=self.inputs(0o600)
            self.n.guard()
            self.n.prepare_mode()
            journal={'version':1,'helper_sha256':self.n.own['sha256'],'phase':'prepared','before':before,'after':None}
            self.save(journal)
        self.n.guard()
        mode=self.state(journal)
        if journal['phase']=='applied':
            check(mode==0o644,'preserve_applied_backend_mode_drift')
            return self.result('backend_mode_already_reconciled',mode)
        if mode==0o600:
            self.n.guard()
            self.n.chmod_backend_mode(journal['before']['unit'],0o644,journal['before']['register'],journal['before']['source'])
        # Only the exact same recorded inode/hash0644 can reconcile a crash
        # after fchmod but before the applied journal commit.
        check(self.state(journal)==0o644,'backend_mode_reconciliation_readback_required')
        self.n.guard()
        journal['after']={**journal['before']['unit'],'mode':0o644};journal['phase']='applied';self.save(journal)
        return self.result('backend_mode_reconciled',0o644)

    def rollback(self):
        check(self.n.mode_journal_exists(),'own_backend_mode_journal_required')
        journal=self.load()
        app=self.n.read(UNIT)[1]
        check(app['sha256']==BEFORE_SHA and app['mode']==0o644,'remove_app_X11_amendment_before_backend_mode_rollback')
        self.n.guard()
        mode=self.state(journal)
        if journal['phase']=='rolled_back':
            check(mode==0o600,'preserve_rolled_back_backend_mode_drift')
            return self.result('backend_mode_already_rolled_back',mode)
        if mode==0o644:
            self.n.guard()
            self.n.chmod_backend_mode({**journal['before']['unit'],'mode':0o644},0o600,
                                     journal['before']['register'],journal['before']['source'])
        check(self.state(journal)==0o600,'backend_mode_rollback_readback_required')
        self.n.guard()
        journal['phase']='rolled_back';self.save(journal)
        return self.result('backend_mode_rolled_back',0o600)


def main():
    operations=(['apply'],['rollback'],['audit'],['reconcile-backend-mode'],['rollback-backend-mode'])
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF or sys.argv[1:] not in operations:
        raise SystemExit('fixed_protected_x11_repair_only')
    if sys.argv[1]=='audit':
        # Audit exits before constructing Native/Repair, taking/creating locks,
        # installing deadlines, touching a transaction or issuing any command.
        try:
            trusted, _ = load_trusted_dependency()
            result = audit(trusted)
        except Exception:
            print(json.dumps({'operation':'audit','status':'failed','error_code':'protected_backend_audit_failed',
                              'writes_performed':False,'service_commands_performed':False,
                              'admission_changed':False,'GPU_window_opened':False}),flush=True)
            raise SystemExit(2)
        print(json.dumps(result),flush=True)
        return
    trusted, own = load_trusted_dependency()
    native = Native(trusted,own)
    trusted.protected_directory(STATE)
    trusted.protected_directory(Path('/home/mani-vmlab-data/window'))
    # Serialize this fixed repair and hold the existing inference-window lock:
    # a new window cannot advance through its protected state mutation while
    # these already-idle app mount settings are replaced and reloaded.
    locks=[]
    def deadline(_signum,_frame):raise TimeoutError('x11_repair_180_second_deadline')
    previous=signal.signal(signal.SIGALRM,deadline); signal.alarm(180)
    try:
        for path in (STATE/'production-x11-v6.lock',Path('/home/mani-vmlab-data/window/lock')):
            flags=os.O_RDWR|os.O_NOFOLLOW|(os.O_CREAT if path.parent==STATE else 0)
            fd=os.open(path,flags,0o600)
            try:
                info=os.fstat(fd)
                check(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and not info.st_mode&0o022,
                      'protected_repair_lock_required')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BaseException:os.close(fd);raise
            locks.append(fd)
        if sys.argv[1]=='reconcile-backend-mode':result=BackendModeRepair(native).apply()
        elif sys.argv[1]=='rollback-backend-mode':result=BackendModeRepair(native).rollback()
        else:result=getattr(Repair(native),sys.argv[1])()
        print(json.dumps(result),flush=True)
    except Exception as error:
        detail=str(error)
        print(json.dumps({'status':'failed','error_category':type(error).__name__,
                          'error_code':detail if re.fullmatch('[a-z][a-z0-9_]{0,159}',detail) else 'protected_repair_failed',
                          'GPU_window_opened':False,'review_own_transaction_before_retry':True}),flush=True)
        raise SystemExit(2)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        for fd in reversed(locks):os.close(fd)


if __name__=='__main__':main()
