"""Conditional completion fixtures; no live service/process/protected reads."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from test_production_x11_setup import FakeNative,repair as old

spec=importlib.util.spec_from_file_location('conditional_finalizer',Path(__file__).resolve().parents[1]/'native/production_x11_finalize.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class FinalNative(FakeNative):
    old=old
    def __init__(self):
        super().__init__();self.own={'sha256':m.OLD_SHA};self.finalizer_own={'sha256':'f'*64};self.seeding=True
        self.after_restart=lambda *_:(_ for _ in ()).throw(RuntimeError('fixture_preexec_failure'))
        try:old.Repair(self).apply()
        except RuntimeError as error:
            if str(error)!='fixture_preexec_failure':raise
        self.seeding=False;self.after_restart=None;self.actions=[];self.completion_created=False;self.publish_count=0
        self.fail_after_publish=False;self.bad_live=False
    def load_repair(self):return old.Repair(self).load()
    def same(self,item):
        if item is self.own:return True  # Root bootstrap/pinned code identity is modeled here.
        return super().same(item)
    def rollback_repair(self):return old.Repair(self).rollback()
    def service_pid(self):return self.pid
    def exists_completion(self):return self.completion_created
    def exists(self,path):return str(path) in self.files
    def prepare_completion(self):self.completion_created=True;self.actions.append(('prepare-completion',))
    def observe_current(self,previous,expected_bind):
        m.check(not self.bad_live and self.pid!=previous and self.bind_present==expected_bind,'fixture_qualified_process_or_mount_failed')
        return {'pid':self.pid,'uid':1000,'capabilities_zero':True,'no_new_privileges':True,'PrivateTmp':True,
                'private_mount_namespace':True,'read_only_X11_bind':expected_bind,'production_health':True,
                'qualification_method':'existing_bounded_health_before_strict_process_identity'}
    def restart(self,previous,expected_bind):
        if self.seeding:return super().restart(previous,expected_bind)
        self.actions.append(('explicit-rollback-app-restart',));self.pid+=100;self.bind_present=expected_bind
        return self.observe_current(previous,expected_bind)
    def publish_completed(self,before,after):
        m.check(self.same(before),'preserve_failure_journal_before_publication')
        actual=self.fp(m.STAGE)
        m.check(all(actual[k]==after[k]for k in m.KEYS if k!='path'),'preserve_completed_stage_drift')
        self.files[str(m.JOURNAL)]=self.files.pop(str(m.STAGE));self.publish_count+=1
        self.actions.append(('publish-completed-journal',))
        if self.fail_after_publish:self.fail_after_publish=False;raise RuntimeError('fixture_publish_before_plan_commit')


class Completion(unittest.TestCase):
    def test_complete_changes_only_completion_fields_without_restarting_or_unit_registry_writes(self):
        n=FinalNative();before=copy.deepcopy(n.files);raw=n.read(m.JOURNAL)[0];original=n.load_repair()
        result=m.Finalizer(n).complete();completed=n.load_repair()
        self.assertEqual(result['status'],'finalized');self.assertEqual(completed['phase'],'installed')
        self.assertEqual(completed['helper_sha256'],m.OLD_SHA)
        changed={'phase','proof','guard_after','completion'}
        self.assertEqual({k:v for k,v in completed.items() if k not in changed},{k:v for k,v in original.items() if k not in changed})
        self.assertEqual(completed['completion']['method'],m.METHOD)
        self.assertEqual(n.read(m.FAILURE)[0],raw)
        for path,record in before.items():
            if path!=str(m.JOURNAL):self.assertEqual(n.files[path],record)
        self.assertEqual(n.publish_count,1);self.assertFalse(any('restart' in action[0]for action in n.actions))
        self.assertFalse(result['additional_restart_performed'])

    def test_complete_repeat_requalifies_without_republishing_or_rewriting_private_plan(self):
        n=FinalNative();engine=m.Finalizer(n);engine.complete();before=copy.deepcopy(n.files)
        self.assertEqual(engine.complete()['status'],'already_finalized')
        self.assertEqual(n.publish_count,1);self.assertEqual(n.files,before)

    def test_unknown_phase_attempt_targets_process_or_profile_is_refused_without_preparation(self):
        def phase(n,j):j['phase']='registered'
        def attempt(n,j):j['restart_attempted']=False
        def helper(n,j):j['helper_sha256']='a'*64
        def target(n,j):n.put(n.unit,b'unknown unit',0o644)
        def live(n,j):n.bad_live=True
        def profile(n,j):j['normal_pins'][next(iter(j['normal_pins']))]='b'*64
        for mutate in (phase,attempt,helper,target,live,profile):
            n=FinalNative();journal=n.load_repair();mutate(n,journal);n.put(m.JOURNAL,m.encoded(journal),0o600)
            before=copy.deepcopy(n.files)
            with self.subTest(mutate=mutate.__name__),self.assertRaises(RuntimeError):m.Finalizer(n).complete()
            self.assertFalse(n.completion_created);self.assertEqual(n.files,before)

    def test_owned_publish_before_private_commit_gap_is_completed_without_extra_publication(self):
        n=FinalNative();n.fail_after_publish=True;engine=m.Finalizer(n)
        with self.assertRaisesRegex(RuntimeError,'publish_before_plan'):engine.complete()
        self.assertEqual(n.load_repair()['phase'],'installed')
        self.assertEqual(json.loads(n.read(m.PLAN)[0])['phase'],'prepared')
        self.assertEqual(engine.complete()['status'],'finalized');self.assertEqual(n.publish_count,1)

    def test_unknown_journal_stage_or_backup_drift_is_preserved(self):
        for target in ('journal','stage','backup'):
            n=FinalNative();engine=m.Finalizer(n);engine.prepare()
            path={'journal':m.JOURNAL,'stage':m.STAGE,'backup':m.FAILURE}[target]
            n.put(path,b'unknown root change',0o600);before=copy.deepcopy(n.files)
            with self.subTest(target=target),self.assertRaises((RuntimeError,json.JSONDecodeError)):engine.complete()
            self.assertEqual(n.files,before);self.assertEqual(n.publish_count,0)

    def test_staged_proof_cannot_be_reused_after_process_changes(self):
        n=FinalNative();engine=m.Finalizer(n);engine.prepare();n.pid+=100;before=copy.deepcopy(n.files)
        with self.assertRaisesRegex(RuntimeError,'staged_completion_process_changed'):engine.complete()
        self.assertEqual(n.files,before);self.assertEqual(n.publish_count,0)

    def test_guarded_rollback_preserves_original_helper_owner_before_or_after_completion(self):
        for completed in (False,True):
            n=FinalNative();engine=m.Finalizer(n)
            failure=n.read(m.JOURNAL)[0]
            if completed:engine.complete()
            result=engine.rollback();journal=n.load_repair()
            with self.subTest(completed=completed):
                self.assertEqual(result['status'],'rolled_back');self.assertEqual(journal['phase'],'rolled_back')
                self.assertEqual(journal['helper_sha256'],m.OLD_SHA);self.assertEqual(n.read(m.FAILURE)[0],failure)
                self.assertEqual(n.fp(n.unit)['sha256'],old.BEFORE_SHA)
                self.assertFalse(journal['rollback_proof']['read_only_X11_bind'])
                self.assertEqual(engine.rollback()['status'],'already_rolled_back')
                with self.assertRaises(RuntimeError):engine.complete()


class QualifiedRestart(unittest.TestCase):
    def test_existing_bounded_health_precedes_first_identity_check_without_loosening_it(self):
        for invalid in (False,True):
            native=m.qualified_native(old,Mock(),{'sha256':m.OLD_SHA},{'sha256':'f'*64});ready=[False];commands=[]
            def run(argv,**kwargs):
                commands.append((argv,kwargs))
                if argv[0]=='/usr/bin/setpriv':ready[0]=True;return b'ready\n'
                if argv[:2]==['/usr/bin/systemctl','show']:return b'yes\n'
                return b''
            def pid():
                if not ready[0] or invalid:raise RuntimeError('exact_unprivileged_app_process_required')
                return 222
            native.run=run;native.service_pid=pid
            def namespace(path):return ('host' if '/self/' in path else 'private') if path.endswith('/mnt') else 'user'
            with self.subTest(invalid=invalid),patch.object(m.os,'readlink',side_effect=namespace),\
                    patch.object(Path,'read_text',return_value='25 22 1:2 / /tmp/.X11-unix ro - tmpfs tmpfs rw\n'),\
                    patch.object(Path,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)):
                if invalid:
                    with self.assertRaisesRegex(RuntimeError,'exact_unprivileged'):native.restart(111,True)
                else:
                    self.assertTrue(native.restart(111,True)['production_health'])
                    self.assertEqual(len(commands),3);self.assertEqual(commands[0][1]['timeout'],35)
                    self.assertEqual(commands[1][0][0],'/usr/bin/setpriv');self.assertEqual(commands[1][1]['timeout'],10)

    def test_original_helper_pin_is_checked_before_import(self):
        with patch.object(m,'protected_read',side_effect=[(b'self',{'mode':0o644}),
                (b'unknown old helper',{'mode':0o644,'sha256':'bad'})]),\
                patch.object(m.importlib.util,'spec_from_file_location') as imported:
            with self.assertRaisesRegex(RuntimeError,'pinned_original_helper'):m.bootstrap()
            imported.assert_not_called()

    def test_readonly_runtime_proof_rejects_mount_namespace_health_and_PID_defects(self):
        good='25 22 1:2 / /tmp/.X11-unix ro - tmpfs tmpfs rw\n'
        for problem in ('missing','writable','duplicate','host_inode','shared_mount_ns','changed_user_ns','PID_drift','health','PrivateTmp'):
            native=m.qualified_native(old,Mock(),{'sha256':m.OLD_SHA},{'sha256':'f'*64})
            native.service_pid=Mock(side_effect=[222,333] if problem=='PID_drift' else None,return_value=222)
            def run(argv,**kwargs):
                if argv[0]=='/usr/bin/setpriv':return b'bad' if problem=='health' else b'ready\n'
                return b'no\n' if problem=='PrivateTmp' else b'yes\n'
            native.run=run
            def namespace(path):
                if path.endswith('/mnt'):return 'shared' if problem=='shared_mount_ns' else ('host' if '/self/'in path else 'private')
                return 'different' if problem=='changed_user_ns' and '/self/'not in path else 'user'
            mount='' if problem=='missing' else good.replace(' ro ',' rw ') if problem=='writable' else good*2 if problem=='duplicate' else good
            stats=[SimpleNamespace(st_dev=1,st_ino=2),SimpleNamespace(st_dev=1,st_ino=3 if problem=='host_inode'else 2)]
            with self.subTest(problem=problem),patch.object(m.os,'readlink',side_effect=namespace),\
                    patch.object(Path,'read_text',return_value=mount),patch.object(Path,'stat',side_effect=stats):
                with self.assertRaises(RuntimeError):native.observe_current(111,True)


if __name__=='__main__':unittest.main()
