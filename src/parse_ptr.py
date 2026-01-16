from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pdfplumber

from .utils import normalize_whitespace, parse_date

DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")


def _extract_header(text: str) -> dict[str, str | None]:
    header = {"member": None, "filing_date": None}
    member_match = re.search(r"Name\s*:?\s*(.+)", text, re.IGNORECASE)
    if member_match:
        header["member"] = normalize_whitespace(member_match.group(1))

    filing_match = re.search(r"Filing\s*Date\s*:?\s*(.+)", text, re.IGNORECASE)
    if filing_match:
        header["filing_date"] = parse_date(filing_match.group(1))
    return header


def _parse_table_rows(table: list[list[str | None]]) -> list[dict[str, str | None]]:
    rows = []
    for raw_row in table:
        if not raw_row or len(raw_row) < 5:
            continue
        cells = [normalize_whitespace(cell or "") for cell in raw_row]
        if not any(DATE_RE.search(cell or "") for cell in cells):
            continue
        row = {
            "transaction_date": parse_date(cells[0]) or parse_date(cells[1]),
            "asset": cells[2] or cells[1],
            "ticker": None,
            "transaction_type": cells[3] if len(cells) > 3 else None,
            "amount_range": cells[4] if len(cells) > 4 else None,
        }
        rows.append(row)
    return rows


def _parse_text_lines(text: str) -> list[dict[str, str | None]]:
    rows = []
    lines = [normalize_whitespace(line) for line in text.splitlines()]
    for line in lines:
        if not DATE_RE.search(line):
            continue
        parts = re.split(r"\s{2,}", line)
        if len(parts) < 4:
            continue
        transaction_date = parse_date(parts[0])
        asset = parts[1] if len(parts) > 1 else None
        transaction_type = parts[2] if len(parts) > 2 else None
        amount_range = parts[3] if len(parts) > 3 else None
        rows.append(
            {
                "transaction_date": transaction_date,
                "asset": asset,
                "ticker": None,
                "transaction_type": transaction_type,
                "amount_range": amount_range,
            }
        )
    return rows


def parse_ptr_pdf(pdf_path: Path) -> tuple[dict[str, str | None], list[dict[str, str | None]]]:
    header = {"member": None, "filing_date": None}
    rows: list[dict[str, str | None]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if i == 0:
                header.update(_extract_header(text))
            table = page.extract_table()
            if table:
                rows.extend(_parse_table_rows(table))
            rows.extend(_parse_text_lines(text))

    return header, rows


def iter_ptr_pdfs(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.pdf"):
        yield path
