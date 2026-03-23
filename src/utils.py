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


def normalize_key(text: str | None) -> str:
    normalized = normalize_whitespace(text or "")
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalize_whitespace(normalized)


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


def make_content_hash(*parts: str | None) -> str:
    payload = "||".join(normalize_whitespace(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_amount_range(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None

    cleaned = normalize_whitespace(value)
    numbers = [int(match.replace(",", "")) for match in re.findall(r"\$?([\d,]+)", cleaned)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return numbers[0], numbers[1]


def split_state_district(value: str | None) -> tuple[str, str]:
    cleaned = normalize_whitespace(value or "")
    if not cleaned:
        return "", ""

    match = re.match(r"^([A-Za-z]{2})(\d{1,2})?$", cleaned)
    if match:
        return match.group(1).upper(), match.group(2) or ""

    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper(), ""

    return cleaned, ""
