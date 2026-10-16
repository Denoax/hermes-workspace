"""Fixture-only transaction/guard regressions. No real service/model operations."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

BASE=Path(__file__).resolve().parent
SOURCE=BASE/'production_x11_setup.py'
if not SOURCE.exists():SOURCE=BASE.parent/'native/production_x11_setup.py'
FIXTURE=BASE/'runtime-unit.before'
if not FIXTURE.exists():FIXTURE=BASE/'fixtures/hermes-workspace-runtime.pre-x11.service'
spec=importlib.util.spec_from_file_location('proposed_x11_setup',SOURCE)
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)
BEFORE=FIXTURE.read_bytes()


class FakeNative:
    unit,register,transaction=repair.UNIT,repair.REGISTER,repair.TRANSACTION
    def __init__(self):
        self.files={};self.serial=10;self.actions=[];self.pid=111;self.created=False
        self.own={'sha256':'e'*64};self.guard_calls=0;self.fail_guard_at=None;self.after_write=None
        self.bind_present=False;self.after_reload=None;self.after_restart=None
        self.merge= lambda original,item:repair.merge_unit(original,item,self.record_files)
        self.put(self.unit,BEFORE,0o644)
        self.other={'path':'/original/restore-target','device':1,'inode':7,'uid':0,'mode':0o644,'sha256':'b'*64,
                    'action':'restore','backup':'/fixed/private/backup','before_sha256':'c'*64,'before_mode':0o644}
        self.initial={'version':1,'files':[self.fp(self.unit),self.other],
                      'accounts':[{'created':False}],'namespaces':[{'retained':'namespace'}],
                      'retained':['conversations','models'],'source_pack_sha256':'original-source-history'}
        self.put(self.register,(json.dumps(self.initial,indent=2)+'\n').encode(),0o600)

    def put(self,path,raw,mode):
        self.serial+=1
        self.files[str(path)]={'raw':raw,'device':1,'inode':self.serial,'uid':0,'mode':mode}
        return self.fp(path)

    def fp(self,path):
        p=self.files[str(path)]
        return {'path':str(path),**{k:p[k] for k in ('device','inode','uid','mode')},'sha256':repair.digest(p['raw'])}

    fingerprint=fp

    def read(self,path):return self.files[str(path)]['raw'],self.fp(path)

    def same(self,item):
        return str(item['path']) in self.files and all(self.fp(item['path']).get(k)==item.get(k) for k in repair.IDENTITY_KEYS)

    def write(self,path,raw,mode):
        result=self.put(path,raw,mode)
        if self.after_write:self.after_write(self,path,raw)
        return result

    @staticmethod
    def record_files(register,changed):
        current={item['path']:dict(item) for item in register['files']}
        for item in changed:current[item['path']]={**current.get(item['path'],{}),**item}
        return {**register,'files':list(current.values())}

    def validate_register(self,register):
        paths=[item['path'] for item in register['files']]
        repair.check(len(paths)==len(set(paths)),'fixture_duplicate_register')
        matches=[item for item in register['files'] if item['path']==str(self.unit)]
        repair.check(len(matches)==1 and self.same(matches[0]),'fixture_unit_register_mismatch')

    def journal_exists(self):return self.created

    def prepare(self,unit,register):
        self.created=True;self.put(self.transaction/'unit.before',unit,0o600);self.put(self.transaction/'register.before',register,0o600)

    def normal_pins(self):return {name:'a'*64 for name in repair.NORMAL_FILES}
    def normal_unchanged(self,pins):repair.check(pins==self.normal_pins(),'fixture_normal_configuration_drift')
    def source_directory(self):pass
    def guard(self):
        self.guard_calls+=1
        if self.fail_guard_at==self.guard_calls:raise RuntimeError('fixture_work_became_active')
        return {'app_pid':self.pid,'active_chats':0,'active_jobs':0,'normal_slots_idle':True,'uid':1000}
    def reload(self):
        self.actions.append(('daemon-reload',))
        if self.after_reload:self.after_reload(self)
    def runtime_state(self):return {'app_pid':self.pid,'X11_bind_present':self.bind_present}
    def restart(self,old_pid,expected_bind):
        repair.check(old_pid==self.pid,'fixture_wrong_process_restart')
        self.actions.append(('restart',repair.UNIT_NAME,expected_bind));self.pid+=100;self.bind_present=expected_bind
        if self.after_restart:self.after_restart(self,expected_bind)
        return {'pid':self.pid,'uid':1000,'PrivateTmp':True,'read_only_X11_bind':expected_bind}
    def journal(self):return json.loads(self.read(self.transaction/'journal.json')[0])


class Amendment(unittest.TestCase):
    def test_exact_unit_diff_is_only_fixed_read_only_bind_after_PrivateTmp(self):
        result=repair.amended_unit(BEFORE)
        self.assertEqual(repair.digest(result),repair.AFTER_SHA)
        self.assertEqual(result.replace(repair.BIND_LINE,b''),BEFORE)
        self.assertIn(b'PrivateTmp=yes\n'+repair.BIND_LINE,result)
        self.assertIn(b'PrivateUsers=no\nNoNewPrivileges=yes\nCapabilityBoundingSet=\nAmbientCapabilities=\n',result)

    def test_modified_or_already_amended_preimage_is_refused(self):
        for raw in (BEFORE+b'\n',BEFORE.replace(b'PrivateTmp=yes',b'PrivateTmp=no'),repair.amended_unit(BEFORE)):
            with self.subTest(raw=repair.digest(raw)),self.assertRaisesRegex(RuntimeError,'exact_original'):
                repair.amended_unit(raw)

    def test_merge_preserves_every_other_entry_field_and_unit_restore_metadata(self):
        native=FakeNative();original=copy.deepcopy(native.initial)
        original['files'][0].update(action='restore',backup='/approved/private/source',before_sha256='1'*64)
        item={**original['files'][0],'inode':999,'sha256':'d'*64}
        item={k:item[k] for k in repair.IDENTITY_KEYS}
        result=native.merge(original,item)
        self.assertEqual(result['files'][1],native.other)
        self.assertEqual(result['retained'],original['retained'])
        self.assertEqual(result['files'][0]['backup'],'/approved/private/source')
        self.assertEqual(result['files'][0]['inode'],999)
        self.assertEqual(original['files'][0]['inode'],native.initial['files'][0]['inode'])

    def test_merge_cannot_add_a_new_unit_or_change_unrelated_data(self):
        native=FakeNative();item={**native.fp(native.unit),'path':'/unregistered/unit'}
        with self.assertRaisesRegex(RuntimeError,'existing_registered'):native.merge(native.initial,item)
        def bad_merge(original,changed):return {**original,'accounts':[]}
        with self.assertRaisesRegex(RuntimeError,'unrelated_register'):repair.merge_unit(native.initial,native.fp(native.unit),bad_merge)


class Transaction(unittest.TestCase):
    def test_apply_changes_only_registered_app_unit_and_bounded_app_restart(self):
        native=FakeNative();result=repair.Repair(native).apply()
        self.assertEqual(result['status'],'installed')
        self.assertEqual(native.files[str(native.unit)]['raw'],repair.amended_unit(BEFORE))
        actual=json.loads(native.read(native.register)[0]);self.assertEqual(actual['files'][1],native.other)
        self.assertEqual({k:v for k,v in actual.items() if k!='files'},
                         {k:v for k,v in native.initial.items() if k!='files'})
        self.assertEqual(actual['files'][0],native.fp(native.unit))
        self.assertEqual(native.actions,[('daemon-reload',),('restart',repair.UNIT_NAME,True)])
        self.assertEqual(native.journal()['phase'],'installed')
        self.assertEqual(native.guard_calls,3)

    def test_second_apply_is_idempotent_and_does_not_reload_or_restart(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();before=copy.deepcopy(native.files)
        native.actions=[];result=runner.apply()
        self.assertEqual(result['status'],'already_installed');self.assertEqual(native.actions,[])
        self.assertEqual(native.files,before)

    def test_preflight_job_activity_prevents_any_unit_or_register_write(self):
        native=FakeNative();before=copy.deepcopy(native.files);native.fail_guard_at=1
        with self.assertRaisesRegex(RuntimeError,'work_became_active'):repair.Repair(native).apply()
        self.assertEqual(native.files,before);self.assertFalse(native.created);self.assertEqual(native.actions,[])

    def test_activity_after_registration_prevents_app_restart_and_keeps_recoverable_journal(self):
        native=FakeNative();native.fail_guard_at=2
        with self.assertRaisesRegex(RuntimeError,'work_became_active'):repair.Repair(native).apply()
        self.assertEqual(native.actions,[('daemon-reload',)])
        self.assertEqual(native.journal()['phase'],'reloaded')
        self.assertFalse(native.journal()['restart_attempted'])
        native.fail_guard_at=None
        result=repair.Repair(native).rollback()
        self.assertEqual(result['status'],'rolled_back')
        self.assertFalse(any(action[0]=='restart' for action in native.actions))

    def test_automatic_restart_after_reload_is_reversed_even_without_explicit_restart_attempt(self):
        native=FakeNative();runner=repair.Repair(native)
        def automatic_restart(n):
            if repair.digest(n.read(n.unit)[0])==repair.AFTER_SHA:n.pid+=1;n.bind_present=True
        native.after_reload=automatic_restart
        with self.assertRaisesRegex(RuntimeError,'changed_app_process_before_restart'):runner.apply()
        self.assertFalse(native.journal()['restart_attempted']);self.assertTrue(native.bind_present)
        native.actions=[];result=runner.rollback()
        self.assertEqual(result['status'],'rolled_back');self.assertFalse(native.bind_present)
        self.assertEqual(native.actions,[('daemon-reload',),('restart',repair.UNIT_NAME,False)])
        self.assertTrue(native.journal()['rollback_proof']['X11_bind_absence_observed'])

    def test_observed_bind_with_original_pid_also_requires_actual_rollback_restart(self):
        native=FakeNative();runner=repair.Repair(native);native.fail_guard_at=2
        with self.assertRaises(RuntimeError):runner.apply()
        native.fail_guard_at=None;native.bind_present=True;native.actions=[]
        runner.rollback();self.assertFalse(native.bind_present)
        self.assertIn(('restart',repair.UNIT_NAME,False),native.actions)

    def test_rollback_never_reports_success_if_final_runtime_still_contains_bind(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply()
        native.after_restart=lambda n,expected:setattr(n,'bind_present',True)
        with self.assertRaisesRegex(RuntimeError,'actual_original_runtime_without_X11_bind'):runner.rollback()
        self.assertNotEqual(native.journal()['phase'],'rolled_back')

    def test_concurrent_register_change_after_unit_write_is_preserved_and_never_restarted(self):
        native=FakeNative()
        def race(n,path,raw):
            if path==n.unit:n.put(n.register,b'{"new_root_change":true}',0o600)
        native.after_write=race
        with self.assertRaisesRegex(RuntimeError,'concurrent_register_or_unit'):repair.Repair(native).apply()
        self.assertEqual(native.read(native.register)[0],b'{"new_root_change":true}')
        self.assertEqual(native.actions,[])

    def test_rollback_restores_original_bytes_and_reregisters_new_inode(self):
        native=FakeNative();runner=repair.Repair(native);old_inode=native.fp(native.unit)['inode'];runner.apply()
        native.actions=[];result=runner.rollback();actual=json.loads(native.read(native.register)[0])
        self.assertEqual(result['status'],'rolled_back');self.assertEqual(native.read(native.unit)[0],BEFORE)
        self.assertNotEqual(native.fp(native.unit)['inode'],old_inode)
        self.assertEqual(actual['files'][0],native.fp(native.unit));self.assertEqual(actual['files'][1],native.other)
        self.assertEqual(native.actions,[('daemon-reload',),('restart',repair.UNIT_NAME,False)])
        native.actions=[];runner.rollback();self.assertEqual(native.actions,[])

    def test_later_unit_or_register_change_blocks_rollback_before_mutation(self):
        for role in ('unit','register'):
            native=FakeNative();runner=repair.Repair(native);runner.apply()
            native.put(getattr(native,role),b'later root changes',0o644 if role=='unit' else 0o600)
            before=copy.deepcopy(native.files);native.actions=[]
            with self.subTest(role=role),self.assertRaises(RuntimeError):runner.rollback()
            self.assertEqual(native.files,before);self.assertEqual(native.actions,[])

    def test_backup_tamper_is_refused_before_rollback(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();native.put(native.transaction/'unit.before',b'bad backup',0o600)
        before=copy.deepcopy(native.files)
        with self.assertRaisesRegex(RuntimeError,'backup_pin_changed'):runner.rollback()
        self.assertEqual(native.files,before)

    def test_apply_refuses_partial_or_rolled_back_journal(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();runner.rollback()
        with self.assertRaisesRegex(RuntimeError,'partial_or_rolled_back'):runner.apply()

    def test_unit_write_before_journal_gap_is_recovered_only_for_exact_fixed_bytes(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();journal=native.journal()
        journal['phase']='prepared';journal['installed']={};journal['restart_attempted']=False
        native.put(native.register,native.read(native.transaction/'register.before')[0],0o600)
        journal['before']['register']=native.fp(native.register);runner.save(journal)
        result=runner.rollback();self.assertEqual(result['status'],'rolled_back')
        self.assertEqual(native.read(native.unit)[0],BEFORE)

    def test_register_write_before_journal_gap_is_recovered_with_exact_known_merge(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();journal=native.journal()
        journal['phase']='unit_written';journal['installed'].pop('register');runner.save(journal)
        result=runner.rollback();self.assertEqual(result['status'],'rolled_back')
        self.assertEqual(json.loads(native.read(native.register)[0])['files'][0],native.fp(native.unit))

    def test_unknown_register_commit_gap_is_never_blessed(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();journal=native.journal()
        journal['phase']='unit_written';journal['installed'].pop('register');runner.save(journal)
        native.put(native.register,b'{"unrelated":"root update"}',0o600);before=copy.deepcopy(native.files)
        with self.assertRaisesRegex(RuntimeError,'unknown_register_commit_gap'):runner.rollback()
        self.assertEqual(native.files,before)

    def test_original_unit_write_before_rollback_journal_gap_is_reregistered(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply()
        native.put(native.unit,BEFORE,0o644)
        result=runner.rollback();self.assertEqual(result['status'],'rolled_back')
        self.assertEqual(json.loads(native.read(native.register)[0])['files'][0],native.fp(native.unit))

    def test_rollback_register_write_gap_accepts_only_exact_restored_merge(self):
        native=FakeNative();runner=repair.Repair(native);runner.apply();journal=native.journal()
        restored=native.put(native.unit,BEFORE,0o644)
        journal['rollback']['unit']=restored;journal['phase']='rollback_unit';runner.save(journal)
        original=json.loads(native.read(native.transaction/'register.before')[0])
        raw=(json.dumps(native.merge(original,restored),indent=2)+'\n').encode()
        native.put(native.register,raw,0o600)
        result=runner.rollback();self.assertEqual(result['status'],'rolled_back')
        self.assertEqual(json.loads(native.read(native.register)[0])['files'][0],native.fp(native.unit))


class DependencyBoundary(unittest.TestCase):
    def test_nonroot_or_noninstalled_entry_stops_before_loading_dependencies(self):
        with patch.object(repair.os,'geteuid',return_value=1000),patch.object(repair,'load_trusted_dependency')as imported:
            with self.assertRaisesRegex(SystemExit,'fixed_protected'):repair.main()
            imported.assert_not_called()

    def test_registered_protected_dependency_identity_must_match_exactly(self):
        actual={'path':str(repair.DEPENDENCY),'device':1,'inode':2,'uid':0,'mode':0o644,'sha256':repair.DEPENDENCY_SHA}
        register={'version':1,'files':[actual.copy()]};repair.registered_dependency(register,actual)
        for key,value in [('inode',3),('uid',1000),('mode',0o666),('sha256','0'*64)]:
            changed=copy.deepcopy(register);changed['files'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'registered_trusted'):
                repair.registered_dependency(changed,actual)
        with self.assertRaisesRegex(RuntimeError,'unique_complete'):
            repair.registered_dependency({'version':1,'files':[actual,actual]},actual)

    def test_wrong_dependency_pin_refuses_import(self):
        own={'mode':0o644,'sha256':'a'*64};dependency={'mode':0o644,'sha256':'bad'}
        with patch.object(repair,'protected_read',side_effect=[(b'self',own),(b'dep',dependency)]),patch.object(repair.importlib.util,'spec_from_file_location')as imported:
            with self.assertRaisesRegex(RuntimeError,'pinned_root_dependency'):repair.load_trusted_dependency()
            imported.assert_not_called()

    def test_unregistered_dependency_refuses_import_even_when_code_pin_matches(self):
        actual={'path':str(repair.DEPENDENCY),'device':1,'inode':2,'uid':0,'mode':0o644,'sha256':repair.DEPENDENCY_SHA}
        register={'version':1,'files':[]}
        with patch.object(repair,'protected_read',side_effect=[(b'self',{'mode':0o644}),
                (b'dep',actual),(json.dumps(register).encode(),{})]),patch.object(repair.importlib.util,'spec_from_file_location')as imported:
            with self.assertRaisesRegex(RuntimeError,'registered_trusted'):repair.load_trusted_dependency()
            imported.assert_not_called()


class AuditBoundary(unittest.TestCase):
    def fixture(self, *, unknown_unit=False, source_drift=False, registered_mode=0o644):
        unit_raw=b'unknown-private-unit-sentinel' if unknown_unit else b'fixed-known-unit'
        source_raw=b'fixed-backend-source'
        def info(path,raw,mode,inode):
            return {'path':str(path),'device':1,'inode':inode,'sha256':repair.digest(raw),'uid':0,'mode':mode}
        unit=info(repair.BACKEND_UNIT,unit_raw,0o600,20)
        source=info(repair.BACKEND_SOURCE,source_raw,0o644,30)
        dependency=info(repair.DEPENDENCY,b'dependency',0o644,10);dependency['sha256']=repair.DEPENDENCY_SHA
        allowed=repair.digest(b'fixed-known-unit')
        entry={**unit,'mode':registered_mode,'allowed_sha256':[allowed]}
        source_entry={**source,'inode':29 if source_drift else source['inode']}
        register={'version':1,'files':[dependency.copy(),entry,source_entry],'retained':['private-history-sentinel']}
        register_raw=json.dumps(register).encode()
        rows={repair.REGISTER:(register_raw,info(repair.REGISTER,register_raw,0o600,40)),
              repair.DEPENDENCY:(b'dependency',dependency),repair.BACKEND_UNIT:(unit_raw,unit),
              repair.BACKEND_SOURCE:(source_raw,source)}
        reader=Mock(side_effect=lambda path,**kwargs:copy.deepcopy(rows[path]))
        trusted=SimpleNamespace(inspect_register=Mock())
        return rows,register,reader,trusted,allowed

    def run_audit(self, *, unknown_unit=False, source_drift=False, other_error=None, registered_mode=0o644):
        rows,register,reader,trusted,allowed=self.fixture(unknown_unit=unknown_unit,source_drift=source_drift,registered_mode=registered_mode)
        if other_error:trusted.inspect_register.side_effect=RuntimeError(other_error)
        original=copy.deepcopy(register)
        with patch.object(repair,'protected_read',reader),\
                patch.object(repair,'BACKEND_VARIANTS',{'normal':'a'*64,'abliterated':allowed}),\
                patch.object(repair,'BACKEND_SOURCE_SHA',repair.digest(b'fixed-backend-source')):
            result=repair.audit(trusted)
        self.assertEqual(register,original)
        inspected=trusted.inspect_register.call_args.args[0]
        self.assertEqual(inspected['retained'],register['retained'])
        self.assertEqual(inspected['files'],[row for row in register['files'] if row['path']!=str(repair.BACKEND_UNIT)])
        return result

    def test_audit_identifies_known_hash_mode_only_drift_without_admission_or_data_changes(self):
        result=self.run_audit()
        self.assertEqual(result['status'],'audited_read_only')
        self.assertEqual(result['backend_unit']['mode'],0o600)
        self.assertEqual(result['backend_unit']['existing_registered_mode'],0o644)
        self.assertEqual(result['backend_unit']['admission_required_mode'],0o644)
        self.assertFalse(result['backend_unit']['mode_satisfies_generated_unit_admission'])
        self.assertFalse(result['backend_unit']['mode_matches_registration'])
        self.assertTrue(result['backend_unit']['hash_in_existing_allowlist'])
        self.assertEqual(result['backend_unit']['matches_fixed_generator_variants'],{'normal':False,'abliterated':True})
        self.assertTrue(result['installed_backend_source']['registered_fingerprint_matches'])
        self.assertTrue(result['installed_backend_source']['matches_reviewed_source'])
        self.assertFalse(result['admission_changed']);self.assertFalse(result['writes_performed'])
        stored_0600=self.run_audit(registered_mode=0o600)['backend_unit']
        self.assertTrue(stored_0600['mode_matches_registration'])
        self.assertFalse(stored_0600['mode_satisfies_generated_unit_admission'])

    def test_unknown_protected_unit_bytes_are_reported_unmatched_without_exporting_text(self):
        result=self.run_audit(unknown_unit=True)
        self.assertFalse(result['backend_unit']['hash_in_existing_allowlist'])
        self.assertFalse(any(result['backend_unit']['matches_fixed_generator_variants'].values()))
        self.assertNotIn('unknown-private-unit-sentinel',json.dumps(result))
        self.assertNotIn('private-history-sentinel',json.dumps(result))

    def test_installed_source_inode_drift_is_not_treated_as_registered_by_hash_alone(self):
        result=self.run_audit(source_drift=True)
        self.assertTrue(result['installed_backend_source']['matches_reviewed_source'])
        self.assertFalse(result['installed_backend_source']['registered_fingerprint_matches'])

    def test_other_registered_drift_is_reported_as_fixed_code_without_private_error_text(self):
        result=self.run_audit(other_error='private-root-path-sentinel')
        self.assertEqual(result['all_other_registered_entries'],{'status':'FAIL','error_code':'other_registered_entry_mismatch'})
        self.assertEqual(result['other_entry_check_scope'],'existing_inspect_register_policy_skips_absent_paths')
        self.assertNotIn('private-root-path-sentinel',json.dumps(result))
        self.assertFalse(result['admission_changed'])

    def test_malformed_allowlist_or_inputs_changing_during_audit_fail_closed(self):
        for allowed in ([],['bad'],['a'*64]*2,'a'*64):
            rows,register,reader,trusted,_=self.fixture();register['files'][1]['allowed_sha256']=allowed
            raw=json.dumps(register).encode();rows[repair.REGISTER]=(raw,{**rows[repair.REGISTER][1],'sha256':repair.digest(raw)})
            with self.subTest(allowed=allowed),patch.object(repair,'protected_read',reader):
                with self.assertRaisesRegex(RuntimeError,'existing_backend_allowlist'):repair.audit(trusted)
            trusted.inspect_register.assert_not_called()
        rows,register,reader,trusted,_=self.fixture();reads=[0]
        def changed(path,**kwargs):
            raw,actual=copy.deepcopy(rows[path])
            if path==repair.BACKEND_UNIT:
                reads[0]+=1
                if reads[0]>1:actual['inode']+=1
            return raw,actual
        with patch.object(repair,'protected_read',side_effect=changed):
            with self.assertRaisesRegex(RuntimeError,'audit_backend_input_changed'):repair.audit(trusted)

    def test_audit_cli_returns_before_native_construction_locks_writes_deadlines_or_commands(self):
        result={'operation':'audit','status':'audited_read_only'}
        with patch.object(repair.os,'geteuid',return_value=0),patch.object(repair,'SELF',Path(repair.__file__).absolute()),\
                patch.object(repair.sys,'argv',['fixed-helper','audit']),\
                patch.object(repair,'load_trusted_dependency',return_value=(Mock(),{})),\
                patch.object(repair,'audit',return_value=result) as audited,\
                patch.object(repair,'Native') as native,patch.object(repair,'Repair') as transaction,\
                patch.object(repair.os,'open') as opened,patch.object(repair.fcntl,'flock') as locked,\
                patch.object(repair.signal,'alarm') as deadline,patch.object(repair.subprocess,'run') as command,\
                patch.object(repair.sys,'stdout',new_callable=io.StringIO) as stdout:
            repair.main()
            self.assertEqual(json.loads(stdout.getvalue()),result)
        audited.assert_called_once();native.assert_not_called();transaction.assert_not_called()
        opened.assert_not_called();locked.assert_not_called();deadline.assert_not_called();command.assert_not_called()

    def test_audit_cli_failure_prints_only_fixed_error_fields(self):
        with patch.object(repair.os,'geteuid',return_value=0),patch.object(repair,'SELF',Path(repair.__file__).absolute()),\
                patch.object(repair.sys,'argv',['fixed-helper','audit']),\
                patch.object(repair,'load_trusted_dependency',side_effect=RuntimeError('private-error-sentinel')),\
                patch.object(repair.sys,'stdout',new_callable=io.StringIO) as stdout:
            with self.assertRaises(SystemExit) as stopped:repair.main()
            self.assertEqual(stopped.exception.code,2)
            result=json.loads(stdout.getvalue())
        self.assertEqual(result['error_code'],'protected_backend_audit_failed')
        self.assertNotIn('private-error-sentinel',json.dumps(result));self.assertFalse(result['writes_performed'])


class ModeNative(FakeNative):
    def __init__(self):
        super().__init__();self.mode_created=False;self.after_mode=None
        self.put(repair.DEPENDENCY,b'trusted dependency',0o644)
        self.put(repair.BACKEND_SOURCE,b'fixed backend source',0o644)
        self.put(repair.BACKEND_UNIT,b'fixed abliterated unit',0o600)
        backend={**self.fp(repair.BACKEND_UNIT),'mode':0o644,'allowed_sha256':list(repair.BACKEND_VARIANTS.values())}
        register={'version':1,'files':[self.fp(self.unit),self.fp(repair.DEPENDENCY),self.fp(repair.BACKEND_SOURCE),backend],
                  'source_pack_sha256':'unchanged-history-sentinel'}
        self.put(self.register,json.dumps(register).encode(),0o600)
        self.trusted=SimpleNamespace(inspect_register=self.inspect)

    def inspect(self,register):
        for row in register['files']:
            if row['path'] not in self.files:continue
            actual=self.fp(row['path'])
            if row['path']==str(repair.BACKEND_UNIT):
                repair.check(actual['uid']==0 and actual['mode']==0o644 and actual['sha256'] in row['allowed_sha256'],
                             'preserve_registered_backend_drift')
            else:repair.check(self.same(row),'preserve_registered_file_drift')

    def mode_journal_exists(self):return self.mode_created
    def prepare_mode(self):self.mode_created=True;self.actions.append(('prepare-mode',))
    def write(self,path,raw,mode):
        self.actions.append(('write-private-journal',str(path)))
        return super().write(path,raw,mode)
    def chmod_backend_mode(self,expected,target,register,source):
        repair.check(self.fp(repair.BACKEND_UNIT)==expected and self.fp(repair.REGISTER)==register
                     and self.fp(repair.BACKEND_SOURCE)==source,'fixture_mode_preimage_changed')
        self.actions.append(('fchmod',target));self.files[str(repair.BACKEND_UNIT)]['mode']=target
        if self.after_mode:self.after_mode(self,target)
        return self.fp(repair.BACKEND_UNIT)


class BackendModeTransaction(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(repair,'BACKEND_VARIANTS',{
            'normal':repair.digest(b'fixed normal unit'),'abliterated':repair.digest(b'fixed abliterated unit')}))
        self.enterContext(patch.object(repair,'BACKEND_SOURCE_SHA',repair.digest(b'fixed backend source')))

    def test_explicit_mode_correction_restores_full_existing_inspection_without_other_mutations(self):
        n=ModeNative();before=copy.deepcopy(n.files);unit=n.fp(repair.BACKEND_UNIT)
        with self.assertRaisesRegex(RuntimeError,'registered_backend_drift'):
            n.inspect(json.loads(n.read(n.register)[0]))
        result=repair.BackendModeRepair(n).apply()
        self.assertEqual(result['status'],'backend_mode_reconciled')
        self.assertEqual(n.fp(repair.BACKEND_UNIT),{**unit,'mode':0o644})
        n.inspect(json.loads(n.read(n.register)[0]))
        for path,old in before.items():
            if path!=str(repair.BACKEND_UNIT):self.assertEqual(n.files[path],old)
        self.assertEqual(n.files[str(repair.BACKEND_UNIT)]['raw'],before[str(repair.BACKEND_UNIT)]['raw'])
        self.assertTrue(all(action[0] in ('prepare-mode','write-private-journal','fchmod') for action in n.actions))
        journal=json.loads(n.read(repair.MODE_TRANSACTION/'journal.json')[0]);self.assertEqual(journal['phase'],'applied')
        self.assertNotIn('fixed abliterated unit',json.dumps(journal))

    def test_apply_and_rollback_are_idempotent_and_rollback_restores_only_recorded_mode(self):
        n=ModeNative();runner=repair.BackendModeRepair(n);runner.apply();n.actions=[];before=copy.deepcopy(n.files)
        self.assertEqual(runner.apply()['status'],'backend_mode_already_reconciled')
        self.assertEqual(n.actions,[]);self.assertEqual(n.files,before)
        unit=n.fp(repair.BACKEND_UNIT);result=runner.rollback()
        self.assertEqual(result['status'],'backend_mode_rolled_back');self.assertFalse(result['generated_unit_admission_mode_satisfied'])
        self.assertEqual(n.fp(repair.BACKEND_UNIT),{**unit,'mode':0o600})
        with self.assertRaisesRegex(RuntimeError,'registered_backend_drift'):n.inspect(json.loads(n.read(n.register)[0]))
        n.actions=[];before=copy.deepcopy(n.files)
        self.assertEqual(runner.rollback()['status'],'backend_mode_already_rolled_back');self.assertEqual(n.actions,[])
        self.assertEqual(n.files,before)
        with self.assertRaisesRegex(RuntimeError,'rolled_back_requires_new_review'):runner.apply()

    def test_only_exact_fchmod_before_journal_gaps_can_resume_in_both_directions(self):
        n=ModeNative();runner=repair.BackendModeRepair(n)
        def interrupted(native,target):raise RuntimeError('fixture_after_fchmod_interrupt')
        n.after_mode=interrupted
        with self.assertRaisesRegex(RuntimeError,'fchmod_interrupt'):runner.apply()
        self.assertEqual(n.fp(repair.BACKEND_UNIT)['mode'],0o644)
        self.assertEqual(json.loads(n.read(repair.MODE_TRANSACTION/'journal.json')[0])['phase'],'prepared')
        n.after_mode=None;n.actions=[];runner.apply()
        self.assertFalse(any(action[0]=='fchmod' for action in n.actions))
        n.after_mode=interrupted
        with self.assertRaisesRegex(RuntimeError,'fchmod_interrupt'):runner.rollback()
        self.assertEqual(n.fp(repair.BACKEND_UNIT)['mode'],0o600)
        n.after_mode=None;n.actions=[];runner.rollback()
        self.assertFalse(any(action[0]=='fchmod' for action in n.actions))

    def test_unknown_mode_hash_source_or_registration_drift_is_preserved_before_preparation(self):
        def mode(n):n.files[str(repair.BACKEND_UNIT)]['mode']=0o640
        def unit(n):n.put(repair.BACKEND_UNIT,b'unknown unit',0o600)
        def source(n):n.put(repair.BACKEND_SOURCE,b'fixed backend source',0o644)
        def registration(n):
            value=json.loads(n.read(n.register)[0]);value['files'][-1]['allowed_sha256'].append('a'*64)
            n.put(n.register,json.dumps(value).encode(),0o600)
        for mutate in (mode,unit,source,registration):
            n=ModeNative();mutate(n);before=copy.deepcopy(n.files)
            with self.subTest(mutate=mutate.__name__),self.assertRaises(RuntimeError):repair.BackendModeRepair(n).apply()
            self.assertFalse(n.mode_created);self.assertEqual(n.actions,[]);self.assertEqual(n.files,before)

    def test_later_register_source_or_amended_app_blocks_rollback_without_blind_restores(self):
        for target in ('register','source','app'):
            n=ModeNative();runner=repair.BackendModeRepair(n);runner.apply()
            if target=='register':
                value=json.loads(n.read(n.register)[0]);value['retained_later_history']=True
                n.put(n.register,json.dumps(value).encode(),0o600)
            elif target=='source':n.put(repair.BACKEND_SOURCE,b'later installed backend source',0o644)
            else:n.put(n.unit,repair.amended_unit(BEFORE),0o644)
            before=copy.deepcopy(n.files);n.actions=[]
            with self.subTest(target=target),self.assertRaises(RuntimeError):runner.rollback()
            self.assertEqual(n.files,before);self.assertEqual(n.actions,[])

    def test_activity_or_tampered_own_journal_stops_mode_change(self):
        n=ModeNative();n.fail_guard_at=1;before=copy.deepcopy(n.files)
        with self.assertRaisesRegex(RuntimeError,'became_active'):repair.BackendModeRepair(n).apply()
        self.assertEqual(n.files,before);self.assertFalse(n.mode_created)
        n=ModeNative();n.fail_guard_at=2;runner=repair.BackendModeRepair(n)
        with self.assertRaisesRegex(RuntimeError,'became_active'):runner.apply()
        self.assertEqual(n.fp(repair.BACKEND_UNIT)['mode'],0o600);self.assertTrue(n.mode_created)
        late=ModeNative();late.fail_guard_at=3
        with self.assertRaisesRegex(RuntimeError,'became_active'):repair.BackendModeRepair(late).apply()
        self.assertEqual(late.fp(repair.BACKEND_UNIT)['mode'],0o600)
        self.assertFalse(any(action[0]=='fchmod' for action in late.actions))
        value=json.loads(n.read(repair.MODE_TRANSACTION/'journal.json')[0]);value['helper_sha256']='bad'
        n.put(repair.MODE_TRANSACTION/'journal.json',json.dumps(value).encode(),0o600);before=copy.deepcopy(n.files);n.actions=[]
        with self.assertRaisesRegex(RuntimeError,'own_backend_mode_journal'):runner.apply()
        self.assertEqual(n.files,before);self.assertEqual(n.actions,[])

    def test_only_explicit_cli_selectors_use_mode_repair_under_both_existing_locks(self):
        for operation,method in (('reconcile-backend-mode','apply'),('rollback-backend-mode','rollback'),('apply','apply')):
            trusted=Mock();mode=Mock();app=Mock()
            getattr(mode,method).return_value={'status':'fixture-mode'}
            getattr(app,method).return_value={'status':'fixture-app'}
            with self.subTest(operation=operation),patch.object(repair.os,'geteuid',return_value=0),\
                    patch.object(repair,'SELF',Path(repair.__file__).absolute()),patch.object(repair.sys,'argv',['helper',operation]),\
                    patch.object(repair,'load_trusted_dependency',return_value=(trusted,{})),patch.object(repair,'Native'),\
                    patch.object(repair,'BackendModeRepair',return_value=mode) as mode_type,\
                    patch.object(repair,'Repair',return_value=app) as app_type,\
                    patch.object(repair.os,'open',side_effect=[10,11]),\
                    patch.object(repair.os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_uid=0,st_nlink=1)),\
                    patch.object(repair.fcntl,'flock') as locked,patch.object(repair.os,'close'),\
                    patch.object(repair.signal,'signal'),patch.object(repair.signal,'alarm'),\
                    patch.object(repair.sys,'stdout',new_callable=io.StringIO):
                repair.main()
                self.assertEqual(locked.call_count,2)
                if operation=='apply':mode_type.assert_not_called();app_type.assert_called_once()
                else:mode_type.assert_called_once();app_type.assert_not_called();getattr(mode,method).assert_called_once()


class BackendModeDescriptor(unittest.TestCase):
    def execute(self,kind='regular',changed_register=False,wrong_hash=False):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);target=folder/'target';target.write_bytes(b'fixed template');target.chmod(0o600)
            path=folder/'unit'
            if kind=='symlink':path.symlink_to(target)
            elif kind=='hardlink':os.link(target,path)
            elif kind=='directory':path.mkdir()
            elif kind=='fifo':os.mkfifo(path)
            else:target.rename(path)
            source={'path':str(repair.BACKEND_SOURCE),'sha256':'s'*64}
            register={'path':str(repair.REGISTER),'sha256':'r'*64}
            def read(value):
                if value==repair.REGISTER:return b'register',{**register,'sha256':'changed' if changed_register else register['sha256']}
                if value==repair.BACKEND_SOURCE:return b'source',source.copy()
                raw=path.read_bytes();info=path.stat()
                return raw,{'path':str(path),'device':info.st_dev,'inode':info.st_ino,'uid':0,
                            'mode':stat.S_IMODE(info.st_mode),'sha256':repair.digest(raw)}
            real_fstat=os.fstat
            def root_owned(descriptor):
                info=real_fstat(descriptor)
                return SimpleNamespace(**{name:getattr(info,name) for name in
                    ('st_mode','st_nlink','st_size','st_dev','st_ino','st_mtime_ns','st_ctime_ns')},st_uid=0,st_gid=0)
            n=repair.Native(Mock(),{});n.read=read
            expected={'path':str(path),'device':path.stat().st_dev,'inode':path.stat().st_ino,'uid':0,'mode':0o600,
                      'sha256':'0'*64 if wrong_hash else repair.digest(b'fixed template')}
            with patch.object(repair,'BACKEND_UNIT',path),patch.object(repair.os,'fstat',side_effect=root_owned):
                if kind!='regular' or changed_register or wrong_hash:
                    with self.assertRaises((OSError,RuntimeError)):n.chmod_backend_mode(expected,0o644,register,source)
                    if kind in ('regular','symlink','hardlink'):
                        actual=target if target.exists() else path
                        self.assertEqual(actual.read_bytes(),b'fixed template');self.assertEqual(stat.S_IMODE(actual.stat().st_mode),0o600)
                else:
                    before=path.stat();result=n.chmod_backend_mode(expected,0o644,register,source)
                    self.assertEqual(result,{**expected,'mode':0o644})
                    self.assertEqual(path.stat().st_ino,before.st_ino);self.assertEqual(path.read_bytes(),b'fixed template')
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644)

    def test_actual_temporary_descriptor_changes_only_mode_not_bytes_or_inode(self):self.execute()

    def test_links_nonregular_identity_or_register_drift_are_refused_before_fchmod(self):
        for kind in ('symlink','hardlink','directory','fifo'):
            with self.subTest(kind=kind):self.execute(kind)
        self.execute(changed_register=True);self.execute(wrong_hash=True)


class UnprivilegedGuard(unittest.TestCase):
    def execute(self,chat='completed',job='review_ready',action='completed',slots=None):
        with tempfile.TemporaryDirectory()as temporary:
            p=Path(temporary)/'catalog.sqlite3';db=sqlite3.connect(p)
            db.executescript('CREATE TABLE chat_runs(state TEXT);CREATE TABLE jobs(state TEXT);CREATE TABLE permission_actions(state TEXT);')
            db.execute('INSERT INTO chat_runs VALUES (?)',(chat,));db.execute('INSERT INTO jobs VALUES (?)',(job,))
            db.execute('INSERT INTO permission_actions VALUES (?)',(action,));db.commit();db.close();p.chmod(0o600)
            before=p.read_bytes();source=repair.USER_GUARD.replace('/home/mani/HermesLab/catalog.sqlite3',str(p))
            response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.read.return_value=json.dumps(slots if slots is not None else [{'is_processing':False}]).encode()
            opener=Mock();opener.open.return_value=response
            with patch('urllib.request.build_opener',return_value=opener),patch('sys.stdout',new_callable=io.StringIO)as stdout:
                exec(compile(source,'fixed-unprivileged-guard','exec'),{})
                result=json.loads(stdout.getvalue())
            self.assertEqual(p.read_bytes(),before)
            opener.open.assert_called_once_with('http://127.0.0.1:8080/slots',timeout=2)
            return result

    def test_real_sqlite_readonly_guard_allows_terminal_states_without_data_changes(self):
        for job in ('review_ready','failed','cancelled','blocked'):
            self.assertEqual(self.execute(job=job)['active_jobs'],0)

    def test_any_active_chat_job_or_model_slot_is_refused(self):
        for kwargs in ({'chat':'streaming'},{'job':'queued'},{'job':'recovery_pending'},
                       {'action':'allowed'},{'action':'executing'},{'action':'cancelling'},
                       {'slots':[{'is_processing':True}]},{'slots':[]}):
            with self.subTest(kwargs=kwargs),self.assertRaises(AssertionError):self.execute(**kwargs)


class RestartBoundary(unittest.TestCase):
    def native(self):
        n=repair.Native(Mock(),{'sha256':'a'*64});n.service_pid=Mock(return_value=222)
        n.run=Mock(side_effect=lambda argv,**kwargs:b'yes\n' if argv[:2]==['/usr/bin/systemctl','show'] else b'ready\n')
        return n

    @staticmethod
    def namespace(path):
        if '/ns/mnt' in path:return 'host-mnt' if path.startswith('/proc/self/')else 'private-mnt'
        return 'initial-user-ns'

    def test_only_app_service_restart_and_readonly_mount_proof_are_allowed(self):
        n=self.native()
        mount='25 22 1:2 / /tmp/.X11-unix ro,nosuid,nodev - tmpfs tmpfs rw\n'
        with patch.object(repair.os,'readlink',side_effect=self.namespace),patch.object(Path,'read_text',return_value=mount),\
                patch.object(Path,'stat',return_value=SimpleNamespace(st_dev=1,st_ino=2)):
            proof=n.restart(111,True)
        self.assertTrue(proof['read_only_X11_bind'])
        self.assertEqual(n.run.call_args_list[0].args[0],['/usr/bin/systemctl','restart',repair.UNIT_NAME])
        self.assertEqual(len(n.run.call_args_list),3)
        self.assertFalse(any('mani-vmlab' in str(call.args[0]) or 'qwen' in str(call.args[0]) for call in n.run.call_args_list))

    def test_writable_missing_or_reused_namespace_proof_is_refused(self):
        for mount in ('','25 22 1:2 / /tmp/.X11-unix rw - tmpfs tmpfs rw\n'):
            n=self.native()
            with patch.object(repair.os,'readlink',side_effect=self.namespace),patch.object(Path,'read_text',return_value=mount):
                with self.subTest(mount=mount),self.assertRaisesRegex(RuntimeError,'read_only_X11_bind'):n.restart(111,True)
        n=self.native();n.run.side_effect=None;n.run.return_value=b'no\n'
        with self.assertRaisesRegex(RuntimeError,'PrivateTmp'):n.restart(111,True)

    def test_rollback_proof_rejects_a_bind_left_active(self):
        n=self.native()
        with patch.object(repair.os,'readlink',side_effect=self.namespace),\
                patch.object(Path,'read_text',return_value='25 22 1:2 / /tmp/.X11-unix ro - tmpfs tmpfs rw\n'):
            with self.assertRaisesRegex(RuntimeError,'original_unit_must_not_keep'):n.restart(111,False)

    def test_runtime_observation_requires_real_mountinfo_and_stable_exact_app_pid(self):
        n=self.native()
        with patch.object(Path,'read_text',return_value='25 22 1:2 / /tmp/.X11-unix ro - tmpfs tmpfs rw\n'):
            self.assertEqual(n.runtime_state(),{'app_pid':222,'X11_bind_present':True})
        with patch.object(Path,'read_text',return_value=''):
            with self.assertRaisesRegex(RuntimeError,'actual_app_mountinfo'):n.runtime_state()
        n.service_pid.side_effect=[222,333]
        with patch.object(Path,'read_text',return_value='25 22 1:2 / / rw - tmpfs tmpfs rw\n'):
            with self.assertRaisesRegex(RuntimeError,'app_changed_during_runtime_mount'):n.runtime_state()


if __name__=='__main__':unittest.main()
