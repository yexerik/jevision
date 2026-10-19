"""Freeze the local ES-module dependency graph used by a browser benchmark.

Following relative imports captures strategy/helper changes as well as entry-point
changes. Historical monolithic snapshots remain readable by their existing runner.
"""
import hashlib
from pathlib import Path
import re

WEB = Path(__file__).resolve().parents[1] / 'web'
IMPORT = re.compile(r'^import\s+[^;]*?\bfrom\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)


def collect_modules(entry='app.js', root=WEB):
    root = root.resolve()
    modules = {}

    def visit(path):
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Frontend import escapes source root')
        name = path.relative_to(root).as_posix()
        if name in modules:
            return
        modules[name] = path.read_bytes()
        for dependency in IMPORT.findall(modules[name].decode()):
            if not dependency.startswith('.'):
                raise ValueError('Benchmark snapshots require local relative imports')
            visit(path.parent / dependency)

    visit(root / entry)
    return modules


def freeze_modules(out, entry='app.js'):
    modules = collect_modules(entry)
    hashes = {}
    for name, source in sorted(modules.items()):
        path = out / 'modules' / name
        if path.exists() and path.read_bytes() != source:
            raise ValueError('Frozen frontend module changed; use a fresh output directory')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
        hashes[name] = hashlib.sha256(source).hexdigest()
    return hashes


def verify_modules(out, hashes):
    base = (out / 'modules').resolve()
    for name, expected in hashes.items():
        path = (base / name).resolve()
        if not path.is_relative_to(base) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen frontend module hash mismatch')
