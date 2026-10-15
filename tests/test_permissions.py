"""Behavioral checks for policy, approval and real anchored workspace dispatch."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from workspace.actions import Actions, parse_model_tool
from workspace.catalog import Catalog
from workspace.permissions import Permissions, PRESETS


def uid():
    return uuid.uuid4().hex


class PermissionBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Catalog(Path(self.tmp.name)/'catalog')
        self.addCleanup(self.c.db.close)
        self.project = self.c.create('Preserved project')['id']
        self.session = self.c.session(self.project, 'normal')['id']
        self.other = self.c.session(self.project, 'normal')['id']
        self.now = [1000.0]
        self.p = Permissions(self.c, clock=lambda:self.now[0])
        self.a = Actions(self.c, self.p)
        self.fs = self.c.files(self.project)
        self.addCleanup(self.fs.close)
        self.base = self.fs.write('program.py', 'print("old")\n')['sha256']

    def mode(self, mode, **changes):
        caps = dict(PRESETS[mode] if mode != 'custom' else PRESETS['chat_only'])
        caps.update(changes)
        current = self.p.read(self.session)
        return self.p.update(self.session, current['version'], mode, caps)

    def request(self, action=None, session=None, run_id=None, request_id=None):
        return self.a.request(session or self.session, run_id, request_id or uid(), action or {'type':'workspace.read','path':'program.py'})

    def allow(self, action, decision='allow_once'):
        return self.p.decide(action['session_id'], action['id'], decision)

    def test_existing_conversation_defaults_chat_only_without_mutating_messages(self):
        self.c.message(self.session, 'user', 'keep this history')
        self.assertEqual(self.p.read(self.session)['mode'], 'chat_only')
        self.assertTrue(all(not x for x in self.p.read(self.session)['capabilities'].values()))
        self.assertEqual(self.c.history(self.session)[0]['text'], 'keep this history')
        action = self.request()
        self.assertEqual(action['state'], 'denied')
        with self.assertRaises(PermissionError):self.a.execute(self.session, action['id'])

    def test_operator_approval_required_then_real_anchored_read(self):
        self.mode('ask')
        action = self.request()
        self.assertEqual(action['state'], 'pending')
        with self.assertRaises(PermissionError):self.a.execute(self.session, action['id'])
        self.allow(action)
        result = self.a.execute(self.session, action['id'])
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['result']['text'], 'print("old")\n')

    def test_allow_once_is_atomic_and_replay_returns_stored_result(self):
        self.mode('ask')
        action = self.request({'type':'workspace.write','path':'program.py','text':'one effect\n','expected_sha256':self.base})
        self.allow(action)
        results = []
        threads = [threading.Thread(target=lambda:results.append(self.a.execute(self.session, action['id']))) for _ in range(3)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r['state'] == 'completed' for r in results))
        count = self.c.db.execute("SELECT COUNT(*) FROM permission_audit WHERE action_id=? AND event='executing'", (action['id'],)).fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(self.fs.read('program.py')['text'], 'one effect\n')

    def test_denial_persists_after_reconnect_and_new_request_id(self):
        self.mode('ask')
        first = self.request()
        self.p.decide(self.session, first['id'], 'deny')
        reconnected = Actions(self.c, Permissions(self.c, clock=lambda:self.now[0]))
        retry = reconnected.request(self.session, None, uid(), {'type':'workspace.read','path':'program.py'})
        self.assertEqual(retry['state'], 'denied')

    def test_denied_action_stays_denied_when_model_retry_uses_a_new_owned_run(self):
        self.mode('ask')
        runs = [uid(),uid()]
        for run in runs:
            self.c.db.execute('INSERT INTO chat_runs VALUES (?,?,?,?,?,?,NULL,NULL)', (run,self.session,'normal','running','{}',self.now[0]))
        self.c.db.commit()
        first = self.request(run_id=runs[0])
        self.p.decide(self.session,first['id'],'deny')
        self.assertEqual(self.request(run_id=runs[1])['state'],'denied')

    def test_narrow_session_grant_does_not_authorize_other_path_or_capability(self):
        self.mode('ask')
        action = self.request()
        self.allow(action, 'session')
        self.assertEqual(self.request()['state'], 'allowed')
        self.fs.write('other.py', 'other')
        self.assertEqual(self.request({'type':'workspace.read','path':'other.py'})['state'], 'pending')
        self.assertEqual(self.request({'type':'workspace.write','path':'program.py','text':'x','expected_sha256':self.base})['state'], 'pending')
        self.assertEqual(self.request(session=self.other)['state'], 'denied')

    def test_session_grant_expiry_is_rechecked_at_final_execution(self):
        self.mode('ask')
        first = self.request()
        self.allow(first, 'session')
        self.now[0] += 1790
        later = self.request()
        self.assertEqual(later['state'], 'allowed')
        self.now[0] += 11
        # The action ticket itself still has 289 seconds, but its session grant
        # has expired. Admission-time permission cannot authorize the effect.
        with self.assertRaises(PermissionError):self.a.execute(self.session, later['id'])

    def test_expiry_rejects_approval_and_execution(self):
        self.mode('ask')
        pending = self.request()
        allowed = self.request({'type':'search.wikipedia','query':'Hermes'})
        self.allow(allowed)
        self.now[0] += 301
        with self.assertRaises(ValueError):self.allow(pending)
        with self.assertRaises(PermissionError):self.a.execute(self.session, allowed['id'])
        self.assertEqual(self.p.list(self.session)[0]['state'], 'expired')

    def test_cross_conversation_ticket_and_run_fail(self):
        self.mode('ask')
        action = self.request()
        with self.assertRaises(ValueError):self.p.decide(self.other, action['id'], 'allow_once')
        with self.assertRaises(ValueError):self.a.execute(self.other, action['id'])
        run = uid()
        self.c.db.execute('INSERT INTO chat_runs VALUES (?,?,?,?,?,?,NULL,NULL)', (run,self.other,'normal','running','{}',self.now[0]))
        self.c.db.commit()
        with self.assertRaises(ValueError):self.request(run_id=run)

    def test_policy_update_revokes_ticket_and_grant_without_affecting_model(self):
        self.mode('ask')
        action = self.request()
        self.allow(action, 'session')
        self.p.revoke(self.session)
        with self.assertRaises(PermissionError):self.a.execute(self.session, action['id'])
        self.assertFalse(self.p.read(self.session)['grants'])
        self.assertEqual(self.c.session_record(self.session)['arm'], 'normal')

    def test_move_to_another_project_resets_scope_instead_of_carrying_grants(self):
        self.mode('workspace_agent')
        action = self.request()
        target = self.c.create('Different workspace')['id']
        self.c.db.execute('UPDATE sessions SET project=? WHERE id=?', (target,self.session))
        self.c.db.commit()
        policy = self.p.read(self.session)
        self.assertEqual(policy['mode'], 'chat_only')
        self.assertEqual(policy['project_id'], target)
        with self.assertRaises(PermissionError):self.a.execute(self.session, action['id'])

    def test_stale_write_base_is_rejected_at_final_dispatch(self):
        self.mode('ask')
        action = self.request({'type':'workspace.write','path':'program.py','text':'candidate','expected_sha256':self.base})
        self.allow(action)
        self.fs.write('program.py', 'new user work', self.base)
        result = self.a.execute(self.session, action['id'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(self.fs.read('program.py')['text'], 'new user work')

    def test_read_base_drift_is_rejected_before_returning_changed_content(self):
        self.mode('ask')
        action = self.request()
        self.allow(action)
        self.fs.write('program.py', 'not the reviewed version', self.base)
        result = self.a.execute(self.session, action['id'])
        self.assertEqual(result['state'], 'failed')
        self.assertIsNone(result['result'])

    def test_path_traversal_symlink_and_host_shell_schemas_fail(self):
        self.mode('workspace_agent')
        outside = Path(self.tmp.name)/'outside.txt'
        outside.write_text('outside')
        (self.c.root/'projects'/self.project/'workspace'/'escape').symlink_to(outside)
        for path in ('../outside.txt', '/etc/passwd', 'escape', 'nested/../../outside.txt'):
            with self.subTest(path=path),self.assertRaises((ValueError,OSError)):
                self.request({'type':'workspace.read','path':path})
        for action in ({'type':'shell','command':'true'}, {'type':'guest.submit','command':'true'}, {'type':'workspace.read','path':'program.py','approve':True}):
            with self.assertRaises(ValueError):self.request(action)

    def test_symlink_swap_between_approval_and_write_cannot_escape(self):
        self.mode('ask')
        action = self.request({'type':'workspace.write','path':'program.py','text':'candidate','expected_sha256':self.base})
        self.allow(action)
        source = self.c.root/'projects'/self.project/'workspace'/'program.py'
        outside = Path(self.tmp.name)/'outside.txt'
        outside.write_text('outside')
        source.unlink()
        source.symlink_to(outside)
        self.assertEqual(self.a.execute(self.session, action['id'])['state'], 'failed')
        self.assertEqual(outside.read_text(), 'outside')

    def test_same_request_id_cannot_change_arguments_or_policy_binding(self):
        self.mode('ask')
        request = uid()
        first = self.request(request_id=request)
        self.assertEqual(first['id'], self.request(request_id=request)['id'])
        with self.assertRaises(ValueError):self.request({'type':'search.wikipedia','query':'changed'}, request_id=request)
        self.p.revoke(self.session)
        self.assertEqual(self.request(request_id=request)['state'], 'revoked')

    def test_search_is_provider_fixed_and_requires_permission(self):
        self.mode('ask')
        with self.assertRaises(PermissionError):self.p.require(self.session, 'search')
        action = self.request({'type':'search.wikipedia','query':'Hermes'})
        self.allow(action)
        with patch('workspace.search.search', return_value={'provider':'Wikipedia','query':'Hermes','sources':[]}) as search:
            result = self.a.execute(self.session, action['id'])
            search.assert_called_once_with('Hermes')
        self.assertEqual(result['result']['provider'], 'Wikipedia')
        with self.assertRaises(ValueError):self.request({'type':'search.wikipedia','query':'Hermes','url':'http://localhost'})

    def test_permitted_search_persists_explicit_source_backed_context_attachment(self):
        self.mode('ask')
        action = self.request({'type':'search.wikipedia','query':'Hermes'})
        self.allow(action)
        source = {'id':'1','title':'Hermes','url':'https://en.wikipedia.org/wiki/Hermes','text':'Actual provider text.'}
        with patch('workspace.search.search',return_value={'provider':'Wikipedia','query':'Hermes','sources':[source]}):
            result = self.a.execute(self.session,action['id'])['result']
        from workspace.attachments import Attachments
        item, text = Attachments(self.c).context(result['attachment']['id'])
        self.assertIn('Actual provider text.',text)
        self.assertEqual(item['metadata']['search']['sources'][0]['url'],source['url'])

    def test_unsupported_guest_is_unavailable_even_in_workspace_mode(self):
        self.mode('workspace_agent')
        snapshot = self.c.snapshot(self.project)
        with patch('workspace.actions.Actions.available', return_value={key:{'available':False,'reason':'not qualified'} for key in ('read','write','guest','search','microphone','host_apply')}):
            action = self.request({'type':'guest.submit','task_kind':'python','prompt':'run program.py','snapshot_sha256':snapshot['sha256']})
        self.assertEqual(action['state'], 'unavailable')
        with self.assertRaises(PermissionError):self.a.execute(self.session, action['id'])
        self.assertFalse(self.c.db.execute('SELECT 1 FROM jobs').fetchone())

    def test_guest_dispatch_uses_fixed_job_boundary_and_same_action_id(self):
        self.mode('workspace_agent')
        snapshot = self.c.snapshot(self.project)
        available = {key:{'available':True,'reason':None} for key in ('read','write','guest','search','microphone','host_apply')}
        with patch.object(self.a, 'available', return_value=available):
            action = self.request({'type':'guest.submit','task_kind':'python','prompt':'run program.py','snapshot_sha256':snapshot['sha256']})
            with patch('workspace.jobs.Jobs.call', return_value={'id':action['id'],'state':'queued'}) as submit:
                result = self.a.execute(self.session, action['id'])
                self.assertEqual(submit.call_args.args[0], 'job.submit')
                self.assertEqual(submit.call_args.args[1]['client_job_id'], action['id'])
        self.assertTrue(result['result']['asynchronous'])

    def test_model_cannot_emit_permission_changes_or_original_host_apply(self):
        def call(arguments):
            return {'id':'tool1','type':'function','function':{'name':'hermes_action','arguments':arguments}}
        for arguments in ('{"type":"permissions.update","mode":"workspace_agent"}',
                          '{"type":"workspace.read","path":"program.py","approve":true}',
                          '{"type":"host.apply","review_ticket":"'+uid()+'"}',
                          '{"type":"workspace.read","path":"safe","path":"../escape"}'):
            with self.assertRaises(ValueError):parse_model_tool(call(arguments))
        self.assertEqual(parse_model_tool(call('{"type":"workspace.read","path":"program.py"}'))['path'], 'program.py')

    def test_completed_write_request_reconnect_reuses_result_after_base_changed(self):
        self.mode('workspace_agent')
        request = uid()
        command = {'type':'workspace.write','path':'program.py','text':'new content','expected_sha256':self.base}
        first = self.request(command, request_id=request)
        self.a.execute(self.session, first['id'])
        replay = self.request(command, request_id=request)
        self.assertEqual(replay['id'], first['id'])
        self.assertEqual(replay['state'], 'completed')

    def host_review(self):
        original = Path(self.tmp.name)/'original'
        original.mkdir()
        (original/'program.py').write_text('print("old")\n')
        info = original.stat()
        job, ticket = uid(), uid()
        text = 'print("reviewed")\n'
        plan = {'source':str(original),'device':info.st_dev,'inode':info.st_ino,'path':'program.py',
                'expected':self.base,'text':text,'candidate':hashlib.sha256(text.encode()).hexdigest()}
        self.c.db.execute('INSERT INTO jobs VALUES (?,?,?,?)', (job,self.session,'review_ready','{}'))
        self.c.db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)', (ticket,job,self.project,json.dumps(plan),self.now[0]+300))
        self.c.db.commit()
        return original, ticket

    def test_original_host_diff_requires_separate_once_approval_even_workspace_mode(self):
        self.mode('workspace_agent')
        original, ticket = self.host_review()
        action = self.request({'type':'host.apply','review_ticket':ticket})
        self.assertEqual(action['state'], 'pending')
        self.assertIn('reviewed', action['diff'])
        with self.assertRaises(ValueError):self.allow(action, 'session')
        self.allow(action)
        # Jobs uses the wall clock; the deterministic ledger clock is deliberately
        # different. Only this test's fixed review expiry is advanced to match it.
        self.c.db.execute('UPDATE reviews SET expires=? WHERE id=?', (9999999999,ticket))
        self.c.db.commit()
        result = self.a.execute(self.session, action['id'])
        self.assertEqual(result['state'], 'completed')
        self.assertEqual((original/'program.py').read_text(), 'print("reviewed")\n')
        self.assertFalse(self.c.db.execute('SELECT 1 FROM reviews WHERE id=?',(ticket,)).fetchone())
        self.assertEqual(self.a.execute(self.session, action['id'])['result'], result['result'])

    def test_original_host_plan_and_base_change_cannot_reuse_approval(self):
        self.mode('ask')
        original, ticket = self.host_review()
        action = self.request({'type':'host.apply','review_ticket':ticket})
        self.allow(action)
        (original/'program.py').write_text('new user work')
        result = self.a.execute(self.session, action['id'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual((original/'program.py').read_text(), 'new user work')
        with self.assertRaises(ValueError):self.request({'type':'host.apply','review_ticket':ticket}, session=self.other)

    def test_revoke_requests_cancellation_only_for_own_async_guest_jobs(self):
        self.mode('workspace_agent')
        snapshot = self.c.snapshot(self.project)
        available = {key:{'available':True,'reason':None} for key in ('read','write','guest','search','microphone','host_apply')}
        with patch.object(self.a,'available',return_value=available):
            action = self.request({'type':'guest.submit','task_kind':'python','prompt':'run program.py','snapshot_sha256':snapshot['sha256']})
            def submit(method, fields):
                self.c.db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(action['id'],self.session,'running',json.dumps({'state':'running'})))
                return {'id':action['id'],'state':'running'}
            with patch('workspace.jobs.Jobs.call',side_effect=submit):self.a.execute(self.session,action['id'])
            with patch('workspace.jobs.Jobs.call',return_value={'status':'ok'}) as cancel:
                result = self.a.revoke(self.session)
                cancel.assert_called_once_with('job.cancel',{'job_id':action['id']})
            self.assertTrue(result['cancelled_work'][0]['cancel_requested'])
            self.assertEqual(result['mode'],'chat_only')

    def test_minimal_audit_has_no_prompt_or_file_payload(self):
        self.mode('workspace_agent')
        action = self.request({'type':'workspace.write','path':'program.py','text':'private content nonce','expected_sha256':self.base})
        self.a.execute(self.session, action['id'])
        audit = json.dumps(self.c.db.execute('SELECT * FROM permission_audit').fetchall())
        self.assertNotIn('private content nonce', audit)
        self.assertNotIn('print(', audit)

    def test_revocation_is_responsive_during_search_and_drops_late_context(self):
        self.mode('custom',search=True)
        action=self.request({'type':'search.wikipedia','query':'labelled fixture'})
        started=threading.Event();release=threading.Event();finished=threading.Event();outcomes=[]
        def provider(query):
            started.set()
            if not release.wait(3):raise RuntimeError('fixture_provider_deadline')
            return {'provider':'Wikipedia','query':query,'sources':[{'title':'Fixture','url':'https://en.wikipedia.org/wiki/Fixture','text':'Labelled fixture data'}]}
        def dispatch():
            try:outcomes.append(self.a.execute(self.session,action['id']))
            finally:finished.set()
        with patch('workspace.search.search',side_effect=provider):
            worker=threading.Thread(target=dispatch);worker.start()
            try:
                self.assertTrue(started.wait(2),'provider did not start')
                self.p.revoke(self.session)
                self.assertFalse(finished.is_set(),'provider must still be waiting')
            finally:release.set();worker.join(4)
        self.assertTrue(finished.is_set());self.assertEqual(outcomes[0]['state'],'revoked')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM attachments').fetchone()[0],0)

    def test_microphone_consent_and_policy_version_are_server_held(self):
        policy = self.p.read(self.session)
        with self.assertRaises(PermissionError):self.p.require(self.session, 'microphone')
        self.p.update(self.session, policy['version'], 'custom', {**PRESETS['chat_only'],'microphone':True})
        self.assertTrue(self.p.require(self.session, 'microphone')['capabilities']['microphone'])
        with self.assertRaises(ValueError):self.p.update(self.session, policy['version'], 'chat_only', dict(PRESETS['chat_only']))
        self.assertTrue(Permissions(self.c).read(self.session)['capabilities']['microphone'])

    def test_run_step_and_time_budgets_terminate_repeated_tool_requests(self):
        self.mode('workspace_agent')
        run = uid()
        self.c.db.execute('INSERT INTO chat_runs VALUES (?,?,?,?,?,?,NULL,NULL)', (run,self.session,'normal','running','{}',self.now[0]))
        self.c.db.commit()
        for i in range(12):self.request(run_id=run)
        with self.assertRaises(ValueError):self.request(run_id=run)
        self.now[0] += 361
        with self.assertRaises(ValueError):self.request({'type':'search.wikipedia','query':'later'}, run_id=run)


if __name__ == '__main__':
    unittest.main()
