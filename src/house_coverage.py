from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .config import house_coverage_max_filing_lag_days, house_coverage_min_year
from .download_house_fd import fd_bulk_extract_dir, fd_bulk_zip_path
from .utils import house_fd_bulk_zip_needs_extract


def _coverage_years(*, today: date | None = None) -> range:
    today = today or date.today()
    y0 = house_coverage_min_year()
    if y0 > today.year:
        return range(today.year, today.year + 1)
    return range(y0, today.year + 1)


def collect_house_coverage_issues(conn: sqlite3.Connection, *, today: date | None = None) -> list[str]:
    """Controlli su disco (metadata FD vs zip) e su DB (freshness fd_filings)."""
    issues: list[str] = []
    today = today or date.today()
    min_year = house_coverage_min_year()

    for year in _coverage_years(today=today):
        dest_dir = fd_bulk_extract_dir(year)
        dest_txt = dest_dir / f"{year}FD.txt"
        dest_zip = fd_bulk_zip_path(year)
        if not dest_txt.exists():
            issues.append(
                f"House FD {year}: manca {dest_txt} - "
                f"python -m src.main download-house-fd --years {year}"
            )
            continue
        if dest_zip.exists() and house_fd_bulk_zip_needs_extract(dest_zip, dest_dir):
            issues.append(
                f"House FD {year}: file estratti in {dest_dir} non coincidono con {dest_zip.name} "
                f"(zip aggiornato o estrazione parziale) - "
                f"python -m src.main download-house-fd --years {year} --overwrite"
            )

    row = conn.execute(
        """
        SELECT MAX(filing_date) FROM fd_filings
        WHERE chamber = 'House' AND UPPER(TRIM(COALESCE(filing_type, ''))) = 'P'
        """
    ).fetchone()
    max_raw = row[0] if row else None
    max_fd: date | None = None
    if max_raw:
        try:
            max_fd = date.fromisoformat(str(max_raw)[:10])
        except ValueError:
            max_fd = None
    if max_fd:
        lag = house_coverage_max_filing_lag_days()
        if today - max_fd > timedelta(days=lag):
            issues.append(
                f"House fd_filings (PTR): ultimo filing_date {max_fd.isoformat()} "
                f"({(today - max_fd).days} giorni fa, soglia {lag}). "
                "Possibile catalogo Clerk non aggiornato - prova download-house-fd --overwrite e ingest-house."
            )

    tx_row = conn.execute(
        """
        SELECT MIN(t.transaction_date), MAX(t.transaction_date)
        FROM transactions t
        JOIN filings f ON t.filing_id = f.id
        WHERE f.chamber = 'House' AND f.filing_type = 'PTR'
          AND COALESCE(t.transaction_date, '') <> ''
        """
    ).fetchone()
    if tx_row and tx_row[0]:
        try:
            min_tx = date.fromisoformat(str(tx_row[0])[:10])
        except ValueError:
            min_tx = None
        if min_tx and min_tx.year > min_year:
            issues.append(
                f"House transazioni: prima transaction_date in DB e {min_tx.isoformat()} "
                f"(ti aspetti copertura dal {min_year}); verifica ingest anni precedenti."
            )

    has_txt = any((fd_bulk_extract_dir(y) / f"{y}FD.txt").exists() for y in _coverage_years(today=today))
    if has_txt and (not max_raw or not str(max_raw).strip()):
        issues.append(
            "House: sono presenti file *FD.txt ma fd_filings non ha filing PTR (P) - eseguire ingest-house."
        )

    return issues


def print_house_coverage_report(conn: sqlite3.Connection, *, label: str = "[copertura House] ") -> None:
    issues = collect_house_coverage_issues(conn)
    y0 = house_coverage_min_year()
    y1 = date.today().year
    if not issues:
        print(f"{label}OK: metadata {y0}–{y1} presente e allineato agli zip; controlli DB superati.")
        return
    for msg in issues:
        print(f"{label}ATTENZIONE: {msg}")
