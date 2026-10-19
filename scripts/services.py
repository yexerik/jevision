"""Start/stop this project's local services without killing unrelated processes.

The supervisor owns Vite and the API watcher. Stop discovers exact project entry
points on Linux/WSL (including legacy standalone servers), verifies process start
identity before signaling, and waits for graceful exit without automatic SIGKILL.
"""
import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def python_executable(root=ROOT):
    for path in [root/'.venv/bin/python', root/'.venv/Scripts/python.exe']:
        if path.is_file():return str(path)
    return sys.executable


def process_identity(pid):
    """PID + Linux kernel start ticks protects against signaling a reused PID."""
    try:
        path=Path('/proc')/str(pid)
        if path.stat().st_uid != os.getuid():return None
        fields=(path/'stat').read_text().rsplit(')',1)[1].split()
        if fields[0]=='Z':return None
        return (pid, fields[19])
    except (OSError,IndexError):return None


def project_processes(root=ROOT):
    """Recognize script entry points, never substring matches or port ownership."""
    root=root.resolve()
    owned={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        pid=int(path.name)
        identity=process_identity(pid)
        if identity is None or pid==os.getpid():continue
        try:
            cwd=(path/'cwd').resolve(strict=True)
            args=[part.decode() for part in (path/'cmdline').read_bytes().split(b'\0') if part]
            if len(args)<2:continue
            executable=Path(args[0]).name
            if not (executable.startswith('python') or executable in ['node','nodejs']):continue
            index=1
            while index<len(args) and args[index] in ['-u','-B','-E']:index+=1
            if index>=len(args) or args[index].startswith('-'):continue
            entry=(cwd/args[index]).resolve()
            role=None
            if executable.startswith('python'):
                if entry==root/'scripts/services.py' and 'start' in args[index+1:]:role='supervisor'
                elif entry==root/'scripts/run_server.py':role='watcher'
                elif entry==root/'server.py':role='api'
            elif entry==(root/'node_modules/vite/bin/vite.js').resolve() and cwd==root:
                role='web'
            elif entry==(root/'node_modules/concurrently/dist/bin/concurrently.js').resolve() and cwd==root:
                role='supervisor'
            if role:owned[identity]=role
        except (OSError,UnicodeError):continue
    return owned


def signal_process(identity):
    if process_identity(identity[0])==identity:
        try:os.kill(identity[0],signal.SIGTERM)
        except ProcessLookupError:pass


def stop(root=ROOT, timeout=30):
    if not Path('/proc/self/stat').exists():
        print('pnpm stop requires Linux/WSL process discovery; use Ctrl+C in the startup terminal.',file=sys.stderr)
        return 1
    deadline=time.monotonic()+timeout
    signaled=set()
    found=False
    while True:
        owned=project_processes(root)
        if not owned:
            print('Jevision prototype services stopped.' if found else 'No Jevision prototype services are running.',flush=True)
            return 0
        found=True
        # Stop supervisors before children so a watcher cannot restart its API.
        for role in ['supervisor','watcher','web','api']:
            for identity,kind in owned.items():
                if kind==role and identity not in signaled:
                    print(f'Stopping {role} (PID {identity[0]})…',flush=True)
                    signal_process(identity)
                    signaled.add(identity)
        if time.monotonic()>=deadline:
            print('Services are still draining work; no processes were force-killed. Run pnpm stop --timeout 120 to wait longer.',file=sys.stderr)
            return 1
        time.sleep(.1)


def start(root=ROOT, production=False):
    stopping=False
    def request_stop(*_):
        nonlocal stopping
        stopping=True
    handlers={sig:signal.signal(sig,request_stop) for sig in [signal.SIGINT,signal.SIGTERM]}
    children=[]
    result=0
    environment={**os.environ,'PYTHONUNBUFFERED':'1'}
    try:
        command=[python_executable(root),str(root/'scripts/run_server.py')]
        if not production:command+=['--api-only','--reload']
        children.append(subprocess.Popen(command,cwd=root,env=environment,start_new_session=True))
        if not production and not stopping:
            node=shutil.which('node')
            if node is None:raise RuntimeError('Node.js is required to start Vite.')
            children.append(subprocess.Popen([node,str(root/'node_modules/vite/bin/vite.js'),'--config',str(root/'vite.config.js')],cwd=root,env=environment,start_new_session=True))
        while not stopping:
            exited=next((child for child in children if child.poll() is not None),None)
            if exited is not None:
                result=exited.returncode
                break
            time.sleep(.1)
    finally:
        for child in children:
            if child.poll() is None:child.terminate()
        for child in children:child.wait()
        for sig,handler in handlers.items():signal.signal(sig,handler)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    launch=sub.add_parser('start')
    launch.add_argument('--production',action='store_true')
    shutdown=sub.add_parser('stop')
    shutdown.add_argument('--timeout',type=float,default=30)
    args=parser.parse_args()
    if args.action=='stop':
        if args.timeout<0:parser.error('--timeout must be nonnegative')
        return stop(timeout=args.timeout)
    return start(production=args.production)


if __name__=='__main__':sys.exit(main())
