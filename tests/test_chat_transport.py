"""Real HTTP streaming against a labelled fake backend, never model evidence."""
import json,socket,tempfile,threading,time,unittest,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from workspace.catalog import Catalog
from workspace.chat import Chat
from workspace.permissions import Permissions, PRESETS


class Backend(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/apply-template':result={'prompt':json.dumps(data['messages'])+str(data['chat_template_kwargs']['enable_thinking'])}
        elif self.path=='/tokenize':result={'tokens':[1,2,3]}
        else:
            self.server.received.append(data);self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
            if 'oom fixture' in data['messages'][-1]['content']:
                self.wfile.write(b'data: {"error":{"message":"decode failed: vk::Device::allocateMemory: ErrorOutOfDeviceMemory"}}\n\n');self.wfile.flush();self.close_connection=True;return
            if 'cancel fixture' in data['messages'][-1]['content']:
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"partial fixture"}}]}\n\n');self.wfile.flush();self.server.started.set()
                self.connection.settimeout(5)
                try:self.connection.recv(1)
                except OSError:pass
                self.server.released.set();return
            for text in ['Labelled',' fixture',' response']:
                self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':text}}]})+'\n\n').encode());self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush();self.close_connection=True;return
        raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


class InventoryFixture:
    def require(self,arm):
        if arm!='abliterated':raise ValueError('fixture model only')
        return {'sha256':'0'*64}


class NativeFixture:
    def __init__(self,server):self.server=server
    def text_connection(self,job_id,arm):return {'status':'ok','identity':{'arm':arm,'model_alias':'labelled-fixture','context':8192,'model_sha256':'0'*64}},socket.create_connection(self.server.server_address)
    def call(self,operation,**fields):return {'status':'ok','compute_idle_acknowledged':True}


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.c=Catalog(Path(self.tmp.name)/'catalog');self.server=ThreadingHTTPServer(('127.0.0.1',0),Backend);self.server.received=[];self.server.started=threading.Event();self.server.released=threading.Event();self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.state_patch=patch('workspace.models.STATE',Path(self.tmp.name));self.state_patch.start()
        self.recovery_patch=patch('workspace.chat.wait_for_normal_recovery',return_value={'alias':'labelled-fixture-normal','context':65536});self.recovery_patch.start()
        self.chat=Chat(self.c,InventoryFixture(),lambda:NativeFixture(self.server),readiness_check=lambda:None);self.session=self.c.session(None,'abliterated')['id']
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.state_patch.stop();self.recovery_patch.stop();self.c.db.close();self.tmp.cleanup()
    def submit(self,prompt):
        return self.chat.submit({'request_id':uuid.uuid4().hex,'session_id':self.session,'model_id':'abliterated','prompt':prompt,'reasoning':'off','attachments':[]})
    def wait_terminal(self,run_id):
        end=time.monotonic()+5
        while time.monotonic()<end:
            r=self.chat.store.run(run_id)
            if r['state'] in ('completed','cancelled','failed'):return r
            threading.Event().wait(.01)
        self.fail('fixture run did not reach terminal state')
    def test_real_fetch_stream_persists_context_and_deduplicates_retry(self):
        first=self.submit('Remember a harmless nonce: fixture-742.');self.assertEqual(self.wait_terminal(first['id'])['state'],'completed')
        self.assertEqual(self.c.history(self.session)[1]['text'],'Labelled fixture response')
        second=self.submit('What was the nonce?');self.assertEqual(self.wait_terminal(second['id'])['state'],'completed')
        request=self.server.received[-1];self.assertIn('fixture-742',request['messages'][1]['content']);self.assertEqual(request['messages'][2]['role'],'assistant')
        events=self.chat.store.events(second['id'],0);self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),'Labelled fixture response')
        self.assertFalse('tools' in request)
    def test_cancel_closes_actual_transport_and_preserves_partial_text(self):
        seen=threading.Event();append=self.chat.store.append
        def persist(run,text):append(run,text);seen.set()
        self.chat.store.append=persist
        r=self.submit('cancel fixture');self.assertTrue(self.server.started.wait(3));self.assertTrue(seen.wait(3));self.chat.cancel(r['id']);result=self.wait_terminal(r['id']);self.assertEqual(result['state'],'cancelled');self.assertTrue(self.server.released.wait(2));self.assertEqual(self.c.history(self.session)[1]['text'],'partial fixture')

    def test_failed_turn_retry_reuses_user_message_and_attachments(self):
        with patch.object(NativeFixture,'text_connection',side_effect=RuntimeError('labelled_admission_failure')):
            r=self.submit('A harmless retry fixture')
            self.assertEqual(self.wait_terminal(r['id'])['state'],'failed')
        self.assertEqual(len(self.c.history(self.session)),1)
        retried=self.chat.retry(r['id']);self.assertEqual(retried['id'],r['id'])
        self.assertEqual(self.wait_terminal(r['id'])['state'],'completed')
        self.assertEqual(len([m for m in self.c.history(self.session) if m['role']=='user']),1)
        self.assertEqual(self.chat.retry(r['id'])['state'],'completed')
    def test_gpu_memory_error_is_actionable_without_exposing_raw_backend_text(self):
        r=self.submit('oom fixture');result=self.wait_terminal(r['id'])
        self.assertEqual(result['state'],'failed');self.assertIn('GPU memory exhausted',result['error']);self.assertNotIn('vk::Device',result['error'])

    def assert_search_interruption_drops_context(self,revoke):
        permissions=Permissions(self.c);self.chat.permissions=permissions
        policy=permissions.read(self.session)
        permissions.update(self.session,policy['version'],'custom',{**PRESETS['chat_only'],'search':True})
        started=threading.Event();release=threading.Event();interrupted=threading.Event();errors=[]
        def provider(query):
            started.set()
            if not release.wait(3):raise RuntimeError('fixture_provider_deadline')
            return {'provider':'Wikipedia','query':query,'sources':[{'title':'Fixture','url':'https://en.wikipedia.org/wiki/Fixture','text':'Late fixture context'}]}
        def interrupt(run_id):
            try:
                if revoke:permissions.revoke(self.session)
                else:self.chat.cancel(run_id)
            except Exception as error:errors.append(error)
            finally:interrupted.set()
        with patch('workspace.search.search',side_effect=provider),patch.object(NativeFixture,'text_connection') as admission:
            run=self.chat.submit({'request_id':uuid.uuid4().hex,'session_id':self.session,'model_id':'abliterated','prompt':'Explicit search fixture','reasoning':'off','attachments':[],'search_query':'labelled fixture'})
            self.assertTrue(started.wait(2),'provider did not start')
            worker=threading.Thread(target=interrupt,args=(run['id'],))
            worker.start()
            try:self.assertTrue(interrupted.wait(1),'interruption blocked on provider I/O')
            finally:release.set();worker.join(3)
            result=self.wait_terminal(run['id'])
            admission.assert_not_called()
        self.assertEqual(errors,[])
        self.assertEqual(result['state'],'failed' if revoke else 'cancelled')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM attachments').fetchone()[0],0)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM turn_attachments').fetchone()[0],0)
        self.assertFalse(any(event['type']=='search' for event in self.chat.store.events(run['id'],0)))
        self.assertEqual(self.c.history(self.session)[0]['text'],'Explicit search fixture')

    def test_revoke_during_explicit_search_drops_late_context_before_inference(self):
        self.assert_search_interruption_drops_context(revoke=True)

    def test_cancel_during_explicit_search_drops_late_context_before_inference(self):
        self.assert_search_interruption_drops_context(revoke=False)

if __name__=='__main__':unittest.main()
