from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
import re
from pathlib import Path
from typing import Iterable

import pdfplumber

from .utils import normalize_whitespace, parse_date

DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
PTR_ROW_RE = re.compile(
    r"^(?:(?P<owner_code>[A-Z]{1,3})\s+)?(?P<asset>.+?)\s+"
    r"(?P<transaction_type>[A-Z](?:\s*\(partial\))?)\s+"
    r"(?P<transaction_date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?P<notification_date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?P<amount_range>\$?[\d,]+(?:\s*-\s*\$?[\d,]+)?)"
)
OWNER_CODE_MAP = {
    "SP": "spouse",
    "JT": "joint",
    "DC": "dependent",
    "CH": "dependent",
    "SC": "self",
    "SF": "self",
}
PTR_PARSE_TIMEOUT_SECONDS = 20


def _clean_cell(value: str | None) -> str:
    return normalize_whitespace((value or "").replace("\x00", " "))


def _owner_type_from_code(value: str | None) -> str | None:
    return OWNER_CODE_MAP.get(normalize_whitespace(value or "").upper())


def _normalize_asset_name(value: str | None, owner_code: str | None = None) -> str:
    asset = _clean_cell(value)
    code = normalize_whitespace(owner_code or "").upper()
    if code and asset.upper().startswith(f"{code} "):
        asset = asset[len(code) + 1 :]
    return asset


def _extract_owner_type(*cells: str) -> str | None:
    for cell in cells:
        code_type = _owner_type_from_code(cell)
        if code_type:
            return code_type
    joined = " ".join(cell for cell in cells if cell).lower()
    if "spouse" in joined:
        return "spouse"
    if "child" in joined or "dependent" in joined:
        return "dependent"
    if "joint" in joined:
        return "joint"
    if "self" in joined:
        return "self"
    return None


def _extract_header(text: str) -> dict[str, str | None]:
    header: dict[str, str | None] = {"member": None, "filing_date": None}
    member_match = re.search(r"Name\s*:?\s*(.+)", text, re.IGNORECASE)
    if member_match:
        header["member"] = normalize_whitespace(member_match.group(1))

    filing_match = re.search(r"Filing\s*Date\s*:?\s*(.+)", text, re.IGNORECASE)
    if filing_match:
        header["filing_date"] = parse_date(filing_match.group(1))
    return header


def _parse_table_rows(table: list[list[str | None]], page_number: int) -> list[dict[str, str | None]]:
    rows = []
    for raw_row in table:
        if not raw_row or len(raw_row) < 5:
            continue
        cells = [_clean_cell(cell) for cell in raw_row]
        if cells[0].lower() == "id" and "transaction" in cells[3].lower():
            continue
        if cells[2].lower().startswith("f s:"):
            continue

        if cells[2] and (cells[4] or cells[5] or cells[6]):
            transaction_date = parse_date(cells[4]) or parse_date(cells[5])
            amount_range = cells[6] or cells[5]
            owner_code = cells[1] if len(cells) > 1 else None
            row = {
                "transaction_date": transaction_date,
                "asset": _normalize_asset_name(cells[2], owner_code),
                "ticker": None,
                "transaction_type": cells[3] if len(cells) > 3 else None,
                "amount_range": amount_range,
                "owner_type": _extract_owner_type(owner_code or "", *cells),
                "source_page": str(page_number),
                "parse_warning": None if transaction_date else "missing_transaction_date",
            }
            if row["asset"]:
                rows.append(row)
            continue

        merged = _clean_cell(" ".join(cell for cell in cells if cell))
        if not DATE_RE.search(merged):
            continue
        match = PTR_ROW_RE.search(merged)
        if not match:
            continue
        row = {
            "transaction_date": parse_date(match.group("transaction_date")),
            "asset": _normalize_asset_name(match.group("asset"), match.group("owner_code")),
            "ticker": None,
            "transaction_type": match.group("transaction_type"),
            "amount_range": match.group("amount_range"),
            "owner_type": _extract_owner_type(match.group("owner_code") or "", *cells),
            "source_page": str(page_number),
            "parse_warning": None if parse_date(match.group("transaction_date")) else "missing_transaction_date",
        }
        rows.append(row)
    return rows


def _parse_text_lines(text: str, page_number: int) -> list[dict[str, str | None]]:
    rows = []
    lines = [_clean_cell(line) for line in text.splitlines()]
    for line in lines:
        match = PTR_ROW_RE.search(line)
        if not match:
            continue
        transaction_date = parse_date(match.group("transaction_date"))
        asset = match.group("asset")
        transaction_type = match.group("transaction_type")
        amount_range = match.group("amount_range")
        rows.append(
            {
                "transaction_date": transaction_date,
                "asset": _normalize_asset_name(asset, match.group("owner_code")),
                "ticker": None,
                "transaction_type": transaction_type,
                "amount_range": amount_range,
                "owner_type": _extract_owner_type(match.group("owner_code") or "", line),
                "source_page": str(page_number),
                "parse_warning": None if transaction_date else "missing_transaction_date",
            }
        )
    return rows


def _dedupe_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    unique_rows: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = (
            normalize_whitespace(row.get("transaction_date") or ""),
            normalize_whitespace(row.get("asset") or ""),
            normalize_whitespace(row.get("transaction_type") or ""),
            normalize_whitespace(row.get("amount_range") or ""),
            normalize_whitespace(row.get("source_page") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def parse_ptr_pdf(pdf_path: Path) -> tuple[dict[str, str | None], list[dict[str, str | None]]]:
    header: dict[str, str | None] = {"member": None, "filing_date": None}
    rows: list[dict[str, str | None]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if i == 0:
                header.update(_extract_header(text))
            table = page.extract_table()
            if table:
                table_rows = _parse_table_rows(table, i + 1)
                if table_rows:
                    rows.extend(table_rows)
                    continue
            rows.extend(_parse_text_lines(text, i + 1))

    return header, _dedupe_rows(rows)


def _parse_ptr_pdf_worker(pdf_path_str: str) -> tuple[dict[str, str | None], list[dict[str, str | None]]]:
    return parse_ptr_pdf(Path(pdf_path_str))


def parse_ptr_pdf_safe(
    pdf_path: Path,
    *,
    timeout_seconds: int = PTR_PARSE_TIMEOUT_SECONDS,
) -> tuple[dict[str, str | None], list[dict[str, str | None]]]:
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_parse_ptr_pdf_worker, str(pdf_path))
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Timed out parsing PTR PDF after {timeout_seconds}s: {pdf_path}") from exc


def iter_ptr_pdfs(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.pdf"):
        yield path
