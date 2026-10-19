"""Check reload detection, crash recovery, and child cleanup without real API calls."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from scripts.run_server import source_snapshot

ROOT=Path(__file__).resolve().parents[1]


class ServerReloadTests(unittest.TestCase):
    def test_only_source_and_environment_changes_invalidate_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            original=source_snapshot(root)
            (root/'data').mkdir()
            (root/'data/page.png').write_bytes(b'png')
            (root/'result.log').write_text('output')
            self.assertEqual(source_snapshot(root),original)
            (root/'.env').write_text('PORT=8877')
            self.assertNotEqual(source_snapshot(root),original)
            (root/'.env').unlink()
            self.assertEqual(source_snapshot(root),original)
            (root/'scripts').mkdir()
            (root/'scripts/helper.py').write_text('x=1')
            self.assertNotEqual(source_snapshot(root),original)

    def test_restarts_after_edit_recovers_after_crash_and_cleans_up_child(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            service=root/'server.py'
            records=root/'starts.txt'
            source="import os,time\nfrom pathlib import Path\nwith Path('starts.txt').open('a') as f: f.write(str(os.getpid())+'\\n')\ntime.sleep(60)\n"
            service.write_text(source)
            code='from pathlib import Path; from scripts.run_server import watch; import sys; watch([sys.executable,sys.argv[1]],Path(sys.argv[2]),.05)'
            log=root/'watch.log'
            output=log.open('w')
            process=subprocess.Popen([sys.executable,'-c',code,str(service),str(root)],cwd=ROOT,stdout=output,stderr=output)
            pids=[]
            def wait_for_starts(count):
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    if records.exists():
                        values=[int(line) for line in records.read_text().splitlines()]
                        if len(values)>=count:
                            return values
                    time.sleep(.05)
                self.fail(f'Expected {count} child starts')
            try:
                pids=wait_for_starts(1)
                service.write_text(source+'# edit\n')
                pids=wait_for_starts(2)
                self.assertNotEqual(pids[0],pids[1])
                with self.assertRaises(ProcessLookupError):os.kill(pids[0],0)
                # A syntax error must not leave the supervisor unable to recover.
                service.write_text('this is invalid python !!!\n')
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    if 'API server exited' in log.read_text():break
                    time.sleep(.05)
                else:self.fail('Supervisor did not observe the syntax-error crash')
                service.write_text(source+'# recovered\n')
                pids=wait_for_starts(3)
                (root/'.env').write_text('PORT=8877\n')
                pids=wait_for_starts(4)
            finally:
                process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
                output.close()
            self.assertEqual(process.returncode,0)
            for pid in pids:
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
