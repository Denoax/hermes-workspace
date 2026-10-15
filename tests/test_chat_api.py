"""Authenticated loopback boundary regression checks with a disposable catalog."""
import http.client,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from workspace.server import Application,BoundedServer,handler


class ApiBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.app=Application(Path(cls.tmp.name)/'catalog');cls.server=BoundedServer(('127.0.0.1',0),handler(cls.app,'labelled-test-cookie'))
        cls.port=cls.server.server_port;cls.origin='http://127.0.0.1:'+str(cls.port);cls.patch_port=patch('workspace.server.PORT',cls.port);cls.patch_origin=patch('workspace.server.ORIGIN',cls.origin);cls.patch_port.start();cls.patch_origin.start();cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.patch_port.stop();cls.patch_origin.stop();cls.app.catalog.db.close();cls.tmp.cleanup()
    def request(self,method,path,body=None,headers=None):
        defaults={'Cookie':'hermes_session=labelled-test-cookie','Origin':self.origin,'X-Hermes-CSRF':self.app.csrf,'Content-Type':'application/json'};defaults.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        try:c.request(method,path,body,defaults);r=c.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally:c.close()
    def test_bootstrap_requires_cookie(self):self.assertEqual(self.request('GET','/hermes-workspace/api/bootstrap',headers={'Cookie':''})[0],401)
    def test_host_origin_and_csrf_fail_closed(self):
        body=json.dumps({'version':1,'method':'workspace.list','fields':{}})
        for headers in [{'Host':'evil.invalid'},{'Origin':'https://evil.invalid'},{'X-Hermes-CSRF':'wrong'},{'Cookie':''}]:
            with self.subTest(headers=headers):self.assertEqual(self.request('POST','/hermes-workspace/api/rpc',body,headers)[0],403)
    def test_registered_ids_are_validated_on_changed_chat_path(self):
        body=json.dumps({'version':1,'method':'chat.read','fields':{'run_id':'../outside'}})
        status,_,raw=self.request('POST','/hermes-workspace/api/rpc',body);self.assertEqual(status,409);self.assertIn(b'invalid_registered_id',raw)
    def test_upload_is_authenticated_and_content_checked(self):
        headers={'Content-Type':'image/png','X-Filename':'fake.png'}
        self.assertEqual(self.request('POST','/hermes-workspace/api/upload',b'fake',headers)[0],409)
        self.assertEqual(self.request('POST','/hermes-workspace/api/upload',b'fake',{**headers,'X-Hermes-CSRF':'wrong'})[0],403)
    def test_media_read_range_and_cookie_boundary(self):
        status,_,raw=self.request('POST','/hermes-workspace/api/upload',b'harmless fixture',{'Content-Type':'text/plain','X-Filename':'fixture.txt'});self.assertEqual(status,200)
        aid=json.loads(raw)['result']['id'];path='/hermes-workspace/api/attachment/'+aid
        self.assertEqual(self.request('GET',path,headers={'Cookie':''})[0],401)
        status,headers,raw=self.request('GET',path,headers={'Range':'bytes=0-7'});self.assertEqual(status,206);self.assertEqual(raw,b'harmless');self.assertIn('Content-Range',headers)
    def test_changed_CSP_keeps_scripts_and_connections_self_only(self):
        status,headers,_=self.request('GET','/hermes-workspace');self.assertEqual(status,200);csp=headers['Content-Security-Policy'];self.assertIn("script-src 'self';",csp);self.assertNotIn('unsafe-eval',csp);self.assertIn("connect-src 'self';",csp);self.assertIn("media-src 'self' blob:",csp)
    def test_arbitrary_paths_and_unknown_assets_stay_unserved(self):
        for path in ['/assets/../../etc/passwd','/assets/does-not-exist.js','/hermes-workspace/api/attachment/../../etc/passwd']:
            self.assertIn(self.request('GET',path)[0],(404,403))
    def test_chat_snapshot_keeps_history_beyond_legacy_hundred_message_limit(self):
        session=self.app.catalog.session(None,'normal')['id']
        for n in range(120):self.app.catalog.message(session,'user','History fixture '+str(n))
        result=self.app.call('chat.snapshot',{'session_id':session})
        self.assertEqual(len(result['messages']),120);self.assertEqual(result['messages'][0]['text'],'History fixture 0');self.assertEqual(result['messages'][-1]['text'],'History fixture 119')

if __name__=='__main__':unittest.main()
