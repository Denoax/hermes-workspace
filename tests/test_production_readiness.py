"""Hermetic admission regression checks; these are not production model trials."""
import stat
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from workspace.catalog import Catalog
from workspace.chat import Chat
from workspace.readiness import AdmissionUnavailable, Readiness, control_metadata
from workspace.server import Application


class ReadinessTests(unittest.TestCase):
    def metadata(self, uid=0):
        path=Mock()
        path.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFSOCK|0o660,st_uid=uid)
        path.parent.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFDIR|0o755,st_uid=uid)
        return patch('workspace.readiness.CONTROL',path)

    def test_unmapped_root_is_rejected_without_peer_connection(self):
        client=Mock()
        with self.metadata(65534):
            result=Readiness(client_factory=lambda:client).read()
        self.assertEqual(result['state'],'repair_required')
        self.assertEqual(result['control']['code'],'root_identity_not_visible')
        client.call.assert_not_called()

    def test_metadata_alone_cannot_claim_root_attested_readiness(self):
        client=Mock();client.call.side_effect=PermissionError('peer_not_root')
        with self.metadata():
            result=Readiness(client_factory=lambda:client).read()
        self.assertTrue(result['control']['trusted'])
        self.assertFalse(result['admission']['available'])
        self.assertEqual(result['state'],'repair_required')

    def test_safe_probe_never_requests_model_load_and_recovers_fresh(self):
        client=Mock();client.call.return_value={'status':'ok','observed_facts':{},'window_status':'closed'}
        with self.metadata():
            ready=Readiness(client_factory=lambda:client)
            self.assertEqual(ready.require()['state'],'ready')
            client.call.assert_called_once_with('status')
            client.call.side_effect=OSError('gone')
            with self.assertRaises(AdmissionUnavailable):ready.require()

    def test_active_window_is_busy_not_a_missing_installation(self):
        client=Mock();client.call.return_value={'status':'ok','observed_facts':{'inference_window_active':True},'window_status':'active'}
        with self.metadata():result=Readiness(client_factory=lambda:client).read()
        self.assertEqual(result['state'],'busy');self.assertTrue(result['control']['trusted'])
        with self.metadata(),self.assertRaises(AdmissionUnavailable):
            Readiness(client_factory=lambda:client).require()

    def test_candidate_requires_native_boot_proof_without_blocking_normal(self):
        client=Mock();client.call.return_value={'status':'ok','observed_facts':{'pinned_model_and_backend_artifacts_current':False},'window_status':'closed'}
        with self.metadata():result=Readiness(client_factory=lambda:client).require()
        self.assertEqual(result['state'],'ready')
        self.assertTrue(result['models']['normal']['available'])
        self.assertFalse(result['models']['abliterated']['available'])
        self.assertEqual(result['models']['abliterated']['code'],'native_artifact_verification_required')
        client.call.assert_called_once_with('status')

    def test_fresh_native_verification_enables_candidate_without_model_load(self):
        client=Mock();client.call.return_value={'status':'ok','observed_facts':{'pinned_model_and_backend_artifacts_current':True},'window_status':'closed'}
        with self.metadata():result=Readiness(client_factory=lambda:client).require()
        self.assertTrue(all(model['available'] for model in result['models'].values()))
        client.call.assert_called_once_with('status')

    def test_missing_socket_has_typed_failure(self):
        with patch('workspace.readiness.CONTROL') as path:
            path.lstat.side_effect=FileNotFoundError()
            self.assertEqual(control_metadata()['code'],'control_socket_missing')


class AdmissionAndPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.catalog=Catalog(Path(self.temp.name)/'catalog')
        self.session=self.catalog.session(None,'normal')['id']
    def tearDown(self):self.catalog.db.close();self.temp.cleanup()

    def test_failed_readiness_creates_no_user_bubble_or_run(self):
        def refuse():raise AdmissionUnavailable({'state':'repair_required'})
        inventory=Mock();chat=Chat(self.catalog,inventory=inventory,readiness_check=refuse)
        with self.assertRaises(AdmissionUnavailable):
            chat.submit({'request_id':uuid.uuid4().hex,'session_id':self.session,'model_id':'normal','prompt':'harmless fixture','reasoning':'off','attachments':[],'search_query':None})
        self.assertEqual(self.catalog.history(self.session),[])
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM chat_runs').fetchone()[0],0)

    def test_unverified_selected_candidate_creates_no_user_bubble_or_run(self):
        result={'state':'ready','admission':{'available':True,'code':'root_peer_attested'},
                'models':{'normal':{'available':True},'abliterated':{
                    'available':False,'code':'native_artifact_verification_required','detail':'Protected verification needed.'}}}
        chat=Chat(self.catalog,inventory=Mock(),readiness_check=lambda:result)
        self.assertIs(chat.require_readiness('normal'),result)
        with self.assertRaises(AdmissionUnavailable) as failure:
            chat.submit({'request_id':uuid.uuid4().hex,'session_id':self.session,'model_id':'abliterated','prompt':'harmless fixture','reasoning':'off','attachments':[],'search_query':None})
        self.assertEqual(failure.exception.readiness['model_id'],'abliterated')
        self.assertEqual(failure.exception.readiness['admission']['code'],'native_artifact_verification_required')
        self.assertEqual(result['state'],'ready')
        self.assertEqual(self.catalog.history(self.session),[])
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM chat_runs').fetchone()[0],0)

    def test_unverified_candidate_retry_preserves_original_failed_turn(self):
        result={'models':{'abliterated':{'available':False,'code':'native_artifact_verification_required','detail':'Protected verification needed.'}}}
        chat=Chat(self.catalog,inventory=Mock(),readiness_check=lambda:result)
        run,_=chat.store.admit(uuid.uuid4().hex,self.session,'abliterated','Original preserved message','off',[])
        chat.store.state(run['id'],'failed',error='Original failure')
        with self.assertRaises(AdmissionUnavailable):chat.retry(run['id'])
        preserved=chat.store.run(run['id'])
        self.assertEqual(preserved['state'],'failed')
        self.assertEqual(preserved['error'],'Original failure')
        self.assertEqual([item['text'] for item in self.catalog.history(self.session)],['Original preserved message'])
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM chat_retry_audit').fetchone()[0],0)

    def test_direct_legacy_routes_cannot_bypass_action_policy(self):
        app=Application(Path(self.temp.name)/'app')
        try:
            for method,fields in [('search.run',{'query':'fixture'}),('workspace.file.read',{'project_id':'a'*32,'relative_path':'note.txt'}),('workspace.file.write',{'project_id':'a'*32,'relative_path':'note.txt','text':'x','expected_sha256':None}),('patch.apply',{'review_ticket':'a'*32}),('job.submit',{'session_id':'a'*32,'client_job_id':'b'*32,'prompt':'x','snapshot_sha256':'0'*64,'task_kind':'python'})]:
                with self.subTest(method=method),self.assertRaisesRegex(PermissionError,'scoped_action_required'):app.call(method,fields)
            sid=app.catalog.session(None,'normal')['id']
            with self.assertRaisesRegex(PermissionError,'microphone'):app.call('recording.authorize',{'session_id':sid})
        finally:app.catalog.db.close()
