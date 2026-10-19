"""Download the train split as numbered PNG/HTML pairs, with provenance."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

DATASET = "SALT-NLP/Design2Code-hf"
REVISION = "9d23e96b0b8dec04d5f5c7f0486f9a267ad81a8e"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "Design2Code-hf"


def download(output=DEFAULT_OUTPUT, progress=lambda **kwargs: None):
    from datasets import load_dataset
    from huggingface_hub import hf_hub_download

    output = Path(output)
    if output.exists():
        try:
            manifest = json.loads((output / "manifest.json").read_text())
            count = manifest["count"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RuntimeError("Existing dataset folder has no valid manifest. Move it aside before downloading again.") from error
        if manifest.get("dataset") != DATASET or manifest.get("revision") != REVISION or count != 484 or not all(
            (output / f"{i:03}.{ext}").is_file()
            for i in range(1, count + 1) for ext in ("png", "html")
        ):
            raise RuntimeError("Existing dataset is incomplete or uses a different revision. Move it aside before downloading again.")
        progress(completed=count, total=count, message="Dataset already downloaded.")
        return manifest
    output.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HUGGING_FACE_API") or os.environ.get("HF_TOKEN") or None
    revision = REVISION
    progress(message="Downloading the train split…", completed=0, total=484)
    rows = load_dataset(DATASET, split="train", revision=revision, token=token)
    with tempfile.TemporaryDirectory(prefix=".design2code-", dir=output.parent) as temporary:
        stage = Path(temporary) / "dataset"
        stage.mkdir()
        for i, row in enumerate(rows, start=1):
            row["image"].save(stage / f"{i:03}.png", format="PNG")
            (stage / f"{i:03}.html").write_text(row["text"], encoding="utf-8")
            progress(completed=i, total=len(rows), message=f"Saving pair {i} of {len(rows)}…")
        if len(rows) != 484:
            raise RuntimeError("Expected 484 HTML/reference pairs; refusing to publish an incomplete dataset.")
        card = Path(hf_hub_download(DATASET, "README.md", repo_type="dataset", revision=revision, token=token))
        (stage / "README.md").write_bytes(card.read_bytes())
        manifest = {"dataset": DATASET, "split": "train", "revision": revision,
                    "count": len(rows), "license": "odc-by", "downloadedAt": datetime.now(timezone.utc).isoformat(),
                    "source": "https://huggingface.co/datasets/" + DATASET,
                    "note": "Images in source webpages are replaced with rick.jpg; that asset is not included in these pairs."}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        stage.rename(output)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    # Same .env convention as the app, without overriding shell credentials.
    from sys import path as module_path
    module_path.insert(0, str(Path(__file__).resolve().parents[1]))
    from server import load_dotenv
    load_dotenv()
    result = download(args.output, lambda **status: print(status.get("message", ""), flush=True))
    print(f"Saved {result['count']} screenshots and HTML files to {args.output}")
