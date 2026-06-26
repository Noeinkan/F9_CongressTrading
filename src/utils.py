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


# Heuristics for asset kinds that do not have a continuous market price on
# Polygon (or any retail quote feed) — Treasury notes, municipal / corporate
# bonds, money-market funds, college / water / hospital / school district
# issues, etc.  When a transaction's ticker matches one of these patterns
# the dashboard should not render an empty "—" for P&L: it should explicitly
# label the row as non-equity so the user understands the value will never
# populate from the Polygon cache.
_NON_EQUITY_ASSET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bGO Bonds?\b", re.I),
    re.compile(r"\bRev(?:enue)?\s+Bonds?\b", re.I),
    re.compile(r"\bMunicipal\b", re.I),
    re.compile(r"\bCommunity College\b", re.I),
    re.compile(r"\bSchool District\b", re.I),
    re.compile(r"\bPublic Works\b", re.I),
    re.compile(r"\bUS(?:\\s+Treasury)?\s+(?:Treasury\s+)?(?:Note|Bond|Bill)s?\b", re.I),
    re.compile(r"\bU\.?\s*S\.?\s+Treasury\b", re.I),
    re.compile(r"\bTreasury\s+Bill\b", re.I),
    re.compile(r"\bUSD\b", re.I),
    re.compile(r"\bAuthority\b", re.I),
    re.compile(r"\b(?:Corporate|Municipal)\s+Bonds?\b", re.I),
    re.compile(r"\b(?:Total|Intl|International)\s+Bond\b", re.I),
    re.compile(r"\bBond\s+(?:Fund|ETF|Adv(?:isor)?)\b", re.I),
    re.compile(r"\bNotes?\s+(?:due|maturing)\b", re.I),
    re.compile(r"\bCUSIP\b", re.I),
    re.compile(r"\b(?:Certificate|Commercial Paper)\b", re.I),
    re.compile(r"\bDistrict\b", re.I),
    re.compile(r"\bWater\s+(?:&\s+Wastewater|&)\b", re.I),
    re.compile(r"\bHospital\b", re.I),
    re.compile(r"\bHealth\s+Facilities\b", re.I),
)


def is_non_equity_asset(ticker: str | None, asset_name_raw: str | None = "") -> bool:
    """Heuristic: True if the asset has no continuous equity price.

    Used by the API to mark rows whose P&L / Return columns can never
    populate from the Polygon daily-bar cache (Treasury notes, municipal
    bonds, bond funds, etc.). The check intentionally accepts the raw
    ``asset_name_raw`` string from the disclosure so the suffix tags
    parsed by the PTR/FD pipelines (e.g. ``[GS]`` for Goldman Sachs, ``[CS]``
    for corporate Schwab, ``[ST]`` for stock) do not defeat the match.
    """
    text = f"{ticker or ''} {asset_name_raw or ''}"
    if not text.strip():
        return False
    return any(p.search(text) for p in _NON_EQUITY_ASSET_PATTERNS)


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


def extract_house_fd_bulk_zip(
    zip_path: Path,
    dest_dir: Path,
    *,
    force: bool = False,
) -> dict[str, int]:
    """
    Estrae zip bulk FD House in modo robusto.

    Se force=True, svuota completamente dest_dir (solo file top-level dello zip) prima di estrarre:
    utile quando i metadata locali sono vecchi ma hanno la stessa dimensione del file nello zip
    succoso (raro, ma succede) oppure quando unlink non ha propagato.

    Ritorna un dict {filename: size_on_disk} dei file effettivamente presenti su disco
    dopo l'estrazione. Se la dimensione di un file estratto non corrisponde a quella
    che lo zip dichiarava, logga un avviso (perche significa che il file sul disco non
    e stato aggiornato).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        top: list[tuple[str, int]] = []
        for name in zf.namelist():
            norm = name.replace("\\", "/").strip("/")
            if not norm or "/" in norm:
                continue
            top.append((norm, zf.getinfo(name).file_size))

        if force:
            for member_name, _ in top:
                (dest_dir / member_name).unlink(missing_ok=True)

        zf.extractall(dest_dir)

    extracted: dict[str, int] = {}
    for member_name, zip_size in top:
        dest = dest_dir / member_name
        if dest.exists():
            actual = dest.stat().st_size
            extracted[member_name] = actual
            if actual != zip_size:
                # File sul disco ha dimensione diversa da quanto estratto dallo zip.
                # Caso tipico: file era aperto da un altro processo durante l'estrazione.
                print(
                    f"[extract_house_fd_bulk_zip] ATTENZIONE: {dest} on-disk size={actual} "
                    f"!= zip size={zip_size} (il file potrebbe non essere stato sovrascritto).",
                    flush=True,
                )
    return extracted


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
