"""Install the version-pinned example photos, verifying every image against SHA-256."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/photo-datasets.json"
EXTENSIONS = {".jpg", ".jpeg", ".png"}


def relative_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in {"..", "."} or ":" in p or "\\" in p for p in path.parts):
        raise ValueError("Manifest contains an unsafe relative path")
    return Path(*path.parts)


def digest(path):
    with path.open("rb") as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify(destination, spec):
    expected = {relative_path(row["path"]).as_posix() for row in spec["files"]}
    actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*")
              if p.suffix.lower() in EXTENSIONS and p.is_file()}
    if actual != expected:
        raise RuntimeError(f"{spec['id']}: image list differs (missing {len(expected - actual)}, extra {len(actual - expected)}). Use a fresh output folder.")
    for row in spec["files"]:
        path = destination / relative_path(row["path"])
        if any(p.is_symlink() for p in [path, *path.parents]) or digest(path) != row["sha256"]:
            raise RuntimeError(f"{spec['id']}: image verification failed: {row['path']}")
    return len(expected)


def install(output, spec, archive=None, verify_only=False):
    destination = output / relative_path(spec["id"])
    if destination.exists():
        return verify(destination, spec)
    if verify_only:
        raise RuntimeError(f"{spec['id']}: dataset is not installed")
    output.mkdir(parents=True, exist_ok=True)
    # The hidden staging directory is skipped by the application's photo scan.
    with tempfile.TemporaryDirectory(prefix=".photo-download-", dir=output) as temporary:
        work = Path(temporary)
        if archive is None:
            archive = work / "source.zip"
            url = f"https://www.kaggle.com/api/v1/datasets/download/{spec['dataset']}?datasetVersionNumber={spec['version']}"
            try:
                with urlopen(url, timeout=120) as response, archive.open("wb") as target:
                    shutil.copyfileobj(response, target)
            except (HTTPError, URLError) as error:
                raise RuntimeError("Kaggle download failed. Download the pinned version in your browser and pass --archive; see docs/photo-datasets.md.") from error
        stage = work / "dataset"
        stage.mkdir()
        with ZipFile(archive) as source:
            members = source.namelist()
            if len(set(members)) != len(members):
                raise RuntimeError("Dataset archive contains duplicate member names")
            for row in spec["files"]:
                # Copy only manifest members, never extract arbitrary archive paths.
                target = stage / relative_path(row["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(row["sourcePath"]) as image, target.open("wb") as target_file:
                    shutil.copyfileobj(image, target_file)
        verify(stage, spec)
        (stage / "provenance.json").write_text(json.dumps({
            "dataset": spec["dataset"], "version": spec["version"],
            "source": spec["source"], "selection": spec["selection"],
            "files": spec["files"],
        }, indent=2) + "\n", encoding="utf-8")
        stage.rename(destination)
    return len(spec["files"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["all", "hymenoptera", "sea-animals"], default="all")
    parser.add_argument("--output", type=Path, default=ROOT / ".photo")
    parser.add_argument("--archive", type=Path, help="Use a manually downloaded ZIP for one selected dataset")
    parser.add_argument("--verify", action="store_true", help="Verify installed files without downloading")
    args = parser.parse_args()
    if args.archive and (args.dataset == "all" or args.verify):
        parser.error("--archive requires one --dataset and cannot be combined with --verify")
    specs = json.loads(MANIFEST.read_text(encoding="utf-8"))["datasets"]
    try:
        for spec in specs:
            if args.dataset in {"all", spec["id"]}:
                print(f"Preparing {spec['id']} (Kaggle version {spec['version']})…", flush=True)
                count = install(args.output.expanduser(), spec, args.archive, args.verify)
                print(f"Verified {count} images: {spec['id']}", flush=True)
    except (OSError, ValueError, RuntimeError, KeyError, BadZipFile) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
