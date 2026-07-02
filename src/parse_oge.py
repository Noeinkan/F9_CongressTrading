"""OGE 278-T (periodic transactions) and 278e (annual report) PDF parsers.

Mirrors the layout in ``parse_ptr.py``: per-page table extraction with a regex
fallback on the merged-cell text, plus a 20-second ``ProcessPoolExecutor``
timeout so a malformed PDF cannot hang the whole ingest pipeline.

Header detection — both forms say "OGE Form 278" on page 1; the suffix
(``-T`` or ``-e``) distinguishes them. If neither appears we raise a clear
error so the caller can skip the file instead of producing garbage rows.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
import re
from pathlib import Path

import pdfplumber

from .utils import normalize_whitespace, parse_amount_range, parse_date

OGE_PARSE_TIMEOUT_SECONDS = 20

# OGE 278-T "Description" codes: P=Purchase, S=Sale, E=Exchange.
# The form layout has a one-letter code in a column whose header reads
# "Description" or "Transaction".  We keep both the canonical and a friendlier
# label so the API can render Buy/Sell/Exchange without re-mapping.
_DESCRIPTION_CODE_MAP: dict[str, str] = {
    "P": "P (Buy)",
    "S": "S (Sell)",
    "E": "E (Exchange)",
}

# OGE 278-T Owner codes (column "Reporting Status" or similar):
#   SP/Spouse -> spouse, DC/Dependent -> dependent, JT/Joint -> joint,
#   blank or filer -> filer.
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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clean_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return normalize_whitespace(text.replace("\x00", " "))


def _detect_form_type(pdf_path: Path) -> str:
    """Return ``"OGE278T"`` or ``"OGE278e"`` based on the page-1 header text.

    Raises ``ValueError`` if neither is found so the caller can skip the file.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            raise ValueError(f"Empty PDF: {pdf_path}")
        first_page_text = pdf.pages[0].extract_text() or ""
    upper = first_page_text.upper()
    if "OGE FORM 278-T" in upper or "OGE FORM 278 T" in upper or "278-T" in upper:
        return "OGE278T"
    if "OGE FORM 278E" in upper or "278E" in upper or "278E." in upper:
        return "OGE278e"
    raise ValueError(
        f"Could not detect OGE form type on page 1 of {pdf_path} "
        f"(expected 'OGE Form 278-T' or 'OGE Form 278e')."
    )


def _extract_filer_name(first_page_text: str) -> str:
    """Best-effort filer name from the header text.

    Tries common labels (Reporting Individual / Filer / Name) in order; falls
    back to the first non-empty line that looks like a person's name.
    """
    patterns = (
        r"Reporting\s+Individual\s*:?\s*(.+)",
        r"Filer\s*Name\s*:?\s*(.+)",
        r"Name\s+of\s+Reporting\s+Individual\s*:?\s*(.+)",
        r"Name\s*:?\s*(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, first_page_text, re.IGNORECASE)
        if match:
            candidate = normalize_whitespace(match.group(1))
            if candidate:
                # Strip trailing colon / "Date" / status lines that often leak in.
                candidate = re.split(r"\bDate\b|\bStatus\b", candidate, maxsplit=1)[0]
                candidate = candidate.strip(" :")
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
    for pattern in patterns:
        match = re.search(pattern, first_page_text, re.IGNORECASE)
        if match:
            candidate = parse_date(match.group(1))
            if candidate:
                return candidate
    # Fall back to any date-shaped substring on page 1 (rare).
    m = _DATE_RE.search(first_page_text)
    if m:
        return parse_date(m.group(0))
    return None


def _owner_from_cells(cells: list[str]) -> str:
    """Look at every cell on a row and map any owner code to the canonical label."""
    joined = " ".join(c for c in cells if c).lower()
    if not joined.strip():
        return "filer"
    for code, label in _OWNER_CODE_MAP.items():
        # Match whole-token to avoid e.g. "JT" matching "JTP".
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


# --------------------------------------------------------------------------- #
# 278-T parser
# --------------------------------------------------------------------------- #
def _parse_278t_table(
    table: list[list[object]], page_number: int
) -> list[dict[str, object]]:
    """Parse one table (list-of-rows) extracted by pdfplumber.

    Heuristics: most 278-T layouts have a header row with "Asset" / "Date" /
    "Description" / "Amount" columns.  We try to align by header text; if
    that fails we fall through to ``_parse_278t_text``.
    """
    rows: list[dict[str, object]] = []
    if not table:
        return rows

    header_cells = [_clean_cell(c) for c in table[0]]
    header_lower = [c.casefold() for c in header_cells]
    asset_idx = next(
        (i for i, c in enumerate(header_lower) if "asset" in c or "description" in c),
        None,
    )
    date_idx = next(
        (i for i, c in enumerate(header_lower) if "transaction date" in c or c == "date"),
        None,
    )
    type_idx = next(
        (i for i, c in enumerate(header_lower) if c in {"type", "description"} or "type" in c),
        None,
    )
    amount_idx = next(
        (i for i, c in enumerate(header_lower) if "amount" in c),
        None,
    )
    owner_idx = next(
        (i for i, c in enumerate(header_lower) if "owner" in c or "reporting" in c),
        None,
    )

    for raw in table[1:]:
        if not raw or all(_clean_cell(c) == "" for c in raw):
            continue
        cells = [_clean_cell(c) for c in raw]
        asset = _clean_cell(cells[asset_idx]) if asset_idx is not None and asset_idx < len(cells) else ""
        transaction_date = (
            parse_date(_clean_cell(cells[date_idx])) if date_idx is not None and date_idx < len(cells) else None
        )
        code = _clean_cell(cells[type_idx]) if type_idx is not None and type_idx < len(cells) else ""
        amount_range = _clean_cell(cells[amount_idx]) if amount_idx is not None and amount_idx < len(cells) else ""
        owner = _owner_from_cells(cells) if owner_idx is None else _owner_from_cells([cells[owner_idx]] if owner_idx < len(cells) else [])
        if not asset:
            continue
        tx_type = _DESCRIPTION_CODE_MAP.get(code.upper().strip(), _clean_cell(code))
        warning = None if transaction_date else "missing_transaction_date"
        rows.append(
            {
                "transaction_date": transaction_date,
                "asset": asset,
                "transaction_type": tx_type,
                "amount_range": amount_range,
                "owner_type": owner,
                "source_page": page_number,
                "parse_warning": warning,
            }
        )
    return rows


def _parse_278t_text(text: str, page_number: int) -> list[dict[str, object]]:
    """Regex fallback for 278-T pages where the table layout broke.

    Expected line shape: ``[Owner] <asset description> <P|S|E> <MM/DD/YYYY> $amount``.
    This is best-effort — many 278-T PDFs are well-formatted and the table path
    will dominate; this exists so a layout glitch doesn't drop the row entirely.
    """
    rows: list[dict[str, object]] = []
    if not text:
        return rows
    pattern = re.compile(
        r"^(?:(?P<owner>SP|JT|DC|Filer|Self|Spouse|Dependent)\s+)?"
        r"(?P<asset>.+?)\s+"
        r"(?P<code>P|S|E)\s+"
        r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
        r"(?P<amount>\$?[\d,]+(?:\s*-\s*\$?[\d,]+)?)\s*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        owner_code_raw = match.group("owner")
        owner_code = owner_code_raw.upper() if owner_code_raw else "FILER"
        owner = _OWNER_CODE_MAP.get(owner_code, owner_code.lower())
        code = match.group("code").upper()
        rows.append(
            {
                "transaction_date": parse_date(match.group("date")),
                "asset": _clean_cell(match.group("asset")),
                "transaction_type": _DESCRIPTION_CODE_MAP.get(code, code),
                "amount_range": _clean_cell(match.group("amount")),
                "owner_type": owner,
                "source_page": page_number,
                "parse_warning": None,
            }
        )
    return rows


def parse_oge_278t(pdf_path: Path) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    """Parse an OGE Form 278-T (periodic transactions) PDF.

    Returns ``(header, rows)``. ``header`` has keys ``filer_name``,
    ``filing_date``, ``form_type`` (always ``"OGE278T"`` on success).
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
    }
    rows: list[dict[str, object]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if page_index == 0:
                header["filer_name"] = _extract_filer_name(text)
                header["filing_date"] = _extract_filing_date(text)
            table = page.extract_table()
            if table:
                table_rows = _parse_278t_table(table, page_index + 1)
                if table_rows:
                    rows.extend(table_rows)
                    continue
            rows.extend(_parse_278t_text(text, page_index + 1))

    return header, rows


# --------------------------------------------------------------------------- #
# 278e parser (annual report — holdings only)
# --------------------------------------------------------------------------- #
def _parse_278e_table(
    table: list[list[object]], page_number: int
) -> list[dict[str, object]]:
    """Parse one table for the annual report.

    278e tables usually have columns ``Asset``, ``Owner``, ``Value`` (``Asset
    Type`` is sometimes present).  We accept variants and label the result with
    the canonical column names.
    """
    rows: list[dict[str, object]] = []
    if not table:
        return rows
    header_cells = [_clean_cell(c) for c in table[0]]
    header_lower = [c.casefold() for c in header_cells]
    asset_idx = next((i for i, c in enumerate(header_lower) if "asset" in c), None)
    value_idx = next((i for i, c in enumerate(header_lower) if "value" in c), None)
    owner_idx = next((i for i, c in enumerate(header_lower) if "owner" in c or "filer" in c or "spouse" in c or "dependent" in c), None)
    type_idx = next((i for i, c in enumerate(header_lower) if "type" in c), None)

    for raw in table[1:]:
        if not raw or all(_clean_cell(c) == "" for c in raw):
            continue
        cells = [_clean_cell(c) for c in raw]
        asset = _clean_cell(cells[asset_idx]) if asset_idx is not None and asset_idx < len(cells) else ""
        if not asset:
            continue
        value_range = _clean_cell(cells[value_idx]) if value_idx is not None and value_idx < len(cells) else ""
        owner = _owner_from_cells(cells) if owner_idx is None else _owner_from_cells(
            [cells[owner_idx]] if owner_idx < len(cells) else []
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
    """Fallback: most 278e pages are tabular, but we attempt a minimal regex
    on the joined line text so a layout glitch doesn't drop the section.
    """
    rows: list[dict[str, object]] = []
    if not text:
        return rows
    for line in text.splitlines():
        if not _DATE_RE.search(line) and not _AMOUNT_RE.search(line):
            continue
        # Without column hints we can't disambiguate owner/asset safely;
        # only emit if the line contains a clear value range AND asset-like
        # text.  Conservative.
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
    """Parse an OGE Form 278e (annual report) PDF.

    Returns ``(header, holdings)``. ``header`` is the same shape as the 278-T
    header; ``holdings`` rows are snapshots (no transaction date).
    """
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
# Process-pool wrappers (mirror parse_ptr.parse_ptr_pdf_safe)
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
            raise TimeoutError(f"Timed out parsing OGE 278-T PDF after {timeout_seconds}s: {pdf_path}") from exc


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
            raise TimeoutError(f"Timed out parsing OGE 278e PDF after {timeout_seconds}s: {pdf_path}") from exc