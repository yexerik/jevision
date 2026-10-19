"""Prepare the app, Chromium, photo datasets, and HTML validation dataset."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(command, root, env=None):
    # Never print environment values: .env may contain credentials.
    subprocess.run([str(part) for part in command], cwd=root, env=env, check=True)


def dotenv_values(text):
    values = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), value.strip().strip("\"'"))
    return values


def configure_env(root):
    path = root / ".env"
    if not path.exists():
        with path.open("x", encoding="utf-8") as stream:
            stream.write((root / ".env.example").read_text(encoding="utf-8"))
        path.chmod(0o600)
    text = path.read_text(encoding="utf-8")
    values = dotenv_values(text)
    if not values.get("PHOTO_ROOT"):
        if "PHOTO_ROOT" in values:
            text = re.sub(r"(?m)^[ \t]*PHOTO_ROOT[ \t]*=.*$", "PHOTO_ROOT=.photo", text, count=1)
        else:
            text = text.rstrip("\n") + "\nPHOTO_ROOT=.photo\n"
    if "TYPESAFE_API_KEY" not in values:
        text = text.rstrip("\n") + "\nTYPESAFE_API_KEY=your_typesafe_api_key_here\n"
    if text != path.read_text(encoding="utf-8"):
        path.write_text(text, encoding="utf-8")
    return dotenv_values(text)


def prerequisites(root):
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")
    found = {name: shutil.which(name) for name in ["node", "pnpm"]}
    if not all(found.values()):
        raise RuntimeError("Install Node.js 22.12+ and pnpm 11, then rerun this command.")
    node = subprocess.check_output([found["node"], "--version"], cwd=root, text=True).strip()
    if tuple(int(part) for part in node.lstrip("v").split(".")[:2]) < (22, 12):
        raise RuntimeError("Node.js 22.12 or newer is required.")
    pnpm = subprocess.check_output([found["pnpm"], "--version"], cwd=root, text=True).strip()
    if pnpm.split(".")[0] != "11":
        raise RuntimeError("pnpm 11 is required (see package.json).")
    return found["pnpm"]


def python_environment(root):
    directory = root / ".venv"
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not directory.exists():
        venv.EnvBuilder(with_pip=True).create(directory)
    if not python.is_file():
        raise RuntimeError("Existing .venv is incomplete; move it aside and rerun setup.")
    return python


def install_chromium(python, root, env):
    run([python, "-m", "playwright", "install", "chromium"], root, env)
    probe = [str(python), "-c", "from playwright.sync_api import sync_playwright; "
             "p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()"]
    result = subprocess.run(probe, cwd=root, env=env, text=True, capture_output=True)
    if result.returncode and sys.platform.startswith("linux"):
        message = (result.stdout + result.stderr).lower()
        if any(marker in message for marker in ["missing dependencies", "error while loading shared libraries", "libraries not found"]):
            print("Installing Chromium system dependencies (Linux may request sudo)…", flush=True)
            run([python, "-m", "playwright", "install-deps", "chromium"], root, env)
            result = subprocess.run(probe, cwd=root, env=env, text=True, capture_output=True)
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        raise RuntimeError("Chromium could not launch; resolve the browser diagnostic above and rerun setup.")


def setup(root=ROOT):
    pnpm = prerequisites(root)
    print("[1/5] Preparing Python and JavaScript dependencies…", flush=True)
    python = python_environment(root)
    run([python, "-m", "pip", "install", "--upgrade", "pip>=26.2,<27"], root)
    run([python, "-m", "pip", "install", "-r", root / "requirements.txt"], root)
    run([pnpm, "install", "--frozen-lockfile"], root)

    print("[2/5] Configuring local settings…", flush=True)
    config = configure_env(root)
    env = {**config, **os.environ}
    photo_root = Path(env.get("PHOTO_ROOT", "").strip() or ".photo").expanduser()
    if not photo_root.is_absolute():
        photo_root = root / photo_root
    if photo_root.resolve() != (root / ".photo").resolve():
        print("Preserving your explicitly configured PHOTO_ROOT for photo downloads.", flush=True)

    print("[3/5] Installing and checking Chromium…", flush=True)
    install_chromium(python, root, env)
    print("[4/5] Preparing ants/bees and sea-animal photos…", flush=True)
    run([python, root / "scripts/download_photo_datasets.py", "--output", photo_root], root, env)
    print("[5/5] Preparing the HTML/reference dataset…", flush=True)
    run([python, root / "scripts/download_design2code.py"], root, env)
    print("\nSetup complete: 13,955 photos and 484 HTML/reference pairs are ready.", flush=True)
    print("Add your TYPESAFE_API_KEY to .env, then run: pnpm start", flush=True)
    print("Open http://127.0.0.1:" + (env.get("PORT") or "8765"), flush=True)


def main():
    try:
        setup()
    except subprocess.CalledProcessError as error:
        print(f"Setup stopped: a command failed (exit {error.returncode}). Fix the error above and rerun setup; completed datasets are reused.", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSetup interrupted. Rerun the command to continue.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(main())
