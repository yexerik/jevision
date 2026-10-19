import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.download_photo_datasets import install, relative_path


class PhotoDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'source.zip'
        self.content = b'original photo bytes'
        self.spec = {'id': 'hymenoptera', 'dataset': 'thedatasith/hymenoptera',
                     'version': 5, 'source': 'https://www.kaggle.com/datasets/thedatasith/hymenoptera',
                     'selection': 'train only', 'files': [
                         {'path': 'ants/example.jpg', 'sourcePath': 'train/ants/example.jpg',
                          'sha256': hashlib.sha256(self.content).hexdigest()}]}
        with ZipFile(self.archive, 'w') as archive:
            archive.writestr('train/ants/example.jpg', self.content)
            archive.writestr('val/ants/held-out.jpg', b'validation image')
            archive.writestr('../../escape.jpg', b'unselected unsafe member')

    def test_selected_images_only_and_no_download_on_repeat(self):
        output = self.root / '.photo'
        self.assertEqual(install(output, self.spec, self.archive), 1)
        self.assertEqual((output / 'hymenoptera/ants/example.jpg').read_bytes(), self.content)
        self.assertFalse((self.root / 'escape.jpg').exists())
        self.assertFalse(list(output.rglob('held-out.jpg')))
        with patch('scripts.download_photo_datasets.urlopen', side_effect=AssertionError('network')):
            self.assertEqual(install(output, self.spec), 1)
        self.assertTrue((output / 'hymenoptera/provenance.json').exists())

    def test_corruption_and_extra_images_are_rejected(self):
        output = self.root / '.photo'
        install(output, self.spec, self.archive)
        image = output / 'hymenoptera/ants/example.jpg'
        image.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'verification failed'):
            install(output, self.spec, verify_only=True)
        image.write_bytes(self.content)
        (image.parent / 'extra.jpg').write_bytes(b'extra')
        with self.assertRaisesRegex(RuntimeError, 'extra 1'):
            install(output, self.spec, verify_only=True)

    def test_bad_source_never_publishes_partial_dataset(self):
        output = self.root / '.photo'
        with ZipFile(self.archive, 'w') as archive:
            archive.writestr('train/ants/example.jpg', b'wrong version')
        with self.assertRaisesRegex(RuntimeError, 'verification failed'):
            install(output, self.spec, self.archive)
        self.assertFalse((output / 'hymenoptera').exists())
        self.assertEqual(list(output.iterdir()), [])

    def test_missing_dataset_verify_never_downloads(self):
        with patch('scripts.download_photo_datasets.urlopen', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                install(self.root / '.photo', self.spec, verify_only=True)

    def test_manifest_destination_cannot_escape_output(self):
        for value in ['../escape.jpg', '/escape.jpg', 'C:/escape.jpg', r'ants\escape.jpg']:
            with self.assertRaises(ValueError):
                relative_path(value)


if __name__ == '__main__':
    unittest.main()
