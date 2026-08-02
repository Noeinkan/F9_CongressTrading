"""OGE 278-T (periodic transactions) and 278e (annual report) PDF parsers.

Mirrors the layout in ``parse_ptr.py``: per-page table extraction with a regex
fallback on the merged-cell text, plus a process-pool timeout so a malformed
PDF cannot hang the whole ingest pipeline.

Scanned OGE filings often ship with a garbage embedded text layer. When
pdfplumber yields zero transaction rows for a page we re-OCR that page via
:mod:`src.ocr_pdf` (Tesseract) and re-run the text heuristics on cleaned OCR.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
import re
from pathlib import Path

import pdfplumber

from .ocr_pdf import OcrUnavailableError, ocr_page_text
from .utils import normalize_whitespace, parse_date

# OCR path can take tens of seconds per page; 8-page 278-Ts need headroom.
OGE_PARSE_TIMEOUT_SECONDS = 180

# OGE 278-T "Description" codes: P=Purchase, S=Sale, E=Exchange.
_DESCRIPTION_CODE_MAP: dict[str, str] = {
    "P": "P (Buy)",
    "S": "S (Sell)",
    "E": "E (Exchange)",
}

_OWNER_CODE_MAP: dict[str, str] = {
    "SP": "spouse",
    "SPOUSE": "spouse",
    "DC": "dependent",
    "DEPENDENT": "dependent",
    "CHILD": "dependent",
    "JT": "joint",
    "JOINT": "joint",
    "FILER": "filer",
    "SELF": "filer",
}

_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_AMOUNT_RE = re.compile(r"\$?[\d,]+(?:\s*-\s*\$?[\d,]+)?")

# Fuzzy date like 2/2l/2026 after common OCR confusions in date tokens only.
_FUZZY_DATE_RE = re.compile(
    r"\b(?P<m>[\dIlO|]{1,2})/(?P<d>[\dIlO|]{1,2})/(?P<y>[\dIlO>]{2,4})\b",
    re.IGNORECASE,
)
# Only touch amounts that start with $ so we never rewrite bare numbers/words.
# Do not allow newlines inside amounts — otherwise a trailing \n gets eaten and
# adjacent transaction lines are glued together.
_FUZZY_AMOUNT_RE = re.compile(
    r"\$(?P<body>[\dIlO, ]{1,}(?:[ \t]*[-–—][ \t]*\$?[\dIlO, ]{1,})?)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clean_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return normalize_whitespace(text.replace("\x00", " "))


def _ocr_digit_map(token: str) -> str:
    """Map common OCR letter/digit confusions inside a numeric token."""
    mapping = str.maketrans(
        {
            "l": "1",
            "I": "1",
            "i": "1",
            "|": "1",
            "O": "0",
            "o": "0",
            ">": "2",
            "S": "5",
            "B": "8",
            "Z": "2",
        }
    )
    return token.translate(mapping)


def repair_ocr_text(text: str) -> str:
    """Normalize common OCR artifacts in OGE page text (dates, $-amounts only)."""
    if not text:
        return ""
    cleaned = text.replace("\x00", " ").replace("–", "-").replace("—", "-")

    def _fix_date(match: re.Match[str]) -> str:
        m = re.sub(r"\D", "", _ocr_digit_map(match.group("m"))) or "0"
        d = re.sub(r"\D", "", _ocr_digit_map(match.group("d"))) or "0"
        y = re.sub(r"\D", "", _ocr_digit_map(match.group("y"))) or "0"
        return f"{m}/{d}/{y}"

    cleaned = _FUZZY_DATE_RE.sub(_fix_date, cleaned)

    def _fix_amount(match: re.Match[str]) -> str:
        body = match.group("body")
        parts: list[str] = []
        for chunk in re.split(r"\s*-\s*", body):
            chunk = chunk.strip().lstrip("$")
            digits = re.sub(r"[^\d]", "", _ocr_digit_map(chunk))
            if not digits:
                parts.append(chunk)
                continue
            parts.append(f"{int(digits):,}")
        if len(parts) == 1:
            return f"${parts[0]}"
        return f"${parts[0]}-${parts[1]}"

    cleaned = _FUZZY_AMOUNT_RE.sub(_fix_amount, cleaned)
    return cleaned


def _parse_ocr_date(value: str) -> str | None:
    repaired = repair_ocr_text(value)
    direct = parse_date(repaired)
    if direct:
        return direct
    match = _DATE_RE.search(repaired)
    if match:
        return parse_date(match.group(0))
    fuzzy = _FUZZY_DATE_RE.search(repaired)
    if fuzzy:
        candidate = (
            f"{_ocr_digit_map(fuzzy.group('m'))}/"
            f"{_ocr_digit_map(fuzzy.group('d'))}/"
            f"{_ocr_digit_map(fuzzy.group('y'))}"
        )
        candidate = re.sub(r"[^\d/]", "", candidate)
        return parse_date(candidate)
    return None


def _normalize_tx_code(code: str) -> str:
    """Map P/S/E or Purchase/Sale/Exchange fragments to canonical labels."""
    raw = _clean_cell(code).upper()
    if not raw:
        return ""
    if raw in _DESCRIPTION_CODE_MAP:
        return _DESCRIPTION_CODE_MAP[raw]
    # Single letter after OCR noise (e.g. "P." / "(P)")
    letter = re.sub(r"[^A-Z]", "", raw)
    if letter in _DESCRIPTION_CODE_MAP:
        return _DESCRIPTION_CODE_MAP[letter]
    # OCR mangling: "purchaso" / "ourthase" / "purd…" → purchase; "salo" → sale.
    compact = letter
    if (
        "PURCHASE" in raw
        or raw == "BUY"
        or "PURCH" in compact
        or "URCHAS" in compact
        or "URTHAS" in compact  # ourthase
        or "PURD" in compact
        or (compact.endswith("HASE") and "EX" not in compact)
    ):
        return "P (Buy)"
    if "SALE" in raw or raw == "SELL" or compact in {"SALE", "SELL", "SALO"}:
        return "S (Sell)"
    if "EXCHANGE" in raw or "XCHANG" in compact:
        return "E (Exchange)"
    return ""


def _detect_form_type(pdf_path: Path) -> str:
    """Return ``"OGE278T"`` or ``"OGE278e"`` based on the page-1 header text."""
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            raise ValueError(f"Empty PDF: {pdf_path}")
        first_page_text = pdf.pages[0].extract_text() or ""

    upper = first_page_text.upper()
    if "OGE FORM 278-T" in upper or "OGE FORM 278 T" in upper or "278-T" in upper:
        return "OGE278T"
    if "OGE FORM 278E" in upper or "278E" in upper or "278E." in upper:
        return "OGE278e"

    alnum = re.sub(r"[^A-Za-z0-9]", "", upper)
    if "278T" in alnum and "278E" not in alnum:
        return "OGE278T"
    if "278E" in alnum and "278T" not in alnum:
        return "OGE278e"
    if "278T" in alnum and "278E" in alnum:
        return "OGE278T"

    raise ValueError(
        f"Could not detect OGE form type on page 1 of {pdf_path} "
        f"(expected 'OGE Form 278-T' or 'OGE Form 278e')."
    )


def _extract_filer_name(first_page_text: str) -> str:
    """Best-effort filer name from the header text."""
    patterns = (
        r"Reporting\s+Individual\s*:?\s*(.+)",
        r"Filer\s*Name\s*:?\s*(.+)",
        r"Name\s+of\s+Reporting\s+Individual\s*:?\s*(.+)",
        r"Name\s*:?\s*(.+)",
    )
    junk = {"mi", "position", "title", "agency", "department", "status", "date"}
    for pattern in patterns:
        match = re.search(pattern, first_page_text, re.IGNORECASE)
        if match:
            candidate = normalize_whitespace(match.group(1))
            if candidate:
                candidate = re.split(r"\bDate\b|\bStatus\b|\bPosition\b|\bTitle\b", candidate, maxsplit=1)[0]
                candidate = candidate.strip(" :")
                tokens = [t for t in re.split(r"\s+", candidate) if t]
                # Reject form-label junk like "MI Position".
                if len(tokens) <= 2 and all(t.casefold().strip(".,") in junk for t in tokens):
                    continue
                if candidate:
                    return candidate
    return ""


def _extract_filing_date(first_page_text: str) -> str | None:
    patterns = (
        r"Filing\s*Date\s*:?\s*(.+)",
        r"Date\s+of\s+Report\s*:?\s*(.+)",
        r"Date\s+Filed\s*:?\s*(.+)",
        r"Period\s*:?\s*(.+)",
    )
    repaired = repair_ocr_text(first_page_text)
    for pattern in patterns:
        match = re.search(pattern, repaired, re.IGNORECASE)
        if match:
            candidate = _parse_ocr_date(match.group(1))
            if candidate:
                return candidate
    m = _DATE_RE.search(repaired)
    if m:
        return parse_date(m.group(0))
    return None


def _owner_from_cells(cells: list[str]) -> str:
    """Look at every cell on a row and map any owner code to the canonical label."""
    joined = " ".join(c for c in cells if c).lower()
    if not joined.strip():
        return "filer"
    for code, label in _OWNER_CODE_MAP.items():
        if re.search(rf"(?:^|\s){re.escape(code.lower())}(?:\s|$|,)", joined):
            return label
    if "spouse" in joined:
        return "spouse"
    if "dependent" in joined or "child" in joined:
        return "dependent"
    if "joint" in joined:
        return "joint"
    if "self" in joined or "filer" in joined:
        return "filer"
    return "filer"


def _fix_ocr_amount_separators(value: str) -> str:
    """Rewrite OCR ``$1.000.001`` / ``$15.001`` thousands-dots into commas."""

    def _fix_one(match: re.Match[str]) -> str:
        body = match.group(1)
        body = re.sub(r"\.(?=\d{3}(?:\D|$))", ",", body)
        return f"${body}"

    return re.sub(r"\$\s*([\d.,]+(?:\s*[-–—•]\s*\$?[\d.,]+)?)", _fix_one, value)


def _normalize_amount_range(value: str) -> str:
    repaired = _fix_ocr_amount_separators(repair_ocr_text(value))
    repaired = repaired.replace("•", "-").replace("–", "-").replace("—", "-")
    match = _FUZZY_AMOUNT_RE.search(repaired) or _AMOUNT_RE.search(repaired)
    if match:
        return _clean_cell(match.group(0))
    return _clean_cell(repaired)


def _is_notify_cell(value: str) -> bool:
    folded = _clean_cell(value).casefold().strip(" .\"'|")
    return folded in {"yes", "no", "y", "n", "ya", "ye"}


def _asset_looks_like_ocr_garbage(asset: str) -> bool:
    """True when an asset cell is mostly OCR noise rather than a name."""
    text = _clean_cell(asset)
    if len(text) < 3:
        return True
    letters = sum(ch.isalpha() for ch in text)
    if letters < 4:
        return True
    # Scanned 278-Ts often yield mojibake / punctuation soups.
    if letters / len(text) < 0.35:
        return True
    weird = sum(1 for ch in text if not ch.isascii() or ch in "~•■▪▫")
    if weird >= 3 and weird / len(text) > 0.08:
        return True
    return False


def _amount_looks_plausible(amount: str) -> bool:
    """True when amount looks like a disclosed dollar range, not Yes/No/noise."""
    text = _normalize_amount_range(amount)
    if not text:
        return False
    folded = text.casefold().strip(" .\"'")
    if folded in {"yes", "no", "y", "n", "true", "false"}:
        return False
    digits = re.sub(r"\D", "", text)
    # Truncated OCR crumbs like "$250" are not OGE buckets.
    if len(digits) < 4:
        return False
    if re.search(r"\$\s*[\d,]+", text):
        return True
    # Bare ranges like "1001 - 15000" (no $) still count.
    if re.search(r"\d{3,}\s*[-–—]\s*\$?\d{3,}", text):
        return True
    return False


def is_usable_278t_row(row: dict[str, object]) -> bool:
    """Drop undated OCR garbage that would otherwise land in ``transactions``.

    Real 278-T rows always disclose a transaction date and a dollar amount.
    Scanned filings often emit punctuation soups with Yes/No "amounts" from
    adjacent form fields — those must not reach the dashboard.
    """
    asset = str(row.get("asset") or "")
    if _asset_looks_like_ocr_garbage(asset):
        return False
    if not row.get("transaction_date"):
        return False
    amount = str(row.get("amount_range") or "")
    if not _amount_looks_plausible(amount):
        return False
    tx = str(row.get("transaction_type") or "")
    if tx not in {"P (Buy)", "S (Sell)", "E (Exchange)"}:
        tx = _normalize_tx_code(tx)
    if tx not in {"P (Buy)", "S (Sell)", "E (Exchange)"}:
        return False
    # Reject absurd OCR dates (e.g. year 0201 / 0202 from digit confusion).
    date_s = str(row.get("transaction_date") or "")
    if date_s:
        try:
            year = int(date_s[:4])
        except ValueError:
            return False
        if year < 2000 or year > 2100:
            return False
    return True


def _rows_quality_score(rows: list[dict[str, object]]) -> tuple[int, int]:
    """Prefer canonical types + plausible assets over raw row count."""
    score = 0
    for row in rows:
        tx = str(row.get("transaction_type") or "")
        if tx in {"P (Buy)", "S (Sell)", "E (Exchange)"}:
            score += 3
        if _amount_looks_plausible(str(row.get("amount_range") or "")):
            score += 1
        asset = str(row.get("asset") or "")
        if asset and not _asset_looks_like_ocr_garbage(asset):
            score += 2
        if "OGE" in asset.upper() and "278" in asset:
            score -= 5
    return score, len(rows)


# Official OGE 278-T row shape (Integrity / paper form):
#   # | Description | Type | Date | Notification Received Over 30 Days Ago | Amount
# The Yes/No column is NOT the amount — earlier parses treated it as such.
# Word forms for free-text / OCR. Bare P/S/E are only accepted in ``_TX_ROW_RE``
# where a date must follow immediately (avoids matching random letters in bonds).
_TX_TYPE_WORD = (
    r"(?:purchase|sale|exchange|purchaso|ourthase|purd\w*|salo)"
)
_TX_ROW_RE = re.compile(
    r"(?:(?P<owner>SP|JT|DC|Filer|Self|Spouse|Dependent)\s+)?"
    r"(?P<asset>[A-Za-z][A-Za-z0-9 ,.&'/*\-_%()]{2,}?)\s+"
    rf"(?P<code>{_TX_TYPE_WORD}|[PSE])\b\s*[,.]?\s*"
    r"(?P<date>\d{1,2}[/Jl|]\d{1,2}[/Jl|]\d{2,4})\s+"
    r"(?:(?P<notify>yes|no|ya|ye)\b[\s|:]*)?"
    r"(?P<amount>\$\s*[\d,]+(?:\.\d+)?(?:\s*[-–—•]\s*\$?\s*[\d,]+(?:\.\d+)?)?)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# 278-T parser
# --------------------------------------------------------------------------- #
def _candidate_from_fields(
    *,
    asset: str,
    code: str,
    transaction_date: str | None,
    amount_range: str,
    owner: str,
    page_number: int,
    parse_warning: str | None = None,
) -> dict[str, object] | None:
    asset = _clean_cell(asset)
    if not asset or len(asset) < 2:
        return None
    if asset.casefold() in {"asset", "description", "asset description"}:
        return None
    # Strip a leading row index that leaked into the asset cell ("12 APPLE…").
    asset = re.sub(r"^\d{1,3}\s+", "", asset).strip()
    warning = parse_warning if parse_warning is not None else (
        None if transaction_date else "missing_transaction_date"
    )
    candidate = {
        "transaction_date": transaction_date,
        "asset": asset,
        "transaction_type": _normalize_tx_code(code),
        "amount_range": _normalize_amount_range(amount_range),
        "owner_type": owner,
        "source_page": page_number,
        "parse_warning": warning,
    }
    return candidate if is_usable_278t_row(candidate) else None


def _parse_positional_278t_cells(cells: list[str]) -> tuple[str, str, str | None, str, str] | None:
    """Map a row of cells to (owner, asset, date, code, amount).

    Handles the official 6-col layout (with # + Yes/No notification) as well as
    older 4/5-col variants without the notification column.
    """
    # Drop trailing empty cells but keep interior blanks.
    while cells and not cells[-1]:
        cells = cells[:-1]
    if len(cells) < 4:
        return None

    # # | Asset | Type | Date | Yes/No | Amount
    if len(cells) >= 6 and _is_notify_cell(cells[4]) and _amount_looks_plausible(cells[5]):
        return "filer", cells[1], _parse_ocr_date(cells[3]), cells[2], cells[5]
    # Asset | Type | Date | Yes/No | Amount
    if len(cells) >= 5 and _is_notify_cell(cells[3]) and _amount_looks_plausible(cells[4]):
        return "filer", cells[0], _parse_ocr_date(cells[2]), cells[1], cells[4]
    # # | Asset | Type | Date | Amount  (notification blank / missing)
    if len(cells) >= 5 and cells[0].isdigit() and _amount_looks_plausible(cells[4]):
        return "filer", cells[1], _parse_ocr_date(cells[3]), cells[2], cells[4]
    # Owner | Asset | Type | Date | Amount
    if len(cells) >= 5 and _amount_looks_plausible(cells[4]) and not _is_notify_cell(cells[4]):
        return _owner_from_cells([cells[0]]), cells[1], _parse_ocr_date(cells[3]), cells[2], cells[4]
    # Asset | Type | Date | Amount
    if len(cells) >= 4 and _amount_looks_plausible(cells[3]):
        return "filer", cells[0], _parse_ocr_date(cells[2]), cells[1], cells[3]
    return None


def _parse_278t_table(
    table: list[list[object]], page_number: int
) -> list[dict[str, object]]:
    """Parse one table (list-of-rows) extracted by pdfplumber."""
    rows: list[dict[str, object]] = []
    if not table:
        return rows

    header_cells = [repair_ocr_text(_clean_cell(c)) for c in table[0]]
    header_lower = [c.casefold() for c in header_cells]
    # "Description" alone is the asset column on modern 278-T; "Type" is P/S/E.
    asset_idx = next(
        (
            i
            for i, c in enumerate(header_lower)
            if "asset" in c or c == "description" or "description" == c.strip()
        ),
        None,
    )
    # Prefer an explicit Type header over a bare "description".
    type_idx = next(
        (
            i
            for i, c in enumerate(header_lower)
            if c == "type" or "transaction type" in c or (c.startswith("type") and "asset" not in c)
        ),
        None,
    )
    date_idx = next(
        (i for i, c in enumerate(header_lower) if "transaction date" in c or c == "date"),
        None,
    )
    amount_idx = next(
        (i for i, c in enumerate(header_lower) if "amount" in c),
        None,
    )
    notify_idx = next(
        (
            i
            for i, c in enumerate(header_lower)
            if "notification" in c or "30 days" in c or c in {"yes/no", "over 30"}
        ),
        None,
    )
    owner_idx = next(
        (i for i, c in enumerate(header_lower) if "owner" in c or "reporting" in c),
        None,
    )

    use_positional = asset_idx is None and len(header_cells) >= 4

    for raw in table[1:]:
        if not raw or all(_clean_cell(c) == "" for c in raw):
            continue
        cells = [repair_ocr_text(_clean_cell(c)) for c in raw]
        if use_positional:
            mapped = _parse_positional_278t_cells(cells)
            if mapped is None:
                continue
            owner, asset, transaction_date, code, amount_range = mapped
        else:
            asset = cells[asset_idx] if asset_idx is not None and asset_idx < len(cells) else ""
            transaction_date = (
                _parse_ocr_date(cells[date_idx]) if date_idx is not None and date_idx < len(cells) else None
            )
            code = cells[type_idx] if type_idx is not None and type_idx < len(cells) else ""
            # Never treat the notification Yes/No column as the amount.
            if amount_idx is not None and amount_idx < len(cells):
                amount_range = cells[amount_idx]
            elif notify_idx is not None and notify_idx + 1 < len(cells):
                amount_range = cells[notify_idx + 1]
            else:
                amount_range = ""
            if _is_notify_cell(amount_range):
                # Header mis-detect: slide one column right looking for $.
                for cell in cells:
                    if _amount_looks_plausible(cell):
                        amount_range = cell
                        break
            owner = (
                _owner_from_cells(cells)
                if owner_idx is None
                else _owner_from_cells([cells[owner_idx]] if owner_idx < len(cells) else [])
            )
        candidate = _candidate_from_fields(
            asset=asset,
            code=code,
            transaction_date=transaction_date,
            amount_range=amount_range,
            owner=owner,
            page_number=page_number,
        )
        if candidate:
            rows.append(candidate)

    # Scanned 278-Ts often collapse every trade into one mega-cell. Fall back to
    # the text heuristics on the joined cell blob when column parsing is thin.
    if len(rows) < 2:
        blob = "\n".join(
            repair_ocr_text(_clean_cell(c))
            for raw in table
            for c in (raw or [])
            if _clean_cell(c)
        )
        text_rows = _parse_278t_text(blob, page_number)
        if len(text_rows) > len(rows):
            return text_rows
    return rows


def _append_unique_278t_row(
    rows: list[dict[str, object]],
    seen: set[tuple[str, str, str]],
    candidate: dict[str, object] | None,
) -> None:
    if not candidate:
        return
    key = (
        str(candidate["transaction_date"] or ""),
        str(candidate["asset"] or "")[:80],
        str(candidate["amount_range"] or ""),
    )
    if key in seen:
        return
    seen.add(key)
    rows.append(candidate)


def _parse_278t_numbered_chunks(text: str, page_number: int) -> list[dict[str, object]]:
    """Split on leading row indexes (``1 ASSET…``) and parse each chunk.

    Scanned pages often omit the transaction date between type and Yes/No, or
    put the date on the next wrapped line. Per-chunk extraction is more
    tolerant than a single-line regex.
    """
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    chunks = re.split(r"(?m)(?=^\s*\d{1,3}\s+[A-Za-z*])", text)
    amount_re = re.compile(
        r"\$\s*[\d,]+(?:\.\d+)?(?:\s*[-–—•]\s*\$?\s*[\d,]+(?:\.\d+)?)?",
        re.IGNORECASE,
    )
    type_re = re.compile(rf"\b({_TX_TYPE_WORD}|[PSE])\b", re.IGNORECASE)
    date_re = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        amount_match = amount_re.search(chunk)
        type_match = type_re.search(chunk)
        if not amount_match or not type_match:
            continue
        if type_match.start() > amount_match.start():
            continue
        dates = list(date_re.finditer(chunk))
        # Prefer a date that sits after the type token (transaction date), not a
        # maturity date embedded earlier in the bond description ("DUE 02/15/31").
        transaction_date = None
        for d in dates:
            if d.start() >= type_match.start():
                transaction_date = _parse_ocr_date(d.group(0))
                if transaction_date:
                    break
        asset = chunk[: type_match.start()]
        asset = re.sub(r"^\d{1,3}\s+", "", asset).strip(" -\t")
        candidate = _candidate_from_fields(
            asset=asset,
            code=type_match.group(1),
            transaction_date=transaction_date,
            amount_range=amount_match.group(0),
            owner="filer",
            page_number=page_number,
        )
        _append_unique_278t_row(rows, seen, candidate)
    return rows


def _parse_278t_text(text: str, page_number: int) -> list[dict[str, object]]:
    """Regex fallback for 278-T pages where the table layout broke.

    Accepts the official Yes/No notification token between date and amount:
    ``… purchase 1/22/2026 Yes $100,001 - $250,000``.
    """
    rows: list[dict[str, object]] = []
    if not text:
        return rows
    repaired = _fix_ocr_amount_separators(repair_ocr_text(text))
    # Normalize common OCR date separators (J / | standing in for /).
    repaired = re.sub(r"(\d{1,2})[Jl|](\d{1,2})[Jl|](\d{2,4})", r"\1/\2/\3", repaired)

    seen: set[tuple[str, str, str]] = set()
    for match in _TX_ROW_RE.finditer(repaired):
        owner_code_raw = match.group("owner")
        owner_code = owner_code_raw.upper() if owner_code_raw else "FILER"
        owner = _OWNER_CODE_MAP.get(owner_code, owner_code.lower())
        asset = _clean_cell(match.group("asset"))
        # Drop leading "#." row markers left inside the asset capture.
        asset = re.sub(r"^\d{1,3}[\).:\-]\s*", "", asset).strip()
        transaction_date = _parse_ocr_date(match.group("date")) or parse_date(match.group("date"))
        candidate = _candidate_from_fields(
            asset=asset,
            code=match.group("code"),
            transaction_date=transaction_date,
            amount_range=match.group("amount"),
            owner=owner,
            page_number=page_number,
        )
        _append_unique_278t_row(rows, seen, candidate)

    # Numbered-chunk pass recovers rows the single-regex pass missed (wrapped
    # dates, missing date between type and Yes/No, etc.).
    for candidate in _parse_278t_numbered_chunks(repaired, page_number):
        _append_unique_278t_row(rows, seen, candidate)
    return rows


def _embedded_text_is_garbage(text: str) -> bool:
    """Heuristic: scanned PDFs leave a high-noise embedded text layer."""
    if not text or len(text) < 40:
        return True
    letters = sum(ch.isalpha() for ch in text)
    ratio = letters / max(len(text), 1)
    if ratio < 0.45:
        return True
    weird = sum(1 for ch in text if not ch.isascii() or ch in "~•■▪▫")
    return weird / max(len(text), 1) > 0.03


def _rows_from_page_text_and_table(
    text: str,
    table: list[list[object]] | None,
    page_number: int,
) -> list[dict[str, object]]:
    table_rows: list[dict[str, object]] = []
    if table:
        table_rows = _parse_278t_table(table, page_number)
    text_rows = _parse_278t_text(text, page_number)
    if len(table_rows) >= len(text_rows) and table_rows:
        return table_rows
    if text_rows:
        return text_rows
    return table_rows


def parse_oge_278t(pdf_path: Path) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    """Parse an OGE Form 278-T (periodic transactions) PDF.

    Returns ``(header, rows)``. ``header`` has keys ``filer_name``,
    ``filing_date``, ``form_type``, and optionally ``ocr_status``
    (``"used"`` / ``"unavailable"`` / ``None``).
    """
    form_type = _detect_form_type(pdf_path)
    if form_type != "OGE278T":
        raise ValueError(
            f"{pdf_path} is not a 278-T (detected {form_type!r}); use parse_oge_278e"
        )

    header: dict[str, str | None] = {
        "filer_name": None,
        "filing_date": None,
        "form_type": "OGE278T",
        "ocr_status": None,
    }
    rows: list[dict[str, object]] = []
    ocr_used = False
    ocr_unavailable = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if page_index == 0:
                header["filer_name"] = _extract_filer_name(text) or _extract_filer_name(
                    repair_ocr_text(text)
                )
                header["filing_date"] = _extract_filing_date(text)
            table = page.extract_table()
            page_rows = _rows_from_page_text_and_table(text, table, page_index + 1)

            # Scanned filings often have a junk embedded layer that still yields
            # a few partial rows. Prefer real OCR whenever the page looks noisy
            # or embedded parsing found nothing.
            needs_ocr = (not page_rows) or _embedded_text_is_garbage(text)
            if needs_ocr:
                try:
                    ocr_text = ocr_page_text(pdf_path, page_index)
                    ocr_used = True
                    if page_index == 0 and not header.get("filer_name"):
                        header["filer_name"] = _extract_filer_name(ocr_text)
                    if page_index == 0 and not header.get("filing_date"):
                        header["filing_date"] = _extract_filing_date(ocr_text)
                    ocr_rows = _parse_278t_text(ocr_text, page_index + 1)
                    # Keep the higher-quality source (not merely the longer list —
                    # OCR can invent many low-quality false positives).
                    if _rows_quality_score(ocr_rows) >= _rows_quality_score(page_rows):
                        page_rows = ocr_rows
                except OcrUnavailableError:
                    ocr_unavailable = True
                except Exception:
                    # Page-level OCR failure should not abort the whole PDF.
                    pass

            rows.extend(page_rows)

    if ocr_used:
        header["ocr_status"] = "used"
    elif ocr_unavailable:
        header["ocr_status"] = "unavailable"

    return header, rows


# --------------------------------------------------------------------------- #
# 278e parser (annual report — holdings only)
# --------------------------------------------------------------------------- #
def _parse_278e_table(
    table: list[list[object]], page_number: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not table:
        return rows
    header_cells = [_clean_cell(c) for c in table[0]]
    header_lower = [c.casefold() for c in header_cells]
    asset_idx = next((i for i, c in enumerate(header_lower) if "asset" in c), None)
    value_idx = next((i for i, c in enumerate(header_lower) if "value" in c), None)
    owner_idx = next(
        (
            i
            for i, c in enumerate(header_lower)
            if "owner" in c or "filer" in c or "spouse" in c or "dependent" in c
        ),
        None,
    )
    type_idx = next((i for i, c in enumerate(header_lower) if "type" in c), None)

    for raw in table[1:]:
        if not raw or all(_clean_cell(c) == "" for c in raw):
            continue
        cells = [_clean_cell(c) for c in raw]
        asset = _clean_cell(cells[asset_idx]) if asset_idx is not None and asset_idx < len(cells) else ""
        if not asset:
            continue
        value_range = _clean_cell(cells[value_idx]) if value_idx is not None and value_idx < len(cells) else ""
        owner = (
            _owner_from_cells(cells)
            if owner_idx is None
            else _owner_from_cells([cells[owner_idx]] if owner_idx < len(cells) else [])
        )
        asset_type = _clean_cell(cells[type_idx]) if type_idx is not None and type_idx < len(cells) else ""
        rows.append(
            {
                "asset_name": asset,
                "value_range": value_range,
                "owner_type": owner,
                "asset_type": asset_type,
                "source_page": page_number,
                "parse_warning": None,
            }
        )
    return rows


def _parse_278e_text(text: str, page_number: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not text:
        return rows
    for line in text.splitlines():
        if not _DATE_RE.search(line) and not _AMOUNT_RE.search(line):
            continue
        match = re.search(
            r"(?P<asset>[A-Z][A-Za-z0-9 ,&\.\-]{3,}?)\s+(?P<owner>SP|Spouse|DC|Dependent|Filer|JT|Joint)\s+(?P<value>\$?[\d,]+(?:\s*-\s*\$?[\d,]+)?)",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        rows.append(
            {
                "asset_name": _clean_cell(match.group("asset")),
                "value_range": _clean_cell(match.group("value")),
                "owner_type": _OWNER_CODE_MAP.get(
                    match.group("owner").upper(), match.group("owner").lower()
                ),
                "asset_type": "",
                "source_page": page_number,
                "parse_warning": "fallback_text_parse",
            }
        )
    return rows


def parse_oge_278e(pdf_path: Path) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    """Parse an OGE Form 278e (annual report) PDF."""
    form_type = _detect_form_type(pdf_path)
    if form_type != "OGE278e":
        raise ValueError(
            f"{pdf_path} is not a 278e (detected {form_type!r}); use parse_oge_278t"
        )

    header: dict[str, str | None] = {
        "filer_name": None,
        "filing_date": None,
        "form_type": "OGE278e",
    }
    holdings: list[dict[str, object]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if page_index == 0:
                header["filer_name"] = _extract_filer_name(text)
                header["filing_date"] = _extract_filing_date(text)
            table = page.extract_table()
            if table:
                table_rows = _parse_278e_table(table, page_index + 1)
                if table_rows:
                    holdings.extend(table_rows)
                    continue
            holdings.extend(_parse_278e_text(text, page_index + 1))

    return header, holdings


# --------------------------------------------------------------------------- #
# Process-pool wrappers
# --------------------------------------------------------------------------- #
def _parse_278t_worker(pdf_path_str: str) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    return parse_oge_278t(Path(pdf_path_str))


def _parse_278e_worker(pdf_path_str: str) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    return parse_oge_278e(Path(pdf_path_str))


def parse_oge_278t_safe(
    pdf_path: Path,
    *,
    timeout_seconds: int = OGE_PARSE_TIMEOUT_SECONDS,
) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    """Process-pool wrapper for ``parse_oge_278t`` with a hard timeout."""
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_parse_278t_worker, str(pdf_path))
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"Timed out parsing OGE 278-T PDF after {timeout_seconds}s: {pdf_path}"
            ) from exc


def parse_oge_278e_safe(
    pdf_path: Path,
    *,
    timeout_seconds: int = OGE_PARSE_TIMEOUT_SECONDS,
) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    """Process-pool wrapper for ``parse_oge_278e`` with a hard timeout."""
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_parse_278e_worker, str(pdf_path))
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"Timed out parsing OGE 278e PDF after {timeout_seconds}s: {pdf_path}"
            ) from exc
