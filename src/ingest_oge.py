"""OGE Executive disclosure ingest pipeline.

Walks ``data/raw/oge/`` for PDFs, auto-detects 278-T vs 278e from page-1
header text, and writes normalized rows into the same SQLite tables House and
Senate use:

* ``members`` (one per filer, ``chamber="Executive"``)
* ``filings`` (one per PDF, ``filing_type="OGE278T"`` or ``"OGE278e"``,
  ``source_url`` populated from :mod:`src.oge_source`)
* ``transactions`` (only for 278-T — periodic trades; reuses ``resolve_asset``
  so ticker resolution is consistent with House/Senate)
* ``executive_holdings`` (only for 278e — annual report snapshot rows; no
  ticker resolution, no review queue entry)

The pipeline marks files in ``files_ingested`` (keyed by SHA-256) so reruns
are idempotent — the same PDF gets reparsed only when the file changes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .config import OGE_RAW_DIR
from .db import (
    get_connection,
    init_db,
    insert_executive_holding,
    insert_filing,
    insert_transaction,
    is_file_ingested,
    make_content_hash,
    mark_file_ingested,
    queue_transaction_review,
    upsert_issuer,
    upsert_member,
)
from .oge_source import TRUMP_OGE_FILINGS, OgeFiling, all_filings, get_filings_for_filer
from .parse_oge import parse_oge_278e_safe, parse_oge_278t_safe
from .ticker_lookup import resolve_asset
from .utils import (
    make_transaction_source_hash,
    normalize_whitespace,
    parse_amount_range,
    sanitize_transaction_date,
    sha256_file,
)


def _iter_oge_pdfs(root: Path) -> Iterable[Path]:
    """Yield every .pdf under ``root`` (recursive)."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*.pdf"), key=lambda p: str(p).casefold()):
        yield path


def _resolve_source_url_for_pdf(pdf_path: Path) -> str:
    """Match a local OGE PDF back to its registered URL (best-effort).

    Matches by ``doc_id`` (which we use as the filename) — the OGE downloader
    saves files as ``<doc_id>.pdf``.  If we can't find a match, returns an
    empty string so callers don't claim a source we don't have.
    """
    stem = pdf_path.stem.strip().upper()
    if not stem:
        return ""
    for filing in all_filings():
        if filing.doc_id.upper() == stem:
            return filing.url
    return ""


def _lookup_known_filing(pdf_path: Path) -> OgeFiling | None:
    """If this PDF was downloaded via ``download-oge``, return its registry entry."""
    stem = pdf_path.stem.strip().upper()
    if not stem:
        return None
    for filing in all_filings():
        if filing.doc_id.upper() == stem:
            return filing
    return None


def _ingest_one(
    conn,
    pdf_path: Path,
    *,
    filer_name_override: str | None = None,
) -> tuple[str, int, int]:
    """Parse one PDF and write to SQLite.

    Returns ``(form_type, n_transactions, n_holdings)``.
    Raises on form-type detection failure so the caller can log + skip.
    """
    sha = sha256_file(pdf_path)

    # Try 278-T first; if the file is a 278e the detector will raise and
    # we'll fall through to the 278e parser.  If neither matches we propagate.
    form_type: str | None = None
    header: dict[str, str | None] = {}
    rows: list[dict[str, object]] = []

    try:
        header, rows = parse_oge_278t_safe(pdf_path)
        form_type = "OGE278T"
    except ValueError:
        # Not a 278-T — try 278e.
        header, rows = parse_oge_278e_safe(pdf_path)
        form_type = "OGE278e"
    except Exception as exc:
        # Hard failure (corrupt PDF, timeout, …) — bubble up.
        raise

    if form_type not in {"OGE278T", "OGE278e"}:
        raise ValueError(f"Unknown OGE form type for {pdf_path}: {form_type!r}")

    filer_name = normalize_whitespace(filer_name_override or header.get("filer_name") or "")
    known = _lookup_known_filing(pdf_path)
    if known and not filer_name:
        filer_name = known.filer_name
    if not filer_name:
        filer_name = "Unknown Executive Filer"

    # Filing metadata: prefer the registry (stable, hand-curated) but fall back
    # to what the parser extracted.
    filing_date = (
        (known.filing_date if known else "")
        or header.get("filing_date")
        or ""
    )
    doc_id = (known.doc_id if known else "") or pdf_path.stem
    source_url = (known.url if known else "") or _resolve_source_url_for_pdf(pdf_path)

    member_id = upsert_member(conn, full_name=filer_name, chamber="Executive")
    filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber="Executive",
        filing_type=form_type,
        filing_date=filing_date,
        doc_id=doc_id,
        source_url=source_url,
        raw_document_path=str(pdf_path),
        source_hash=sha,
    )

    n_transactions = 0
    n_holdings = 0

    if form_type == "OGE278T":
        for index, row in enumerate(rows):
            asset = normalize_whitespace(str(row.get("asset") or ""))
            if not asset:
                continue
            transaction_date = row.get("transaction_date")
            amount_range = normalize_whitespace(str(row.get("amount_range") or ""))
            amount_low, amount_high = parse_amount_range(amount_range)
            source_page_value = row.get("source_page")
            try:
                source_page = int(source_page_value) if source_page_value is not None else None
            except (TypeError, ValueError):
                source_page = None
            owner_type = str(row.get("owner_type") or "filer")
            transaction_type = normalize_whitespace(str(row.get("transaction_type") or ""))
            parse_warning = row.get("parse_warning")

            resolution = resolve_asset(conn, asset)
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
                    transaction_date if isinstance(transaction_date, str) else None,
                    filing_date,
                ),
                owner_type=owner_type,
                asset_name_raw=asset,
                asset_name_normalized=resolution.get("asset_name_normalized"),
                asset_type=resolution.get("asset_type"),
                ticker=resolution.get("ticker"),
                cusip_or_figi=resolution.get("cusip_or_figi"),
                transaction_type=transaction_type,
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
                    transaction_date if isinstance(transaction_date, str) else None,
                    asset,
                    transaction_type,
                    amount_range,
                    owner_type,
                ),
            )
            review_status = resolution.get("review_status")
            if review_status != "exact_match":
                if review_status == "fuzzy_match":
                    review_notes = (
                        f"Fuzzy asset match: {asset} -> "
                        f"{resolution.get('issuer_name') or asset} "
                        f"({resolution.get('ticker') or 'no ticker'})"
                    )
                else:
                    review_notes = f"Asset requires manual review: {asset}"
                queue_transaction_review(
                    conn,
                    transaction_id=transaction_id,
                    reason="asset_resolution",
                    notes=review_notes,
                )
            if parse_warning:
                queue_transaction_review(
                    conn,
                    transaction_id=transaction_id,
                    reason="parse_warning",
                    notes=str(parse_warning),
                )
            n_transactions += 1
    else:  # OGE278e — annual holdings snapshot
        for index, row in enumerate(rows):
            asset_name = normalize_whitespace(str(row.get("asset_name") or ""))
            if not asset_name:
                continue
            value_range = normalize_whitespace(str(row.get("value_range") or ""))
            owner_type = normalize_whitespace(str(row.get("owner_type") or "filer"))
            asset_type = normalize_whitespace(str(row.get("asset_type") or ""))
            source_page_value = row.get("source_page")
            try:
                source_page = int(source_page_value) if source_page_value is not None else None
            except (TypeError, ValueError):
                source_page = None
            parse_warning = row.get("parse_warning")

            insert_executive_holding(
                conn,
                filing_id=filing_id,
                asset_name=asset_name,
                value_range=value_range,
                owner_type=owner_type,
                asset_type=asset_type,
                source_page=source_page,
                source_row=str(index),
                parse_warning=str(parse_warning) if parse_warning else None,
                source_hash=make_content_hash(
                    str(filing_id),
                    asset_name,
                    value_range,
                    owner_type,
                    asset_type,
                    str(index),
                ),
            )
            n_holdings += 1

    mark_file_ingested(conn, str(pdf_path), sha)
    return form_type, n_transactions, n_holdings


def ingest_oge(filer_name: str | None = None) -> None:
    """Ingest every PDF under ``data/raw/oge/`` into the normalized SQLite.

    Parameters
    ----------
    filer_name:
        Optional registry name (e.g. ``"Donald J. Trump"``) used only as a
        hint for the parsed header.  All PDFs on disk are processed
        regardless; this just changes what name we record if the PDF
        header is illegible.
    """
    OGE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)

    pdf_paths = list(_iter_oge_pdfs(OGE_RAW_DIR))
    if not pdf_paths:
        print(
            f"OGE: 0 PDF in {OGE_RAW_DIR}. "
            "Esegui `python -m src.main download-oge` per scaricare i filing.",
            flush=True,
        )
        conn.close()
        return

    print(f"OGE: trovati {len(pdf_paths)} PDF in {OGE_RAW_DIR}; avvio parsing...", flush=True)

    parsed = 0
    skipped = 0
    errors: list[tuple[Path, str]] = []
    tx_total = 0
    holdings_total = 0

    for pdf_path in pdf_paths:
        sha = sha256_file(pdf_path)
        if is_file_ingested(conn, str(pdf_path), sha):
            skipped += 1
            continue
        try:
            form_type, n_tx, n_hold = _ingest_one(
                conn,
                pdf_path,
                filer_name_override=filer_name,
            )
        except Exception as exc:  # noqa: BLE001 — surface failures but keep going.
            errors.append((pdf_path, str(exc)))
            print(f"  SKIP {pdf_path.name}: {exc}", flush=True)
            # Still mark as ingested so a broken file doesn't loop forever;
            # operator can remove the entry from files_ingested if they want
            # to retry after fixing the parser.
            mark_file_ingested(conn, str(pdf_path), sha)
            continue
        parsed += 1
        tx_total += n_tx
        holdings_total += n_hold
        print(
            f"  PDF {parsed + skipped}/{len(pdf_paths)}: {pdf_path.name} | "
            f"{form_type} | {n_tx} txn, {n_hold} holdings",
            flush=True,
        )

    summary = (
        f"OGE completato: {parsed} PDF parsati, {skipped} gia ingeriti (skip), "
        f"{tx_total} transazioni, {holdings_total} holdings, "
        f"{len(errors)} errori."
    )
    print(summary, flush=True)
    conn.close()


# Keep a reference to TRUMP_OGE_FILINGS so static analyzers see it as used;
# this module is the "registry importer" the CLI expects.
__all__ = [
    "ingest_oge",
    "TRUMP_OGE_FILINGS",
]