"""Hermetic ownership/commit regressions. No native services, model or live reads."""
import copy
import hashlib
import importlib.util
import json
import fcntl
import os
import stat
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[1]/'native/backend_writer_setup.py'
spec=importlib.util.spec_from_file_location('backend_overlay_subject',MODULE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class FakeTrusted:
    def __init__(self,files):self.files=files
    def fingerprint(self,path):return self.files.read(path)[1]
    def inspect_register(self,register):
        rows=m.inventory(register,'files')
        for path,row in rows.items():
            if not self.files.exists(Path(path)):continue
            actual=self.fingerprint(path)
            if path==str(m.BACKEND_UNIT) and row.get('allowed_sha256'):
                m.check(actual['uid']==0 and actual['mode']==0o644 and actual['sha256']in row['allowed_sha256'],'preserve_registered_backend_drift')
            else:m.check(all(actual[k]==row[k]for k in m.IDENTITY_KEYS),'preserve_registered_file_drift')


class FakeNative:
    transaction=m.TRANSACTION
    own={'sha256':'7'*64}
    stage=m.Native.stage
    validate_registers=m.Native.validate_registers
    unchanged_registered=m.Native.unchanged_registered
    unchanged_snapshot=m.Native.unchanged_snapshot
    recognize_x11_rollback=m.Native.recognize_x11_rollback

    def __init__(self):
        self.files={};self.next_inode=10;self.created=False;self.commands=[];self.pid_value=101
        self.socket_value='active';self.idle=True;self.fail_before=None;self.fail_after=None
        self.fail_stage=None;self.fail_activate=False;self.bad_artifact=False;self.base_pack=bytes.fromhex('00')
        self.trusted=FakeTrusted(self)
        self.write(m.SOURCE,b'old-fixture',0o644)
        self.write(m.DEPENDENCY,b'known-protected-dependency',0o644)
        self.write(m.APP_UNIT,b'original-app-unit',0o644)
        self.write(m.X11_HELPER,b'known-x11-helper',0o644)
        other=m.INSTALL/'other-policy.py';self.write(other,b'policy-stays-exact',0o644)
        self.write(m.BACKEND_UNIT,b'known-unit',0o644)
        # The fixture unit SHA is one of the two authorized exact fixture variants.
        self.variant_sha=self.read(m.BACKEND_UNIT)[1]['sha256']
        runtime={'status':'installed','source_pack_sha256':m.BASE_PACK,'accounts_created':False,
                 'installed_files':[{k:self.read(p)[1][k]for k in m.RUNTIME_KEYS}for p in(m.SOURCE,other)]}
        complete={'version':1,'source_pack_sha256':m.BASE_PACK,'namespaces':[{'keep':'original'}],
                  'files':[self.read(p)[1]for p in(m.SOURCE,m.DEPENDENCY,other,m.APP_UNIT,m.BACKEND_UNIT)]}
        complete['files'][0].update(action='restore',backup='/fixed/original-source',before_sha256='1'*64,before_mode=0o644)
        complete['files'][-1]['allowed_sha256']=[self.variant_sha,'a'*64]
        self.write(m.RUNTIME,m.encoded(runtime),0o600);self.write(m.COMPLETE,m.encoded(complete),0o600)
        self.guard_path=m.STATE/'VM-watchdog-qualified.json'
        self.write(self.guard_path,m.encoded({'all_passed':False,'boot_id':'old-failed-receipt'}),0o600)
        self.proof={str(self.guard_path):self.read(self.guard_path)[1]}
        self.original_files=copy.deepcopy(self.files)
        self.initial_source=self.read(m.SOURCE)[1]
        self.calls=0
    def exists(self,path):return str(path)in self.files or(path==self.transaction and self.created)
    def read(self,path):
        raw,item=self.files[str(path)];return raw,dict(item)
    def write(self,path,raw,mode):
        self.next_inode+=1
        item=dict(path=str(path),device=9,inode=self.next_inode,sha256=m.sha(raw),uid=0,mode=mode)
        self.files[str(path)]=(bytes(raw),item);return dict(item)
    def same(self,item):
        if item['path']not in self.files:return False
        actual=self.files[item['path']][1]
        return all(actual.get(k)==item.get(k)for k in m.IDENTITY_KEYS)
    def payload(self):return b'new-fixture'
    def guard(self,allow_x11=False):
        m.check(self.idle,'idle_guard_failed')
        m.check(allow_x11 or not self.exists(m.X11_TRANSACTION),'overlay_must_precede_X11_transaction')
        return {'no_inference':True,'no_VM':True}
    def snapshot(self):return copy.deepcopy(self.proof)
    def artifact_proof(self):
        m.check(not self.bad_artifact,'preserve_artifact_identity_drift')
        return {'verified_file_count':42}
    def prepare_directory(self):self.created=True
    def stage(self,name,target,raw,mode):
        if self.fail_stage==name:self.fail_stage=None;raise RuntimeError('fixture_stage_interruption')
        return m.Native.stage(self,name,target,raw,mode)
    def commit(self,item):
        role=next(role for role,path in m.TARGETS.items()if str(path)==item['path'])
        if self.fail_before==role:self.fail_before=None;raise RuntimeError('fixture_before_publication')
        raw,actual=self.read(self.transaction/item['stage'])
        m.check(all(actual[k]==item[k]for k in m.IDENTITY_KEYS if k!='path'),'preserve_changed_stage')
        del self.files[str(self.transaction/item['stage'])]
        self.files[item['path']]=(raw,{k:item[k]for k in m.IDENTITY_KEYS})
        self.commands.append('publish:'+role)
        if self.fail_after==role:self.fail_after=None;raise RuntimeError('fixture_after_publication')
    def pid(self):return self.pid_value
    def socket_state(self):return self.socket_value
    def quiesce(self):
        self.commands.extend(('stop:socket','stop:supervisor'))
        self.socket_value='inactive';self.pid_value=0
    def activate(self,old):
        self.commands.extend(('start:socket','start:supervisor'))
        self.socket_value='active'
        if self.fail_activate:self.fail_activate=False;raise RuntimeError('fixture_activation_failure')
        self.calls+=1;self.pid_value=200+self.calls
        m.check(self.pid_value!=old,'fresh_supervisor_PID_required')
        return {'pid':self.pid_value,'VM_watchdog_qualified':False,'artifact_proof_current':True,
                'inference_started':False,'VM_started':False}
    def restore_states(self,before):return self.activate(before['pid'])


class BackendOverlay(unittest.TestCase):
    def setUp(self):
        self.patchers=[patch.object(m,'BEFORE_SHA',m.sha(b'old-fixture')),
                       patch.object(m,'AFTER_SHA',m.sha(b'new-fixture')),
                       patch.object(m,'X11_HELPER_SHA',m.sha(b'known-x11-helper')),
                       patch.object(m,'APP_BEFORE_SHA',m.sha(b'original-app-unit')),
                       patch.object(m,'VARIANTS',frozenset((m.sha(b'known-unit'),'a'*64)))]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
        self.reset()
    def reset(self):
        self.n=FakeNative();self.overlay=m.Overlay(self.n)
    def documents(self):return {role:json.loads(self.n.read(path)[0])for role,path in(('runtime',m.RUNTIME),('complete',m.COMPLETE))}
    def assert_paired(self,source_sha):
        source=self.n.read(m.SOURCE)[1];self.assertEqual(source['sha256'],source_sha)
        for role,key,keys in(('runtime','installed_files',m.RUNTIME_KEYS),('complete','files',m.IDENTITY_KEYS)):
            row=m.inventory(self.documents()[role],key)[str(m.SOURCE)]
            self.assertTrue(all(row[k]==source[k]for k in keys))
    def test_exact_source_and_two_rows_commit_without_sourcepack_or_permission_changes(self):
        before=self.documents();proof=copy.deepcopy(self.n.files[str(self.n.guard_path)])
        result=self.overlay.apply();after=self.documents()
        self.assertEqual(result['status'],'installed');self.assert_paired(m.AFTER_SHA)
        for role,key in(('runtime','installed_files'),('complete','files')):
            old=m.inventory(before[role],key);new=m.inventory(after[role],key)
            self.assertEqual(set(old),set(new))
            self.assertEqual({p:r for p,r in old.items()if p!=str(m.SOURCE)},
                             {p:r for p,r in new.items()if p!=str(m.SOURCE)})
            self.assertEqual({k:v for k,v in before[role].items()if k!=key},{k:v for k,v in after[role].items()if k!=key})
        self.assertEqual(proof,self.n.files[str(self.n.guard_path)])
        row=m.inventory(after['complete'],'files')[str(m.SOURCE)]
        self.assertEqual(row['action'],'restore');self.assertEqual(row['backup'],'/fixed/original-source')
        self.assertFalse(result['GPU_window_opened']);self.assertFalse(result['qualifications_rewritten'])
        self.assertEqual(self.n.commands[:2],['stop:socket','stop:supervisor'])
        self.assertEqual(self.n.commands[2:5],['publish:source','publish:runtime','publish:complete'])
        self.assertEqual(self.n.commands[-2:],['start:socket','start:supervisor'])
    def test_busy_or_inactive_initial_context_is_refused_before_writes(self):
        for condition in('busy','socket','service'):
            with self.subTest(condition=condition):
                self.reset();before=copy.deepcopy(self.n.files)
                if condition=='busy':self.n.idle=False
                elif condition=='socket':self.n.socket_value='inactive'
                else:self.n.pid_value=0
                with self.assertRaises(RuntimeError):self.overlay.apply()
                self.assertEqual(self.n.files,before);self.assertEqual(self.n.commands,[])
    def test_mode_or_unknown_unit_or_changed_allowlist_is_never_reconciled_by_overlay(self):
        for change in('mode','bytes','allowlist'):
            with self.subTest(change=change):
                self.setUp()
                if change=='mode':self.n.files[str(m.BACKEND_UNIT)][1]['mode']=0o600
                elif change=='bytes':self.n.write(m.BACKEND_UNIT,b'unknown-unit',0o644)
                else:
                    doc=json.loads(self.n.read(m.COMPLETE)[0]);m.inventory(doc,'files')[str(m.BACKEND_UNIT)]['allowed_sha256'].append('f'*64)
                    self.n.write(m.COMPLETE,m.encoded(doc),0o600)
                before=copy.deepcopy(self.n.files)
                with self.assertRaises(RuntimeError):self.overlay.apply()
                self.assertEqual(self.n.files,before);self.assertFalse(self.n.created)
    def test_all_commit_boundaries_resume_only_owned_staged_identities(self):
        for boundary in('fail_before','fail_after'):
            for role in('source','runtime','complete'):
                with self.subTest(boundary=boundary,role=role):
                    self.reset();setattr(self.n,boundary,role)
                    with self.assertRaises(RuntimeError):self.overlay.apply()
                    self.assertEqual(self.overlay.apply()['status'],'installed')
                    self.assert_paired(m.AFTER_SHA)
    def test_preparation_interruption_recovers_private_stage_without_live_change(self):
        self.n.fail_stage='new-runtime'
        with self.assertRaisesRegex(RuntimeError,'stage_interruption'):self.overlay.apply()
        self.assert_paired(m.BEFORE_SHA);self.assertEqual(self.n.commands,[])
        self.assertEqual(self.overlay.apply()['status'],'installed');self.assert_paired(m.AFTER_SHA)
    def test_changed_unjournaled_stage_is_preserved_and_refused(self):
        self.n.fail_stage='new-runtime'
        with self.assertRaises(RuntimeError):self.overlay.apply()
        self.n.write(self.n.transaction/'new-runtime',b'unknown-private-stage',0o600)
        before=copy.deepcopy(self.n.files)
        with self.assertRaisesRegex(RuntimeError,'unknown_prepared_stage'):self.overlay.apply()
        self.assertEqual(self.n.files,before);self.assert_paired(m.BEFORE_SHA)
    def test_same_bytes_unknown_inode_is_preserved_instead_of_blessed(self):
        self.n.fail_after='source'
        with self.assertRaises(RuntimeError):self.overlay.apply()
        self.n.write(m.SOURCE,b'new-fixture',0o644);before=copy.deepcopy(self.n.files)
        with self.assertRaisesRegex(RuntimeError,'unowned_source_or_register_drift'):self.overlay.apply()
        self.assertEqual(self.n.files,before)
        with self.assertRaisesRegex(RuntimeError,'unowned_source_or_register_drift'):self.overlay.rollback()
        self.assertEqual(self.n.files,before)
    def test_existing_false_receipt_policy_or_artifact_drift_is_never_rewritten(self):
        for change in('receipt','artifact','other_source'):
            with self.subTest(change=change):
                self.reset();self.n.fail_before='source'
                with self.assertRaises(RuntimeError):self.overlay.apply()
                if change=='receipt':self.n.write(self.n.guard_path,m.encoded({'all_passed':True}),0o600)
                elif change=='artifact':self.n.bad_artifact=True
                else:self.n.write(m.INSTALL/'other-policy.py',b'changed',0o644)
                before=copy.deepcopy(self.n.files)
                with self.assertRaises(RuntimeError):self.overlay.apply()
                self.assertEqual(self.n.files,before)
                with self.assertRaises(RuntimeError):self.overlay.rollback()
                self.assertEqual(self.n.files,before)
    def test_activation_failure_preserves_journal_and_explicit_rollback_restores_new_inode_rows(self):
        self.n.fail_activate=True
        with self.assertRaisesRegex(RuntimeError,'activation_failure'):self.overlay.apply()
        self.assertEqual(self.overlay.load()['phase'],'complete_written');self.assert_paired(m.AFTER_SHA)
        result=self.overlay.rollback();self.assertEqual(result['status'],'rolled_back')
        self.assert_paired(m.BEFORE_SHA)
        self.assertNotEqual(self.n.read(m.SOURCE)[1]['inode'],self.n.initial_source['inode'])
        self.assertEqual(self.n.socket_value,'active');self.assertGreater(self.n.pid_value,1)
        self.assertEqual(self.overlay.rollback()['status'],'already_rolled_back')
    def test_rollback_before_publication_preserves_original_inodes(self):
        self.n.fail_before='source'
        with self.assertRaises(RuntimeError):self.overlay.apply()
        self.overlay.rollback();self.assert_paired(m.BEFORE_SHA)
        self.assertEqual(self.n.read(m.SOURCE)[1],self.n.initial_source)
    def test_rollback_each_partial_commit_recovers_paired_original_source(self):
        for role in('source','runtime','complete'):
            with self.subTest(role=role):
                self.reset();self.n.fail_after=role
                with self.assertRaises(RuntimeError):self.overlay.apply()
                self.overlay.rollback();self.assert_paired(m.BEFORE_SHA)
    def test_rollback_publication_interruption_can_resume_exact_own_restored_inode(self):
        self.overlay.apply();self.n.fail_after='runtime'
        with self.assertRaises(RuntimeError):self.overlay.rollback()
        self.overlay.rollback();self.assert_paired(m.BEFORE_SHA)
    def test_installed_repeat_does_not_restart_or_rewrite_and_drift_still_refused(self):
        self.overlay.apply();commands=list(self.n.commands);before=copy.deepcopy(self.n.files)
        self.assertEqual(self.overlay.apply()['status'],'already_installed')
        self.assertEqual(self.n.commands,commands);self.assertEqual(self.n.files,before)
        self.n.write(m.INSTALL/'other-policy.py',b'later-drift',0o644)
        with self.assertRaises(RuntimeError):self.overlay.apply()
    def test_registry_self_reference_and_wrong_base_identity_are_preserved(self):
        for change in('cross_registry','base'):
            with self.subTest(change=change):
                self.reset();doc=json.loads(self.n.read(m.COMPLETE)[0])
                if change=='cross_registry':doc['files'].append(self.n.read(m.RUNTIME)[1])
                else:doc['source_pack_sha256']='f'*64
                self.n.write(m.COMPLETE,m.encoded(doc),0o600);before=copy.deepcopy(self.n.files)
                with self.assertRaises(RuntimeError):self.overlay.apply()
                self.assertEqual(self.n.files,before)
    def test_tampered_backup_or_staged_source_cannot_be_used_for_rollback(self):
        for target in('source.before','complete.before'):
            with self.subTest(target=target):
                self.reset();self.overlay.apply();self.n.write(self.n.transaction/target,b'unknown',0o600)
                before=copy.deepcopy(self.n.files)
                with self.assertRaises(RuntimeError):self.overlay.rollback()
                # Guard may quiesce first, but no source/registration writes occur.
                for path in m.TARGETS.values():self.assertEqual(self.n.files[str(path)],before[str(path)])
    def test_existing_X11_transaction_is_refused_before_any_overlay_write(self):
        self.n.files[str(m.STATE/'production-x11-v6')]=(b'',{'path':str(m.STATE/'production-x11-v6')})
        before=copy.deepcopy(self.n.files)
        with self.assertRaisesRegex(RuntimeError,'precede_X11'):self.overlay.apply()
        self.assertEqual(before,self.n.files);self.assertFalse(self.n.created)
    def completed_x11_rollback(self):
        before_unit=self.n.read(m.APP_UNIT)[1];before_register=self.n.read(m.COMPLETE)[1]
        doc=json.loads(self.n.read(m.COMPLETE)[0])
        self.n.write(m.APP_UNIT,b'amended-app-unit',0o644)
        self.n.write(m.APP_UNIT,b'original-app-unit',0o644);unit=self.n.read(m.APP_UNIT)[1]
        m.inventory(doc,'files')[str(m.APP_UNIT)].update(unit)
        self.n.write(m.COMPLETE,m.encoded(doc),0o600);complete=self.n.read(m.COMPLETE)[1]
        x11={'version':1,'repair':'production_x11_v6','phase':'rolled_back','helper_sha256':m.X11_HELPER_SHA,
             'before':{'unit':before_unit,'register':before_register},'rollback':{'unit':unit,'register':complete}}
        self.n.files[str(m.X11_TRANSACTION)]=(b'',{'path':str(m.X11_TRANSACTION)})
        self.n.write(m.X11_TRANSACTION/'journal.json',m.encoded(x11),0o600)
        return x11,unit
    def test_only_exact_completed_X11_rollback_chain_preserves_restored_app_unit_registration(self):
        self.overlay.apply();_,app=self.completed_x11_rollback()
        result=self.overlay.rollback();self.assertEqual(result['status'],'rolled_back');self.assert_paired(m.BEFORE_SHA)
        self.assertEqual(m.inventory(self.documents()['complete'],'files')[str(m.APP_UNIT)],app)
        self.assertEqual(self.n.read(m.APP_UNIT)[1],app)
        self.assertEqual(self.overlay.rollback()['status'],'already_rolled_back')
    def test_X11_active_phase_helper_unit_source_and_unrelated_history_are_not_accepted(self):
        for change in('phase','helper','unit','source','other_row','starting_register'):
            with self.subTest(change=change):
                self.reset();self.overlay.apply();history,_=self.completed_x11_rollback()
                if change=='phase':history['phase']='installed'
                elif change=='helper':self.n.write(m.X11_HELPER,b'unknown-helper',0o644)
                elif change=='unit':self.n.write(m.APP_UNIT,b'unknown-app-unit',0o644)
                elif change=='source':self.n.write(m.SOURCE,b'new-fixture',0o644)
                elif change=='starting_register':history['before']['register']['inode']+=1000
                else:
                    doc=json.loads(self.n.read(m.COMPLETE)[0]);doc['namespaces'].append({'unknown':'registration'})
                    self.n.write(m.COMPLETE,m.encoded(doc),0o600);history['rollback']['register']=self.n.read(m.COMPLETE)[1]
                self.n.write(m.X11_TRANSACTION/'journal.json',m.encoded(history),0o600)
                before=copy.deepcopy(self.n.files)
                with self.assertRaises(RuntimeError):self.overlay.rollback()
                self.assertEqual(self.n.files,before)
    def test_recognized_X11_history_drift_during_our_rollback_is_preserved(self):
        self.overlay.apply();self.completed_x11_rollback();self.n.fail_after='source'
        with self.assertRaises(RuntimeError):self.overlay.rollback()
        self.n.write(m.X11_TRANSACTION/'journal.json',b'changed',0o600)
        before=copy.deepcopy(self.n.files)
        with self.assertRaisesRegex(RuntimeError,'recognized_X11_history_drift'):self.overlay.rollback()
        self.assertEqual(self.n.files,before)
    def test_frozen_payload_rejects_unknown_source_bytes(self):
        self.assertEqual(m.validate_payload(b'new-fixture'),b'new-fixture')
        with self.assertRaisesRegex(RuntimeError,'frozen_backend_source'):m.validate_payload(b'unknown')
    def test_journal_cannot_redirect_a_fixed_target(self):
        self.n.fail_before='source'
        with self.assertRaises(RuntimeError):self.overlay.apply()
        path=self.n.transaction/'journal.json';journal=json.loads(self.n.read(path)[0])
        journal['new']['source']['path']='/unrelated/file';self.n.write(path,m.encoded(journal),0o600)
        before=copy.deepcopy(self.n.files)
        with self.assertRaisesRegex(RuntimeError,'fixed_overlay_journal_paths'):self.overlay.apply()
        self.assertEqual(before,self.n.files)


class ProtectedLocks(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'owned.lock'
    def root_metadata(self):
        original=os.fstat
        def root_stat(fd):
            values=list(original(fd));values[4]=0
            return os.stat_result(values)
        return patch.object(m.os,'fstat',side_effect=root_stat)
    def test_existing_protected_lock_contends_without_waiting_or_replacing_inode(self):
        self.path.write_bytes(b'');self.path.chmod(0o600);before=self.path.stat()
        with self.root_metadata():
            fd=m.acquire_lock(self.path,False)
            try:
                with self.assertRaises(BlockingIOError):m.acquire_lock(self.path,False)
            finally:os.close(fd)
        self.assertEqual(self.path.stat().st_ino,before.st_ino)
        with self.root_metadata():
            fd=m.acquire_lock(self.path,False);os.close(fd)
    def test_shared_existing_lock_is_not_created_when_absent(self):
        with self.assertRaises(FileNotFoundError):m.acquire_lock(self.path,False)
        self.assertFalse(self.path.exists())
    def test_symlink_hardlink_writable_and_nonroot_lock_are_rejected(self):
        target=self.path.with_name('target');target.write_bytes(b'');target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(OSError):m.acquire_lock(self.path,False)
        self.path.unlink();os.link(target,self.path)
        with self.root_metadata():
            with self.assertRaisesRegex(RuntimeError,'protected_single_link'):m.acquire_lock(self.path,False)
        self.path.unlink();self.path.write_bytes(b'');self.path.chmod(0o666)
        with self.root_metadata():
            with self.assertRaisesRegex(RuntimeError,'protected_single_link'):m.acquire_lock(self.path,False)
        self.path.chmod(0o600)
        if os.getuid()!=0:
            with self.assertRaisesRegex(RuntimeError,'protected_single_link'):m.acquire_lock(self.path,False)


if __name__=='__main__':unittest.main()
