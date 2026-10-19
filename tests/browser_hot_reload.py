"""Optional real pnpm-start smoke test on temporary ports, with no paid API calls.

Touches source timestamps (never contents) to verify CSS updates, JS refreshes,
and backend restarts. Owns and stops only its temporary process group.
Run from the repository root: .venv/bin/python tests/browser_hot_reload.py
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def free_ports():
    sockets=[socket.socket(),socket.socket()]
    try:
        for connection in sockets:connection.bind(('127.0.0.1',0))
        return [connection.getsockname()[1] for connection in sockets]
    finally:
        for connection in sockets:connection.close()


def run():
    port,api_port=free_ports()
    base=f'http://127.0.0.1:{port}'
    environment={**os.environ,'PORT':str(port),'API_PORT':str(api_port)}
    with tempfile.TemporaryDirectory() as directory:
        log=Path(directory)/'start.log'
        with log.open('w') as output:
            process=subprocess.Popen(['pnpm','start'],cwd=ROOT,env=environment,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise RuntimeError(log.read_text())
                    try:
                        with urlopen(base+'/api/health',timeout=1) as response:
                            if json.load(response)['ok']:break
                    except OSError:time.sleep(.1)
                else:raise RuntimeError('Vite/API proxy did not become ready: '+log.read_text())
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    try:
                        page=browser.new_page()
                        page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
                        page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
                        page.route('**/api/library',lambda route:route.fulfill(json={'datasets':[]}))
                        page.route('**/api/design2code/examples',lambda route:route.fulfill(json={'examples':[]}))
                        page.route('**/api/design2code/status',lambda route:route.fulfill(json={'status':'idle'}))
                        messages=[]
                        module_responses=[]
                        page.on('response',lambda response:module_responses.append(response.status) if urlsplit(response.url).path=='/api.js' else None)
                        def websocket(socket):
                            socket.on('framereceived',lambda payload:messages.append(json.loads(payload)))
                        page.on('websocket',websocket)
                        page.goto(base+'/tools/find',wait_until='networkidle')
                        page.wait_for_function("document.querySelector('#breadcrumbCurrent').textContent === 'Find objects'",timeout=10000)
                        assert module_responses and all(status==200 for status in module_responses),'Frontend API module was incorrectly proxied'
                        errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        os.utime(ROOT/'web/styles.css',None)
                        deadline=time.monotonic()+10
                        while time.monotonic()<deadline:
                            page.wait_for_timeout(100)
                            if any(m.get('type')=='update' and any(u.get('type')=='css-update' for u in m.get('updates',[])) for m in messages):break
                        else:raise AssertionError('No CSS hot-update event')
                        with page.expect_navigation(wait_until='domcontentloaded',timeout=10000):
                            os.utime(ROOT/'web/tools/find/v3.js',None)
                        assert page.url.endswith('/tools/find')
                        assert any(m.get('type')=='full-reload' for m in messages)
                        assert not errors,errors
                    finally:browser.close()
                before=log.read_text().count('Jevision prototype API listening')
                os.utime(ROOT/'server.py',None)
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    if log.read_text().count('Jevision prototype API listening')>before:
                        with urlopen(base+'/api/health',timeout=2) as response:assert json.load(response)['ok']
                        break
                    time.sleep(.1)
                else:raise AssertionError('API did not restart after Python edit: '+log.read_text())
                print('PASS: pnpm start, custom-port API proxy, CSS hot update, JS page refresh, and Python auto-restart.')
            finally:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
        deadline=time.monotonic()+10
        while True:
            listening=[]
            for number in [port,api_port]:
                connection=socket.socket()
                try:
                    connection.settimeout(.2)
                    if connection.connect_ex(('127.0.0.1',number))==0:listening.append(number)
                finally:connection.close()
            if not listening:break
            assert time.monotonic()<deadline,'Temporary server survived shutdown'
            time.sleep(.1)


if __name__=='__main__':run()
