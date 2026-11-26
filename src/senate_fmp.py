"""Senate PTRs from Financial Modeling Prep (FMP).

Since late October 2026 efdsearch.senate.gov answers "Access Denied" to every
address outside the US, so neither the VPS nor a home connection in Italy can
download filings any more. FMP republishes them, one row per transaction, with
the eFD link of the filing each row came from.

The free plan returns only the newest 25 Senate rows, with no further pages. So:

* ``poll_senate_fmp`` runs every 30 minutes on the server and accumulates the
  rows into one JSON file per filing, ``data/raw/senate/fmp/<uuid>.json``. The
  file stem is the eFD uuid, the same stem an eFD HTML of that filing would have.
* When all 25 rows of a poll are new, rows may have scrolled past between two
  polls (a big filing pushes out everything older). That is reported as a
  possible gap, with the filings involved, instead of being silently lost.
* ``parse_senate_fmp_json`` turns a file into the (header, rows) contract of
  ``parse_ptr``, so ``ingest_senate`` persists it like an HTML filing.
* An eFD HTML or PDF of the same filing always wins: ``ingest_senate`` skips the
  JSON and removes what it had written (``purge_filing_rows``).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .config import (
    FMP_SENATE_LATEST_URL,
    FMP_SENATE_PAGE_LIMIT,
    SENATE_FMP_DIR,
    SENATE_RAW_DIR,
    fmp_api_key,
)
from .parse_ptr import _dedupe_rows, _extract_owner_type, _normalize_asset_name, _senate_transaction_type
from .utils import normalize_key, normalize_whitespace, parse_date

_UUID_RE = re.compile(r"/search/view/(?:ptr|paper)/([0-9a-fA-F-]{8,})/?")
_NO_TICKER = {"", "--", "—", "n/a", "na"}
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


class FmpError(RuntimeError):
    """An FMP call failed. The message never contains the API key."""


@dataclass
class PollResult:
    fetched: int = 0
    new_rows: int = 0
    new_filings: list[str] = field(default_factory=list)
    already_on_disk: int = 0
    seeded: bool = False
    possible_gap: bool = False
    # (member, disclosure date, eFD link) of every filing in a poll that may have a gap.
    gap_filings: list[tuple[str, str, str]] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{self.fetched} rows fetched", f"{self.new_rows} new"]
        if self.new_filings:
            parts.append(f"{len(self.new_filings)} new filings")
        if self.already_on_disk:
            parts.append(f"{self.already_on_disk} rows of filings already on disk as eFD files")
        if self.seeded:
            parts.append("first run (seeded, no gap check)")
        if self.possible_gap:
            parts.append("POSSIBLE GAP: every row was new")
        return "Senate FMP: " + ", ".join(parts) + "."


def filing_uuid(link: str | None) -> str | None:
    match = _UUID_RE.search(link or "")
    return match.group(1).lower() if match else None


def fetch_latest(api_key: str | None = None, *, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """The newest Senate rows from FMP (free plan: 25, page 0 only)."""
    key = api_key if api_key is not None else fmp_api_key()
    if not key:
        raise FmpError("FMP_API_KEY is not set.")
    http = session or requests
    try:
        resp = http.get(
            FMP_SENATE_LATEST_URL,
            params={"page": 0, "limit": FMP_SENATE_PAGE_LIMIT, "apikey": key},
            timeout=30,
        )
    except requests.RequestException as exc:
        # requests puts the full URL, key included, in its messages.
        raise FmpError(f"FMP request failed ({type(exc).__name__}).") from None
    body = resp.text.replace(key, "***")
    if resp.status_code != 200:
        raise FmpError(f"FMP answered HTTP {resp.status_code}: {body[:200]}")
    try:
        data = resp.json()
    except ValueError:
        raise FmpError(f"FMP answered with something that is not JSON: {body[:200]}") from None
    if not isinstance(data, list):
        raise FmpError(f"FMP answered with an unexpected shape: {body[:200]}")
    return data


def _row_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        normalize_whitespace(str(row.get(name) or ""))
        for name in ("transactionDate", "symbol", "assetDescription", "assetType", "type", "amount", "owner", "comment")
    )


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    # Write then rename, so the nightly ingest never reads a half-written file.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def store_rows(
    rows: list[dict[str, Any]],
    *,
    dest_dir: Path = SENATE_FMP_DIR,
    efd_dir: Path = SENATE_RAW_DIR,
    page_limit: int = FMP_SENATE_PAGE_LIMIT,
) -> PollResult:
    """Merge one poll's rows into the per-filing JSON files."""
    result = PollResult(fetched=len(rows))
    result.seeded = not any(dest_dir.glob("*.json"))
    efd_stems = {
        p.stem.lower() for p in efd_dir.rglob("*") if p.suffix.lower() in {".html", ".pdf"}
    }

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        uuid = filing_uuid(row.get("link"))
        if uuid:
            groups.setdefault(uuid, []).append(row)

    any_known = False
    for uuid, batch in groups.items():
        if uuid in efd_stems:
            any_known = True
            result.already_on_disk += len(batch)
            continue
        path = dest_dir / f"{uuid}.json"
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
        else:
            first = batch[0]
            doc = {
                "source": "fmp",
                "uuid": uuid,
                "link": first.get("link") or "",
                "first_name": normalize_whitespace(first.get("firstName") or ""),
                "last_name": normalize_whitespace(first.get("lastName") or ""),
                "office": first.get("office") or "",
                "senate_id": first.get("senateID") or "",
                "filing_date": first.get("disclosureDate") or "",
                "trades": [],
            }
        seen = {_row_key(t) for t in doc["trades"]}
        added = []
        for row in batch:
            key = _row_key(row)
            if key in seen:
                any_known = True
                continue
            seen.add(key)
            added.append(row)
        if added:
            if not doc["trades"]:
                result.new_filings.append(uuid)
            doc["trades"].extend(added)
            _write_json(path, doc)
            result.new_rows += len(added)

    # A full page with nothing we already had: rows may have scrolled past
    # between this poll and the previous one.
    if not result.seeded and len(rows) >= page_limit and not any_known:
        result.possible_gap = True
        for uuid, batch in groups.items():
            first = batch[0]
            member = normalize_whitespace(f"{first.get('firstName') or ''} {first.get('lastName') or ''}")
            result.gap_filings.append((member, first.get("disclosureDate") or "", first.get("link") or ""))
    return result


def poll_senate_fmp(*, session: requests.Session | None = None) -> PollResult:
    return store_rows(fetch_latest(session=session))


def gap_alert_detail(result: PollResult) -> str:
    lines = [
        "The last FMP poll returned 25 Senate trades, all new: older rows may have "
        "scrolled past since the previous poll (the free plan shows only the newest 25).",
        "Check these filings on efdsearch from a US connection or another source:",
    ]
    lines += [f"- {member}, filed {date}: {link}" for member, date, link in result.gap_filings]
    return "\n".join(lines)


def is_fmp_file(path: Path) -> bool:
    return path.suffix.lower() == ".json" and path.parent.name == SENATE_FMP_DIR.name


def parse_senate_fmp_json(path: Path) -> tuple[dict[str, str | None], list[dict[str, str | None]]]:
    """Same (header, rows) contract as ``parse_senate_ptr_html``."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    member = normalize_whitespace(f"{doc.get('first_name') or ''} {doc.get('last_name') or ''}")
    header: dict[str, str | None] = {
        "member": member or None,
        "first_name": doc.get("first_name") or None,
        "last_name": doc.get("last_name") or None,
        "filing_date": parse_date(doc.get("filing_date")),
        "source_url": doc.get("link") or "",
    }
    rows: list[dict[str, str | None]] = []
    for trade in doc.get("trades") or []:
        asset = normalize_whitespace(trade.get("assetDescription") or "")
        ticker = normalize_whitespace(trade.get("symbol") or "")
        if ticker.lower() in _NO_TICKER:
            ticker = ""
        if not asset and not ticker:
            continue
        asset_type = normalize_whitespace(trade.get("assetType") or "")
        if "option" in asset_type.lower() and "option" not in asset.lower():
            asset = f"{asset} {asset_type}"
        # The comment tells apart rows that are otherwise identical, e.g. the same
        # partnership bought through four holding vehicles on one day. Without it
        # they would collapse into one transaction. Brackets, not parentheses, so
        # it is never mistaken for a ticker.
        comment = normalize_whitespace(trade.get("comment") or "")
        if comment:
            asset = f"{asset} [{comment}]"
        # Same shape as the HTML parser: the ticker rides in parentheses so
        # resolve_asset's disclosure-paren path picks it up.
        asset_for_resolution = f"{asset} ({ticker})" if ticker and asset else (asset or ticker)
        transaction_date = parse_date(trade.get("transactionDate"))
        rows.append(
            {
                "transaction_date": transaction_date,
                "asset": _normalize_asset_name(asset_for_resolution),
                "ticker": None,
                "transaction_type": _senate_transaction_type(trade.get("type")),
                "amount_range": normalize_whitespace(trade.get("amount") or "") or None,
                "owner_type": _extract_owner_type(trade.get("owner") or ""),
                "source_page": None,
                "parse_warning": None if transaction_date else "missing_transaction_date",
            }
        )
    return header, _dedupe_rows(rows)


def _last_name_key(name: str) -> str:
    tokens = [t for t in normalize_key(name).split() if t not in _NAME_SUFFIXES]
    return tokens[-1] if tokens else ""


def resolve_member_name(conn: sqlite3.Connection, first_name: str | None, last_name: str | None) -> str:
    """The name the eFD HTML gave this senator, so FMP does not create a second member.

    eFD writes "Mr. Thomas H Tuberville", FMP "Tommy Tuberville". When exactly one
    Senate member shares the last name, that member's name is used.
    """
    fallback = normalize_whitespace(f"{first_name or ''} {last_name or ''}")
    last = _last_name_key(last_name or "")
    if not last:
        return fallback
    matches = [
        str(row[0])
        for row in conn.execute("SELECT full_name FROM members WHERE chamber = 'Senate'")
        if _last_name_key(str(row[0])) == last
    ]
    return matches[0] if len(set(matches)) == 1 else fallback


def purge_filing_rows(conn: sqlite3.Connection, raw_document_path: str) -> int:
    """Delete everything one ingested file wrote. Returns the transactions removed."""
    filings = conn.execute(
        "SELECT id, member_id FROM filings WHERE raw_document_path = ?", (raw_document_path,)
    ).fetchall()
    filing_ids = [int(row[0]) for row in filings]
    removed = 0
    if filing_ids:
        marks = ", ".join("?" for _ in filing_ids)
        txn_ids = [
            int(row[0])
            for row in conn.execute(f"SELECT id FROM transactions WHERE filing_id IN ({marks})", filing_ids)
        ]
        if txn_ids:
            txn_marks = ", ".join("?" for _ in txn_ids)
            conn.execute(f"DELETE FROM review_queue WHERE transaction_id IN ({txn_marks})", txn_ids)
            conn.execute(f"DELETE FROM transaction_tags WHERE transaction_id IN ({txn_marks})", txn_ids)
            conn.execute(f"DELETE FROM transactions WHERE id IN ({txn_marks})", txn_ids)
        removed = len(txn_ids)
        conn.execute(f"DELETE FROM filings WHERE id IN ({marks})", filing_ids)
        for member_id in {int(row[1]) for row in filings}:
            conn.execute(
                "DELETE FROM members WHERE id = ? AND NOT EXISTS (SELECT 1 FROM filings WHERE member_id = ?)",
                (member_id, member_id),
            )
    conn.execute("DELETE FROM trades WHERE source_file = ?", (raw_document_path,))
    conn.execute("DELETE FROM files_ingested WHERE file_path = ?", (raw_document_path,))
    conn.commit()
    return removed
