"""Complete one measured X11 restart failure without changing the pinned helper."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys

sys.dont_write_bytecode=True
SELF=Path('/usr/local/lib/mani-vmlab-setup/production_x11_finalize.py')
OLD_HELPER=SELF.with_name('production_x11_setup.py')
OLD_SHA='3c80a7b77e9964d8d799baab7b7cb96c19cdf65ee2c7f5a417b121a69cf70d43'
STATE=Path('/var/lib/mani-vmlab-setup')
DIRECTORY=STATE/'production-x11-v6-completion'
JOURNAL=STATE/'production-x11-v6/journal.json'
PLAN=DIRECTORY/'journal.json'
FAILURE=DIRECTORY/'failure-journal.before'
STAGE=DIRECTORY/'journal.completed'
KEYS=('path','device','inode','sha256','uid','mode')
METHOD='qualified_existing_process_without_additional_restart'


def check(value,code):
    if not value:raise RuntimeError(code)


def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,indent=2)+'\n').encode()


def protected_read(path):
    path=Path(path);check(path.is_absolute() and '..' not in path.parts,'fixed_absolute_path_required')
    directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            info=os.fstat(child)
            if info.st_uid!=0 or info.st_mode&0o022:
                os.close(child);raise RuntimeError('protected_parent_required')
            os.close(directory);directory=child
        descriptor=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    finally:os.close(directory)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        check(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0
              and not info.st_mode&0o022 and info.st_size<=4*1024*1024,'protected_regular_input_required')
        raw=source.read(4*1024*1024+1);after=os.fstat(source.fileno())
        check(len(raw)<=4*1024*1024 and (info.st_size,info.st_mtime_ns,info.st_ctime_ns)==
              (after.st_size,after.st_mtime_ns,after.st_ctime_ns),'protected_input_changed')
    return raw,dict(path=str(path),device=info.st_dev,inode=info.st_ino,sha256=digest(raw),uid=info.st_uid,mode=stat.S_IMODE(info.st_mode))


def bootstrap():
    _,own=protected_read(SELF);check(own['mode']==0o644,'fixed_finalizer0644_required')
    _,previous=protected_read(OLD_HELPER)
    check(previous['sha256']==OLD_SHA and previous['mode']==0o644,'pinned_original_helper_required')
    spec=importlib.util.spec_from_file_location('_pinned_original_x11_helper',OLD_HELPER)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    check(protected_read(OLD_HELPER)[1]==previous,'original_helper_changed_during_import')
    trusted,old_own=old.load_trusted_dependency()
    check(old_own==previous,'original_helper_identity_changed')
    return old,trusted,old_own,own


def qualified_native(old,trusted,old_own,own):
    class QualifiedNative(old.Native):
        def __init__(self):
            super().__init__(trusted,old_own)
            self.old=old;self.finalizer_own=own

        def observe_current(self,previous_pid,expected_bind):
            # Type=simple can acknowledge fork before credentials/exec finish.
            # Reuse the existing bounded health call before the first PID gate.
            healthy=self.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
                             '/usr/bin/python3','-I','-c',old.HEALTH_GUARD],timeout=10)
            check(healthy.strip()==b'ready','fresh_production_app_health_required')
            pid=self.service_pid();check(pid!=previous_pid,'fresh_app_pid_required')
            check(self.run(['/usr/bin/systemctl','show',old.UNIT_NAME,'-p','PrivateTmp','--value']).strip()==b'yes',
                  'PrivateTmp_must_remain_enabled')
            check(os.readlink(f'/proc/{pid}/ns/mnt')!=os.readlink('/proc/self/ns/mnt'),'private_mount_namespace_required')
            check(os.readlink(f'/proc/{pid}/ns/user')==os.readlink('/proc/self/ns/user'),'existing_user_namespace_must_survive')
            rows=Path(f'/proc/{pid}/mountinfo').read_text().splitlines()
            check(rows and all(len(row.split())>=10 for row in rows),'actual_app_mountinfo_required')
            binds=[row.split() for row in rows if row.split()[4]=='/tmp/.X11-unix']
            if expected_bind:
                check(len(binds)==1 and 'ro' in binds[0][5].split(','),'read_only_X11_bind_required')
                host=Path('/tmp/.X11-unix').stat();child=Path(f'/proc/{pid}/root/tmp/.X11-unix').stat()
                check((host.st_dev,host.st_ino)==(child.st_dev,child.st_ino),'actual_host_socket_directory_bind_required')
            else:check(not binds,'restored_original_unit_must_not_keep_X11_bind')
            check(self.service_pid()==pid,'fresh_production_app_health_required')
            return {'pid':pid,'uid':1000,'capabilities_zero':True,'no_new_privileges':True,
                    'PrivateTmp':True,'private_mount_namespace':True,'read_only_X11_bind':expected_bind,
                    'production_health':True,'qualification_method':'existing_bounded_health_before_strict_process_identity'}

        def restart(self,previous_pid,expected_bind):
            self.run(['/usr/bin/systemctl','restart',old.UNIT_NAME],timeout=35)
            return self.observe_current(previous_pid,expected_bind)

        def load_repair(self):return old.Repair(self).load()
        def rollback_repair(self):return old.Repair(self).rollback()

        def exists_completion(self):
            check(not DIRECTORY.is_symlink(),'protected_completion_directory_required')
            if not DIRECTORY.exists():return False
            self.trusted.protected_directory(DIRECTORY)
            return True

        def exists(self,path):
            check(not path.is_symlink(),'preserve_completion_symlink')
            return path.exists()

        def prepare_completion(self):
            self.trusted.protected_directory(STATE)
            DIRECTORY.mkdir(mode=0o700)
            self.trusted.protected_directory(DIRECTORY)

        def publish_completed(self,before,after):
            actual=self.read(STAGE)[1]
            check(all(actual[key]==after[key] for key in KEYS if key!='path'),'preserve_completed_stage_drift')
            check(self.same(before),'preserve_failure_journal_before_publication')
            with self.trusted.parent_fd(STAGE) as(src,sname),self.trusted.parent_fd(JOURNAL) as(dst,dname):
                os.replace(sname,dname,src_dir_fd=src,dst_dir_fd=dst);os.fsync(dst)
            check(self.same(after),'published_completed_journal_identity_required')

    return QualifiedNative()


class Finalizer:
    def __init__(self,native):self.n=native

    def failure_shape(self,journal):
        check(journal.get('phase')=='restarting' and journal.get('restart_attempted') is True
              and journal.get('helper_sha256')==OLD_SHA and journal.get('repair')=='production_x11_v6'
              and journal.get('version')==1,'only_original_attempted_restarting_phase_allowed')
        check(set(journal.get('installed',{}))=={'unit','register'} and journal.get('rollback')=={}
              and all(key not in journal for key in ('proof','guard_after','completion')),
              'exact_unfinished_restart_journal_required')
        unit=journal['installed']['unit'];register=journal['installed']['register']
        check(journal.get('before',{}).get('unit',{}).get('path')==str(self.n.unit)
              and journal['before']['unit'].get('sha256')==self.n.old.BEFORE_SHA
              and journal['before'].get('register',{}).get('path')==str(self.n.register),
              'fixed_original_failure_journal_paths_required')
        check(unit['path']==str(self.n.unit) and unit['sha256']==self.n.old.AFTER_SHA and unit['uid']==0 and unit['mode']==0o644
              and register['path']==str(self.n.register) and register['uid']==0 and register['mode']==0o600,
              'exact_installed_restart_targets_required')
        previous=journal.get('guard_before',{}).get('app_pid')
        check(type(previous) is int and previous>1,'original_pre_restart_app_PID_required')

    def live(self,journal):
        self.failure_shape(journal)
        check(all(self.n.same(journal['installed'][role]) for role in ('unit','register'))
              and self.n.same(self.n.own),'preserve_installed_restart_target_or_helper_drift')
        self.n.validate_register(json.loads(self.n.read(self.n.register)[0]))
        check(self.n.normal_pins()==journal['normal_pins'],'unchanged_original_normal_profile_required')
        self.n.normal_unchanged(journal['normal_pins']);before=self.n.guard()
        proof=self.n.observe_current(journal['guard_before']['app_pid'],True)
        self.n.normal_unchanged(journal['normal_pins']);after=self.n.guard()
        check(before['app_pid']==after['app_pid']==proof['pid'],'qualified_app_PID_changed')
        check(all(self.n.same(journal['installed'][role]) for role in ('unit','register')),'preserve_installed_restart_target_drift')
        return proof,after

    def backup_failure(self,raw,journal):
        if not self.n.exists_completion():self.n.prepare_completion()
        if self.n.exists(FAILURE):
            saved=self.n.read(FAILURE)[0];failure=json.loads(saved);self.failure_shape(failure)
            ignored={'phase','proof','guard_after','completion','rollback','rollback_proof'}
            check({k:v for k,v in failure.items() if k not in ignored}==
                  {k:v for k,v in journal.items() if k not in ignored},'preserve_other_failure_backup_history')
            return saved
        self.failure_shape(journal)
        self.n.write(FAILURE,raw,0o600)
        return raw

    def save(self,plan):self.n.write(PLAN,encoded(plan),0o600)

    def load(self):
        plan=json.loads(self.n.read(PLAN)[0])
        check(plan.get('version')==1 and plan.get('kind')=='pinned_X11_restart_completion'
              and plan.get('finalizer_sha256')==self.n.finalizer_own['sha256'] and plan.get('original_helper_sha256')==OLD_SHA
              and plan.get('phase') in ('prepared','finalized'),'own_fixed_completion_plan_required')
        check(plan['before']['path']==str(JOURNAL) and plan['after']['path']==str(JOURNAL)
              and plan['after']['uid']==0 and plan['after']['mode']==0o600,'fixed_completion_journal_paths_required')
        return plan

    def prepare(self):
        raw,before=self.n.read(JOURNAL);journal=self.n.load_repair();self.failure_shape(journal)
        check(json.loads(raw)==journal and self.n.same(before),'failure_journal_changed_during_read')
        proof,guard=self.live(journal)
        check(self.n.same(before),'failure_journal_changed_during_qualification')
        saved=self.backup_failure(raw,journal);check(saved==raw,'exact_original_failure_bytes_required')
        completed={**journal,'phase':'installed','proof':proof,'guard_after':guard,'completion':{
            'method':METHOD,'finalizer_sha256':self.n.finalizer_own['sha256'],'original_helper_sha256':OLD_SHA,
            'original_failure_journal_sha256':before['sha256'],'additional_restart_performed':False}}
        payload=encoded(completed)
        if self.n.exists(STAGE):
            staged,item=self.n.read(STAGE);check(staged==payload and item['mode']==0o600,'preserve_unknown_completed_stage')
        else:item=self.n.write(STAGE,payload,0o600)
        plan={'version':1,'kind':'pinned_X11_restart_completion','finalizer_sha256':self.n.finalizer_own['sha256'],
              'original_helper_sha256':OLD_SHA,'phase':'prepared','before':before,'after':{**item,'path':str(JOURNAL)},
              'proof_pid':proof['pid']}
        self.save(plan)
        return plan

    def completed_payload(self,plan,failure):
        path=JOURNAL if self.n.same(plan['after']) else STAGE
        raw,item=self.n.read(path)
        check(all(item[key]==plan['after'][key] for key in KEYS if key!='path'),'preserve_completed_payload_identity')
        completed=json.loads(raw)
        changed={'phase','proof','guard_after','completion'}
        check(set(completed)==set(failure)|changed and all(completed[key]==value for key,value in failure.items() if key not in changed)
              and completed['phase']=='installed' and completed['proof']['pid']==plan['proof_pid']
              and completed['completion']=={'method':METHOD,'finalizer_sha256':self.n.finalizer_own['sha256'],
                    'original_helper_sha256':OLD_SHA,'original_failure_journal_sha256':plan['before']['sha256'],
                    'additional_restart_performed':False},'only_known_completion_fields_may_change')
        return completed

    def complete(self):
        plan=self.load() if self.n.exists_completion() and self.n.exists(PLAN) else self.prepare()
        raw=self.n.read(FAILURE)[0];check(digest(raw)==plan['before']['sha256'],'preserve_original_failure_backup')
        failure=json.loads(raw);self.failure_shape(failure)
        before=self.n.same(plan['before']);after=self.n.same(plan['after'])
        check(before or after,'preserve_unowned_X11_journal_drift')
        check(plan['phase']!='finalized' or after,'preserve_finalized_X11_journal_drift')
        completed=self.completed_payload(plan,failure);proof,_=self.live(failure)
        check(proof['pid']==completed['proof']['pid']==plan['proof_pid'],'staged_completion_process_changed')
        if before:self.n.publish_completed(plan['before'],plan['after'])
        check(self.n.same(plan['after']),'completed_journal_publication_required')
        self.n.normal_unchanged(failure['normal_pins']);guard=self.n.guard()
        check(guard['app_pid']==plan['proof_pid'] and self.n.service_pid()==plan['proof_pid'],'completed_app_PID_changed')
        check(all(self.n.same(failure['installed'][role]) for role in ('unit','register'))
              and self.n.same(self.n.own),'preserve_final_installed_targets_or_original_helper_drift')
        already=plan['phase']=='finalized'
        if not already:plan['phase']='finalized';self.save(plan)
        return {'status':'already_finalized' if already else 'finalized','completion_method':METHOD,
                'original_helper_sha256':OLD_SHA,'app_pid':plan['proof_pid'],'additional_restart_performed':False,
                'register_and_unit_unchanged':True,'normal_configuration_hashes_unchanged':True,'GPU_window_opened':False}

    def rollback(self):
        raw,_=self.n.read(JOURNAL);journal=self.n.load_repair()
        check(json.loads(raw)==journal,'rollback_journal_changed_during_read')
        self.backup_failure(raw,journal)
        self.n.normal_unchanged(journal['normal_pins']);self.n.guard()
        result=self.n.rollback_repair()
        current=self.n.load_repair();check(current['phase']=='rolled_back','guarded_original_rollback_required')
        self.n.normal_unchanged(current['normal_pins']);guard=self.n.guard()
        proof=self.n.observe_current(current['guard_before']['app_pid'],False)
        check(proof['pid']==guard['app_pid'],'rolled_back_app_PID_changed')
        return {**result,'rollback_method':'pinned_original_Repair_with_bounded_health_before_identity',
                'original_helper_sha256':OLD_SHA,'finalizer_sha256':self.n.finalizer_own['sha256']}


def main():
    check(os.geteuid()==0 and Path(__file__).absolute()==SELF and sys.argv[1:] in (['complete'],['rollback']),
          'fixed_root_finalizer_complete_or_rollback_only')
    old,trusted,old_own,own=bootstrap();native=qualified_native(old,trusted,old_own,own)
    trusted.protected_directory(STATE);trusted.protected_directory(Path('/home/mani-vmlab-data/window'))
    locks=[]
    def deadline(_signum,_frame):raise TimeoutError('X11_finalizer_180_second_deadline')
    previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(180)
    try:
        for path in (STATE/'production-x11-v6.lock',Path('/home/mani-vmlab-data/window/lock'),STATE/'production-x11-v6-completion.lock'):
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|(os.O_CREAT if path.parent==STATE else 0),0o600)
            try:
                info=os.fstat(fd)
                check(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and not info.st_mode&0o022,
                      'protected_completion_lock_required')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BaseException:os.close(fd);raise
            locks.append(fd)
        print(json.dumps(getattr(Finalizer(native),sys.argv[1])()),flush=True)
    except Exception as error:
        code=str(error)
        print(json.dumps({'status':'failed','error_category':type(error).__name__,
              'error_code':code if re.fullmatch('[A-Za-z0-9_]{1,159}',code) else 'protected_finalizer_failed',
              'GPU_window_opened':False,'preserve_original_and_completion_journals':True}),flush=True)
        raise SystemExit(2)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        for fd in reversed(locks):os.close(fd)


if __name__=='__main__':main()
