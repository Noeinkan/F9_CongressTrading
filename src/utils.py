from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from dateutil import parser


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parser.parse(value, dayfirst=False).date().isoformat()
    except Exception:
        return None


def ensure_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")
