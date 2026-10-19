import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

from PIL import Image
import server
from layout_renderer import render


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), server.AppHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def test_invalid_render_inputs(self):
        for value in [{}, {'html':'hi', 'viewport':[]}, {'html':'hi','viewport':'huge'}]:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.base+'/api/render-html', json.dumps(value).encode(), {'Content-Type':'application/json'}))
            self.assertEqual(error.exception.code, 400)

    def test_example_ids_and_missing_files(self):
        for identifier, status in [('..%2F.env',400), ('001',404)]:
            with tempfile.TemporaryDirectory() as folder, patch.object(server,'DEFAULT_OUTPUT',Path(folder)):
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.base+'/api/design2code/html?id='+identifier)
                self.assertEqual(error.exception.code,status)

    def test_pairs_only_and_html_served_as_json(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(server,'DEFAULT_OUTPUT',Path(folder)):
            root=Path(folder)
            (root/'001.html').write_text('<script>alert(1)</script>')
            (root/'001.png').write_bytes(b'png')
            (root/'002.html').write_text('unpaired')
            with urlopen(self.base+'/api/design2code/examples') as response:
                self.assertEqual(len(json.load(response)['examples']),1)
            with urlopen(self.base+'/api/design2code/html?id=001') as response:
                self.assertIn('application/json',response.headers['Content-Type'])
                self.assertEqual(json.load(response)['html'],'<script>alert(1)</script>')

    def test_html_dataset_is_hidden_from_photo_tools_and_still_available_to_validator(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            layout=root/'data/Design2Code-hf'
            layout.mkdir(parents=True)
            (layout/'001.html').write_text('<h1>Layout fixture</h1>')
            (layout/'001.png').write_bytes(b'png')
            (layout/'nested').mkdir()
            (layout/'nested/screenshot.png').write_bytes(b'png')
            photos=root/'data/dogs'
            photos.mkdir()
            (photos/'dog.png').write_bytes(b'png')
            metadata=root/'.library.json'
            metadata.write_text(json.dumps({'datasets':{
                'data/Design2Code-hf':{'name':'Saved HTML screenshots'},
                'data/Design2Code-hf/nested':{'name':'Saved nested screenshots'},
            }}))
            with patch.object(server,'photo_root',return_value=root), patch.object(server,'DEFAULT_OUTPUT',layout), patch.object(server,'LIBRARY_META',metadata):
                # Existing metadata must not bring the excluded folders back as empty datasets.
                datasets=server._scan_library()
                self.assertEqual([dataset['id'] for dataset in datasets],['data/dogs'])
                self.assertIn('data/Design2Code-hf',json.loads(metadata.read_text())['datasets'])
                with urlopen(self.base+'/api/design2code/examples') as response:
                    self.assertEqual([item['id'] for item in json.load(response)['examples']],['001'])
                with urlopen(self.base+'/api/design2code/image?id=001') as response:
                    self.assertEqual(response.read(),b'png')
                with urlopen(self.base+'/api/design2code/html?id=001') as response:
                    self.assertEqual(json.load(response)['html'],'<h1>Layout fixture</h1>')
                with patch.object(server,'photo_root',return_value=layout):
                    self.assertEqual(server._scan_library(),[])

    def test_duplicate_download_request_starts_one_job(self):
        entered=threading.Event(); release=threading.Event()
        def fake(*args):
            entered.set(); release.wait(5); return {'count':484}
        with patch.object(server,'download_design2code',side_effect=fake) as download:
            server.DOWNLOAD_STATE['status']='idle'
            server.start_dataset_download(); self.assertTrue(entered.wait(2))
            server.start_dataset_download()
            self.assertEqual(download.call_count,1)
            release.set()
        server.DOWNLOAD_STATE['status']='idle'


class RenderTests(unittest.TestCase):
    def test_external_requests_never_reach_network(self):
        requests=[]
        class Observer(server.AppHandler):
            def do_GET(self):
                requests.append(self.path)
                self._json(200,{})
        http=ThreadingHTTPServer(('127.0.0.1',0),Observer)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{http.server_port}/private'
        try:
            render(f'<body><img src="{url}"><script>fetch("{url}")</script>',390,844)
            self.assertEqual(requests,[])
        finally:
            http.shutdown();http.server_close()

    def test_sizes_scripts_and_resource_isolation(self):
        for width,height in [(1280,900),(390,844)]:
            source='''<body><style>body{margin:0;background:#f00}</style><script>
            document.body.style.background='rgb(0, 128, 0)';
            fetch('http://127.0.0.1:1/private').then(()=>document.body.style.background='blue');
            </script><iframe src="file:///etc/passwd"></iframe>'''
            image=Image.open(io.BytesIO(render(source,width,height)))
            self.assertEqual(image.size,(width,height))
            self.assertEqual(image.getpixel((width-1,height-1))[:3],(0,128,0))


if __name__=='__main__': unittest.main()


class LibraryScanTests(unittest.TestCase):
    def test_concurrent_requests_share_scan_and_later_rescan_is_fresh(self):
        from concurrent.futures import ThreadPoolExecutor
        original=dict(server.LAST_LIBRARY_SCAN)
        server.LAST_LIBRARY_SCAN.update(root=None,finished=0,datasets=None)
        barrier=threading.Barrier(8)
        try:
            with patch.object(server,'_scan_library',return_value=[{'id':'data/Design2Code-hf'}]) as scan, patch.object(server.time,'monotonic',return_value=1) as clock:
                def request():
                    barrier.wait()
                    return server.scan_library()
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results=list(pool.map(lambda _:request(),range(8)))
                self.assertEqual(scan.call_count,1)
                self.assertEqual(len(results),8)
                clock.return_value=2
                server.scan_library()
                self.assertEqual(scan.call_count,2)
        finally:
            server.LAST_LIBRARY_SCAN.clear();server.LAST_LIBRARY_SCAN.update(original)
