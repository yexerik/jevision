"""Exercise real HTTP dispatch with deterministic peer-disconnect write failures."""
import http.client
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError

import server


class DisconnectTests(unittest.TestCase):
    def setUp(self):
        self.fault = {}
        self.statuses = []
        self.errors = []
        self.finished = threading.Event()
        owner = self

        class Writer:
            def __init__(self, stream, handler):
                self.stream, self.handler, self.writes = stream, handler, 0

            def write(self, data):
                self.writes += 1
                if owner.fault.get('path') == self.handler.path and self.writes == owner.fault.get('write'):
                    raise owner.fault['error']('simulated peer disconnect')
                return self.stream.write(data)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        class Handler(server.AppHandler):
            def setup(self):
                super().setup()
                self.wfile = Writer(self.wfile, self)

            def send_response(self, code, message=None):
                owner.statuses.append(code)
                super().send_response(code, message)

            def log_message(self, *args):
                pass

        class HttpServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                owner.errors.append(sys.exc_info()[1])

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    owner.finished.set()

        self.http = HttpServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)

    def request(self, path, method='GET', body=None, headers=None):
        self.finished.clear()
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        except (http.client.HTTPException, OSError):
            return None
        finally:
            connection.close()
            self.assertTrue(self.finished.wait(3), 'Request thread did not finish')

    def test_library_disconnect_does_not_send_second_response_and_server_remains_healthy(self):
        with patch.object(server, 'scan_library', return_value=[]) as scan:
            for error in [BrokenPipeError, ConnectionResetError, ConnectionAbortedError]:
                for write in [1, 2]:  # Header write and body write.
                    with self.subTest(error=error.__name__, write=write):
                        self.fault = {'path':'/api/library', 'error':error, 'write':write}
                        self.statuses.clear()
                        self.request('/api/library')
                        self.assertEqual(self.statuses, [200])
                        self.assertEqual(self.errors, [])
                        self.assertEqual(self.request('/api/health')[0], 200)
            self.assertEqual(scan.call_count, 6)

    def test_library_filesystem_failure_still_returns_500(self):
        with patch.object(server, 'scan_library', side_effect=PermissionError('folder unreadable')):
            status, body = self.request('/api/library')
        self.assertEqual(status, 500)
        self.assertIn(b'Could not read the configured photo folder', body)
        self.assertEqual(self.errors, [])

    def test_proxy_disconnect_does_not_turn_success_into_upstream_failure_or_retry(self):
        self.fault = {'path':'/api/system-one', 'error':BrokenPipeError, 'write':2}
        with patch.dict(os.environ, {'TYPESAFE_API_KEY':'test-only'}), patch.object(server, 'urlopen') as upstream:
            upstream.return_value.__enter__.return_value.status = 200
            upstream.return_value.__enter__.return_value.read.return_value = b'{"answers":{}}'
            self.request('/api/system-one', 'POST', b'fixture', {'Content-Type':'multipart/form-data; boundary=test'})
            self.assertEqual(upstream.call_count, 1)
        self.assertEqual(self.statuses, [200])
        self.assertEqual(self.errors, [])

    def test_actual_upstream_failure_still_returns_502(self):
        with patch.dict(os.environ, {'TYPESAFE_API_KEY':'test-only'}), patch.object(server, 'urlopen', side_effect=URLError('offline')):
            status, body = self.request('/api/system-one', 'POST', b'fixture', {'Content-Type':'multipart/form-data; boundary=test'})
        self.assertEqual(status, 502)
        self.assertIn(b'Could not reach the TypeSafe API', body)

    def test_static_file_and_photo_disconnects_are_also_handled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.png'
            path.write_bytes(b'png')
            (Path(directory)/'index.html').write_text('<h1>Disconnect fixture</h1>')
            with patch.object(server, 'safe_path', return_value=path), patch.object(server, 'API_ONLY', False), patch.object(server, 'WEB_ROOT', Path(directory)):
                for route in ['/api/photo?path=fixture.png', '/index.html']:
                    with self.subTest(route=route):
                        self.fault = {'path':route, 'error':ConnectionResetError, 'write':2}
                        self.statuses.clear()
                        self.request(route)
                        self.assertEqual(self.statuses, [200])
                        self.assertEqual(self.errors, [])

    def test_unrelated_response_io_errors_are_not_suppressed_or_reclassified(self):
        self.fault = {'path':'/api/library', 'error':OSError, 'write':2}
        with patch.object(server, 'scan_library', return_value=[]):
            self.request('/api/library')
        self.assertEqual(self.statuses, [200])
        self.assertEqual(len(self.errors), 1)
        self.assertIs(type(self.errors[0]), OSError)
