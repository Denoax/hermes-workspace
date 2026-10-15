"""Hermetic guest-receipt races; never call native services or execute code."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from workspace.catalog import Catalog
from workspace.jobs import Jobs
from workspace.permissions import Permissions, PRESETS


class JobPolling(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.c=Catalog(Path(self.temp.name)/'catalog')
        self.addCleanup(self.c.db.close)
        self.project=self.c.create('Owned polling fixture')['id']
        self.session=self.c.session(self.project,'normal')['id']
        self.job=uuid.uuid4().hex
        self.jobs=Jobs(self.c)
        self.old={'id':self.job,'state':'starting','snapshot':[{'path':'input.txt','text':'admitted fixture'}]}
        with self.c.db:
            self.c.db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(self.job,self.session,'starting',json.dumps(self.old)))

    def receipt(self,state='review_ready',sequence=2):
        text='print("review fixture")\n'
        return {'status':'ok','id':self.job,'session_id':self.session,'project_id':self.project,'state':state,
                'evidence_kind':'actual_guest_Hermes_workspace_job','answer':'Labelled guest answer',
                'files':[{'path':'program.py','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}],
                'tool_events':[{'tool':'read_file','wall_seconds':0.001,'result':{'fixture':True}}],
                'events':[{'sequence':index,'detail':'Fixture event '+str(index)} for index in range(1,sequence+1)]}

    def worker(self,operation,outcomes,errors):
        def run():
            try:outcomes.append(operation())
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=run)
        thread.start()
        return thread

    def test_stalled_poll_allows_cancel_and_revocation(self):
        started=threading.Event();release=threading.Event();cancelled=threading.Event();revoked=threading.Event()
        errors=[];outcomes=[]
        policy=Permissions(self.c)
        current=policy.read(self.session)
        policy.update(self.session,current['version'],'workspace_agent',dict(PRESETS['workspace_agent']))
        def native(operation,**_fields):
            if operation=='workspace_read':
                started.set()
                if not release.wait(3):raise RuntimeError('fixture_poll_deadline')
                return {**self.receipt('cancelled'),'files':[],'evidence_kind':'cancelled_fixture'}
            self.assertEqual(operation,'workspace_cancel')
            cancelled.set()
            return {'status':'ok','state':'cancelling'}
        def revoke():
            policy.revoke(self.session)
            revoked.set()
        with patch('workspace.jobs.NativeClient.available',return_value=True),patch('workspace.jobs.NativeClient.call',side_effect=native):
            poll=self.worker(lambda:self.jobs.read(self.job),outcomes,errors)
            self.assertTrue(started.wait(2),'native poll did not start')
            cancel=self.worker(lambda:self.jobs.call('job.cancel',{'job_id':self.job}),outcomes,errors)
            revoke_thread=self.worker(revoke,outcomes,errors)
            try:
                self.assertTrue(cancelled.wait(1),'Stop blocked behind native poll')
                self.assertTrue(revoked.wait(1),'Revoke blocked behind native poll')
            finally:
                release.set()
                for thread in (poll,cancel,revoke_thread):thread.join(4)
        self.assertEqual(errors,[])
        self.assertEqual(policy.read(self.session)['mode'],'chat_only')

    def test_simultaneous_polls_share_one_export_and_event_cursor(self):
        barrier=threading.Barrier(2)
        errors=[];outcomes=[]
        def native(*_args,**_fields):
            barrier.wait(timeout=2)
            return self.receipt()
        with patch('workspace.jobs.NativeClient.available',return_value=True),patch('workspace.jobs.NativeClient.call',side_effect=native):
            threads=[self.worker(lambda:self.jobs.read(self.job),outcomes,errors) for _ in range(2)]
            for thread in threads:thread.join(4)
        self.assertEqual(errors,[])
        self.assertEqual(len(outcomes),2)
        self.assertTrue(all(item['exported'] for item in outcomes))
        history=self.c.history(self.session)
        self.assertEqual([item['text'] for item in history if item['role']=='assistant'],['Labelled guest answer'])
        self.assertEqual(len([item for item in history if item['role']=='event']),3)
        _,stored=self.jobs.local(self.job)
        self.assertEqual(stored['last_sequence'],2)
        self.assertEqual(stored['snapshot'],self.old['snapshot'])
        artifact=self.c.root/'projects'/self.project/'outputs'/self.job/'program.py'
        self.assertEqual(artifact.read_text(),self.receipt()['files'][0]['text'])
        self.assertEqual(artifact.stat().st_mode&0o777,0o400)

    def test_older_concurrent_reply_cannot_regress_final_state_or_cursor(self):
        started=threading.Event();release=threading.Event();errors=[];outcomes=[]
        count=[0];count_lock=threading.Lock()
        def native(*_args,**_fields):
            with count_lock:
                count[0]+=1
                first=count[0]==1
            if first:
                started.set()
                if not release.wait(3):raise RuntimeError('fixture_poll_deadline')
                return {**self.receipt('running',1),'evidence_kind':'in_progress_fixture','files':[]}
            return self.receipt()
        with patch('workspace.jobs.NativeClient.available',return_value=True),patch('workspace.jobs.NativeClient.call',side_effect=native):
            older=self.worker(lambda:self.jobs.read(self.job),outcomes,errors)
            self.assertTrue(started.wait(2),'first poll did not start')
            try:self.assertEqual(self.jobs.read(self.job)['state'],'review_ready')
            finally:release.set();older.join(4)
        self.assertEqual(errors,[])
        self.assertEqual(outcomes[0]['state'],'review_ready')
        _,stored=self.jobs.local(self.job)
        self.assertEqual((stored['state'],stored['last_sequence']),('review_ready',2))
        self.assertEqual(len([item for item in self.c.history(self.session) if item['role']=='assistant']),1)

    def test_failed_cursor_commit_rolls_back_history_and_retry_reuses_verified_export(self):
        import sqlite3
        with self.c.db:
            self.c.db.execute("CREATE TRIGGER fixture_abort BEFORE UPDATE ON jobs BEGIN SELECT RAISE(ABORT,'fixture commit failure'); END")
        with patch('workspace.jobs.NativeClient.available',return_value=True),patch('workspace.jobs.NativeClient.call',side_effect=lambda *_args,**_fields:self.receipt()):
            with self.assertRaises(sqlite3.IntegrityError):self.jobs.read(self.job)
            self.assertEqual(self.c.history(self.session),[])
            self.assertNotIn('exported',self.jobs.local(self.job)[1])
            with self.c.db:self.c.db.execute('DROP TRIGGER fixture_abort')
            self.assertTrue(self.jobs.read(self.job)['exported'])
        history=self.c.history(self.session)
        self.assertEqual(len([item for item in history if item['role']=='assistant']),1)
        self.assertEqual(len([item for item in history if item['role']=='event']),3)

    def test_deleted_or_moved_scope_during_poll_cannot_publish_foreign_exports(self):
        for change in ('conversation_deleted','project_deleted','conversation_moved'):
            with self.subTest(change=change):
                self.setUp_scope_for_race()
                started=threading.Event();release=threading.Event();errors=[];outcomes=[]
                def native(*_args,**_fields):
                    started.set()
                    if not release.wait(3):raise RuntimeError('fixture_poll_deadline')
                    return self.receipt()
                with patch('workspace.jobs.NativeClient.available',return_value=True),patch('workspace.jobs.NativeClient.call',side_effect=native):
                    poll=self.worker(lambda:self.jobs.read(self.job),outcomes,errors)
                    self.assertTrue(started.wait(2),'native poll did not start')
                    try:
                        with self.c.lock,self.c.db:
                            if change=='conversation_deleted':
                                self.c.db.execute('DELETE FROM jobs WHERE id=?',(self.job,))
                                self.c.db.execute('DELETE FROM sessions WHERE id=?',(self.session,))
                            elif change=='project_deleted':self.c.db.execute('DELETE FROM projects WHERE id=?',(self.project,))
                            else:self.c.db.execute("UPDATE sessions SET project='' WHERE id=?",(self.session,))
                    finally:release.set();poll.join(4)
                self.assertEqual(outcomes,[])
                self.assertEqual(len(errors),1)
                self.assertIsInstance(errors[0],ValueError)
                self.assertFalse((self.c.root/'projects'/self.project/'outputs'/self.job).exists())

    def setUp_scope_for_race(self):
        self.project=self.c.create('Fresh race scope')['id']
        self.session=self.c.session(self.project,'normal')['id']
        self.job=uuid.uuid4().hex
        with self.c.lock,self.c.db:
            self.c.db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(self.job,self.session,'starting',json.dumps({'id':self.job,'state':'starting'})))


if __name__=='__main__':
    unittest.main()
