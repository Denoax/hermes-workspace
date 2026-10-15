"""Real loopback fixture for the exact added asset allowlist; no native/model calls."""
import http.client
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from http.server import ThreadingHTTPServer
from workspace.server import handler


class PortfolioAssetRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = SimpleNamespace(csrf='fixture-csrf')
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), handler(app, 'fixture-only-cookie'))
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join(timeout=2)

    def get(self, path, **headers):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=3)
        try:
            connection.request('GET', path, headers={'Host':'127.0.0.1:18791', **headers})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally: connection.close()

    def test_added_modules_and_styles_have_explicit_types(self):
        for path in ('/icons.mjs','/pane-motion.mjs','/portfolio-nav.mjs','/interface-audio.mjs','/portfolio.css'):
            with self.subTest(path=path):
                status, headers, body = self.get(path)
                self.assertEqual(status,200); self.assertTrue(body)
                self.assertEqual(headers['Content-Type'], 'text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8')
                self.assertEqual(headers['X-Content-Type-Options'],'nosniff')

    def test_exact_audio_and_font_assets(self):
        for path, mime, signature in (('/fonts/Inter-Medium.woff2','font/woff2',b'wOF2'),('/fonts/Rubik.ttf','font/ttf',b'\0\1\0\0'),('/sounds/soft-press.wav','audio/wav',b'RIFF'),('/sounds/soft-close.wav','audio/wav',b'RIFF')):
            status, headers, body = self.get(path)
            self.assertEqual((status,headers['Content-Type']),(200,mime));self.assertTrue(body.startswith(signature))

    def test_no_directory_or_unlisted_sound_access(self):
        for path in ('/sounds/','/sounds/LICENSE.txt','/sounds/click1.wav','/../server.py','/fonts/../../server.py','/sounds/soft-press.wav?file=server.py'):
            self.assertEqual(self.get(path)[0],404)

    def test_host_origin_and_bootstrap_auth_are_preserved(self):
        self.assertEqual(self.get('/portfolio.css',Host='evil.invalid')[0],403)
        self.assertEqual(self.get('/icons.mjs',Origin='https://evil.invalid')[0],403)
        self.assertEqual(self.get('/hermes-workspace/api/bootstrap')[0],401)


if __name__ == '__main__': unittest.main()
