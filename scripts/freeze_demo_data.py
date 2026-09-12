"""Freeze a public-demo snapshot from the live SQLite database.

The demo must render with no API key, no network and no ingest run, so it reads
a committed copy of the data rather than the live file. This script builds that
copy: it trims the window, cascades the deletes, scrubs local filesystem paths,
vacuums, gzips, and stamps the capture date into ``demo/demo.json``.

    python scripts/freeze_demo_data.py
    python scripts/freeze_demo_data.py --since 2024-01-01 --bars-since 2023-10-01

Why a window at all: the live database is ~146 MB, nearly all of it daily price
bars. Trimming to the recent slice keeps the committed fixture small enough to
live in git without turning every refresh into a 100 MB history entry.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = BASE_DIR / "data" / "db" / "congress_trades.sqlite"
DEFAULT_OUT = BASE_DIR / "demo" / "fixtures" / "demo-snapshot.sqlite.gz"
MANIFEST = BASE_DIR / "demo" / "demo.json"

# Transactions on or after this date survive; everything else cascades away.
DEFAULT_SINCE = "2025-01-01"
# Price bars start a little earlier so a trade on day one still has a price.
DEFAULT_BARS_SINCE = "2024-10-01"

# Ingest bookkeeping and the FD (annual disclosure) side: neither is read by any
# dashboard page, and together they are a third of the file.
DROP_WHOLE = ("fd_filings", "files_ingested", "trades", "polygon_daily_bar_cache")

# ``filings`` is UNIQUE on (member_id, chamber, filing_type, filing_date, doc_id,
# raw_document_path), so shortening the path can collide two rows into one. Three
# segments (``house/<year>/<doc>.pdf``) is the shortest tail that stays unique on
# this data while still feeding the PTR-URL inference in ``repository.py``.
PATH_SEGMENTS_KEPT = 3

# Rows whose source path is a pytest temp dir: test fixtures that leaked into the
# live database. They are not real disclosures and have no business in a demo.
TEST_ARTEFACT_PATTERNS = ("%pytest-of-%", "%/pytest-%", "%\\pytest-%")


def _drop_test_artefacts(conn: sqlite3.Connection) -> int:
    """Delete filings captured from a pytest temp directory, and their rows."""
    where = " OR ".join("raw_document_path LIKE ?" for _ in TEST_ARTEFACT_PATTERNS)
    ids = [
        r[0]
        for r in conn.execute(
            f"SELECT id FROM filings WHERE {where}", TEST_ARTEFACT_PATTERNS
        ).fetchall()
    ]
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    conn.execute(f"DELETE FROM transactions WHERE filing_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM filings WHERE id IN ({marks})", ids)
    conn.commit()
    return len(ids)


def _trim(conn: sqlite3.Connection, since: str, bars_since: str) -> None:
    dropped = _drop_test_artefacts(conn)
    if dropped:
        print(f"  dropped {dropped} filing(s) sourced from a pytest temp dir")

    conn.executescript(
        f"""
        DELETE FROM transactions
         WHERE COALESCE(NULLIF(transaction_date, ''), '0000-00-00') < '{since}';

        DELETE FROM filings
         WHERE id NOT IN (SELECT DISTINCT filing_id FROM transactions WHERE filing_id IS NOT NULL);

        DELETE FROM members
         WHERE id NOT IN (SELECT DISTINCT member_id FROM filings WHERE member_id IS NOT NULL);

        DELETE FROM transaction_tags
         WHERE transaction_id NOT IN (SELECT id FROM transactions);

        DELETE FROM review_queue
         WHERE transaction_id NOT IN (SELECT id FROM transactions);

        DELETE FROM issuers
         WHERE id NOT IN (SELECT DISTINCT issuer_id FROM transactions WHERE issuer_id IS NOT NULL);
        """
    )
    for table in DROP_WHOLE:
        try:
            conn.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass  # table absent in this build of the schema

    conn.execute(
        f"""DELETE FROM yahoo_daily_bar_cache
             WHERE bar_date < '{bars_since}'
                OR ticker NOT IN (
                    SELECT DISTINCT ticker FROM transactions
                     WHERE ticker IS NOT NULL AND ticker <> ''
                )"""
    )
    conn.commit()


def _scrub(conn: sqlite3.Connection) -> None:
    """Remove anything local to the machine that captured the snapshot.

    ``raw_document_path`` holds absolute paths from the ingest box
    (``C:\\Users\\andre\\...``). It cannot simply be blanked: the API reads the
    parent folder and the stem out of it to rebuild the link to the original
    House PTR PDF on disclosures-clerk.house.gov. So keep exactly those two
    segments and throw the rest away — the links still resolve, the directory
    layout of a private machine does not ship.

    The public ``source_url`` beside it is kept as-is: it points at the
    government PDF, which is the provenance the demo claims.
    """
    rows = conn.execute(
        "SELECT id, raw_document_path FROM filings "
        "WHERE raw_document_path IS NOT NULL AND raw_document_path <> ''"
    ).fetchall()
    trimmed = []
    for filing_id, raw in rows:
        parts = str(raw).replace("\\", "/").rstrip("/").split("/")
        short = "/".join(parts[-PATH_SEGMENTS_KEPT:])
        if short != raw:
            trimmed.append((short, filing_id))
    conn.executemany("UPDATE filings SET raw_document_path = ? WHERE id = ?", trimmed)

    for table in ("asset_resolution_cache", "ticker_cache", "ticker_details_cache"):
        try:
            conn.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    print(f"  scrubbed {len(trimmed):,} filing paths to <folder>/<file>")


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    def one(sql: str) -> int:
        try:
            return int(conn.execute(sql).fetchone()[0])
        except sqlite3.OperationalError:
            return 0

    return {
        "members": one("SELECT COUNT(*) FROM members"),
        "filings": one("SELECT COUNT(*) FROM filings"),
        "transactions": one("SELECT COUNT(*) FROM transactions"),
        "tickers": one(
            "SELECT COUNT(DISTINCT ticker) FROM transactions "
            "WHERE ticker IS NOT NULL AND ticker <> ''"
        ),
        "reviewQueue": one("SELECT COUNT(*) FROM review_queue"),
        "priceBars": one("SELECT COUNT(*) FROM yahoo_daily_bar_cache"),
    }


def _stamp_manifest(counts: dict[str, int], since: str, captured: str, out: Path) -> None:
    if not MANIFEST.exists():
        print(f"  (no {MANIFEST.relative_to(BASE_DIR)} yet — skipping stamp)")
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data = manifest.setdefault("data", {})
    data["source"] = str(out.relative_to(BASE_DIR)).replace("\\", "/")
    data["snapshot"] = captured
    data["window"] = f"transactions from {since}"
    data["counts"] = counts
    data["sizeMb"] = round(out.stat().st_size / 1048576, 1)
    manifest["updatedAt"] = captured
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  stamped {MANIFEST.relative_to(BASE_DIR)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--bars-since", default=DEFAULT_BARS_SINCE)
    ap.add_argument(
        "--captured",
        default=date.today().isoformat(),
        help="Capture date recorded in the manifest and shown on the demo banner.",
    )
    args = ap.parse_args(argv)

    if not args.source.exists():
        print(f"Source database not found: {args.source}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Freezing {args.source.name} -> {args.out.relative_to(BASE_DIR)}")
    print(f"  transactions from {args.since}, price bars from {args.bars_since}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work.sqlite"
        vacuumed = Path(tmp) / "snapshot.sqlite"
        shutil.copy(args.source, work)

        conn = sqlite3.connect(work)
        try:
            _trim(conn, args.since, args.bars_since)
            _scrub(conn)
            counts = _counts(conn)
            conn.execute("VACUUM INTO ?", (str(vacuumed),))
        finally:
            conn.close()

        with open(vacuumed, "rb") as raw, gzip.open(args.out, "wb", compresslevel=9) as gz:
            shutil.copyfileobj(raw, gz)

        plain_mb = vacuumed.stat().st_size / 1048576

    gz_mb = args.out.stat().st_size / 1048576
    for key, value in counts.items():
        print(f"  {value:>8,}  {key}")
    print(f"  {plain_mb:.1f} MB uncompressed, {gz_mb:.1f} MB committed")
    _stamp_manifest(counts, args.since, args.captured, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
