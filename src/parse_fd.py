from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from .utils import normalize_whitespace, parse_date


FD_TXT_HEADERS = {
    "Prefix",
    "Last",
    "First",
    "Suffix",
    "FilingType",
    "StateDst",
    "Year",
    "FilingDate",
    "DocID",
}


def _build_member(prefix: str | None, first: str | None, last: str | None, suffix: str | None) -> str:
    parts = [prefix, first, last, suffix]
    return normalize_whitespace(" ".join([p for p in parts if p]))


def parse_fd_txt(path: Path, chamber: str) -> Iterable[dict[str, str | None]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames:
            return []
        if not FD_TXT_HEADERS.issubset(set(reader.fieldnames)):
            return []
        rows = []
        for row in reader:
            member = _build_member(
                row.get("Prefix"),
                row.get("First"),
                row.get("Last"),
                row.get("Suffix"),
            )
            rows.append(
                {
                    "member": member or normalize_whitespace(
                        f"{row.get('First', '')} {row.get('Last', '')}"
                    ),
                    "chamber": chamber,
                    "filing_type": normalize_whitespace(row.get("FilingType") or ""),
                    "state_district": normalize_whitespace(row.get("StateDst") or ""),
                    "year": normalize_whitespace(row.get("Year") or ""),
                    "filing_date": parse_date(row.get("FilingDate") or ""),
                    "doc_id": normalize_whitespace(row.get("DocID") or ""),
                    "source_file": str(path),
                }
            )
        return rows


def parse_fd_xml(path: Path, chamber: str) -> Iterable[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for _event, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != "Member":
            continue
        values = {child.tag: (child.text or "") for child in elem}
        member = _build_member(
            values.get("Prefix"),
            values.get("First"),
            values.get("Last"),
            values.get("Suffix"),
        )
        rows.append(
            {
                "member": member or normalize_whitespace(
                    f"{values.get('First', '')} {values.get('Last', '')}"
                ),
                "chamber": chamber,
                "filing_type": normalize_whitespace(values.get("FilingType") or ""),
                "state_district": normalize_whitespace(values.get("StateDst") or ""),
                "year": normalize_whitespace(values.get("Year") or ""),
                "filing_date": parse_date(values.get("FilingDate") or ""),
                "doc_id": normalize_whitespace(values.get("DocID") or ""),
                "source_file": str(path),
            }
        )
        elem.clear()
    return rows


def iter_fd_files(root: Path) -> Iterable[Path]:
    txt_files = list(root.rglob("*.txt"))
    txt_stems = {p.stem.lower() for p in txt_files}
    for path in txt_files:
        yield path
    for path in root.rglob("*.xml"):
        if path.stem.lower() in txt_stems:
            continue
        yield path
