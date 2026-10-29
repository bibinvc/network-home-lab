import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('ops_app', Path(__file__).parents[1] / 'app/app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ApplicationChecks(unittest.TestCase):
    def setUp(self):
        self.rows = [{'hostname': 'lab-01', 'purpose': 'synthetic', 'status': 'healthy'}]
        self.loader = lambda: self.rows
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), app.handler(lambda: self.loader()))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%d' % self.httpd.server_port

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()

    def get(self, path, method='GET'):
        try:
            response = urllib.request.urlopen(urllib.request.Request(self.url + path, method=method), timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        return response.status, response.headers, response.read().decode()

    def test_liveness_does_not_need_database(self):
        self.loader = lambda: (_ for _ in ()).throw(RuntimeError('private database details'))
        self.assertEqual(self.get('/healthz')[0], 200)
        self.assertEqual(self.get('/readyz')[0], 503)

    def test_records_and_count(self):
        status, _, body = self.get('/records')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'count': 1, 'records': self.rows})

    def test_database_errors_do_not_leak_details(self):
        self.loader = lambda: (_ for _ in ()).throw(ValueError('password=never-print-this'))
        status, _, body = self.get('/records')
        self.assertEqual(status, 503)
        self.assertNotIn('password', body)

    def test_html_escapes_inventory(self):
        self.rows[0]['hostname'] = '<script>alert(1)</script>'
        _, headers, body = self.get('/')
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertEqual(headers['X-Frame-Options'], 'DENY')

    def test_mutations_are_rejected(self):
        for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            self.assertEqual(self.get('/records', method)[0], 405)

    def test_forced_unready_drill(self):
        with patch.dict(os.environ, {'APP_FORCE_UNREADY': '1'}):
            self.assertEqual(self.get('/readyz')[0], 503)
            self.assertEqual(self.get('/healthz')[0], 200)

    def test_metrics_and_unknown_path(self):
        self.assertIn('ops_inventory_records 1', self.get('/metrics')[2])
        self.assertEqual(self.get('/unknown')[0], 404)

    def test_version_has_no_database_dependency(self):
        self.loader = lambda: (_ for _ in ()).throw(RuntimeError())
        with patch.dict(os.environ, {'APP_RELEASE': '2.0.0'}):
            self.assertEqual(json.loads(self.get('/version')[2])['release'], '2.0.0')


if __name__ == '__main__':
    unittest.main()
