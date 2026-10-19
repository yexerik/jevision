"""Project-scoped stop, watcher shutdown, and in-flight HTTP drain regressions."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from scripts.services import stop
import server

ROOT=Path(__file__).resolve().parents[1]
FIXTURE='''import os,signal,time
from pathlib import Path
with Path('starts.txt').open('a') as file:file.write(str(os.getpid())+'\\n')
stopping=False
def shutdown(*_):
    global stopping
    if stopping:return
    stopping=True
    time.sleep(.4)
    Path('stopped.txt').write_text('drained')
    raise SystemExit(0)
signal.signal(signal.SIGTERM,shutdown)
while True:time.sleep(.02)
'''


def wait_file(path):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if path.exists() and path.stat().st_size:return path.read_text()
        time.sleep(.02)
    raise AssertionError(f'Timed out waiting for {path.name}')


class ServiceTests(unittest.TestCase):
    def test_shutdown_download_checkpoint_cleans_unpublished_staging(self):
        import threading
        entered=threading.Event();release=threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def download(output,progress):
                with tempfile.TemporaryDirectory(dir=root,prefix='.stage-') as temporary:
                    (Path(temporary)/'partial.png').write_bytes(b'partial')
                    entered.set();release.wait(5)
                    progress(completed=1)
            try:
                server.SERVER_STOPPING.clear()
                with patch.object(server,'download_design2code',side_effect=download):
                    server.start_dataset_download()
                    self.assertTrue(entered.wait(2))
                    with server.DOWNLOAD_LOCK:threads=list(server.DOWNLOAD_THREADS)
                    server.SERVER_STOPPING.set();release.set()
                    for thread in threads:thread.join(timeout=3)
                self.assertFalse(any(root.iterdir()))
                self.assertEqual(server.download_status()['status'],'failed')
                self.assertIn('server shutdown',server.download_status()['error'])
            finally:
                release.set();server.SERVER_STOPPING.clear()

    def test_stop_scopes_project_waits_without_force_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as unrelated:
            root=Path(folder);other=Path(unrelated)
            for directory in [root,other]:(directory/'server.py').write_text(FIXTURE)
            owned=subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root)
            outside=subprocess.Popen([sys.executable,str(other/'server.py')],cwd=other)
            # Mentioning a project path in an argument must not count as executing that script.
            mention=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)',str(root/'server.py')],cwd=root)
            try:
                wait_file(root/'starts.txt');wait_file(other/'starts.txt')
                with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(stop(root,timeout=.05),1)
                    self.assertIsNone(owned.poll(),'Graceful handler was force-killed')
                    self.assertEqual(stop(root,timeout=3),0)
                    self.assertEqual(stop(root,timeout=1),0)
                self.assertEqual(owned.wait(timeout=2),0)
                self.assertEqual((root/'stopped.txt').read_text(),'drained')
                self.assertIsNone(outside.poll())
                self.assertIsNone(mention.poll())
            finally:
                for process in [owned,outside,mention]:
                    if process.poll() is None:process.terminate()
                    process.wait(timeout=5)

    def test_stop_shuts_watcher_before_api_can_respawn(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'scripts').mkdir()
            shutil.copyfile(ROOT/'scripts/run_server.py',root/'scripts/run_server.py')
            (root/'server.py').write_text(FIXTURE)
            watcher=subprocess.Popen([sys.executable,str(root/'scripts/run_server.py'),'--api-only','--reload'],cwd=root,stdout=subprocess.DEVNULL)
            try:
                wait_file(root/'starts.txt')
                with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(stop(root,timeout=5),0)
                self.assertEqual(watcher.wait(timeout=2),0)
                self.assertEqual(len((root/'starts.txt').read_text().splitlines()),1)
                self.assertEqual((root/'stopped.txt').read_text(),'drained')
            finally:
                if watcher.poll() is None:watcher.terminate()
                watcher.wait(timeout=5)

    def test_python_server_drains_in_flight_http_request_on_sigterm(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            code='''from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys,time
from server import serve_gracefully
root=Path(sys.argv[1])
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  (root/'entered').write_text('yes')
  time.sleep(.4)
  self.send_response(200);self.end_headers();self.wfile.write(b'drained')
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
(root/'port').write_text(str(server.server_port))
serve_gracefully(server)
'''
            process=subprocess.Popen([sys.executable,'-c',code,str(root)],cwd=ROOT,stdout=subprocess.DEVNULL)
            try:
                port=int(wait_file(root/'port'))
                def request():
                    with urlopen(f'http://127.0.0.1:{port}/slow',timeout=5) as response:return response.read()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending=pool.submit(request)
                    wait_file(root/'entered')
                    process.send_signal(signal.SIGTERM)
                    self.assertEqual(pending.result(timeout=5),b'drained')
                self.assertEqual(process.wait(timeout=5),0)
            finally:
                if process.poll() is None:process.terminate()
                process.wait(timeout=5)
