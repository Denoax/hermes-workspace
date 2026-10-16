"""Hermetic request-failure and exact-case resume guards; no GUI/native actions."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / 'scripts')]
from scripts import owned_action_review as actions
from scripts import owned_v6_import as imports
from scripts import unassisted_native_picker as private_picker
from workspace.desktop import _PICKER_ERRORS

spec = importlib.util.spec_from_file_location('existing_chooser_fixtures', BASE / 'tests/test_unassisted_native_picker.py')
chooser_fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chooser_fixtures)
chooser_fixtures.picker=private_picker

NONCE='V5review-9bf13fce-actions-684a7ff3'
PREFIX='V5review-9bf13fce'


def prior_receipt():
    return {'status':'PARTIAL','case':{'nonce':NONCE,'created_session_ids':['a'*32],
        'version':1,'kind':'v6_fresh_import_only','import_project_id':'b'*32,'import_session':'a'*32},
        'checks':{'folder_real_hover_click_keyboard_reverse':True}}


class RequestFailure(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.recovery=Path(self.tmp.name)/'private-state/recovery'
        self.browser=Mock()

    def observed(self, responses, alert='only private alert'):
        self.browser.evaluate.return_value={'responses':responses,'ui_alert':alert,'ui_alert_unoccluded':False}

    def test_known_actual_error_is_classified_and_preserved_only_privately(self):
        self.observed([{'status':409,'error':_PICKER_ERRORS['parent_unavailable'],'result':None}])
        result=imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker')
        self.assertEqual(result['classification'],'parent_unavailable')
        self.assertEqual(result['HTTP_status'],409)
        self.assertNotIn(_PICKER_ERRORS['parent_unavailable'],json.dumps(result))
        files=list(self.recovery.iterdir());self.assertEqual(len(files),1)
        self.assertEqual(files[0].stat().st_mode&0o777,0o600)
        self.assertEqual(self.recovery.stat().st_mode&0o777,0o700)
        saved=json.loads(files[0].read_text())
        self.assertEqual(saved['response']['error'],_PICKER_ERRORS['parent_unavailable'])
        self.assertFalse(saved['ui_alert_unoccluded'])
        self.assertEqual(saved['ui_alert'],'only private alert')

    def test_unknown_exception_text_never_becomes_a_public_category_or_field(self):
        private='unexpected /home/someone/private-document'
        self.observed([{'status':409,'error':private,'result':None}],private)
        result=imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker')
        self.assertEqual(result['classification'],'unclassified_backend_error')
        self.assertNotIn(private,json.dumps(result))
        self.assertIn(private,next(self.recovery.iterdir()).read_text())

    def test_pending_response_keeps_waiting_without_private_artifact(self):
        self.observed([])
        self.assertIsNone(imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker'))
        self.assertFalse(self.recovery.exists())

    def test_previous_phase_cancel_does_not_abort_the_next_pending_chooser(self):
        self.observed([{'status':200,'error':None,'result':{'cancelled':True}}])
        self.assertIsNone(imports.picker_request_outcome(self.browser,self.recovery,'preview_cancel'))
        self.assertIsNone(imports.picker_request_outcome(self.browser,self.recovery,'commit'))
        self.assertFalse(self.recovery.exists())

    def test_second_phase_uses_its_own_reply_instead_of_prior_cancel(self):
        self.observed([{'status':200,'error':None,'result':{'cancelled':True}},
                       {'status':409,'error':_PICKER_ERRORS['dialog_failed'],'result':None}])
        result=imports.picker_request_outcome(self.browser,self.recovery,'preview_cancel')
        self.assertEqual(result['classification'],'dialog_failed')

    def test_unobserved_cancel_has_explicit_limited_classification(self):
        self.observed([{'status':200,'error':None,'result':{'cancelled':True}}])
        result=imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker')
        self.assertEqual(result['classification'],'cancelled_before_chooser_observed')

    def test_public_or_symlink_recovery_and_malformed_response_are_refused(self):
        self.observed([{'status':409,'error':'unknown','result':None}])
        with self.assertRaisesRegex(RuntimeError,'private_error_recovery_required'):
            imports.picker_request_outcome(self.browser,Path(self.tmp.name)/'review','cancel_picker')
        self.recovery.parent.mkdir(mode=0o700)
        self.recovery.symlink_to(Path(self.tmp.name),target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,'private_error_recovery_required'):
            imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker')
        self.recovery.unlink();self.recovery.mkdir(mode=0o755)
        with self.assertRaisesRegex(RuntimeError,'owner_only'):
            imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker')
        self.browser.evaluate.return_value={'responses':[{'status':True}]}
        with self.assertRaisesRegex(RuntimeError,'HTTP_status'):
            imports.picker_request_outcome(self.browser,self.recovery,'cancel_picker')


class ExactResume(unittest.TestCase):
    def test_exact_uncommitted_receipt_can_resume_without_aliasing(self):
        prior=prior_receipt();case=imports.resumed_import_case(prior,PREFIX)
        self.assertEqual(case,prior['case'])
        case['created_session_ids'].append('c'*32)
        self.assertEqual(prior['case']['created_session_ids'],['a'*32])

    def test_wrong_scope_or_already_copied_receipt_cannot_resume(self):
        mutations=[lambda r:r['case'].update(kind='other'),
            lambda r:r['case'].update(nonce='V5review-00000000-actions-684a7ff3'),
            lambda r:r['case'].update(project_id='c'*32),
            lambda r:r['case'].update(created_session_ids=['d'*32]),
            lambda r:r['case'].update(import_session='../private'),
            lambda r:r.update(status='PASS_SCOPED_TECHNICAL'),
            lambda r:r['checks'].update(folder_real_hover_click_keyboard_reverse=False),
            lambda r:r['checks'].update(real_picker_preview_cancel_commit_copy_and_original_unchanged={'files':['README.md']})]
        for mutate in mutations:
            prior=prior_receipt();mutate(prior)
            with self.subTest(prior=prior),self.assertRaises(RuntimeError):imports.resumed_import_case(prior,PREFIX)

    def test_fixture_reuse_checks_existing_exact_bytes_and_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary);original=actions.make_import_fixture(parent,NONCE)
            resumed=imports.existing_import_fixture(parent,NONCE)
            self.assertEqual(resumed,original)
            (Path(original['root'])/'README.md').write_text('later user edits')
            with self.assertRaisesRegex(RuntimeError,'fixture_bytes_changed'):
                imports.existing_import_fixture(parent,NONCE)

    def test_fixture_symlink_or_extra_file_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary);original=actions.make_import_fixture(parent,NONCE)
            root=Path(original['root']);(root/'extra.txt').write_text('new content')
            with self.assertRaisesRegex(RuntimeError,'inventory_changed'):imports.existing_import_fixture(parent,NONCE)
            (root/'extra.txt').unlink();saved=parent/'saved';root.rename(saved);root.symlink_to(saved,target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError,'existing_exact_owned_fixture'):imports.existing_import_fixture(parent,NONCE)

    def test_new_job_in_original_import_case_blocks_before_view_write_or_native_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture=actions.make_import_fixture(Path(temporary),NONCE)
            obj=actions.OwnedActionReview.__new__(actions.OwnedActionReview)
            obj.case=prior_receipt()['case'];obj.b=Mock();obj.original_view={};writes=[]
            def rpc(method,fields=None):
                if method=='workspace.list':return [{'id':'b'*32,'label':NONCE+' · Import case'}]
                if method=='session.list':return [{'id':'a'*32,'project':'b'*32,'title':NONCE+' · Import preview'}]
                if method=='workspace.files':return {'files':[]}
                if method=='chat.snapshot':return {'runs':[],'messages':[]}
                if method=='draft.read':return {'text':'','mode':'chat'}
                if method=='session.jobs':return [{'id':'later-user-job'}]
                writes.append(method);raise AssertionError('Unexpected mutation')
            obj.rpc=rpc;picker=Mock()
            with self.assertRaisesRegex(RuntimeError,'import_case_acquired_content'):
                obj.import_motion(Mock(segment=Mock()),fixture,picker,Mock(),stop_after_cancel=True)
            self.assertEqual(writes,[]);picker.assert_not_called();obj.b.click.assert_not_called()


class PromptFailureStopsWait(unittest.TestCase):
    def fixture(self):return chooser_fixtures.UnassistedChooser().fixture()

    def test_completed_failure_stops_before_sleep_or_any_targeted_input(self):
        driver,state,*_=self.fixture();state['clients']=[]
        outcome={'HTTP_status':409,'classification':'parent_unavailable'}
        driver.request_observer=Mock(return_value=outcome)
        with self.assertRaisesRegex(RuntimeError,'request_completed_before_observed_chooser'):
            driver('cancel_picker','/tmp/owned-source')
        self.assertEqual(state['clock'],0);self.assertEqual(state['dispatches'],[])
        self.assertEqual(driver.last_failure['request_outcome'],outcome)
        self.assertEqual(driver.last_failure['targeted_shortcuts'],0)

    def test_pending_response_still_uses_original_bounded_wait(self):
        driver,state,*_=self.fixture();state['clients']=[]
        driver.request_observer=Mock(return_value=None)
        with self.assertRaisesRegex(TimeoutError,'actual_native_chooser_not_observed'):
            driver('cancel_picker','/tmp/owned-source')
        self.assertLessEqual(state['clock'],25.2);self.assertEqual(state['dispatches'],[])

    def test_actual_chooser_is_verified_before_any_completed_reply_diagnostic(self):
        driver,state,*_=self.fixture();driver.request_observer=Mock(side_effect=AssertionError('Must not read stale reply'))
        result=driver('cancel_picker','/tmp/owned-source')
        self.assertTrue(result['unassisted_parenting']['verified_transient_parent'])
        driver.request_observer.assert_not_called()


if __name__=='__main__':unittest.main()
