from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from .config import DB_PATH
from .utils import make_content_hash, normalize_key, normalize_whitespace


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: Mapping[str, str]) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name in existing:
            continue
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            chamber TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT '',
            district TEXT NOT NULL DEFAULT '',
            party TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(normalized_name, chamber, state, district)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS filings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            chamber TEXT NOT NULL,
            filing_type TEXT NOT NULL,
            filing_date TEXT NOT NULL DEFAULT '',
            doc_id TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            raw_document_path TEXT NOT NULL,
            source_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(member_id) REFERENCES members(id),
            UNIQUE(member_id, chamber, filing_type, filing_date, doc_id, raw_document_path)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issuers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issuer_name TEXT NOT NULL,
            ticker TEXT NOT NULL DEFAULT '',
            sector TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(issuer_name, ticker, asset_type)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_id INTEGER NOT NULL,
            issuer_id INTEGER,
            transaction_date TEXT NOT NULL DEFAULT '',
            owner_type TEXT NOT NULL DEFAULT '',
            asset_name_raw TEXT NOT NULL,
            asset_name_normalized TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL DEFAULT '',
            ticker TEXT NOT NULL DEFAULT '',
            cusip_or_figi TEXT NOT NULL DEFAULT '',
            transaction_type TEXT NOT NULL DEFAULT '',
            amount_low INTEGER,
            amount_high INTEGER,
            amount_range_raw TEXT NOT NULL DEFAULT '',
            confidence_score REAL NOT NULL DEFAULT 0.0,
            review_status TEXT NOT NULL DEFAULT 'pending',
            source_page INTEGER,
            source_row TEXT NOT NULL DEFAULT '',
            source_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(filing_id) REFERENCES filings(id),
            FOREIGN KEY(issuer_id) REFERENCES issuers(id),
            UNIQUE(filing_id, source_hash)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transaction_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id),
            UNIQUE(transaction_id, tag, value)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL UNIQUE,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_resolution_cache (
            asset_name_key TEXT PRIMARY KEY,
            asset_name_raw TEXT NOT NULL,
            asset_name_normalized TEXT NOT NULL DEFAULT '',
            issuer_name TEXT NOT NULL DEFAULT '',
            ticker TEXT NOT NULL DEFAULT '',
            cusip_or_figi TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL DEFAULT '',
            sector TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            confidence_score REAL NOT NULL DEFAULT 0.0,
            resolution_status TEXT NOT NULL DEFAULT '',
            match_source TEXT NOT NULL DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member TEXT NOT NULL,
            chamber TEXT NOT NULL,
            filing_date TEXT,
            transaction_date TEXT,
            asset TEXT,
            ticker TEXT,
            transaction_type TEXT,
            amount_range TEXT,
            source_url TEXT,
            source_file TEXT,
            inserted_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_unique
        ON trades (
            member, chamber, filing_date, transaction_date,
            asset, transaction_type, amount_range, source_url
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files_ingested (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            sha256 TEXT,
            ingested_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ticker_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT NOT NULL UNIQUE,
            ticker TEXT,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fd_filings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member TEXT NOT NULL,
            chamber TEXT NOT NULL,
            filing_type TEXT,
            state_district TEXT,
            year INTEGER,
            filing_date TEXT,
            doc_id TEXT,
            source_file TEXT,
            inserted_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fd_unique
        ON fd_filings (
            member, chamber, filing_type, state_district,
            year, filing_date, doc_id, source_file
        )
        """
    )
    _ensure_columns(
        conn,
        "asset_resolution_cache",
        {
            "sector": "TEXT NOT NULL DEFAULT ''",
            "industry": "TEXT NOT NULL DEFAULT ''",
            "resolution_status": "TEXT NOT NULL DEFAULT ''",
        },
    )
    conn.execute(
        """
        UPDATE asset_resolution_cache
        SET resolution_status = CASE
            WHEN ticker <> '' AND confidence_score >= 0.98 THEN 'exact_match'
            WHEN ticker <> '' THEN 'fuzzy_match'
            ELSE 'manual_review'
        END
        WHERE COALESCE(resolution_status, '') = ''
        """
    )
    conn.commit()


def _text(value: str | None) -> str:
    return normalize_whitespace(value or "")


def insert_trades(conn: sqlite3.Connection, rows: Iterable[Mapping[str, str | None]]) -> int:
    rows_list = list(rows)
    if not rows_list:
        return 0
    conn.executemany(
        """
        INSERT OR IGNORE INTO trades (
            member, chamber, filing_date, transaction_date,
            asset, ticker, transaction_type, amount_range,
            source_url, source_file
        ) VALUES (
            :member, :chamber, :filing_date, :transaction_date,
            :asset, :ticker, :transaction_type, :amount_range,
            :source_url, :source_file
        )
        """,
        rows_list,
    )
    conn.commit()
    return conn.total_changes


def insert_fd_filings(conn: sqlite3.Connection, rows: Iterable[Mapping[str, str | None]]) -> int:
    rows_list = list(rows)
    if not rows_list:
        return 0
    conn.executemany(
        """
        INSERT OR IGNORE INTO fd_filings (
            member, chamber, filing_type, state_district,
            year, filing_date, doc_id, source_file
        ) VALUES (
            :member, :chamber, :filing_type, :state_district,
            :year, :filing_date, :doc_id, :source_file
        )
        """,
        rows_list,
    )
    conn.commit()
    return conn.total_changes


def mark_file_ingested(conn: sqlite3.Connection, file_path: str, sha256: str | None) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO files_ingested (file_path, sha256)
        VALUES (?, ?)
        """,
        (file_path, sha256),
    )
    conn.commit()


def is_file_ingested(conn: sqlite3.Connection, file_path: str, sha256: str | None) -> bool:
    row = conn.execute(
        "SELECT sha256 FROM files_ingested WHERE file_path = ?",
        (file_path,),
    ).fetchone()
    if row is None:
        return False
    if sha256 is None:
        return True
    return row["sha256"] == sha256


def upsert_member(
    conn: sqlite3.Connection,
    *,
    full_name: str,
    chamber: str,
    state: str | None = None,
    district: str | None = None,
    party: str | None = None,
) -> int:
    normalized_name = normalize_key(full_name)
    chamber_value = _text(chamber)
    state_value = _text(state)
    district_value = _text(district)
    party_value = _text(party)
    full_name_value = _text(full_name)

    conn.execute(
        """
        INSERT INTO members (
            full_name, normalized_name, chamber, state, district, party
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_name, chamber, state, district) DO UPDATE SET
            full_name=excluded.full_name,
            party=CASE WHEN excluded.party <> '' THEN excluded.party ELSE members.party END,
            updated_at=datetime('now')
        """,
        (full_name_value, normalized_name, chamber_value, state_value, district_value, party_value),
    )
    row = conn.execute(
        """
        SELECT id FROM members
        WHERE normalized_name = ? AND chamber = ? AND state = ? AND district = ?
        """,
        (normalized_name, chamber_value, state_value, district_value),
    ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("Failed to upsert member")
    return int(row["id"])


def insert_filing(
    conn: sqlite3.Connection,
    *,
    member_id: int,
    chamber: str,
    filing_type: str,
    filing_date: str | None,
    doc_id: str | None,
    source_url: str | None,
    raw_document_path: str,
    source_hash: str | None,
) -> int:
    chamber_value = _text(chamber)
    filing_type_value = _text(filing_type)
    filing_date_value = _text(filing_date)
    doc_id_value = _text(doc_id)
    source_url_value = _text(source_url)
    raw_document_path_value = _text(raw_document_path)
    source_hash_value = _text(source_hash)

    conn.execute(
        """
        INSERT INTO filings (
            member_id, chamber, filing_type, filing_date, doc_id,
            source_url, raw_document_path, source_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(member_id, chamber, filing_type, filing_date, doc_id, raw_document_path)
        DO UPDATE SET
            source_url=CASE WHEN excluded.source_url <> '' THEN excluded.source_url ELSE filings.source_url END,
            source_hash=CASE WHEN excluded.source_hash <> '' THEN excluded.source_hash ELSE filings.source_hash END,
            updated_at=datetime('now')
        """,
        (
            member_id,
            chamber_value,
            filing_type_value,
            filing_date_value,
            doc_id_value,
            source_url_value,
            raw_document_path_value,
            source_hash_value,
        ),
    )
    row = conn.execute(
        """
        SELECT id FROM filings
        WHERE member_id = ? AND chamber = ? AND filing_type = ?
          AND filing_date = ? AND doc_id = ? AND raw_document_path = ?
        """,
        (
            member_id,
            chamber_value,
            filing_type_value,
            filing_date_value,
            doc_id_value,
            raw_document_path_value,
        ),
    ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("Failed to insert filing")
    return int(row["id"])


def upsert_issuer(
    conn: sqlite3.Connection,
    *,
    issuer_name: str | None,
    ticker: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    asset_type: str | None = None,
) -> int | None:
    issuer_name_value = _text(issuer_name) or _text(ticker)
    if not issuer_name_value:
        return None

    ticker_value = _text(ticker)
    sector_value = _text(sector)
    industry_value = _text(industry)
    asset_type_value = _text(asset_type)

    conn.execute(
        """
        INSERT INTO issuers (issuer_name, ticker, sector, industry, asset_type)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(issuer_name, ticker, asset_type) DO UPDATE SET
            sector=CASE WHEN excluded.sector <> '' THEN excluded.sector ELSE issuers.sector END,
            industry=CASE WHEN excluded.industry <> '' THEN excluded.industry ELSE issuers.industry END,
            updated_at=datetime('now')
        """,
        (issuer_name_value, ticker_value, sector_value, industry_value, asset_type_value),
    )
    row = conn.execute(
        """
        SELECT id FROM issuers
        WHERE issuer_name = ? AND ticker = ? AND asset_type = ?
        """,
        (issuer_name_value, ticker_value, asset_type_value),
    ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("Failed to upsert issuer")
    return int(row["id"])


def insert_transaction(
    conn: sqlite3.Connection,
    *,
    filing_id: int,
    issuer_id: int | None,
    transaction_date: str | None,
    owner_type: str | None,
    asset_name_raw: str,
    asset_name_normalized: str | None,
    asset_type: str | None,
    ticker: str | None,
    cusip_or_figi: str | None,
    transaction_type: str | None,
    amount_low: int | None,
    amount_high: int | None,
    amount_range_raw: str | None,
    confidence_score: float,
    review_status: str | None,
    source_page: int | None,
    source_row: str | None,
    source_hash: str | None = None,
) -> int:
    asset_name_raw_value = _text(asset_name_raw)
    source_hash_value = _text(source_hash) or make_content_hash(
        str(filing_id),
        transaction_date,
        asset_name_raw_value,
        transaction_type,
        amount_range_raw,
        source_row,
    )

    conn.execute(
        """
        INSERT INTO transactions (
            filing_id, issuer_id, transaction_date, owner_type, asset_name_raw,
            asset_name_normalized, asset_type, ticker, cusip_or_figi,
            transaction_type, amount_low, amount_high, amount_range_raw,
            confidence_score, review_status, source_page, source_row, source_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filing_id, source_hash) DO UPDATE SET
            issuer_id=excluded.issuer_id,
            asset_name_normalized=excluded.asset_name_normalized,
            asset_type=excluded.asset_type,
            ticker=excluded.ticker,
            cusip_or_figi=excluded.cusip_or_figi,
            amount_low=excluded.amount_low,
            amount_high=excluded.amount_high,
            confidence_score=excluded.confidence_score,
            review_status=excluded.review_status,
            updated_at=datetime('now')
        """,
        (
            filing_id,
            issuer_id,
            _text(transaction_date),
            _text(owner_type),
            asset_name_raw_value,
            _text(asset_name_normalized),
            _text(asset_type),
            _text(ticker),
            _text(cusip_or_figi),
            _text(transaction_type),
            amount_low,
            amount_high,
            _text(amount_range_raw),
            confidence_score,
            _text(review_status) or "pending",
            source_page,
            _text(source_row),
            source_hash_value,
        ),
    )
    row = conn.execute(
        "SELECT id FROM transactions WHERE filing_id = ? AND source_hash = ?",
        (filing_id, source_hash_value),
    ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("Failed to insert transaction")
    return int(row["id"])


def insert_transaction_tag(
    conn: sqlite3.Connection,
    *,
    transaction_id: int,
    tag: str,
    value: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO transaction_tags (transaction_id, tag, value)
        VALUES (?, ?, ?)
        """,
        (transaction_id, _text(tag), _text(value)),
    )
    conn.commit()


def queue_transaction_review(
    conn: sqlite3.Connection,
    *,
    transaction_id: int,
    reason: str,
    notes: str | None = None,
    status: str = "open",
) -> None:
    conn.execute(
        """
        INSERT INTO review_queue (transaction_id, reason, status, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(transaction_id) DO UPDATE SET
            reason=excluded.reason,
            status=excluded.status,
            notes=excluded.notes,
            updated_at=datetime('now')
        """,
        (transaction_id, _text(reason), _text(status), _text(notes)),
    )
    conn.commit()


def upsert_asset_resolution(
    conn: sqlite3.Connection,
    *,
    asset_name_raw: str,
    asset_name_normalized: str | None,
    issuer_name: str | None,
    ticker: str | None,
    cusip_or_figi: str | None,
    asset_type: str | None,
    sector: str | None,
    industry: str | None,
    confidence_score: float,
    resolution_status: str,
    match_source: str,
) -> None:
    asset_name_key = normalize_key(asset_name_raw)
    conn.execute(
        """
        INSERT INTO asset_resolution_cache (
            asset_name_key, asset_name_raw, asset_name_normalized, issuer_name,
            ticker, cusip_or_figi, asset_type, sector, industry,
            confidence_score, resolution_status, match_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_name_key) DO UPDATE SET
            asset_name_raw=excluded.asset_name_raw,
            asset_name_normalized=excluded.asset_name_normalized,
            issuer_name=excluded.issuer_name,
            ticker=excluded.ticker,
            cusip_or_figi=excluded.cusip_or_figi,
            asset_type=excluded.asset_type,
            sector=excluded.sector,
            industry=excluded.industry,
            confidence_score=excluded.confidence_score,
            resolution_status=excluded.resolution_status,
            match_source=excluded.match_source,
            updated_at=datetime('now')
        """,
        (
            asset_name_key,
            _text(asset_name_raw),
            _text(asset_name_normalized),
            _text(issuer_name),
            _text(ticker),
            _text(cusip_or_figi),
            _text(asset_type),
            _text(sector),
            _text(industry),
            confidence_score,
            _text(resolution_status),
            _text(match_source),
        ),
    )
    conn.execute(
        """
        INSERT INTO ticker_cache (asset, ticker, source)
        VALUES (?, ?, ?)
        ON CONFLICT(asset) DO UPDATE SET
            ticker=excluded.ticker,
            source=excluded.source,
            updated_at=datetime('now')
        """,
        (_text(asset_name_raw), _text(ticker) or None, _text(match_source)),
    )
    conn.commit()


def get_asset_resolution(conn: sqlite3.Connection, asset_name_raw: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM asset_resolution_cache WHERE asset_name_key = ?",
        (normalize_key(asset_name_raw),),
    ).fetchone()


def upsert_ticker_cache(conn: sqlite3.Connection, asset: str, ticker: str | None, source: str) -> None:
    upsert_asset_resolution(
        conn,
        asset_name_raw=asset,
        asset_name_normalized=asset,
        issuer_name=asset,
        ticker=ticker,
        cusip_or_figi=None,
        asset_type="",
        sector="",
        industry="",
        confidence_score=1.0 if ticker else 0.0,
        resolution_status="exact_match" if ticker else "manual_review",
        match_source=source,
    )


def get_ticker_cache(conn: sqlite3.Connection, asset: str) -> str | None:
    row = get_asset_resolution(conn, asset)
    if row is not None and row["ticker"]:
        return row["ticker"]

    legacy_row = conn.execute(
        "SELECT ticker FROM ticker_cache WHERE asset = ?",
        (_text(asset),),
    ).fetchone()
    return legacy_row["ticker"] if legacy_row else None
