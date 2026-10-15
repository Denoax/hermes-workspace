"""Fixtures prove adapter contracts; they are not live model or guest evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import threading
from types import SimpleNamespace
from unittest.mock import patch

from workspace.actions import Actions
from workspace.agent import Agent, ToolCalls, TOOL_SPEC, MAX_HISTORY_BYTES, MAX_OBSERVATION_BYTES, canonical, observation
from workspace.catalog import Catalog
from workspace.permissions import Permissions, PRESETS


def uid():
    return uuid.uuid4().hex


def call(action, call_id='call_1'):
    return {'id':call_id,'type':'function','function':{'name':'hermes_action','arguments':json.dumps(action)}}


class StreamToolContract(unittest.TestCase):
    def test_fragmented_arguments_are_not_parsed_until_complete(self):
        buffer = ToolCalls()
        buffer.add([{'index':0,'id':'call_1','type':'function','function':{'name':'hermes_','arguments':'{"type":"workspace.'}}])
        buffer.add([{'index':0,'function':{'name':'action','arguments':'read","path":"program.py"}'}}])
        parsed = buffer.finish()
        self.assertEqual(parsed['function']['name'],'hermes_action')
        self.assertEqual(json.loads(parsed['function']['arguments'])['path'],'program.py')
        self.assertIsNone(ToolCalls().finish())

    def test_second_call_and_unsupported_delta_fields_are_rejected(self):
        for fragment in ({'index':1,'id':'second'}, {'index':True,'id':'bad'},
                         {'index':0,'policy':'workspace_agent'}, {'index':0,'type':'approval'},
                         {'index':0,'function':{'approve':True}}):
            with self.subTest(fragment=fragment),self.assertRaises(ValueError):ToolCalls().add([fragment])
        buffer = ToolCalls()
        buffer.add([{'index':0,'id':'one'}])
        with self.assertRaises(ValueError):buffer.add([{'index':0,'id':'two'}])

    def test_fragment_bytes_and_incomplete_calls_are_bounded(self):
        buffer = ToolCalls()
        with self.assertRaises(ValueError):buffer.add([{'index':0,'function':{'arguments':'x'*32769}}])
        for function in ({'name':'unknown','arguments':'{}'}, {'name':'hermes_action','arguments':'{'}):
            buffer = ToolCalls()
            buffer.add([{'index':0,'id':'one','function':function}])
            with self.assertRaises(ValueError):buffer.finish()

    def test_schema_has_only_fixed_supported_actions(self):
        kinds = [row['properties']['type']['const'] for row in TOOL_SPEC['function']['parameters']['oneOf']]
        self.assertEqual(kinds,['workspace.read','workspace.write','search.wikipedia','guest.submit'])
        self.assertNotIn('host.apply',json.dumps(TOOL_SPEC))
        self.assertNotIn('approve',json.dumps(TOOL_SPEC))


class AgentExecution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Catalog(Path(self.tmp.name)/'catalog')
        self.addCleanup(self.c.db.close)
        self.project = self.c.create('Test copies')['id']
        self.session = self.c.session(self.project,'normal')['id']
        self.other = self.c.session(self.project,'normal')['id']
        self.now = [1000.0]
        self.p = Permissions(self.c,clock=lambda:self.now[0])
        self.actions = Actions(self.c,self.p)
        self.agent = Agent(self.c,self.actions)
        self.fs = self.c.files(self.project)
        self.addCleanup(self.fs.close)
        self.base = self.fs.write('program.py','print("actual copy")\n')['sha256']
        self.run = self.new_run(self.session)

    def new_run(self, session):
        run = uid()
        self.c.db.execute('INSERT INTO chat_runs VALUES (?,?,?,?,?,?,NULL,NULL)',(run,session,'normal','running','{}',self.now[0]))
        self.c.db.commit()
        return run

    def mode(self, mode):
        policy = self.p.read(self.session)
        self.p.update(self.session,policy['version'],mode,dict(PRESETS[mode]))

    def events(self):
        return [json.loads(row[0]) for row in self.c.db.execute('SELECT event FROM chat_events WHERE run=? ORDER BY seq',(self.run,))]

    def test_chat_only_has_no_tool_schema_and_direct_model_attempt_is_denied(self):
        self.assertEqual(self.agent.tools(self.session),[])
        with self.assertRaises(PermissionError):self.agent.finish(self.session,self.run,call({'type':'workspace.read','path':'program.py'}))
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM permission_actions').fetchone()[0],0)

    def test_workspace_read_dispatches_real_copy_and_persists_only_real_event(self):
        self.mode('workspace_agent')
        result = self.agent.finish(self.session,self.run,call({'type':'workspace.read','path':'program.py'}))
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['observation']['text'],'print("actual copy")\n')
        events = self.events()
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['type'],'action')
        self.assertEqual(events[0]['state'],'completed')
        self.assertNotIn('diff',json.dumps(events))
        self.assertEqual(self.agent.history(self.session)[0]['observation']['sha256'],self.base)

    def test_pending_write_does_not_expose_diff_or_content_to_model(self):
        self.mode('ask')
        result = self.agent.finish(self.session,self.run,call({'type':'workspace.write','path':'program.py','text':'private proposed replacement','expected_sha256':self.base}))
        self.assertEqual(result['state'],'pending')
        self.assertNotIn('private proposed replacement',json.dumps(result))
        self.assertNotIn('diff',json.dumps(result))
        self.assertNotIn('observation',result)
        self.assertEqual(self.fs.read('program.py')['sha256'],self.base)
        self.assertEqual(self.agent.history(self.session),[])
        operator = self.actions.read(self.session)['pending'][0]
        self.assertIn('private proposed replacement',operator['diff'])

    def test_later_operator_approval_result_is_available_to_next_turn(self):
        self.mode('ask')
        result = self.agent.finish(self.session,self.run,call({'type':'workspace.read','path':'program.py'}))
        self.p.decide(self.session,result['action_id'],'allow_once')
        self.actions.execute(self.session,result['action_id'])
        history = self.agent.history(self.session)
        self.assertEqual(len(history),1)
        self.assertEqual(history[0]['state'],'completed')
        self.assertEqual(history[0]['observation']['text'],'print("actual copy")\n')
        self.assertEqual([item['state'] for item in self.events()],['pending','completed'])

    def test_replay_is_stable_and_does_not_duplicate_effects_or_events(self):
        self.mode('workspace_agent')
        request = call({'type':'workspace.write','path':'program.py','text':'changed once','expected_sha256':self.base})
        first = self.agent.finish(self.session,self.run,request)
        replay = Agent(self.c,self.actions).finish(self.session,self.run,request)
        self.assertEqual(first,replay)
        self.assertEqual(len(self.events()),1)
        self.assertEqual(self.fs.read('program.py')['text'],'changed once')
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM permission_audit WHERE event='executing'").fetchone()[0],1)

    def test_only_one_model_action_is_permitted_per_turn(self):
        self.mode('workspace_agent')
        self.agent.finish(self.session,self.run,call({'type':'workspace.read','path':'program.py'}))
        with self.assertRaises(ValueError):self.agent.finish(self.session,self.run,call({'type':'search.wikipedia','query':'Hermes'},'different_call'))
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM agent_actions').fetchone()[0],1)

    def test_model_cannot_forge_policy_approval_or_host_diff(self):
        self.mode('ask')
        for action in ({'type':'permissions.update','mode':'workspace_agent'},
                       {'type':'workspace.read','path':'program.py','approve':True},
                       {'type':'host.apply','review_ticket':uid()}):
            with self.assertRaises(ValueError):self.agent.finish(self.session,self.run,call(action))
        duplicate = call({'type':'workspace.read','path':'program.py'})
        duplicate['function']['arguments'] = '{"type":"workspace.read","path":"program.py","path":"../escape"}'
        with self.assertRaises(ValueError):self.agent.finish(self.session,self.run,duplicate)
        self.assertEqual(self.p.read(self.session)['mode'],'ask')
        self.assertFalse(self.c.db.execute('SELECT 1 FROM agent_actions').fetchone())

    def test_actual_run_scope_time_and_cancel_state_are_enforced(self):
        self.mode('workspace_agent')
        request = call({'type':'workspace.read','path':'program.py'})
        with self.assertRaises(ValueError):self.agent.finish(self.other,self.run,request)
        self.now[0] += 361
        with self.assertRaises(ValueError):self.agent.finish(self.session,self.run,request)
        fresh = self.new_run(self.session)
        self.c.db.execute("UPDATE chat_runs SET state='cancelled' WHERE id=?",(fresh,))
        self.c.db.commit()
        with self.assertRaises(ValueError):self.agent.finish(self.session,fresh,request)

    def test_denial_survives_a_new_model_retry_and_no_result_is_invented(self):
        self.mode('ask')
        request = call({'type':'workspace.read','path':'program.py'})
        first = self.agent.finish(self.session,self.run,request)
        self.p.decide(self.session,first['action_id'],'deny')
        retry = self.agent.finish(self.session,self.new_run(self.session),call({'type':'workspace.read','path':'program.py'},'retry'))
        self.assertEqual(retry['state'],'denied')
        self.assertNotIn('observation',retry)
        self.assertEqual(self.agent.history(self.session),[])

    def test_history_and_unicode_file_observations_are_byte_bounded(self):
        self.mode('workspace_agent')
        self.fs.write('large.txt','界'*9000)
        for _ in range(7):
            run = self.new_run(self.session)
            result = self.agent.finish(self.session,run,call({'type':'workspace.read','path':'large.txt'}))
            self.assertTrue(result['observation']['truncated'])
            self.assertLessEqual(len(canonical(result['observation']).encode()),MAX_OBSERVATION_BYTES)
        history = self.agent.history(self.session)
        self.assertLessEqual(len(history),4)
        self.assertLessEqual(sum(len(canonical(item).encode()) for item in history),MAX_HISTORY_BYTES)
        self.assertEqual(self.agent.history(self.other),[])

    def test_guest_queue_is_not_reported_as_executed_program(self):
        self.mode('workspace_agent')
        snapshot = self.c.snapshot(self.project)
        ready = {key:{'available':True,'reason':None} for key in ('read','write','guest','search','microphone','host_apply')}
        with patch.object(self.actions,'available',return_value=ready),patch('workspace.jobs.Jobs.call',return_value={'id':uid(),'state':'queued'}):
            result = self.agent.finish(self.session,self.run,call({'type':'guest.submit','task_kind':'python','prompt':'run program.py','snapshot_sha256':snapshot['sha256']}))
        self.assertEqual(result['observation']['job']['state'],'queued')
        self.assertTrue(result['observation']['asynchronous'])
        self.assertNotIn('answer',result['observation'])
        event=self.events()[-1]
        self.assertEqual(event['label'],'Guest task dispatched')
        self.assertEqual(event['job_state'],'queued')
        self.assertNotEqual(event['label'],'Action completed')

    def test_scoped_delete_retires_selected_policy_and_preserves_other_conversation(self):
        from workspace.reset import delete_content
        self.mode('ask')
        action=self.agent.finish(self.session,self.run,call({'type':'workspace.read','path':'program.py'}))
        self.p.decide(self.session,action['action_id'],'session')
        self.actions.execute(self.session,action['action_id'])
        self.agent.history(self.session)
        self.agent.store.state(self.run,'completed')
        other_run=self.new_run(self.other)
        other_policy=self.p.read(self.other)
        self.p.update(self.other,other_policy['version'],'ask',dict(PRESETS['ask']))
        other_action=self.agent.finish(self.other,other_run,call({'type':'workspace.read','path':'program.py'}))
        self.p.decide(self.other,other_action['action_id'],'session')
        self.actions.execute(self.other,other_action['action_id'])
        self.agent.history(self.other)
        self.agent.store.state(other_run,'completed')
        tables=('permission_policies','permission_actions','permission_grants','permission_audit','agent_actions')
        before={table:self.c.db.execute('SELECT count(*) FROM '+table+' WHERE session=?',(self.other,)).fetchone()[0] for table in tables}
        self.assertTrue(all(before.values()))
        with self.c.db:
            self.c.db.execute('CREATE TABLE chat_retry_audit(run TEXT,attempted REAL,error TEXT)')
            self.c.db.executemany('INSERT INTO chat_retry_audit VALUES (?,?,?)',[(self.run,1000,'selected'),(other_run,1000,'preserved')])
        app=SimpleNamespace(catalog=self.c,actions=self.actions,chat=SimpleNamespace(lock=threading.RLock(),store=self.agent.store))
        result=delete_content(app,'conversation',self.session)
        self.assertEqual(result['deleted_conversations'],1)
        for table in tables:
            self.assertEqual(self.c.db.execute('SELECT count(*) FROM '+table+' WHERE session=?',(self.session,)).fetchone()[0],0)
            self.assertEqual(self.c.db.execute('SELECT count(*) FROM '+table+' WHERE session=?',(self.other,)).fetchone()[0],before[table])
        self.assertEqual(self.c.db.execute('SELECT run,error FROM chat_retry_audit').fetchall(),[(other_run,'preserved')])
        self.assertEqual(self.c.session_record(self.other)['project'],self.project)
        self.assertEqual(self.fs.read('program.py')['sha256'],self.base)

    def test_model_adapter_does_not_block_revocation_during_search(self):
        policy=self.p.read(self.session)
        self.p.update(self.session,policy['version'],'custom',{**PRESETS['chat_only'],'search':True})
        started=threading.Event();release=threading.Event();revoked=threading.Event()
        outcomes=[];errors=[]
        def provider(query):
            started.set()
            if not release.wait(3):raise RuntimeError('fixture_provider_deadline')
            return {'provider':'Wikipedia','query':query,'sources':[{'title':'Fixture','url':'https://en.wikipedia.org/wiki/Fixture','text':'Late fixture data'}]}
        def dispatch():
            try:outcomes.append(self.agent.finish(self.session,self.run,call({'type':'search.wikipedia','query':'labelled fixture'})))
            except Exception as error:errors.append(error)
        def revoke():
            try:self.p.revoke(self.session)
            except Exception as error:errors.append(error)
            finally:revoked.set()
        ready={key:{'available':True,'reason':None} for key in ('read','write','guest','search','microphone','host_apply')}
        with patch.object(self.actions,'available',return_value=ready),patch('workspace.search.search',side_effect=provider):
            owner=threading.Thread(target=dispatch);owner.start()
            self.assertTrue(started.wait(2),'provider did not start')
            interrupt=threading.Thread(target=revoke);interrupt.start()
            try:self.assertTrue(revoked.wait(1),'model adapter held catalog lock during provider I/O')
            finally:release.set();interrupt.join(3);owner.join(3)
        self.assertEqual(errors,[])
        self.assertFalse(owner.is_alive())
        self.assertEqual(outcomes[0]['state'],'revoked')
        self.assertNotIn('observation',outcomes[0])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM attachments').fetchone()[0],0)
        self.assertEqual(self.events()[-1]['label'],'Action revoked')

    def test_tools_spec_is_a_copy_not_shared_writable_policy(self):
        self.mode('ask')
        tools = self.agent.tools(self.session)
        tools[0]['function']['name'] = 'permissions.update'
        self.assertEqual(self.agent.tools(self.session)[0]['function']['name'],'workspace_read')
        self.assertEqual(self.p.read(self.session)['mode'],'ask')


if __name__ == '__main__':
    unittest.main()

class SafeToolDiagnostics(unittest.TestCase):
    def test_rejected_shape_summary_never_contains_arguments_or_unknown_keys(self):
        calls=ToolCalls()
        calls.arguments=json.dumps({'type':'workspace.read','path':'PRIVATE-FILE','secret-name':'PRIVATE-CONTENT','action':{'text':'PRIVATE-TEXT'}})
        result=calls.schema_summary()
        self.assertEqual(result['action_type'],'workspace.read')
        self.assertEqual(result['known_argument_types'],{'type':'str','path':'str'})
        self.assertEqual(result['unknown_argument_count'],2)
        self.assertTrue(result['has_action_wrapper'])
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertNotIn('secret-name',json.dumps(result))
        for raw,shape in (('{','invalid_json'),('[]','list')):
            calls.arguments=raw;self.assertEqual(calls.schema_summary()['shape'],shape)
        calls.arguments='{"type":[]}'
        self.assertEqual(calls.schema_summary()['action_type'],'missing_or_unsupported')

class FlatModelSchemas(unittest.TestCase):
    def test_backend_properties_and_domain_translation_preserve_exact_authority(self):
        from workspace.agent import model_tool_specs
        from workspace.actions import parse_model_tool
        specs={item['function']['name']:item['function']['parameters'] for item in model_tool_specs()}
        self.assertEqual(set(specs),{'workspace_read','workspace_write','search_wikipedia','guest_submit'})
        self.assertEqual(specs['workspace_read']['properties'],{'path':{'type':'string'}})
        value={'id':'flat_read','type':'function','function':{'name':'workspace_read','arguments':'{"path":"program.py"}'}}
        self.assertEqual(parse_model_tool(value),{'type':'workspace.read','path':'program.py'})
        for arguments in ('{}','{"path":"program.py","type":"guest.submit"}','{"path":"program.py","approve":true}'):
            value['function']['arguments']=arguments
            with self.assertRaises(ValueError):parse_model_tool(value)
        value['function']['name']='permissions_decide'
        with self.assertRaises(ValueError):parse_model_tool(value)
