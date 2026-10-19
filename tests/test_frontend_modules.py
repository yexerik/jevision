"""Regression checks for modular benchmark snapshots and historical replay."""
from pathlib import Path
import tempfile
import unittest

from scripts.frontend_modules import collect_modules, freeze_modules, verify_modules
from scripts.benchmark_find import benchmark_source


class FrontendSnapshotTests(unittest.TestCase):
    def test_strategy_changes_cannot_escape_frozen_snapshot_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            hashes=freeze_modules(out, 'tools/find/engine.js')
            self.assertTrue(all(f'tools/find/v{i}.js' in hashes for i in range(1,5)))
            self.assertIn('tools/find/v6/combined.js',hashes)
            self.assertIn('tools/find/v6/prompts.js',hashes)
            verify_modules(out, hashes)
            source=benchmark_source(out, {'moduleHashes':hashes})
            self.assertIn('createFindRuntime', source)
            self.assertNotIn('init();', source)
            (out/'modules/tools/find/v3.js').write_text('modified')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                benchmark_source(out, {'moduleHashes':hashes})

    def test_historical_monolithic_bridge_still_removes_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            (out/'app.js').write_text('import { initLayout } from "./layout.js";\nconst oldEngine=true;\ninit();\n')
            source=benchmark_source(out, {})
            self.assertIn('oldEngine=true',source)
            self.assertNotIn('init();',source)
            self.assertNotIn('initLayout',source)

    def test_tool_imports_do_not_boot_the_application_shell(self):
        modules=collect_modules('tools/find/engine.js')
        self.assertNotIn('app.js',modules)
        for entry in ['tools/count.js','tools/find.js','tools/search.js']:
            self.assertNotIn('app.js',collect_modules(entry))

    def test_snapshot_follows_multiline_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'entry.js').write_text('import {\n  helper,\n} from "./helper.js";\nexport { helper };')
            (root/'helper.js').write_text('export const helper=1;')
            self.assertEqual(set(collect_modules('entry.js',root)),{'entry.js','helper.js'})
