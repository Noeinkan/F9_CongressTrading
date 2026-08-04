from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HOUSE_INGEST_PARSE_WORKERS = int(os.getenv("HOUSE_INGEST_PARSE_WORKERS", "4"))
HOUSE_INGEST_DB_COMMIT_CHUNK = int(os.getenv("HOUSE_INGEST_DB_COMMIT_CHUNK", "25"))

from .config import (
    HOUSE_RAW_DIR,
    house_ingest_force_reparse_pdfs,
    house_ingest_skip_external_asset_lookup,
    house_ptr_auto_download_enabled,
    house_ptr_auto_download_max_filing_year,
    house_ptr_auto_download_min_filing_year,
)
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
from .parse_ptr import parse_ptr_pdf_safe
from .ticker_lookup import bulk_resolve_unique_assets_for_reconcile, resolve_asset
from .house_coverage import print_house_coverage_report
from .house_ptr_download import download_house_ptr_pdfs, extract_local_zip_files
from .house_ptr_repair import (
    backfill_house_ptr_filing_dates,
    delete_invalid_house_ptr_transactions,
    fix_future_transaction_dates,
    lookup_house_ptr_filing_date,
    merge_duplicate_house_ptr_filings,
    repair_house_ptr_dates,
)
from .re_resolve_tickers import re_resolve_all_transaction_tickers
from .utils import (
    ensure_dirs,
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

# Public re-exports (CLI / tests historically import from ingest_house).
__all__ = ["ingest_house", "re_resolve_all_transaction_tickers"]


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


def _process_pdf_batch(
    conn,
    pdf_paths: list[Path],
    fd_lookup: dict[str, dict[str, str | None]],
    start_index: int,
    total_pending: int,
) -> tuple[int, int]:
    """Parse a chunk of PDFs (parallel, in a process pool) and persist their transactions.

    ``start_index`` / ``total_pending`` are 0-based offset and count within the
    *pending* queue (new/changed PDFs only), not the full on-disk corpus — so
    logs read ``PDF 1/3`` instead of ``PDF 1131/1690`` on an incremental Refresh.

    Returns ``(parsed_count, persisted_count)``. Each call to this function ends with a single
    explicit ``conn.commit()`` so a crash mid-run keeps the dashboard up-to-date with everything
    up to the last completed batch.
    """
    if not pdf_paths:
        return 0, 0

    # Step 1: parse PDFs in a process pool. pdfplumber is mostly I/O + regex and the per-call
    # ProcessPoolExecutor in parse_ptr_pdf_safe pays a fork cost; we share one pool here.
    parsed: list[tuple[Path, str, dict[str, str | None], list[dict[str, str | None]]]] = []
    parsed_count = 0
    max_workers = max(1, min(HOUSE_INGEST_PARSE_WORKERS, len(pdf_paths)))
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(parse_ptr_pdf_safe, p): (idx, p)
            for idx, p in enumerate(pdf_paths)
        }
        for future in as_completed(future_to_path):
            idx, pdf_path = future_to_path[future]
            try:
                header, rows = future.result()
            except Exception as exc:
                print(
                    f"  ✗ PDF {start_index + idx + 1}/{total_pending}: {pdf_path.name} — errore: {exc}",
                    flush=True,
                )
                continue
            parsed.append((pdf_path, sha256_file(pdf_path), header, rows))
            parsed_count += 1

    if not parsed:
        return 0, 0

    # Step 2: bulk-resolve distinct assets once for the whole chunk (cuts Polygon/OpenFIGI calls
    # by N where N is the avg transactions-per-PDF in the chunk).
    distinct_assets: dict[str, None] = {}
    for _pdf, _sha, header, rows in parsed:
        for row in rows:
            asset = normalize_whitespace(row.get("asset") or "")
            if asset:
                distinct_assets[asset] = None
    bulk = bulk_resolve_unique_assets_for_reconcile(
        conn, list(distinct_assets.keys()), commit=False
    )

    # Step 3: persist everything on the main thread (serial DB writes).
    persisted = 0
    for pdf_path, sha, header, rows in parsed:
        member = header.get("member") or fd_lookup.get(pdf_path.stem, {}).get("member") or pdf_path.stem
        _fd_hint = fd_lookup.get(pdf_path.stem, {})
        _filing_hint = header.get("filing_date") or _fd_hint.get("filing_date") or "?"
        _txn_count = len([r for r in rows if (r.get("asset") or "").strip()])
        print(
            f"  PDF {start_index + pdf_paths.index(pdf_path) + 1}/{total_pending}: {pdf_path.name} | "
            f"{member} | filed {_filing_hint} | {_txn_count} txn",
            flush=True,
        )
        member = header.get("member") or pdf_path.stem
        filing_date = header.get("filing_date") or lookup_house_ptr_filing_date(conn, pdf_path.stem)
        source_url = ""
        member_id = upsert_member(conn, full_name=normalize_whitespace(member), chamber="House")
        filing_id = insert_filing(
            conn,
            member_id=member_id,
            chamber="House",
            filing_type="PTR",
            filing_date=filing_date,
            doc_id=pdf_path.stem,
            source_url=source_url,
            raw_document_path=str(pdf_path),
            source_hash=sha,
        )
        to_insert = []
        for index, row in enumerate(rows):
            asset = normalize_whitespace(row.get("asset") or "")
            if not asset:
                continue
            resolution = bulk.get(asset) or resolve_asset(conn, asset, commit=False)
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
                commit=False,
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
                    commit=False,
                )
            if row.get("parse_warning"):
                queue_transaction_review(
                    conn,
                    transaction_id=transaction_id,
                    reason="parse_warning",
                    notes=row.get("parse_warning"),
                    commit=False,
                )
            if resolution.get("sector"):
                insert_transaction_tag(
                    conn,
                    transaction_id=transaction_id,
                    tag="sector",
                    value=str(resolution.get("sector")),
                    # NB: insert_transaction_tag commits internally; safe to call here.
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
                    "member": normalize_whitespace(member),
                    "chamber": "House",
                    "filing_date": filing_date,
                    "transaction_date": sanitize_transaction_date(
                        parse_date(row.get("transaction_date") or ""), filing_date
                    ),
                    "asset": asset,
                    "ticker": resolution.get("ticker"),
                    "transaction_type": normalize_whitespace(row.get("transaction_type") or ""),
                    "amount_range": amount_range,
                    "source_url": source_url,
                    "source_file": str(pdf_path),
                }
            )
        insert_trades(conn, to_insert)
        mark_file_ingested(conn, str(pdf_path), sha)
        persisted += 1

    conn.commit()
    return parsed_count, persisted


def ingest_house(
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[[str, int, int], None] | None = None,
) -> None:
    ensure_dirs([HOUSE_RAW_DIR])
    conn = get_connection()
    init_db(conn)
    _check_cancel(cancel_event)
    merged_filings = merge_duplicate_house_ptr_filings(conn)
    if merged_filings:
        print(f"Consolidati {merged_filings} filing PTR House duplicati.")
    backfilled_filing_dates = backfill_house_ptr_filing_dates(conn)
    if backfilled_filing_dates:
        print(f"Backfillate {backfilled_filing_dates} filing_date PTR House da FD metadata.")
    repaired_rows = repair_house_ptr_dates(conn)
    if repaired_rows:
        print(f"Riparate {repaired_rows} transazioni PTR House con date mancanti.")
    fixed_future_dates = fix_future_transaction_dates(conn)
    if fixed_future_dates:
        print(f"Corrected {fixed_future_dates} transaction(s) with future dates (year-typo).")
    deleted_invalid_rows = delete_invalid_house_ptr_transactions(conn)
    if deleted_invalid_rows:
        print(f"Rimosse {deleted_invalid_rows} righe PTR House non valide residue.")

    extract_local_zip_files()
    _check_cancel(cancel_event)

    fd_rows: list[dict[str, str | None]] = []
    new_fd_rows: list[dict[str, str | None]] = []
    for fd_path in iter_fd_files(HOUSE_RAW_DIR):
        if fd_path.suffix.lower() not in {".txt", ".xml"}:
            continue
        if fd_path.suffix.lower() == ".txt":
            parsed_rows = list(parse_fd_txt(fd_path, "House"))
        else:
            parsed_rows = list(parse_fd_xml(fd_path, "House"))
        fd_rows.extend(parsed_rows)

        sha = sha256_file(fd_path)
        if is_file_ingested(conn, str(fd_path), sha):
            continue
        new_fd_rows.extend(parsed_rows)
        mark_file_ingested(conn, str(fd_path), sha)
    if new_fd_rows:
        insert_fd_filings(conn, new_fd_rows)
        for row in new_fd_rows:
            state, district = split_state_district(row.get("state_district"))
            member_id = upsert_member(
                conn,
                full_name=row.get("member") or "Unknown Member",
                chamber="House",
                state=state,
                district=district,
            )
            insert_filing(
                conn,
                member_id=member_id,
                chamber="House",
                filing_type=row.get("filing_type") or "FD",
                filing_date=row.get("filing_date"),
                doc_id=row.get("doc_id"),
                source_url="",
                raw_document_path=row.get("source_file") or "",
                source_hash=make_content_hash(row.get("source_file"), row.get("doc_id"), row.get("filing_date")),
            )

    downloaded_count = download_house_ptr_pdfs(
        fd_rows,
        cancel_event=cancel_event,
        progress_hook=progress_hook,
    )
    if downloaded_count:
        print(f"Scaricati {downloaded_count} PTR House automaticamente.")
    elif not house_ptr_auto_download_enabled():
        print("Autodownload PTR House disattivato (imposta HOUSE_PTR_AUTO_DOWNLOAD=1 per riattivarlo).")
    else:
        print(
            "Nessun nuovo PTR House scaricato dal Clerk (PDF gia presenti, nessuna riga P nei metadata, "
            f"o anni fuori da [{house_ptr_auto_download_min_filing_year()}, {house_ptr_auto_download_max_filing_year()}] per filing Year)."
        )

    ptr_paths = sorted(HOUSE_RAW_DIR.rglob("*.pdf"), key=lambda p: str(p).casefold())
    if not ptr_paths:
        print("Nessun PDF trovato in data/raw/house/. Nessun PTR House scaricabile automaticamente dai metadata disponibili.")
        print_house_coverage_report(conn)
        conn.close()
        return

    total_pdfs = len(ptr_paths)
    print(f"Trovati {total_pdfs} PDF PTR in {HOUSE_RAW_DIR}; avvio parsing...", flush=True)
    if house_ingest_force_reparse_pdfs():
        print("Modalita HOUSE_INGEST_FORCE_REPARSE_PDFS: ogni PDF verra riparsato anche se gia ingerito.", flush=True)
    if not house_ingest_skip_external_asset_lookup() and total_pdfs > 80:
        print(
            "Suggerimento: con molti PDF la risoluzione ticker (Polygon) puo richiedere molto tempo. "
            "Per un ingest veloce: $env:HOUSE_INGEST_SKIP_EXTERNAL_ASSET_LOOKUP='1' poi rilancia senza per arricchire.",
            flush=True,
        )

    fd_lookup: dict[str, dict[str, str | None]] = {}
    for _fdr in fd_rows:
        _doc = _fdr.get("doc_id")
        if _doc and _doc not in fd_lookup:
            fd_lookup[_doc] = _fdr

    skipped = 0
    parsed_count = 0
    persisted_count = 0

    # Pre-filter: only PDFs that need parsing get queued. With FORCE_REPARSE_PDFS set, all of them
    # are queued; without it, anything already in files_ingested (by path) is skipped without
    # hashing — Refresh is "new since last scrape", not a content-diff of every PDF on disk.
    pending: list[Path] = []
    for pdf_path in ptr_paths:
        if not house_ingest_force_reparse_pdfs() and is_file_ingested(conn, str(pdf_path), None):
            skipped += 1
            continue
        pending.append(pdf_path)
    print(
        f"Da processare: {len(pending)} nuovi/changed; skip {skipped} gia ingeriti "
        f"(su {total_pdfs} su disco).",
        flush=True,
    )

    if not pending:
        print("Nessun PDF da processare.", flush=True)
    else:
        chunk = max(1, HOUSE_INGEST_DB_COMMIT_CHUNK)
        batches_total = (len(pending) + chunk - 1) // chunk
        if progress_hook is not None:
            progress_hook("Parsing House PTR PDFs", 0, len(pending), unit="PDFs")
        for batch_num, batch_start in enumerate(range(0, len(pending), chunk), start=1):
            # Check cancel between batches: in-flight ProcessPoolExecutor work
            # in `_process_pdf_batch` cannot be interrupted cleanly, but we can
            # bail out before submitting the next batch so the job ends within
            # at most one chunk's worth of latency after the user clicks Cancel.
            _check_cancel(cancel_event)
            batch_paths = pending[batch_start : batch_start + chunk]
            t0 = time.time()
            batch_parsed, batch_persisted = _process_pdf_batch(
                conn,
                batch_paths,
                fd_lookup,
                batch_start,
                len(pending),
            )
            parsed_count += batch_parsed
            persisted_count += batch_persisted
            elapsed = time.time() - t0
            done = min(batch_start + chunk, len(pending))
            print(
                f"  [batch {done}/{len(pending)}] parsed={batch_parsed} persisted={batch_persisted} "
                f"in {elapsed:.1f}s — commit eseguito, dati visibili al dashboard.",
                flush=True,
            )
            if progress_hook is not None:
                progress_hook(
                    f"House PTR batch {batch_num}/{batches_total}",
                    batch_num,
                    batches_total,
                    unit="batches",
                )
                progress_hook(
                    "Parsing House PTR PDFs",
                    done,
                    len(pending),
                    unit="PDFs",
                )

    print(
        f"House PTR completato: {parsed_count} PDF parsati, {persisted_count} persistiti, "
        f"{skipped} gia ingeriti (skip), {total_pdfs} totali.",
        flush=True,
    )
    print_house_coverage_report(conn)
    conn.close()


if __name__ == "__main__":
    ingest_house()
