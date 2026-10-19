"""Publication scans use isolated Git fixtures; never include real credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_public import audit, inspect_content


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.git('init','-q')
        self.git('config','user.name','Public contributor')
        self.git('config','user.email','contributor@users.noreply.github.com')
        (self.root/'.gitignore').write_text('.env\n')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL)

    def test_ignored_credentials_stay_local_but_exact_leaks_are_redacted(self):
        credential='local-'+'credential-fixture-123456'
        (self.root/'.env').write_text('TYPESAFE_API_KEY='+credential)
        (self.root/'README.md').write_text('Public project')
        self.assertFalse(audit(self.root)['findings'])
        (self.root/'bad.js').write_text(credential)
        result=audit(self.root)
        self.assertTrue(any(f['kind']=='exact-local-credential' for f in result['findings']))
        self.assertNotIn(credential,json.dumps(result))

    def test_staged_credentials_cannot_be_hidden_by_clean_worktree(self):
        credential='fixture-'+'private-api-key-12345678'
        (self.root/'.env').write_text('TYPESAFE_API_KEY='+credential)
        file=self.root/'source.js';file.write_text(credential)
        self.git('add','source.js');file.write_text('clean worktree')
        findings=audit(self.root)['findings']
        self.assertTrue(any(f['path']=='index:source.js' and f['kind']=='exact-local-credential' for f in findings))

    def test_history_and_forced_private_files_are_checked(self):
        credential='fixture-'+'historical-secret-12345678'
        (self.root/'.env').write_text('TYPESAFE_API_KEY='+credential)
        self.git('add','-f','.env');self.git('commit','-qm','fixture')
        self.git('rm','-q','--cached','.env');self.git('commit','-qm','remove fixture')
        findings=audit(self.root)['findings']
        self.assertTrue(any(f['kind']=='historical-private-file' for f in findings))
        self.assertTrue(any(f['path']=='history:.env' and f['kind']=='exact-local-credential' for f in findings))

    def test_bundle_home_paths_external_symlinks_and_identity(self):
        (self.root/'dist').mkdir()
        (self.root/'dist/app.js').write_text('/'+'home'+'/fixture-person/project')
        (self.root/'external').symlink_to(self.root.parent/'outside')
        self.git('config','user.email','private-person@example.test')
        findings=audit(self.root)['findings']
        self.assertTrue(any(f['kind']=='personal-home-path' for f in findings))
        self.assertTrue(any(f['kind']=='nonportable-or-external-symlink' for f in findings))
        self.assertTrue(any(f['kind']=='public-commit-identity-not-configured' for f in findings))
        self.assertFalse(any(f['kind']=='public-commit-identity-not-configured' for f in audit(self.root,files_only=True)['findings']))
        self.assertNotIn('private-person@example.test',json.dumps(findings))

    def test_known_token_format_is_reported_without_value(self):
        credential='hf_'+'x'*30
        findings=inspect_content('fixture.txt',credential.encode(),{})
        self.assertEqual(findings[0]['kind'],'credential-format')
        self.assertNotIn(credential,json.dumps(findings))

    def test_local_tool_tree_refs_are_separate_from_public_branch_history(self):
        credential='fixture-'+'local-snapshot-key-12345678'
        (self.root/'.env').write_text('TYPESAFE_API_KEY='+credential)
        self.git('add','-f','.env')
        tree=self.git('write-tree').decode().strip()
        self.git('update-ref','refs/codex/fixture',tree)
        self.git('read-tree','--empty')
        public=audit(self.root)
        self.assertFalse(public['findings'])
        self.assertEqual(public['localOnlyRefs'],1)
        private=audit(self.root,all_refs=True)
        self.assertTrue(any(f['kind']=='historical-private-file' for f in private['findings']))
