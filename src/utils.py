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


def sanitize_transaction_date(
    transaction_date: str | None,
    filing_date: str | None,
) -> str | None:
    """Fix year-typo where transaction_date falls well after the filing date.

    PTR filers occasionally enter the wrong year (e.g. 2026 instead of 2025).
    When the transaction date is more than 90 days after the filing date (or
    after today when no filing date is available), subtracting one year usually
    produces the correct date.  Small gaps (days/weeks) are left untouched
    because those are minor data-quality issues, not year typos.
    """
    if not transaction_date:
        return transaction_date
    try:
        txn = datetime.strptime(transaction_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return transaction_date

    cutoff = None
    if filing_date:
        try:
            cutoff = datetime.strptime(filing_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    if cutoff is None:
        cutoff = datetime.utcnow().date()

    gap_days = (txn - cutoff).days
    if gap_days <= 90:
        return transaction_date

    try:
        corrected = txn.replace(year=txn.year - 1)
    except ValueError:
        corrected = txn.replace(year=txn.year - 1, day=28)

    if corrected <= cutoff:
        return corrected.isoformat()

    return transaction_date


def ensure_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)


_HOUSE_FD_BULK_ZIP_STEM = re.compile(r"^\d{4}FD$", re.IGNORECASE)


def is_house_fd_bulk_zip_path(path: Path) -> bool:
    """True per zip bulk metadata House tipo 2026FD.zip (stem AAAAFD)."""
    return path.suffix.lower() == ".zip" and bool(_HOUSE_FD_BULK_ZIP_STEM.match(path.stem))


def _zip_top_level_names(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        out: list[str] = []
        for name in zf.namelist():
            norm = name.replace("\\", "/").strip("/")
            if not norm or "/" in norm:
                continue
            out.append(norm)
        return out


def house_fd_bulk_zip_needs_extract(zip_path: Path, dest_dir: Path) -> bool:
    """
    True se manca un file top-level dello zip FD o la dimensione sul disco non coincide
    con quella attesa nel zip (evita metadata .txt/.xml obsoleti rispetto al .zip).
    """
    if not zip_path.exists():
        return False
    with zipfile.ZipFile(zip_path, "r") as zf:
        top = []
        for name in zf.namelist():
            norm = name.replace("\\", "/").strip("/")
            if not norm or "/" in norm:
                continue
            top.append((norm, zf.getinfo(name).file_size))
        if not top:
            return True
        for member_name, expected_size in top:
            dest = dest_dir / member_name
            if not dest.exists() or dest.stat().st_size != expected_size:
                return True
    return False


def extract_house_fd_bulk_zip(zip_path: Path, dest_dir: Path) -> None:
    """Estrae zip bulk FD House: rimuove i file top-level che verranno estratti, poi extractall."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            norm = name.replace("\\", "/").strip("/")
            if not norm or "/" in norm:
                continue
            (dest_dir / norm).unlink(missing_ok=True)
        zf.extractall(dest_dir)


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def make_content_hash(*parts: str | None) -> str:
    payload = "||".join(normalize_whitespace(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_transaction_source_hash(
    document_hash: str | None,
    source_page: str | int | None,
    transaction_date: str | None,
    asset_name: str | None,
    transaction_type: str | None,
    amount_range: str | None,
    owner_type: str | None = None,
) -> str:
    return make_content_hash(
        document_hash,
        str(source_page) if source_page is not None else None,
        transaction_date,
        asset_name,
        transaction_type,
        amount_range,
        owner_type,
    )


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
