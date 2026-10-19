"""Exercise concurrent library writes through the actual local HTTP endpoints."""
from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import server


class LibraryIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        self.metadata = self.root / 'library.json'
        class QuietHandler(server.AppHandler):
            def log_message(self, *args):
                pass
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.patches = [patch.object(server, 'photo_root', return_value=self.photos),
                        patch.object(server, 'LIBRARY_META', self.metadata)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def post(self, path, payload, content_type='application/json'):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=10)
        try:
            body = json.dumps(payload).encode() if isinstance(payload, dict) else payload
            connection.request('POST', path, body, {'Content-Type': content_type})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_concurrent_dataset_edits_preserve_every_dataset(self):
        for index in range(6):
            (self.photos / f'dataset-{index}').mkdir()
        original = server.load_library_meta
        def slow_read():
            metadata = original()
            time.sleep(.025)  # Widen the real read/modify/write race.
            return metadata
        with patch.object(server, 'load_library_meta', side_effect=slow_read):
            with ThreadPoolExecutor(max_workers=6) as pool:
                responses = list(pool.map(lambda index: self.post('/api/dataset-settings', {
                    'id': f'dataset-{index}', 'name': f'Edited {index}', 'target': 'ants',
                }), range(6)))
        self.assertTrue(all(status == 200 for status, _ in responses), responses)
        datasets = json.loads(self.metadata.read_text())['datasets']
        self.assertEqual(len(datasets), 6)
        self.assertEqual({value['name'] for value in datasets.values()}, {f'Edited {i}' for i in range(6)})

    def test_stale_result_saves_keep_newer_and_unrelated_results_and_settings(self):
        folder = self.photos / 'ants'
        folder.mkdir()
        for name in ['first.png', 'second.png']:
            (folder / name).write_bytes(b'fixture')
        self.post('/api/dataset-settings', {'id': 'ants', 'name': 'Renamed dataset', 'target': 'bees'})
        newer = {'target': 'ants', 'choice': '2', 'createdAt': 200}
        older = {'target': 'ants', 'choice': '1', 'createdAt': 100}
        other = {'target': 'bees', 'choice': '3', 'createdAt': 300}
        self.assertEqual(self.post('/api/dataset-settings', {'id': 'ants', 'images': [
            {'path': 'ants/first.png', 'results': [newer]},
        ]})[0], 200)
        self.assertEqual(self.post('/api/dataset-settings', {'id': 'ants', 'images': [
            {'path': 'ants/first.png', 'results': [older, other]},
            {'path': 'ants/second.png', 'results': [newer]},
        ]})[0], 200)
        self.assertEqual(self.post('/api/dataset-settings', {'id': 'ants', 'images': [
            {'path': 'ants/first.png', 'results': []},
        ]})[0], 200)
        dataset = json.loads(self.metadata.read_text())['datasets']['ants']
        self.assertEqual(dataset['name'], 'Renamed dataset')
        self.assertEqual(dataset['target'], 'bees')
        self.assertCountEqual(dataset['results']['ants/first.png'], [newer, other])
        self.assertEqual(dataset['results']['ants/second.png'], [newer])

    def test_concurrent_uploads_keep_all_bytes_under_distinct_names(self):
        (self.photos / 'ants').mkdir()
        (self.photos / 'ants' / 'same.png').write_bytes(b'existing user photo')
        def upload(index):
            content = b'photo-fixture-' + str(index).encode()
            body = (b'--fixture\r\nContent-Disposition: form-data; name="datasetId"\r\n\r\nants\r\n'
                    b'--fixture\r\nContent-Disposition: form-data; name="photos"; filename="same.png"\r\n'
                    b'Content-Type: image/png\r\n\r\n' + content + b'\r\n--fixture--\r\n')
            status, payload = self.post('/api/dataset-photos', body, 'multipart/form-data; boundary=fixture')
            self.assertEqual(status, 201)
            return payload['paths'][0], content
        with ThreadPoolExecutor(max_workers=6) as pool:
            uploads = list(pool.map(upload, range(6)))
        self.assertEqual(len({path for path, _ in uploads}), 6)
        for path, content in uploads:
            self.assertEqual((self.photos / path).read_bytes(), content)
        self.assertEqual((self.photos / 'ants' / 'same.png').read_bytes(), b'existing user photo')

    def test_malformed_result_arrays_return_errors_without_changing_saved_data(self):
        (self.photos / 'ants').mkdir()
        self.post('/api/dataset-settings', {'id': 'ants', 'name': 'Keep me', 'target': 'ants'})
        before = self.metadata.read_bytes()
        for images in [None, {}, ['bad'], [{'results': None}], [{'results': [None]}],
                       [{'results': [{'target': 'ants', 'createdAt': 'invalid'}]}],
                       [{'results': [{'target': 'ants', 'createdAt': 10**400}]}],
                       [{'results': [{'target': 'ants', 'createdAt': float('inf')}]}],
                       [{'results': [{'target': 'ants', 'createdAt': True}]}]]:
            with self.subTest(images=images):
                status, _ = self.post('/api/dataset-settings', {'id': 'ants', 'name': 'Bad edit', 'images': images})
                self.assertEqual(status, 400)
                self.assertEqual(self.metadata.read_bytes(), before)
