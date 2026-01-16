from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from .config import DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
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
    conn.commit()


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


def upsert_ticker_cache(conn: sqlite3.Connection, asset: str, ticker: str | None, source: str) -> None:
    conn.execute(
        """
        INSERT INTO ticker_cache (asset, ticker, source)
        VALUES (?, ?, ?)
        ON CONFLICT(asset) DO UPDATE SET
            ticker=excluded.ticker,
            source=excluded.source,
            updated_at=datetime('now')
        """,
        (asset, ticker, source),
    )
    conn.commit()


def get_ticker_cache(conn: sqlite3.Connection, asset: str) -> str | None:
    row = conn.execute(
        "SELECT ticker FROM ticker_cache WHERE asset = ?",
        (asset,),
    ).fetchone()
    return row["ticker"] if row else None
