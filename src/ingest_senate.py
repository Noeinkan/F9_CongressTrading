from __future__ import annotations

from pathlib import Path

from .config import RAW_DIR, SENATE_RAW_DIR
from .db import get_connection, init_db, insert_fd_filings, insert_trades, is_file_ingested, mark_file_ingested
from .parse_fd import iter_fd_files, parse_fd_txt, parse_fd_xml
from .parse_ptr import iter_ptr_pdfs, parse_ptr_pdf
from .ticker_lookup import lookup_ticker
from .utils import extract_zip, normalize_whitespace, parse_date, sha256_file


def ingest_senate() -> None:
    """
    Senate eFD richiede accettazione dei termini; qui si usa una modalità manuale:
    inserisci i PDF dei PTR in data/raw/senate/ (es. dal 2022+)
    e avvia ingest_senate per il parsing e la normalizzazione.
    """
    SENATE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)

    zip_paths = list(SENATE_RAW_DIR.glob("*.zip")) + list(RAW_DIR.glob("*.zip"))
    for zip_path in zip_paths:
        name = zip_path.name.lower()
        if zip_path.parent == RAW_DIR and "senate" not in name:
            continue
        if zip_path.parent == RAW_DIR and "house" in name:
            continue
        dest_dir = SENATE_RAW_DIR / zip_path.stem
        extract_zip(zip_path, dest_dir)

    fd_rows: list[dict[str, str | None]] = []
    for fd_path in iter_fd_files(SENATE_RAW_DIR):
        if fd_path.suffix.lower() not in {".txt", ".xml"}:
            continue
        sha = sha256_file(fd_path)
        if is_file_ingested(conn, str(fd_path), sha):
            continue
        if fd_path.suffix.lower() == ".txt":
            fd_rows.extend(parse_fd_txt(fd_path, "Senate"))
        else:
            fd_rows.extend(parse_fd_xml(fd_path, "Senate"))
        mark_file_ingested(conn, str(fd_path), sha)
    if fd_rows:
        insert_fd_filings(conn, fd_rows)

    if not any(SENATE_RAW_DIR.rglob("*.pdf")):
        print("Nessun PDF trovato in data/raw/senate/. Aggiungi i PTR manualmente.")
        return

    for pdf_path in iter_ptr_pdfs(SENATE_RAW_DIR):
        sha = sha256_file(pdf_path)
        if is_file_ingested(conn, str(pdf_path), sha):
            continue
        header, rows = parse_ptr_pdf(pdf_path)
        member = header.get("member") or pdf_path.stem
        filing_date = header.get("filing_date")
        source_url = ""
        to_insert = []
        for row in rows:
            asset = normalize_whitespace(row.get("asset") or "")
            if not asset:
                continue
            ticker = lookup_ticker(conn, asset)
            to_insert.append(
                {
                    "member": normalize_whitespace(member),
                    "chamber": "Senate",
                    "filing_date": filing_date,
                    "transaction_date": parse_date(row.get("transaction_date") or ""),
                    "asset": asset,
                    "ticker": ticker,
                    "transaction_type": normalize_whitespace(row.get("transaction_type") or ""),
                    "amount_range": normalize_whitespace(row.get("amount_range") or ""),
                    "source_url": source_url,
                    "source_file": str(pdf_path),
                }
            )
        insert_trades(conn, to_insert)
        mark_file_ingested(conn, str(pdf_path), sha)

    conn.close()


if __name__ == "__main__":
    ingest_senate()
