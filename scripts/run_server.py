"""Launch the API with project dependencies and optional development reloads.

The polling supervisor watches Python source and .env, debounces edits, and
replaces the child server. It ignores image/data/output changes and cleans up
the child on exit. Production runs exec the server without a watcher.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def source_snapshot(root):
    """Include absent fixed files so .env creation/deletion also triggers reload."""
    paths = {root / 'server.py', root / 'layout_renderer.py', root / '.env'}
    paths.update((root / 'scripts').rglob('*.py'))
    snapshot = {}
    for path in paths:
        try:
            stat = path.stat()
            snapshot[path] = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            snapshot[path] = None
    return snapshot


def stop_server(child):
    if child.poll() is None:
        child.terminate()
        # The API drains requests/rendering/download cleanup; do not kill it
        # merely because a legitimate operation takes more than five seconds.
        child.wait()


def watch(command, root=ROOT, interval=0.25):
    """Keep a single child; after a crash, wait for an edit rather than respawn-loop."""
    stopping = False
    def request_stop(*_):
        nonlocal stopping
        stopping = True

    handlers = {sig:signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    child = None
    previous = source_snapshot(root)
    changed_at = None
    crash_reported = False
    environment = {**os.environ, 'PYTHONUNBUFFERED':'1'}
    try:
        print('[reload] Watching server.py, layout_renderer.py, scripts/**/*.py, and .env', flush=True)
        child = subprocess.Popen(command, cwd=root, env=environment)
        while not stopping:
            current = source_snapshot(root)
            if current != previous:
                previous = current
                changed_at = time.monotonic()
            if changed_at is not None and time.monotonic() - changed_at >= interval:
                print('[reload] Source/config changed; restarting API server.', flush=True)
                stop_server(child)
                child = subprocess.Popen(command, cwd=root, env=environment)
                changed_at = None
                crash_reported = False
            if child.poll() is not None and not crash_reported:
                print('[reload] API server exited; waiting for a source/config edit.', flush=True)
                crash_reported = True
            time.sleep(interval)
    finally:
        if child is not None:
            stop_server(child)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main():
    python = ROOT / '.venv' / 'bin' / 'python'
    if not python.is_file():
        python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    executable = str(python) if python.is_file() else sys.executable
    args = sys.argv[1:]
    command = [executable, str(ROOT / 'server.py'), *(arg for arg in args if arg != '--reload')]
    if '--reload' in args:
        watch(command)
    else:
        os.execv(executable, command)


if __name__ == '__main__':
    main()
