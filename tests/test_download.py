import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from PIL import Image
from scripts.download_design2code import download, REVISION


class DownloadTests(unittest.TestCase):
    def test_pairs_provenance_token_and_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); card=root/'card.md';card.write_text('license: odc-by')
            rows=[{'image':Image.new('RGB',(2,2)), 'text':'<p>Reference</p>'} for _ in range(484)]
            with patch.dict(os.environ,{'HUGGING_FACE_API':'test-secret'}), patch('datasets.load_dataset',return_value=rows) as load, patch('huggingface_hub.HfApi') as api, patch('huggingface_hub.hf_hub_download',return_value=str(card)):
                api.return_value.dataset_info.return_value.sha='fixed-revision'
                output=root/'data'
                result=download(output)
                self.assertEqual(result['count'],484)
                self.assertEqual((output/'001.html').read_text(),'<p>Reference</p>')
                self.assertTrue((output/'484.png').is_file())
                self.assertNotIn('test-secret',(output/'manifest.json').read_text())
                self.assertEqual(load.call_args.kwargs['token'],'test-secret')
                self.assertEqual(load.call_args.kwargs['revision'],REVISION)
                self.assertEqual(download(output),result)
                self.assertEqual(load.call_count,1)

    def test_existing_unmanaged_folder_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            (output/'important.html').write_text('preserve this')
            with self.assertRaisesRegex(RuntimeError,'valid manifest'): download(output)
            self.assertEqual((output/'important.html').read_text(),'preserve this')

    def test_interrupted_download_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data'
            bad_image=Mock();bad_image.save.side_effect=OSError('disk failed')
            with patch('datasets.load_dataset',return_value=[{'image':bad_image,'text':'html'}]), patch('huggingface_hub.HfApi') as api:
                api.return_value.dataset_info.return_value.sha='revision'
                with self.assertRaises(OSError): download(output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_wrong_revision_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            manifest={'dataset':'SALT-NLP/Design2Code-hf','revision':'different','count':484}
            (output/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(RuntimeError,'different revision'):download(output)
            self.assertEqual(json.loads((output/'manifest.json').read_text()),manifest)

    def test_short_dataset_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data'
            with patch('datasets.load_dataset',return_value=[{'image':Image.new('RGB',(2,2)),'text':'html'}]):
                with self.assertRaisesRegex(RuntimeError,'484'):download(output)
            self.assertFalse(output.exists())
