from __future__ import annotations

import threading
from collections.abc import Callable

from .config import RAW_DIR, SENATE_RAW_DIR, senate_efd_auto_download_enabled
from .db import (
    get_connection,
    init_db,
    insert_fd_filings,
    insert_filing,
    insert_trades,
    insert_transaction,
    insert_transaction_tag,
    is_file_ingested,
    mark_file_ingested,
    queue_transaction_review,
    upsert_issuer,
    upsert_member,
)
from .parse_fd import iter_fd_files, parse_fd_txt, parse_fd_xml
from .parse_ptr import parse_ptr_pdf_safe, parse_senate_ptr_html
from .ticker_lookup import resolve_asset
from .utils import (
    extract_zip,
    make_content_hash,
    make_transaction_source_hash,
    normalize_whitespace,
    parse_amount_range,
    parse_date,
    sanitize_transaction_date,
    sha256_file,
    split_state_district,
)
from .api.jobs import CancelledError  # noqa: E402 — single source of truth, no circular import


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


def _persist_ptr_filing(
    conn,
    *,
    member: str,
    filing_date: str | None,
    rows: list[dict[str, str | None]],
    source_path,
    sha: str,
    source_url: str = "",
) -> int:
    """
    Normalize + insert one Senate PTR filing (shared by the PDF and HTML paths).
    ``rows`` must follow the parse_ptr contract (see parse_ptr_pdf / parse_senate_ptr_html).
    Returns the number of transactions inserted.
    """
    member = normalize_whitespace(member)
    member_id = upsert_member(conn, full_name=member, chamber="Senate")
    filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber="Senate",
        filing_type="PTR",
        filing_date=filing_date,
        doc_id=source_path.stem,
        source_url=source_url,
        raw_document_path=str(source_path),
        source_hash=sha,
    )
    to_insert: list[dict[str, str | None]] = []
    for index, row in enumerate(rows):
        asset = normalize_whitespace(row.get("asset") or "")
        if not asset:
            continue
        resolution = resolve_asset(conn, asset)
        amount_range = normalize_whitespace(row.get("amount_range") or "")
        amount_low, amount_high = parse_amount_range(amount_range)
        source_page_value = row.get("source_page")
        source_page = int(source_page_value) if source_page_value else None
        issuer_id = upsert_issuer(
            conn,
            issuer_name=resolution.get("issuer_name") or asset,
            ticker=resolution.get("ticker"),
            sector=resolution.get("sector"),
            industry=resolution.get("industry"),
            asset_type=resolution.get("asset_type"),
        )
        transaction_id = insert_transaction(
            conn,
            filing_id=filing_id,
            issuer_id=issuer_id,
            transaction_date=sanitize_transaction_date(
                parse_date(row.get("transaction_date") or ""), filing_date
            ),
            owner_type=row.get("owner_type"),
            asset_name_raw=asset,
            asset_name_normalized=resolution.get("asset_name_normalized"),
            asset_type=resolution.get("asset_type"),
            ticker=resolution.get("ticker"),
            cusip_or_figi=resolution.get("cusip_or_figi"),
            transaction_type=normalize_whitespace(row.get("transaction_type") or ""),
            amount_low=amount_low,
            amount_high=amount_high,
            amount_range_raw=amount_range,
            confidence_score=float(resolution.get("confidence_score") or 0.0),
            review_status=resolution.get("review_status"),
            source_page=source_page,
            source_row=str(index),
            source_hash=make_transaction_source_hash(
                sha,
                source_page,
                row.get("transaction_date"),
                asset,
                row.get("transaction_type"),
                amount_range,
                row.get("owner_type"),
            ),
        )
        review_status = resolution.get("review_status")
        if review_status != "exact_match":
            if review_status == "fuzzy_match":
                review_notes = (
                    f"Fuzzy asset match: {asset} -> "
                    f"{resolution.get('issuer_name') or asset} ({resolution.get('ticker') or 'no ticker'})"
                )
            else:
                review_notes = f"Asset requires manual review: {asset}"
            queue_transaction_review(
                conn,
                transaction_id=transaction_id,
                reason="asset_resolution",
                notes=review_notes,
            )
        if row.get("parse_warning"):
            queue_transaction_review(
                conn,
                transaction_id=transaction_id,
                reason="parse_warning",
                notes=row.get("parse_warning"),
            )
        if resolution.get("sector"):
            insert_transaction_tag(
                conn,
                transaction_id=transaction_id,
                tag="sector",
                value=str(resolution.get("sector")),
            )
        if resolution.get("industry"):
            insert_transaction_tag(
                conn,
                transaction_id=transaction_id,
                tag="industry",
                value=str(resolution.get("industry")),
            )
        to_insert.append(
            {
                "member": member,
                "chamber": "Senate",
                "filing_date": filing_date,
                "transaction_date": sanitize_transaction_date(
                    parse_date(row.get("transaction_date") or ""), filing_date
                ),
                "asset": asset,
                "ticker": resolution.get("ticker"),
                "transaction_type": normalize_whitespace(row.get("transaction_type") or ""),
                "amount_range": amount_range,
                "source_url": source_url,
                "source_file": str(source_path),
            }
        )
    insert_trades(conn, to_insert)
    return len(to_insert)


def ingest_senate(
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[..., None] | None = None,
) -> None:
    """
    Parsa i PTR del Senato presenti in data/raw/senate/: PDF (``parse_ptr_pdf_safe``)
    e HTML dei PTR elettronici efdsearch (``parse_senate_ptr_html``). I file possono
    essere scaricati con ``python -m src.main download-senate`` (in locale) oppure,
    se ``SENATE_EFD_AUTO_DOWNLOAD=1``, all'inizio di questa funzione (default OFF: lo
    scraping efdsearch va fatto da IP residenziale, non dal VPS — vedi AGENTS.md).

    ``cancel_event`` (opzionale) viene osservato tra un file e l'altro e prima di
    ogni fase grossolana. Quando viene settato dal background runner, la funzione
    solleva ``CancelledError`` che il job runner intercetta per marcare il job
    come "cancelled" invece di "succeeded".
    """
    SENATE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)
    try:
        _check_cancel(cancel_event)

        if senate_efd_auto_download_enabled():
            from .download_senate_efd import download_senate_efd

            print("SENATE_EFD_AUTO_DOWNLOAD attivo: scarico i PTR elettronici da efdsearch...", flush=True)
            download_senate_efd(cancel_event=cancel_event, progress_hook=progress_hook)

        zip_paths = list(SENATE_RAW_DIR.glob("*.zip")) + list(RAW_DIR.glob("*.zip"))
        for zip_path in zip_paths:
            _check_cancel(cancel_event)
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
            for row in fd_rows:
                state, district = split_state_district(row.get("state_district"))
                member_id = upsert_member(
                    conn,
                    full_name=row.get("member") or "Unknown Member",
                    chamber="Senate",
                    state=state,
                    district=district,
                )
                insert_filing(
                    conn,
                    member_id=member_id,
                    chamber="Senate",
                    filing_type=row.get("filing_type") or "FD",
                    filing_date=row.get("filing_date"),
                    doc_id=row.get("doc_id"),
                    source_url="",
                    raw_document_path=row.get("source_file") or "",
                    source_hash=make_content_hash(row.get("source_file"), row.get("doc_id"), row.get("filing_date")),
                )

        # Corpus = PDF PTR (scansioni / vecchi) + HTML dei PTR elettronici efdsearch.
        senate_files = sorted(
            (p for p in SENATE_RAW_DIR.rglob("*") if p.suffix.lower() in {".pdf", ".html"}),
            key=lambda p: str(p).casefold(),
        )
        if not senate_files:
            # Il job 'Refresh data' mostra gia un messaggio piu dettagliato; qui stampiamo solo un
            # reminder sintetico quando ingest_senate viene invocato standalone (CLI / script).
            print(
                "Senate: 0 PTR (PDF/HTML) in data/raw/senate/. "
                "Esegui 'python -m src.main download-senate' oppure aggiungi i file a mano da https://efdsearch.senate.gov/."
            )
            return

        total = len(senate_files)
        print(f"Trovati {total} PTR (PDF/HTML) in {SENATE_RAW_DIR}; avvio parsing...", flush=True)
        if progress_hook is not None:
            progress_hook("Parsing Senate PTRs", 0, total, unit="PTRs")

        skipped = 0
        parsed_count = 0
        for file_index, ptr_path in enumerate(senate_files):
            # Cancel between files: parse_ptr_pdf_safe is one long pdfplumber call we
            # cannot interrupt, but per-file granularity is fine (small corpus).
            _check_cancel(cancel_event)
            sha = sha256_file(ptr_path)
            if is_file_ingested(conn, str(ptr_path), sha):
                skipped += 1
                if progress_hook is not None:
                    progress_hook(f"Senate {ptr_path.name} (skip)", file_index + 1, total, unit="PTRs")
                continue

            if ptr_path.suffix.lower() == ".html":
                header, rows = parse_senate_ptr_html(ptr_path)
            else:
                header, rows = parse_ptr_pdf_safe(ptr_path)
            parsed_count += 1
            member = header.get("member") or ptr_path.stem
            filing_date = header.get("filing_date")
            _txn_count = len([r for r in rows if (r.get("asset") or "").strip()])
            print(
                f"  {file_index + 1}/{total}: {ptr_path.name} | "
                f"{member} | filed {filing_date or '?'} | {_txn_count} txn",
                flush=True,
            )
            _persist_ptr_filing(
                conn,
                member=member,
                filing_date=filing_date,
                rows=rows,
                source_path=ptr_path,
                sha=sha,
            )
            mark_file_ingested(conn, str(ptr_path), sha)
            if progress_hook is not None:
                progress_hook(f"Senate {ptr_path.name}", file_index + 1, total, unit="PTRs")

        print(
            f"Senate PTR completato: {parsed_count} parsati, {skipped} gia ingeriti (skip), "
            f"{total} totali.",
            flush=True,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    ingest_senate()