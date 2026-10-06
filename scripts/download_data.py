"""Fetch pinned, public source files. No credentials or Kaggle account required."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "08c1fab7f9257bc73679d415d65d644165d351d4"
BASE = f"https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/resolve/{REVISION}/data"
FILES = {
    "train.parquet": "6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d",
    "eval.parquet": "1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset": "FreshRetailNet-50K",
        "revision": REVISION,
        "license": "CC BY 4.0",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }
    for filename, expected in FILES.items():
        target = destination / filename
        if not target.exists():
            temporary = target.with_suffix(".part")
            request = urllib.request.Request(
                f"{BASE}/{filename}", headers={"User-Agent": "scdi-portfolio/1.0"}
            )
            try:
                with (
                    urllib.request.urlopen(request, timeout=180) as response,
                    temporary.open("wb") as out,
                ):
                    shutil.copyfileobj(response, out)
                if sha256(temporary) != expected:
                    raise ValueError(f"SHA-256 mismatch for {filename}; source data not accepted")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        actual = sha256(target)
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch for {target}; use a fresh pinned download")
        manifest["files"].append(
            {
                "name": filename,
                "url": f"{BASE}/{filename}",
                "bytes": target.stat().st_size,
                "sha256": actual,
            }
        )
        print(f"Verified {filename}: {target.stat().st_size:,} bytes")
    (destination / "download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "data/raw")
    download(parser.parse_args().destination)
