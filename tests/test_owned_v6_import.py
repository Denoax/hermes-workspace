"""Hermetic import-entry, immutable-source and presentation-preservation guards."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from scripts import owned_action_review as actions
from scripts import owned_v6_import as imports
from scripts import probe_v6_import as runner


class ImportEntry(unittest.TestCase):
    def review(self,dashboard):
        obj = actions.OwnedActionReview.__new__(actions.OwnedActionReview)
        obj.b = Mock()
        obj.b.evaluate.return_value = dashboard
        obj.button = Mock();obj.require_native = Mock()
        return obj

    def test_existing_v5_dashboard_path_stays_unchanged(self):
        obj = self.review(True);obj.open_import_surface()
        obj.require_native.assert_called_once()
        obj.button.assert_called_once_with('Import folder',"document.querySelector('.dashboard-actions')")
        obj.b.click.assert_not_called()
        obj.b.wait.assert_called_once()

    def test_v6_conversation_uses_real_composer_plus_menu(self):
        obj = self.review(False);obj.open_import_surface()
        obj.b.click.assert_called_once_with('#plus-menu')
        obj.button.assert_called_once_with('Import folder',"document.querySelector('#composer-actions')")
        obj.b.wait.assert_called_once()

    def test_unqualified_native_input_cannot_open_either_route(self):
        obj = self.review(False);obj.require_native.side_effect = RuntimeError('native not qualified')
        with self.assertRaises(RuntimeError):obj.open_import_surface()
        obj.b.click.assert_not_called();obj.button.assert_not_called()


class SourceGuard(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in runner.SOURCES:
            p = self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
        self.plan = {'version':1,'sources':runner.source_snapshot(self.root)}

    def test_exact_reconciled_source_is_accepted_before_any_production_import(self):
        self.assertEqual(runner.guard_source(self.root,self.plan),self.plan['sources'])

    def test_later_source_edit_is_refused_without_rebuilding_approved_map(self):
        (self.root/runner.SOURCES[0]).write_text('later edit')
        with self.assertRaisesRegex(RuntimeError,'source_changed_before_execution'):
            runner.guard_source(self.root,self.plan)

    def test_unlisted_or_missing_scope_and_invalid_hashes_are_refused(self):
        for changed in [{'version':2,'sources':self.plan['sources']},
                        {'version':1,'sources':{**self.plan['sources'],'unknown.py':'a'*64}},
                        {'version':1,'sources':{}},
                        {'version':1,'sources':{**self.plan['sources'],runner.SOURCES[0]:'not a hash'}}]:
            with self.subTest(changed=str(changed)[:40]),self.assertRaises(RuntimeError):
                runner.guard_source(self.root,changed)

    def test_source_symlink_and_hardlink_are_not_followed(self):
        p = self.root/runner.SOURCES[0]
        p.unlink();p.symlink_to(self.root/runner.SOURCES[1])
        with self.assertRaisesRegex(RuntimeError,'source_symlink_refused'):runner.source_snapshot(self.root)
        p.unlink();os.link(self.root/runner.SOURCES[1],p)
        with self.assertRaisesRegex(RuntimeError,'owned_regular_import_source_required'):runner.source_snapshot(self.root)

    def test_missing_execute_flag_stops_before_source_or_pin_access(self):
        args=['probe','--output','/not/used','--private-recovery','/not/used','--fixture-parent','/not/used',
              '--navigation','/not/used','--navigation-sha256','a'*64,'--expected-source-map','/not/used']
        with patch.object(sys,'argv',args),patch.object(runner,'guard_source') as guard,patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:runner.main()
        self.assertEqual(error.exception.code,2);guard.assert_not_called()


class BaseWindowSetup(unittest.TestCase):
    def fixture(self, *, outside=False):
        from workspace import launcher
        state = {'client': {'address':'0xabcd','pid':2468,'class':'HermesWorkspace','floating':True,
                            'xwayland':True,'fullscreen':0,'monitor':1,
                            'at':[2841 if outside else 2220,120],'size':[1320,900]}}
        monitor = {'id':1,'x':1920,'y':0,'width':1920,'height':1080,'scale':1,'reserved':[0,0,0,0]}
        def read_json(*arguments):
            if arguments == ('/usr/bin/hyprctl','clients','-j'):
                return copy.deepcopy(state.get('clients', [state['client']]))
            if arguments == ('/usr/bin/hyprctl','monitors','-j'):
                return [copy.deepcopy(monitor)]
            raise AssertionError('Unexpected desktop command')
        fake = Mock()
        fake.owns_browser.side_effect = lambda pid: pid in (2468,2469)
        fake.monitor_work_area = launcher.monitor_work_area
        fake.surface_inside_monitor = launcher.surface_inside_monitor
        return state,read_json,fake

    def test_unknown_ambiguous_or_nonstandard_window_never_gets_placement(self):
        for change in ({'pid':1234},{'address':'untrusted'},{'floating':False},
                       {'fullscreen':1},{'xwayland':False},{'class':'kdialog'}):
            with self.subTest(change=change):
                state,read,fake=self.fixture(outside=True);state['client'].update(change)
                with self.assertRaises(RuntimeError):
                    runner.setup_base_window(Mock(),fake,{},read_json=read)
                fake.position_browser_window.assert_not_called()
        state,read,fake=self.fixture(outside=True)
        state['clients']=[state['client'],copy.deepcopy(state['client'])]
        with self.assertRaisesRegex(RuntimeError,'unique_owned_base_window_required'):
            runner.setup_base_window(Mock(),fake,{},read_json=read)
        fake.position_browser_window.assert_not_called()

    def test_inside_window_is_reread_without_resize_or_placement(self):
        state,read,fake=self.fixture();record={}
        identity=runner.setup_base_window(Mock(),fake,record,read_json=read)
        self.assertEqual(identity,{'address':'0xabcd','pid':2468})
        self.assertFalse(record['applied']);self.assertEqual(record['status'],'PASS')
        self.assertEqual(record['before'],record['after'])
        self.assertFalse(record['chooser_focus_or_float_applied'])
        fake.position_browser_window.assert_not_called()

    def test_outside_base_window_uses_existing_setup_once_then_fresh_same_identity_fit(self):
        state,read,fake=self.fixture(outside=True);browser=Mock();record={}
        def center(pipe,target,client):
            self.assertIs(pipe,browser.pipe);self.assertIs(target,browser.target)
            self.assertEqual(client['address'],'0xabcd');state['client']['at']=[2220,120]
        fake.position_browser_window.side_effect=center
        identity=runner.setup_base_window(browser,fake,record,read_json=read)
        fake.position_browser_window.assert_called_once()
        self.assertTrue(record['applied']);self.assertFalse(record['before']['fully_inside_monitor'])
        self.assertTrue(record['after']['fully_inside_monitor'])
        _,fresh=runner.owned_base_window(fake,expected=identity,read_json=read)
        self.assertTrue(fresh['fully_inside_monitor'])
        state['client']['pid']=2469
        with self.assertRaisesRegex(RuntimeError,'base_window_identity_changed'):
            runner.owned_base_window(fake,expected=identity,read_json=read)
        fake.position_browser_window.assert_called_once()

    def test_persistent_outside_state_fails_without_retry_and_keeps_evidence(self):
        state,read,fake=self.fixture(outside=True);record={}
        with self.assertRaisesRegex(RuntimeError,'base_window_still_outside_after_setup'):
            runner.setup_base_window(Mock(),fake,record,read_json=read)
        fake.position_browser_window.assert_called_once()
        self.assertTrue(record['applied']);self.assertEqual(record['status'],'IN_PROGRESS')
        self.assertFalse(record['before']['fully_inside_monitor'])
        self.assertFalse(record['after']['fully_inside_monitor'])


class ImportRestoration(unittest.TestCase):
    def fixture(self):
        obj = imports.OwnedImportReview.__new__(imports.OwnedImportReview)
        project,sid,original_sid = 'a'*32,'b'*32,'c'*32
        obj.case = {'version':1,'kind':'v6_fresh_import_only','nonce':'V5review-1234abcd-actions-5678abcd',
                    'import_project_id':project,'import_session':sid,'created_session_ids':[sid]}
        obj.original_view = {'project_id':'d'*32,'session_id':original_sid,'arm':'normal'}
        obj.original_draft = {'text':'original saved user draft','mode':'chat'}
        obj.original_filter = '';obj.original_scroll = 42
        obj.original_storage = {'hermes-ui:sounds':'on','hermes-ui:interface-volume':'12',
                                'hermes:new-draft':None,imports.NEW_SELECTION:None,imports.INTENT:None}
        state = {'view':{'project_id':project,'session_id':sid,'arm':'normal'},'draft':{'text':'','mode':'chat'},
                 'original_draft':dict(obj.original_draft),'snapshot':{'messages':[],'runs':[]},'jobs':[],
                 'selection':None,'storage':{**obj.original_storage,imports.INTENT:json.dumps({'version':1,'project_id':project})},
                 'writes':[],'CAS':[],'prompt_empty':True}
        def rpc(method,fields=None):
            if method=='view.read':return copy.deepcopy(state['view'])
            if method=='view.write':state['writes'].append(fields);state['view']=dict(fields['state']);return state['view']
            if method=='session.list':return [{'id':sid,'project':project,'title':obj.case['nonce']+' · Import preview'}]
            if method=='draft.read':return copy.deepcopy(state['draft'] if fields['session_id']==sid else state['original_draft'])
            if method=='chat.snapshot':return copy.deepcopy(state['snapshot'])
            if method=='session.jobs':return list(state['jobs'])
            raise AssertionError('Unexpected RPC mutation: '+method)
        def evaluate(script):
            if script=='globalThis.__ownedImportObserver?.cleanup()':return None
            if script.startswith('localStorage.getItem('):return state['selection']
            if "document.querySelector('#prompt').value===''" in script:return state['prompt_empty']
            if script.startswith("document.querySelector('.conversation').scrollTop="):return None
            if script=="document.querySelector('.rail-search input').value":return obj.original_filter
            raise AssertionError('Unexpected browser mutation: '+script[:80])
        obj.b=Mock();obj.b.evaluate.side_effect=evaluate
        obj.rpc=rpc;obj._storage=lambda:copy.deepcopy(state['storage'])
        def cas(changes):
            for key,item in changes.items():
                if state['storage'][key]!=item['expected']:raise RuntimeError('concurrent storage')
            state['CAS'].append(changes)
            for key,item in changes.items():state['storage'][key]=item['value']
        obj._restore_storage=cas;obj.reload_ready=Mock();obj.report={'checks':{}};obj.save=Mock()
        return obj,state

    def restore(self,obj):
        with patch('scripts.probe_v4_visual.close_panels'),patch('scripts.probe_v4_visual.input_text'):
            obj.restore()

    def test_only_known_owned_composing_bookkeeping_is_restored(self):
        obj,state=self.fixture();self.restore(obj)
        self.assertEqual(state['view'],obj.original_view)
        self.assertEqual(state['storage'],obj.original_storage)
        self.assertEqual(state['original_draft'],obj.original_draft)
        self.assertTrue(obj.report['checks']['original_view_draft_attachments_sound_and_composing_intent_preserved'])
        self.assertEqual(len(state['writes']),1)

    def test_unexpected_view_does_not_trigger_any_restoration_write(self):
        obj,state=self.fixture();state['view']['session_id']='f'*32
        with self.assertRaisesRegex(RuntimeError,'unexpected_user_view_preserved'):self.restore(obj)
        self.assertEqual(state['writes'],[]);self.assertEqual(state['CAS'],[])

    def test_new_user_content_on_import_record_is_preserved_without_restore(self):
        for key,value in [('draft',{'text':'new user text','mode':'chat'}),('snapshot',{'messages':[{}],'runs':[]}),
                          ('selection',json.dumps({'version':1,'ids':['f'*32]})),('prompt_empty',False)]:
            with self.subTest(key=key):
                obj,state=self.fixture();state[key]=value
                with self.assertRaises(RuntimeError):self.restore(obj)
                self.assertEqual(state['writes'],[]);self.assertEqual(state['CAS'],[])

    def test_later_original_draft_change_is_never_overwritten_or_hidden(self):
        obj,state=self.fixture();state['original_draft']={'text':'later user draft','mode':'chat'}
        with self.assertRaisesRegex(RuntimeError,'new_original_user_draft_preserved'):self.restore(obj)
        self.assertEqual(state['writes'],[]);self.assertEqual(state['CAS'],[])

    def test_unowned_composing_scope_and_sound_change_block_restore(self):
        for key,value in [(imports.INTENT,json.dumps({'version':1,'project_id':'f'*32})),
                          ('hermes-ui:sounds','off'),('hermes:new-draft','new user text')]:
            with self.subTest(key=key):
                obj,state=self.fixture();state['storage'][key]=value
                with self.assertRaises(RuntimeError):self.restore(obj)
                self.assertEqual(state['writes'],[]);self.assertEqual(state['CAS'],[])

    def test_import_view_requires_both_created_record_and_project(self):
        obj,state=self.fixture()
        self.assertTrue(imports.allowed_import_view(obj.case,state['view'],obj.original_view))
        for view in [{**state['view'],'project_id':'f'*32},{**state['view'],'arm':'abliterated'},
                     {**state['view'],'session_id':None}]:
            self.assertFalse(imports.allowed_import_view(obj.case,view,obj.original_view))
        self.assertFalse(imports.allowed_import_view({**obj.case,'created_session_ids':[]},state['view'],obj.original_view))




class SinglePassQualification(unittest.TestCase):
    def fixture(self, status='PASS_POINTS_ONLY'):
        browser = Mock()
        browser.rect.return_value = {'x': 100, 'y': 20, 'width': 50, 'height': 30}
        client = {'address': '0xabcd', 'pid': 2345}
        points = {'status': status, 'mapping': [1, 1, 300, 90]}
        return browser, client, points

    def run_fixture(self, browser, client, points):
        from scripts import probe_v4_visual as visual, v6_zoom_restore as zoom, v6_surface_review as surface
        with patch.object(zoom,'active_owned',return_value=client), \
             patch.object(zoom,'command',return_value={'x':10,'y':10}), \
             patch.object(zoom,'qualify_points_once',return_value=points) as qualify, \
             patch.object(visual,'NativeX11Input'), patch.object(visual,'enable_native_input'), \
             patch.object(surface,'require_owned_native_focus'):
            result = runner.qualify_native_pointer(browser,client)
            qualify.assert_called_once()
            return result

    def test_single_pass_still_requires_actual_Settings_activation_and_Escape(self):
        browser, client, points = self.fixture()
        result = self.run_fixture(browser, client, points)
        self.assertEqual(result['status'],'PASS')
        browser.click.assert_called_once_with('#settings-toggle')
        browser.key.assert_called_once_with('Escape')
        self.assertTrue(result['native_mouse_open_and_Escape_close'])

    def test_failed_point_pass_sends_no_click_or_key(self):
        browser, client, points = self.fixture('FAIL_SETTINGS_POINT')
        with self.assertRaisesRegex(RuntimeError,'single_pass_native_points_not_qualified'):
            self.run_fixture(browser, client, points)
        browser.click.assert_not_called();browser.key.assert_not_called()

    def test_Settings_trigger_drift_remains_a_failure(self):
        browser, client, points = self.fixture()
        browser.rect.side_effect = [{'x':100,'y':20,'width':50,'height':30},
                                    {'x':101,'y':20,'width':50,'height':30}]
        with self.assertRaisesRegex(RuntimeError,'native_click_shifted_trigger'):
            self.run_fixture(browser, client, points)


if __name__=='__main__':unittest.main()
