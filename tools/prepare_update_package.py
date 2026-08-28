"""Prepare the two files that must be copied to the corporate update share."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runner.version import __version__  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    app_dir = ROOT / "dist" / "PytestRunner"
    exe = app_dir / "PytestRunner.exe"
    if not exe.is_file():
        print(f"Missing build: {exe}")
        return 1

    release = ROOT / "release"
    release.mkdir(exist_ok=True)

    stem = release / f"PytestRunner_{__version__}"
    zip_path = Path(shutil.make_archive(str(stem), "zip", root_dir=app_dir.parent,
                                        base_dir=app_dir.name))
    checksum = sha256(zip_path)

    manifest = {
        "version": __version__,
        "package": zip_path.name,
        "sha256": checksum,
    }
    manifest_path = release / "latest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Prepared update {__version__}")
    print(f"  {zip_path}")
    print(f"  {manifest_path}")
    print(f"  SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
