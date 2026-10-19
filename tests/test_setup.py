import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import setup


class SetupTests(unittest.TestCase):
    def test_unsupported_python_fails_before_installing_dependencies(self):
        with patch.object(setup.sys, 'version_info', (3, 9)):
            with self.assertRaisesRegex(RuntimeError, 'Python 3.10'):
                setup.prerequisites(Path('.'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.env.example').write_text('TYPESAFE_API_KEY=placeholder\nPHOTO_ROOT=.photo\nPORT=8765\n')

    def test_fresh_config_and_repeat(self):
        self.assertEqual(setup.configure_env(self.root)['PHOTO_ROOT'], '.photo')
        path = self.root / '.env'
        before = path.read_bytes()
        setup.configure_env(self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_preserves_key_comments_and_custom_root(self):
        original = '# My settings\nTYPESAFE_API_KEY=existing-private-key\nPHOTO_ROOT=custom-photos\nPORT=9999\n'
        (self.root / '.env').write_text(original)
        config = setup.configure_env(self.root)
        self.assertEqual(config['PHOTO_ROOT'], 'custom-photos')
        self.assertEqual((self.root / '.env').read_text(), original)

    def test_existing_key_without_root_is_preserved(self):
        (self.root / '.env').write_text('TYPESAFE_API_KEY=existing-private-key')
        config = setup.configure_env(self.root)
        self.assertEqual(config['TYPESAFE_API_KEY'], 'existing-private-key')
        self.assertEqual(config['PHOTO_ROOT'], '.photo')

    def test_empty_root_is_replaced_without_duplicate(self):
        (self.root / '.env').write_text("# root\nPHOTO_ROOT=''\nPORT=9876\n")
        config = setup.configure_env(self.root)
        self.assertEqual(config['PHOTO_ROOT'], '.photo')
        self.assertEqual(config['PORT'], '9876')
        self.assertEqual((self.root / '.env').read_text().count('PHOTO_ROOT='), 1)

    def test_setup_runs_both_downloaders_with_effective_config(self):
        (self.root / '.env').write_text('TYPESAFE_API_KEY=existing-private-key\nPHOTO_ROOT=custom\n')
        python = self.root / '.venv/bin/python'
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(setup, 'prerequisites', return_value='pnpm'), patch.object(setup, 'python_environment', return_value=python), patch.object(setup, 'run') as run, patch.object(setup, 'install_chromium') as browser, contextlib.redirect_stdout(output):
            setup.setup(self.root)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], [python, '-m', 'pip', 'install', '--upgrade', 'pip>=26.2,<27'])
        self.assertIn(['pnpm', 'install', '--frozen-lockfile'], commands)
        self.assertIn([python, self.root / 'scripts/download_photo_datasets.py', '--output', self.root / 'custom'], commands)
        self.assertIn([python, self.root / 'scripts/download_design2code.py'], commands)
        browser.assert_called_once()
        self.assertEqual(run.call_args_list[-1].args[2]['TYPESAFE_API_KEY'], 'existing-private-key')
        self.assertNotIn('existing-private-key', output.getvalue())
        self.assertIn('Setup complete', output.getvalue())

    def test_failure_stops_before_success_message(self):
        output = io.StringIO()
        with patch.object(setup, 'prerequisites', return_value='pnpm'), patch.object(setup, 'python_environment', return_value=Path('python')), patch.object(setup, 'run', side_effect=subprocess.CalledProcessError(1, ['pip'])), contextlib.redirect_stdout(output):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.setup(self.root)
        self.assertNotIn('Setup complete', output.getvalue())
        self.assertFalse((self.root / '.env').exists())

    def test_linux_missing_libraries_are_installed_and_rechecked(self):
        missing = subprocess.CompletedProcess([], 1, '', 'Host system is missing dependencies to run browsers.')
        success = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(setup.sys, 'platform', 'linux'), patch.object(setup, 'run') as run, patch.object(setup.subprocess, 'run', side_effect=[missing, success]), contextlib.redirect_stdout(io.StringIO()):
            setup.install_chromium(Path('python'), self.root, {})
        self.assertEqual(run.call_args_list[-1].args[0], [Path('python'), '-m', 'playwright', 'install-deps', 'chromium'])

    def test_missing_package_managers_do_not_modify_project(self):
        with patch.object(setup.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Node.js'):
                setup.prerequisites(self.root)
        self.assertFalse((self.root / '.env').exists())


if __name__ == '__main__':
    unittest.main()
