"""Ensure local endpoints do not disclose paths or accept cross-site credential use."""
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import server


class RequestPrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.AppHandler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def request(self,path='/api/health',method='GET',headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        try:
            connection.request(method,path,headers=headers or {})
            response=connection.getresponse()
            return response.status,json.loads(response.read())
        finally:connection.close()

    def test_library_response_omits_absolute_photo_root(self):
        with patch.object(server,'scan_library',return_value=[]):
            status,payload=self.request('/api/library')
        self.assertEqual(status,200)
        self.assertEqual(payload,{'datasets':[]})

    def test_fresh_clone_placeholder_is_not_a_configured_api_key(self):
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':'your_typesafe_api_key_here'}),patch.object(server,'urlopen') as upstream:
            self.assertFalse(self.request()[1]['apiKeyConfigured'])
            self.assertEqual(self.request('/api/system-one','POST')[0],503)
            upstream.assert_not_called()

    def test_nonlocal_hosts_and_cross_site_origins_are_rejected_before_proxy(self):
        cases=[{'Host':'external.invalid'}, {'Origin':'https://external.invalid'},
               {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}, {'Host':'localhost:invalid'}]
        with patch.object(server,'urlopen') as upstream:
            for headers in cases:
                with self.subTest(headers=headers):
                    status,_=self.request('/api/system-one','POST',headers)
                    self.assertEqual(status,403)
            upstream.assert_not_called()

    def test_same_origin_and_vite_preserved_host_are_allowed(self):
        host=f'127.0.0.1:{self.http.server_port}'
        for headers in [{},{'Origin':'http://'+host}, {'Host':'127.0.0.1:9876','Origin':'http://127.0.0.1:9876'}]:
            self.assertEqual(self.request(headers=headers)[0],200)

    def test_real_vite_proxy_preserves_browser_origin_and_rejects_other_origins(self):
        root=Path(__file__).resolve().parents[1]
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        env={**os.environ,'PORT':str(port),'API_PORT':str(self.http.server_port)}
        with tempfile.TemporaryFile() as log:
            process=subprocess.Popen(['node',str(root/'node_modules/vite/bin/vite.js'),
                                      '--config',str(root/'vite.config.js')],
                                     cwd=root,env=env,stdout=log,stderr=log)
            def through_vite(path,method='GET',headers=None,body=None):
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                try:
                    connection.request(method,path,body=body,headers=headers or {})
                    response=connection.getresponse()
                    return response.status,response.read()
                finally:connection.close()
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    if process.poll() is not None:self.fail('Vite exited before startup')
                    try:
                        if through_vite('/api/health')[0]==200:break
                    except OSError:pass
                    time.sleep(.05)
                else:self.fail('Vite did not become ready')
                for host in [f'127.0.0.1:{port}',f'localhost:{port}']:
                    headers={'Host':host,'Origin':'http://'+host,'Sec-Fetch-Site':'same-origin'}
                    with self.subTest(host=host):
                        self.assertEqual(through_vite('/api/health',headers=headers)[0],200)
                        # Invalid input reaches validation without creating a dataset.
                        status,body=through_vite('/api/datasets','POST',
                            headers|{'Content-Type':'application/json'},b'{}')
                        self.assertEqual(status,400)
                        self.assertIn('dataset name',json.loads(body)['error'])
                for origin in ['https://external.invalid',f'http://127.0.0.1:{self.http.server_port}']:
                    self.assertEqual(through_vite('/api/datasets','POST',
                        {'Origin':origin,'Content-Type':'application/json'},b'{}')[0],403)
                status,body=through_vite('/api.js')
                self.assertEqual(status,200)
                self.assertIn(b'export async function sendImageJudgment',body)
            finally:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
