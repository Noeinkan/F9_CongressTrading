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
import unicodedata
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

_NAME_NOISE_TOKENS = frozenset(
    {"hon", "dr", "mr", "mrs", "ms", "jr", "sr", "ii", "iii", "iv", "md", "facs", "phd", "esq"}
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


def _fold_accents(text: str) -> str:
    """``Barragán`` -> ``Barragan``; normalize_key would split on the accent."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def name_tokens(name: str) -> list[str]:
    """Name tokens without titles, suffixes and credentials, wherever they sit.

    House forms embed them mid-name ("Mark Dr Green", "Neal Patrick Dunn, MD,
    FACS", "August Lee Pfluger II"), which hides the real last name.
    """
    key = normalize_key(_fold_accents(strip_honorifics(name)))
    return [token for token in key.split() if token not in _NAME_NOISE_TOKENS]


def disclosure_name_key(name: str) -> str:
    """Normalize a disclosure filer name for party lookup."""
    return " ".join(name_tokens(name))


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


def _build_lookup_indexes(legislators: list[dict[str, str]]) -> dict[str, Any]:
    """Index legislator records by full name, first+last, and last name.

    Values are lists: two legislators can share a name (the two Mike Rogers),
    and the matcher narrows by state before trusting a hit.
    """
    by_full: dict[str, list[dict[str, str]]] = {}
    by_first_last: dict[str, list[dict[str, str]]] = {}
    by_last: dict[str, list[dict[str, str]]] = {}

    for row in legislators:
        full_key = disclosure_name_key(row["official_full"])
        if full_key:
            by_full.setdefault(full_key, []).append(row)
        first = row.get("first") or ""
        last = row.get("last") or ""
        if first and last:
            fl_key = disclosure_name_key(f"{first} {last}")
            if fl_key:
                by_first_last.setdefault(fl_key, []).append(row)
        last_tokens = name_tokens(last)
        if last_tokens:
            by_last.setdefault(last_tokens[-1], []).append(row)
    return {"by_full": by_full, "by_first_last": by_first_last, "by_last": by_last}


def _same_initial(candidates: list[dict[str, str]], given_names: list[str]) -> list[dict[str, str]]:
    """Keep legislators whose first name starts like one of the filer's given names.

    Initials survive nicknames: "Michael" -> Mike Garcia, "A. Mitchell" -> Mitch McConnell.
    """
    initials = {token[0] for token in given_names if token}
    return [row for row in candidates if (row.get("first") or "")[:1].lower() in initials]


def match_legislators(
    name: str,
    *,
    chamber: str = "",
    state: str = "",
    lookup: dict[str, Any] | None = None,
    legislators: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Legislator records a disclosure name can refer to, best rule first.

    Rules, first one with a hit wins:
    1. full name, then first+last (also filer's first + last token), narrowed
       to ``state`` when known and preferring ``chamber`` when it breaks a tie;
    2. last name + state + chamber;
    3. last name + state in the other chamber (members move House -> Senate),
       only when a first initial agrees;
    4. no state known: last name + chamber, only when a first initial agrees.
    """
    if lookup is None:
        rows = legislators if legislators is not None else load_legislators_parties()
        lookup = _build_lookup_indexes(rows)
    tokens = name_tokens(name)
    if not tokens:
        return []
    state = (state or "").strip().upper()
    chamber = (chamber or "").strip()

    key = " ".join(tokens)
    name_keys = [("by_full", key), ("by_first_last", key)]
    if len(tokens) > 2:
        name_keys.append(("by_first_last", f"{tokens[0]} {tokens[-1]}"))
    for index, lookup_key in name_keys:
        hits = lookup[index].get(lookup_key) or []
        if state:
            hits = [row for row in hits if row.get("state") == state]
        if chamber:
            hits = [row for row in hits if row.get("chamber") == chamber] or hits
        if hits:
            return hits

    same_last = lookup["by_last"].get(tokens[-1]) or []
    given_names = tokens[:-1]
    if state:
        in_state = [row for row in same_last if row.get("state") == state]
        same_chamber = [row for row in in_state if not chamber or row.get("chamber") == chamber]
        if same_chamber:
            return _same_initial(same_chamber, given_names) or same_chamber
        return _same_initial(in_state, given_names)
    if chamber:
        return _same_initial(
            [row for row in same_last if row.get("chamber") == chamber], given_names
        )
    return []


def _unanimous(candidates: list[dict[str, str]], field: str) -> str:
    values = {(row.get(field) or "").strip() for row in candidates}
    values.discard("")
    return next(iter(values)) if len(values) == 1 else ""


def match_party(
    name: str,
    *,
    chamber: str = "",
    state: str = "",
    lookup: dict[str, Any] | None = None,
    legislators: list[dict[str, str]] | None = None,
) -> str:
    """Resolve party for a disclosure member name. Empty string if no match."""
    candidates = match_legislators(
        name, chamber=chamber, state=state, lookup=lookup, legislators=legislators
    )
    return _unanimous(candidates, "party")


def match_state(
    name: str,
    *,
    chamber: str = "",
    lookup: dict[str, Any] | None = None,
    legislators: list[dict[str, str]] | None = None,
) -> str:
    """Two-letter state for a disclosure name with no state of its own ('' if unsure)."""
    candidates = match_legislators(name, chamber=chamber, lookup=lookup, legislators=legislators)
    return _unanimous(candidates, "state")


def _parties_mtime_key(path: Path | None = None) -> str:
    target = path or LEGISLATORS_PARTIES_PATH
    if target.exists():
        return str(target.stat().st_mtime_ns)
    return "missing"


def get_party_lookup(path: Path | None = None) -> dict[str, Any]:
    """Cached indexes for API overlay. Keys: by_full, by_first_last, by_last."""
    global _lookup_cache_key, _lookup_cache
    key = _parties_mtime_key(path)
    if key != _lookup_cache_key:
        _lookup_cache_key = key
        _lookup_cache = None
    if _lookup_cache is not None:
        return _lookup_cache

    _lookup_cache = _build_lookup_indexes(load_legislators_parties(path))
    return _lookup_cache


def resolve_party_for_row(
    member: str,
    *,
    chamber: str = "",
    state: str = "",
    lookup: dict[str, Any] | None = None,
) -> str:
    return match_party(member, chamber=chamber, state=state, lookup=lookup or get_party_lookup())


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
    lookup = _build_lookup_indexes(legislators)

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
            lookup=lookup,
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
