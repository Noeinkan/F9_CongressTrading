"""Member party enrichment from unitedstates/congress-legislators.

Downloads legislators YAML, writes a compact ``data/legislators_parties.json``,
and backfills ``members.party``. The API also overlays blank party from the
JSON at load time so Patterns bipartisan (and party UI) work without a DB
rewrite after every ingest.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

from .config import DATA_DIR
from .utils import normalize_key

LEGISLATORS_PARTIES_PATH = DATA_DIR / "legislators_parties.json"

_CURRENT_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/"
    "main/legislators-current.yaml"
)
_HISTORICAL_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/"
    "main/legislators-historical.yaml"
)

# Keep historical file small: only members whose latest term ended on/after this.
_HISTORICAL_MIN_END = date(2015, 1, 1)

_HONORIFIC_RE = re.compile(
    r"^(?:hon(?:orable)?|mr|mrs|ms|miss|dr|rep(?:resentative)?|sen(?:ator)?|"
    r"the\s+honorable)\b\.?\s*",
    re.IGNORECASE,
)

_lookup_cache_key: str | None = None
_lookup_cache: dict[str, Any] | None = None


def strip_honorifics(name: str) -> str:
    """Remove leading titles (Hon., Mr., Dr., Rep., …) repeatedly."""
    text = (name or "").strip()
    while True:
        cleaned = _HONORIFIC_RE.sub("", text).strip()
        if cleaned == text:
            return cleaned
        text = cleaned


def disclosure_name_key(name: str) -> str:
    """Normalize a disclosure filer name for party lookup."""
    return normalize_key(strip_honorifics(name))


def _term_chamber(term_type: str) -> str:
    t = (term_type or "").strip().lower()
    if t in {"rep", "house"}:
        return "House"
    if t in {"sen", "senate"}:
        return "Senate"
    return ""


def _parse_term_end(raw: object) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _latest_term(terms: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not terms:
        return None
    def sort_key(term: dict[str, Any]) -> str:
        return str(term.get("end") or term.get("start") or "")

    return max(terms, key=sort_key)


def legislator_record_from_yaml(entry: dict[str, Any], *, require_recent: bool) -> dict[str, str] | None:
    """Convert one congress-legislators YAML person to a compact record."""
    terms = entry.get("terms") or []
    if not isinstance(terms, list) or not terms:
        return None
    latest = _latest_term([t for t in terms if isinstance(t, dict)])
    if latest is None:
        return None
    if require_recent:
        end = _parse_term_end(latest.get("end"))
        # Current members often have a future end date; historical without end
        # are skipped when require_recent is set for the historical file only.
        if end is not None and end < _HISTORICAL_MIN_END:
            return None

    name_block = entry.get("name") or {}
    if not isinstance(name_block, dict):
        name_block = {}
    official = str(name_block.get("official_full") or "").strip()
    first = str(name_block.get("first") or "").strip()
    last = str(name_block.get("last") or "").strip()
    if not official and first and last:
        official = f"{first} {last}"
    if not official:
        return None

    party = str(latest.get("party") or "").strip()
    if not party:
        return None
    chamber = _term_chamber(str(latest.get("type") or ""))
    state = str(latest.get("state") or "").strip().upper()

    return {
        "official_full": official,
        "first": first,
        "last": last,
        "party": party,
        "chamber": chamber,
        "state": state,
    }


def download_legislators_yaml() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch current + historical YAML lists from GitHub."""
    import yaml

    current = yaml.safe_load(requests.get(_CURRENT_URL, timeout=120).text) or []
    historical = yaml.safe_load(requests.get(_HISTORICAL_URL, timeout=180).text) or []
    if not isinstance(current, list):
        raise RuntimeError("legislators-current.yaml did not parse to a list")
    if not isinstance(historical, list):
        raise RuntimeError("legislators-historical.yaml did not parse to a list")
    return current, historical


def build_legislators_payload(
    current: list[dict[str, Any]],
    historical: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build compact JSON payload from YAML person lists."""
    by_key: dict[str, dict[str, str]] = {}

    def add(entry: dict[str, Any], *, require_recent: bool) -> None:
        if not isinstance(entry, dict):
            return
        rec = legislator_record_from_yaml(entry, require_recent=require_recent)
        if rec is None:
            return
        key = disclosure_name_key(rec["official_full"])
        if not key:
            return
        # Prefer current over historical when both exist.
        if key in by_key and require_recent:
            return
        by_key[key] = rec

    for entry in historical:
        add(entry, require_recent=True)
    for entry in current:
        add(entry, require_recent=False)

    legislators = sorted(by_key.values(), key=lambda r: r["official_full"].casefold())
    return {
        "meta": {
            "source": "unitedstates/congress-legislators",
            "updated": date.today().isoformat(),
            "historical_min_end": _HISTORICAL_MIN_END.isoformat(),
            "count": len(legislators),
        },
        "legislators": legislators,
    }


def write_legislators_parties_json(
    payload: dict[str, Any],
    path: Path | None = None,
) -> Path:
    out = path or LEGISLATORS_PARTIES_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def refresh_legislators_parties_json(path: Path | None = None) -> Path:
    """Download upstream YAML and rewrite the compact JSON map."""
    current, historical = download_legislators_yaml()
    payload = build_legislators_payload(current, historical)
    return write_legislators_parties_json(payload, path=path)


def load_legislators_parties(path: Path | None = None) -> list[dict[str, str]]:
    target = path or LEGISLATORS_PARTIES_PATH
    if not target.exists():
        return []
    payload = json.loads(target.read_text(encoding="utf-8"))
    rows = payload.get("legislators") or []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        official = str(row.get("official_full") or "").strip()
        party = str(row.get("party") or "").strip()
        if not official or not party:
            continue
        out.append(
            {
                "official_full": official,
                "first": str(row.get("first") or "").strip(),
                "last": str(row.get("last") or "").strip(),
                "party": party,
                "chamber": str(row.get("chamber") or "").strip(),
                "state": str(row.get("state") or "").strip().upper(),
            }
        )
    return out


def _build_lookup_indexes(
    legislators: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str], dict[tuple[str, str, str], str]]:
    """Return (by_full_key, by_first_last_key, by_last_state_chamber)."""
    by_full: dict[str, str] = {}
    by_first_last: dict[str, str] = {}
    by_lsc: dict[tuple[str, str, str], list[str]] = {}

    for row in legislators:
        party = row["party"]
        full_key = disclosure_name_key(row["official_full"])
        if full_key:
            by_full[full_key] = party
        first = row.get("first") or ""
        last = row.get("last") or ""
        if first and last:
            fl_key = disclosure_name_key(f"{first} {last}")
            if fl_key:
                by_first_last[fl_key] = party
        last_key = normalize_key(last)
        chamber = (row.get("chamber") or "").strip()
        state = (row.get("state") or "").strip().upper()
        if last_key and chamber and state:
            key = (last_key, state, chamber)
            by_lsc.setdefault(key, []).append(party)

    unique_lsc: dict[tuple[str, str, str], str] = {}
    for key, parties in by_lsc.items():
        distinct = {p for p in parties if p}
        if len(distinct) == 1:
            unique_lsc[key] = next(iter(distinct))
    return by_full, by_first_last, unique_lsc


def match_party(
    name: str,
    *,
    chamber: str = "",
    state: str = "",
    by_full: dict[str, str] | None = None,
    by_first_last: dict[str, str] | None = None,
    by_lsc: dict[tuple[str, str, str], str] | None = None,
    legislators: list[dict[str, str]] | None = None,
) -> str:
    """Resolve party for a disclosure member name. Empty string if no match."""
    if by_full is None or by_first_last is None or by_lsc is None:
        rows = legislators if legislators is not None else load_legislators_parties()
        by_full, by_first_last, by_lsc = _build_lookup_indexes(rows)

    key = disclosure_name_key(name)
    if not key:
        return ""
    if key in by_full:
        return by_full[key]
    if key in by_first_last:
        return by_first_last[key]

    # Fallback: last token + state + chamber when unique.
    tokens = key.split()
    if len(tokens) >= 1 and chamber and state:
        last_key = tokens[-1]
        lsc_key = (last_key, state.strip().upper(), chamber.strip())
        if lsc_key in by_lsc:
            return by_lsc[lsc_key]
    return ""


def _parties_mtime_key(path: Path | None = None) -> str:
    target = path or LEGISLATORS_PARTIES_PATH
    if target.exists():
        return str(target.stat().st_mtime_ns)
    return "missing"


def get_party_lookup(path: Path | None = None) -> dict[str, Any]:
    """Cached indexes for API overlay. Keys: by_full, by_first_last, by_lsc."""
    global _lookup_cache_key, _lookup_cache
    key = _parties_mtime_key(path)
    if key != _lookup_cache_key:
        _lookup_cache_key = key
        _lookup_cache = None
    if _lookup_cache is not None:
        return _lookup_cache

    by_full, by_first_last, by_lsc = _build_lookup_indexes(load_legislators_parties(path))
    _lookup_cache = {
        "by_full": by_full,
        "by_first_last": by_first_last,
        "by_lsc": by_lsc,
    }
    return _lookup_cache


def resolve_party_for_row(
    member: str,
    *,
    chamber: str = "",
    state: str = "",
    lookup: dict[str, Any] | None = None,
) -> str:
    indexes = lookup or get_party_lookup()
    return match_party(
        member,
        chamber=chamber,
        state=state,
        by_full=indexes["by_full"],
        by_first_last=indexes["by_first_last"],
        by_lsc=indexes["by_lsc"],
    )


def backfill_member_parties(
    conn: sqlite3.Connection,
    *,
    overwrite: bool = False,
    path: Path | None = None,
) -> dict[str, int]:
    """Update ``members.party`` from the compact legislators JSON.

    Returns counts: matched, updated, unmatched, skipped.
    """
    legislators = load_legislators_parties(path)
    if not legislators:
        raise FileNotFoundError(
            f"No legislators party map at {path or LEGISLATORS_PARTIES_PATH}. "
            "Run with --refresh first."
        )
    by_full, by_first_last, by_lsc = _build_lookup_indexes(legislators)

    rows = conn.execute(
        "SELECT id, full_name, chamber, state, party FROM members"
    ).fetchall()

    matched = 0
    updated = 0
    unmatched = 0
    skipped = 0

    for row in rows:
        existing = (row["party"] or "").strip()
        if existing and not overwrite:
            skipped += 1
            continue
        party = match_party(
            row["full_name"] or "",
            chamber=row["chamber"] or "",
            state=row["state"] or "",
            by_full=by_full,
            by_first_last=by_first_last,
            by_lsc=by_lsc,
        )
        if not party:
            unmatched += 1
            continue
        matched += 1
        if party == existing:
            skipped += 1
            continue
        conn.execute(
            "UPDATE members SET party = ?, updated_at = datetime('now') WHERE id = ?",
            (party, row["id"]),
        )
        updated += 1

    conn.commit()
    return {
        "matched": matched,
        "updated": updated,
        "unmatched": unmatched,
        "skipped": skipped,
        "total": len(rows),
        "legislators": len(legislators),
    }


def enrich_member_parties(
    *,
    refresh: bool = False,
    overwrite: bool = False,
    path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """CLI entry: optionally refresh JSON, then backfill SQLite."""
    from .db import get_connection, init_db

    target = path or LEGISLATORS_PARTIES_PATH
    if refresh or not target.exists():
        refresh_legislators_parties_json(path=target)

    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
        init_db(conn)
    assert conn is not None
    try:
        stats = backfill_member_parties(conn, overwrite=overwrite, path=target)
    finally:
        if owns_conn:
            conn.close()

    try:
        from .api.repository import invalidate_data_cache

        invalidate_data_cache()
    except Exception:
        pass

    return stats
