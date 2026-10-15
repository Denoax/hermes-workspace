"""Real HTTP streaming against a labelled fake backend, never model evidence."""
import json,socket,tempfile,threading,time,unittest,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from workspace.catalog import Catalog
from workspace.chat import Chat


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
        self.chat=Chat(self.c,InventoryFixture(),lambda:NativeFixture(self.server));self.session=self.c.session(None,'abliterated')['id']
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
    def test_gpu_memory_error_is_actionable_without_exposing_raw_backend_text(self):
        r=self.submit('oom fixture');result=self.wait_terminal(r['id'])
        self.assertEqual(result['state'],'failed');self.assertIn('GPU memory exhausted',result['error']);self.assertNotIn('vk::Device',result['error'])

if __name__=='__main__':unittest.main()
