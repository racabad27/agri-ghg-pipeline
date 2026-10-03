from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    """Current time in UTC, e.g. '2026-09-29T02:15:00+00:00'."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_batch_id() -> str:
    """An ID for one pipeline run, e.g. '20260929T021500Z'."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_of(path: Path) -> str:
    """Fingerprint of a file. If the source changes, the fingerprint changes."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(data, path: Path) -> Path:
    """Save data as pretty JSON, creating folders if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_metadata(file_path: Path, **info) -> Path:
    """Save '<file>.meta.json' next to a raw file: where it came from and when."""
    file_path = Path(file_path)
    metadata = {
        "file": file_path.name,
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_of(file_path),
        "recorded_at": utc_now(),
        **info,
    }
    return write_json(metadata, file_path.with_name(file_path.name + ".meta.json"))


def reset_dir(path: Path) -> Path:
    """Delete a folder and create it again, empty (a '.gitkeep' placeholder is kept).

    Used before writing a layer's output, so a rerun replaces old files
    instead of adding duplicates next to them.
    """
    path = Path(path)
    had_gitkeep = (path / ".gitkeep").exists()
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    if had_gitkeep:
        (path / ".gitkeep").touch()
    return path