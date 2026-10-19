from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import subprocess
import tempfile
import uuid
import threading
import signal
import time
from scripts.download_design2code import download as download_design2code, DEFAULT_OUTPUT
from layout_renderer import render as render_layout
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "dist"
LIBRARY_META = ROOT / ".jev-image-data" / "library.json"
API_URL = "https://api.typesafe.ai/v1/systemone"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SKIP_DIRECTORIES = {".git", ".agents", ".codex", ".aws", ".jev-image-data", "node_modules", "dist", "__pycache__", "web", ".venv", "venv", "build"}
MAX_BODY_BYTES = 34 * 1024 * 1024
MAX_RENDER_BODY_BYTES = 6 * 1024 * 1024
MAX_IMPORT_BYTES = 256 * 1024 * 1024
API_ONLY = "--api-only" in sys.argv


def load_dotenv() -> None:
    """Load simple KEY=VALUE lines from .env without replacing shell variables."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def photo_root() -> Path:
    configured = os.environ.get("PHOTO_ROOT", "").strip()
    return Path(configured).expanduser().resolve() if configured else ROOT


def configured_api_key() -> str:
    """A fresh clone's example placeholder is not a configured credential."""
    value = os.environ.get('TYPESAFE_API_KEY', '').strip()
    return '' if value.lower() in {'your_typesafe_api_key_here', 'placeholder'} else value


def load_library_meta() -> dict:
    try:
        value = json.loads(LIBRARY_META.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"datasets": {}}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"datasets": {}}


def save_library_meta(metadata: dict) -> None:
    LIBRARY_META.parent.mkdir(parents=True, exist_ok=True)
    temporary = LIBRARY_META.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary.replace(LIBRARY_META)


def merge_saved_results(previous, incoming):
    """Keep the newest count per target; stale clients cannot erase other results."""
    merged = list(previous)
    def timestamp(result):
        value = result.get("createdAt", 0)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 2**53 - 1 else 0
    for result in incoming:
        target = result["target"]
        matching = [old for old in merged if isinstance(old, dict) and old.get("target") == target]
        if not matching or timestamp(result) >= max(timestamp(old) for old in matching):
            merged = [old for old in merged if not isinstance(old, dict) or old.get("target") != target]
            merged.insert(0, result)
    return merged


def safe_path(relative: str, root: Path | None = None) -> Path | None:
    base = (root or photo_root()).resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def infer_target_from_folder(folder: str) -> str:
    """Use the dataset folder's name as its count target unless it is the root."""
    if folder == ".":
        return "cars"
    name = re.sub(r"[-_]+", " ", Path(folder).name).strip().lower()
    aliases = {
        "car": "cars", "cars": "cars",
        "person": "people", "people": "people",
        "bus": "buses", "buses": "buses",
        "bike": "bicycles", "bikes": "bicycles",
        "bicycle": "bicycles", "bicycles": "bicycles",
        "truck": "trucks", "trucks": "trucks",
        "dolphin": "dolphins", "dolphins": "dolphins",
        "whale": "whales", "whales": "whales",
    }
    return aliases.get(name, name or "cars")


LIBRARY_SCAN_LOCK = threading.Lock()
LAST_LIBRARY_SCAN = {"finished": 0.0, "root": None, "datasets": None}


def scan_library() -> list[dict]:
    # Requests arriving during one scan share its result. A later explicit
    # rescan still walks the folder, without an arbitrary cache TTL.
    requested = time.monotonic()
    root = photo_root()
    with LIBRARY_SCAN_LOCK:
        if LAST_LIBRARY_SCAN["root"] == root and LAST_LIBRARY_SCAN["finished"] >= requested:
            return LAST_LIBRARY_SCAN["datasets"]
        datasets = _scan_library()
        LAST_LIBRARY_SCAN.update(finished=time.monotonic(), root=root, datasets=datasets)
        return datasets


def _scan_library() -> list[dict]:
    """Discover photo datasets, keeping HTML screenshots in the validator only.

    Design2Code pairs are served by dedicated endpoints; excluding their folder
    here prevents Count, Find, Search, and the shared photo navigation listing it.
    """
    root = photo_root()
    layout_root = DEFAULT_OUTPUT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    metadata = load_library_meta()
    dataset_meta = metadata.setdefault("datasets", {})
    grouped: dict[str, list[Path]] = {}

    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path.resolve().is_relative_to(layout_root):
            directories.clear()
            continue
        directories[:] = [
            name for name in directories
            if name not in SKIP_DIRECTORIES and not name.startswith(".")
            and not (current_path / name).is_symlink()
            and not (current_path / name).resolve().is_relative_to(layout_root)
        ]
        images = []
        for filename in filenames:
            file_path = current_path / filename
            if file_path.suffix.lower() not in IMAGE_EXTENSIONS or file_path.is_symlink():
                continue
            resolved = file_path.resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                continue
            images.append((relative, resolved))
        if images:
            folder = current_path.relative_to(root).as_posix() or "."
            grouped[folder] = [item[1] for item in sorted(images)]

    for folder in dataset_meta:
        if folder == "." or folder in grouped:
            continue
        directory = safe_path(folder, root)
        if directory is not None and directory.is_dir() and not directory.resolve().is_relative_to(layout_root):
            grouped[folder] = []

    datasets = []
    for folder, files in sorted(grouped.items(), key=lambda item: (item[0] != ".", item[0].lower())):
        entry = dataset_meta.setdefault(folder, {})
        entry.setdefault("name", "Workspace photos" if folder == "." else Path(folder).name.replace("-", " ").replace("_", " ").title())
        inferred_target = infer_target_from_folder(folder)
        if entry.get("targetSource") == "inferred":
            entry["target"] = inferred_target
        elif "target" not in entry:
            entry["target"] = inferred_target
            entry["targetSource"] = "inferred"
        elif "targetSource" not in entry:
            # Older scans assigned "cars" as a default, without recording
            # whether the user chose it. Replace that default for named folders.
            if entry["target"] == "cars" and inferred_target != "cars":
                entry["target"] = inferred_target
                entry["targetSource"] = "inferred"
            else:
                entry["targetSource"] = "manual"
        entry.setdefault("createdAt", int((root if folder == "." else root / folder).stat().st_mtime * 1000))
        images = []
        for file_path in files:
            relative = file_path.relative_to(root).as_posix()
            images.append({
                "id": relative,
                "path": relative,
                "name": file_path.name,
                "url": "/api/photo?path=" + quote(relative, safe=""),
                "results": entry.get("results", {}).get(relative, []),
            })
        datasets.append({
            "id": folder,
            "name": entry["name"],
            "target": entry["target"],
            "createdAt": entry["createdAt"],
            "storage": "workspace",
            "path": folder,
            "images": images,
        })
    save_library_meta(metadata)
    return datasets


def dataset_metadata_for_path(folder: str, metadata: dict) -> dict | None:
    root = photo_root()
    directory = safe_path(folder, root)
    if directory is None or not directory.is_dir():
        return None
    relative = directory.relative_to(root).as_posix() or "."
    return metadata.setdefault("datasets", {}).setdefault(relative, {})


def find_browser() -> Path | None:
    configured = os.environ.get("CHROME_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    for executable in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        resolved = shutil.which(executable)
        if resolved:
            candidates.append(Path(resolved))
    candidates.extend([
        Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path("/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ])
    return next((path for path in candidates if path.is_file()), None)


def windows_file_url(path: Path) -> str:
    windows_path = subprocess.check_output(["wslpath", "-w", str(path)], text=True, timeout=5).strip()
    return "file:///" + windows_path.replace("\\", "/")


def render_html_screenshot(source: str, width: int, height: int) -> bytes:
    return render_layout(source, width, height)


DOWNLOAD_LOCK = threading.Lock()
DOWNLOAD_STATE = {"status": "idle", "completed": 0, "total": 484}
DOWNLOAD_THREADS = set()
SERVER_STOPPING = threading.Event()


def download_status():
    with DOWNLOAD_LOCK:
        return dict(DOWNLOAD_STATE)


def start_dataset_download():
    with DOWNLOAD_LOCK:
        if DOWNLOAD_STATE["status"] == "running":
            return
        DOWNLOAD_STATE.update(status="running", completed=0, message="Starting download…", error=None)

    def update(**fields):
        with DOWNLOAD_LOCK:
            DOWNLOAD_STATE.update(fields)

    def progress(**fields):
        if SERVER_STOPPING.is_set():
            raise RuntimeError('Download interrupted by server shutdown; incomplete pairs were not published.')
        update(**fields)

    def run():
        try:
            manifest = download_design2code(DEFAULT_OUTPUT, progress)
            update(status="complete", completed=manifest["count"], total=manifest["count"], message="Download complete.")
        except ImportError:
            update(status="failed", error="Install requirements.txt in the server's Python environment, then restart.")
        except Exception as error:
            update(status="failed", error=str(error)[:400])
        finally:
            with DOWNLOAD_LOCK:
                DOWNLOAD_THREADS.discard(threading.current_thread())
    thread = threading.Thread(target=run, daemon=False)
    with DOWNLOAD_LOCK:
        DOWNLOAD_THREADS.add(thread)
    thread.start()


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # A browser may navigate away or cancel while headers/body are sent.
            # The connection is gone; do not attempt a second HTTP response.
            self.close_connection = True

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _allow_local_request(self) -> bool:
        """Reject nonlocal Host values and cross-origin browser requests.

        Vite preserves the frontend Host header when proxying, so its normal
        same-origin requests still pass. CLI clients need no Origin header.
        """
        host = self.headers.get('Host', '')
        try:
            address = urlsplit('//' + host)
            address.port  # Reject malformed TCP ports as well as malformed IPv6.
            valid_host = address.hostname in {'127.0.0.1', 'localhost', '::1'} and not address.username and not address.password and not address.path and not address.query and not address.fragment
            origin = self.headers.get('Origin')
            source = urlsplit(origin) if origin else None
            valid_origin = not source or (source.scheme == 'http' and source.netloc.lower() == host.lower() and not source.path and not source.query and not source.fragment)
        except ValueError:
            valid_host = valid_origin = False
        if not valid_host or not valid_origin or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self._json(403, {'error':'Only local, same-origin app requests are allowed.'})
            return False
        return True

    def _read_body(self, limit: int) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > limit:
            self._json(413, {"error": "The request is empty or too large."})
            return None
        return self.rfile.read(length)

    def _read_json(self, limit: int = 2 * 1024 * 1024) -> dict | None:
        body = self._read_body(limit)
        if body is None:
            return None
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._json(400, {"error": "Expected a JSON request."})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"error": "Expected a JSON object."})
            return None
        return payload

    def _send_image(self, relative: str) -> None:
        path = safe_path(relative)
        if path is None:
            self._json(403, {"error": "That photo is outside the configured photo folder."})
            return
        if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
            self._json(404, {"error": "Photo not found."})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._allow_local_request():
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/api/design2code/status":
            self._json(200, download_status())
            return
        if parsed.path == "/api/design2code/examples":
            pairs = []
            if DEFAULT_OUTPUT.is_dir():
                pairs = [{"id": p.stem, "imageUrl": "/api/design2code/image?id=" + p.stem}
                         for p in sorted(DEFAULT_OUTPUT.glob("[0-9][0-9][0-9].html"))
                         if p.with_suffix(".png").is_file()]
            self._json(200, {"examples": pairs})
            return
        if parsed.path in {"/api/design2code/html", "/api/design2code/image"}:
            identifier = parse_qs(parsed.query).get("id", [""])[0]
            if not re.fullmatch(r"[0-9]{3}", identifier):
                self._json(400, {"error": "Invalid example ID."})
                return
            extension = ".html" if parsed.path.endswith("html") else ".png"
            path = DEFAULT_OUTPUT / (identifier + extension)
            if not path.is_file():
                self._json(404, {"error": "Download this example first."})
                return
            if extension == ".html":
                self._json(200, {"html": path.read_text(encoding="utf-8")})
            else:
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        if parsed.path == "/api/health":
            self._json(200, {"ok": True, "apiKeyConfigured": bool(configured_api_key())})
            return
        if parsed.path == "/api/library":
            try:
                payload = {"datasets": scan_library()}
            except OSError:
                self._json(500, {"error": "Could not read the configured photo folder."})
            else:
                self._json(200, payload)
            return
        if parsed.path == "/api/photo":
            relative = parse_qs(parsed.query).get("path", [""])[0]
            self._send_image(relative)
            return
        if API_ONLY:
            self._json(404, {"error": "Not found"})
            return
        if parsed.path in {"/tools/count", "/tools/find", "/tools/search", "/tools/qa"}:
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        if not self._allow_local_request():
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/api/design2code/download":
            start_dataset_download()
            self._json(202, download_status())
            return
        if parsed.path == "/api/render-html":
            payload = self._read_json(MAX_RENDER_BODY_BYTES)
            if payload is None:
                return
            source = payload.get("html")
            if not isinstance(source, str) or not source.strip():
                self._json(400, {"error": "Choose an HTML page to render."})
                return
            if len(source.encode("utf-8")) > 5 * 1024 * 1024:
                self._json(413, {"error": "HTML files must be 5 MB or smaller."})
                return
            viewport = payload.get("viewport")
            dimensions = {"desktop": (1280, 900), "mobile": (390, 844)}.get(viewport) if isinstance(viewport, str) else None
            if dimensions is None:
                self._json(400, {"error": "Choose a supported viewport."})
                return
            try:
                image = render_html_screenshot(source, *dimensions)
            except RuntimeError as error:
                self._json(422, {"error": str(error)})
                return
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                self._json(500, {"error": "Could not render this HTML page: " + str(error)[:300]})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(image)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(image)
            return

        if parsed.path == "/api/datasets":
            payload = self._read_json()
            if payload is None:
                return
            name = str(payload.get("name", "")).strip()[:60]
            target = str(payload.get("target", "cars")).strip().lower()[:80]
            if not name or not target:
                self._json(400, {"error": "A dataset name and count target are required."})
                return
            root = photo_root()
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "dataset"
            folder = root / "photos" / (slug + "-" + uuid.uuid4().hex[:8])
            folder.mkdir(parents=True, exist_ok=False)
            relative = folder.relative_to(root).as_posix()
            with LIBRARY_SCAN_LOCK:
                metadata = load_library_meta()
                metadata.setdefault("datasets", {})[relative] = {"name": name, "target": target, "targetSource": "manual", "createdAt": int(__import__("time").time() * 1000), "results": {}}
                save_library_meta(metadata)
            self._json(201, {"id": relative})
            return

        if parsed.path == "/api/dataset-settings":
            payload = self._read_json()
            if payload is None:
                return
            images = payload.get("images", [])
            if not isinstance(images, list) or any(
                not isinstance(image, dict) or not isinstance(image.get("results", []), list)
                or any(not isinstance(result, dict) or not isinstance(result.get("target"), str)
                       or not isinstance(result.get("createdAt", 0), (int, float))
                       or isinstance(result.get("createdAt", 0), bool)
                       or not 0 <= result.get("createdAt", 0) <= 2**53 - 1
                       for result in image.get("results", []))
                for image in images
            ):
                self._json(400, {"error": "Expected photo results as arrays with targets and numeric timestamps."})
                return
            folder = str(payload.get("id", ""))
            with LIBRARY_SCAN_LOCK:
                metadata = load_library_meta()
                entry = dataset_metadata_for_path(folder, metadata)
                if entry is None:
                    self._json(404, {"error": "Dataset folder not found."})
                    return
                name = str(payload.get("name", entry.get("name", ""))).strip()[:60]
                target = str(payload.get("target", entry.get("target", "cars"))).strip().lower()[:80]
                if not name or not target:
                    self._json(400, {"error": "A dataset name and count target are required."})
                    return
                entry["name"] = name
                entry["target"] = target
                entry["targetSource"] = "manual"
                for image in images:
                    if not isinstance(image, dict):
                        continue
                    path_value = str(image.get("path", ""))
                    photo = safe_path(path_value)
                    folder_path = safe_path(folder)
                    if photo is None or folder_path is None or not photo.is_relative_to(folder_path) or not photo.is_file():
                        continue
                    entry.setdefault("results", {})[path_value] = merge_saved_results(
                        entry.get("results", {}).get(path_value, []), image.get("results", []))
                save_library_meta(metadata)
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/dataset-photos":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("multipart/form-data;"):
                self._json(400, {"error": "Expected multipart photo uploads."})
                return
            body = self._read_body(MAX_IMPORT_BYTES)
            if body is None:
                return
            try:
                message = BytesParser(policy=email_policy).parsebytes(
                    b"Content-Type: " + content_type.encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
                )
            except (UnicodeEncodeError, ValueError):
                self._json(400, {"error": "Could not parse the photo upload."})
                return
            fields = {}
            files = []
            for part in message.iter_parts():
                field_name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                content = part.get_payload(decode=True) or b""
                if field_name == "datasetId":
                    fields[field_name] = content.decode("utf-8", "replace")
                elif field_name == "photos" and filename:
                    files.append((filename, part.get_content_type(), content))
            folder = fields.get("datasetId", "")
            directory = safe_path(folder)
            if directory is None or not directory.is_dir():
                self._json(404, {"error": "Dataset folder not found."})
                return
            saved = []
            with LIBRARY_SCAN_LOCK:
                for filename, content_type, content in files[:25]:
                    name = Path(filename.replace("\\", "/")).name
                    suffix = Path(name).suffix.lower()
                    if suffix not in IMAGE_EXTENSIONS or content_type not in {"image/jpeg", "image/png"} or not content:
                        continue
                    stem = Path(name).stem[:100] or "photo"
                    duplicate = 1
                    while True:
                        destination = directory / (stem + ("-" + str(duplicate) if duplicate > 1 else "") + suffix)
                        try:
                            stream = destination.open("xb")
                        except FileExistsError:
                            duplicate += 1
                            continue
                        with stream:
                            stream.write(content)
                        break
                    saved.append(destination.relative_to(photo_root()).as_posix())
            if not saved:
                self._json(400, {"error": "No supported PNG or JPEG photos were uploaded."})
                return
            self._json(201, {"paths": saved})
            return

        if parsed.path not in {"/api/count-cars", "/api/system-one"}:
            self._json(404, {"error": "Not found"})
            return

        api_key = configured_api_key()
        if not api_key:
            self._json(503, {"error": "Add your TypeSafe API key to .env, then restart the app."})
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            self._json(400, {"error": "Expected a multipart image request."})
            return
        body = self._read_body(MAX_BODY_BYTES)
        if body is None:
            return
        request = Request(
            API_URL,
            data=body,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": content_type,
                "TypeSafe-Danger-Zone-Images": "true",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                response_body = response.read()
                response_status = response.status
        except HTTPError as error:
            error_body = error.read()
            try:
                detail = json.loads(error_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = {"error": "TypeSafe returned an unexpected error."}
            self._json(error.code, detail if isinstance(detail, dict) else {"error": str(detail)})
        except (TimeoutError, URLError, OSError):
            self._json(502, {"error": "Could not reach the TypeSafe API. Check your connection and try again."})
        else:
            self.send_response(response_status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response_body)

    def do_PUT(self) -> None:
        self._json(405, {"error": "Method not allowed"})


def serve_gracefully(server) -> None:
    """Stop accepting connections on signals, then drain requests and downloads."""
    SERVER_STOPPING.clear()
    server.daemon_threads = False
    server.block_on_close = True
    def request_stop(*_):
        if not SERVER_STOPPING.is_set():
            SERVER_STOPPING.set()
            print('Shutting down Jevision prototype; waiting for active work…',flush=True)
            # shutdown() must run outside the serve_forever thread.
            threading.Thread(target=server.shutdown,daemon=True).start()
    handlers={sig:signal.signal(sig,request_stop) for sig in [signal.SIGINT,signal.SIGTERM]}
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()
        with DOWNLOAD_LOCK:
            downloads=list(DOWNLOAD_THREADS)
        for thread in downloads:thread.join()
        for sig,handler in handlers.items():signal.signal(sig,handler)
        print('Jevision prototype server stopped.',flush=True)


def main() -> None:
    load_dotenv()
    root = photo_root()
    root.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("API_PORT", "8766")) if API_ONLY else int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print("Jevision prototype API listening at http://127.0.0.1:" + str(port) if API_ONLY else "Jevision prototype is running at http://127.0.0.1:" + str(port))
    print("Photo folder: " + str(root))
    serve_gracefully(server)


if __name__ == "__main__":
    main()
