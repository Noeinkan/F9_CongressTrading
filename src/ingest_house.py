from __future__ import annotations

from pathlib import Path
from typing import Iterable

import requests
from tqdm import tqdm

from .config import HOUSE_PTR_DOWNLOAD_YEARS, HOUSE_PTR_PDF_URL, HOUSE_RAW_DIR, RAW_DIR, START_YEAR, USER_AGENT
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
from .parse_ptr import iter_ptr_pdfs, parse_ptr_pdf
from .ticker_lookup import resolve_asset
from .utils import (
    ensure_dirs,
    extract_zip,
    make_content_hash,
    normalize_whitespace,
    parse_amount_range,
    parse_date,
    sha256_file,
    split_state_district,
)


def _download_zip(url: str, dest: Path) -> Path:
    headers = {"User-Agent": USER_AGENT}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        with dest.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as pbar:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
    return dest


def _download_house_ptr_pdf(year: int, doc_id: str, dest: Path) -> bool:
    url = HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id)
    headers = {"User-Agent": USER_AGENT}
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            if "pdf" not in (resp.headers.get("Content-Type") or "").lower():
                return False

            total = int(resp.headers.get("Content-Length", 0))
            with dest.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as pbar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        return True
    except requests.RequestException:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


def _download_house_ptr_pdfs(fd_rows: Iterable[dict[str, str | None]]) -> int:
    targets: list[tuple[int, str, Path]] = []
    seen: set[tuple[int, str]] = set()

    for row in fd_rows:
        if normalize_whitespace(row.get("filing_type") or "").upper() != "P":
            continue
        doc_id = normalize_whitespace(row.get("doc_id") or "")
        year_text = normalize_whitespace(row.get("year") or "")
        if not doc_id or not year_text.isdigit():
            continue
        year = int(year_text)
        if year < START_YEAR:
            continue
        if year not in HOUSE_PTR_DOWNLOAD_YEARS:
            continue
        key = (year, doc_id)
        if key in seen:
            continue
        seen.add(key)
        dest = HOUSE_RAW_DIR / str(year) / f"{doc_id}.pdf"
        if dest.exists():
            continue
        targets.append((year, doc_id, dest))

    downloaded = 0
    for year, doc_id, dest in targets:
        if _download_house_ptr_pdf(year, doc_id, dest):
            downloaded += 1
    return downloaded


def _extract_local_zip_files() -> None:
    zip_paths = list(HOUSE_RAW_DIR.glob("*.zip")) + list(RAW_DIR.glob("*.zip"))
    for zip_path in zip_paths:
        name = zip_path.name.lower()
        if zip_path.parent == RAW_DIR and "senate" in name:
            continue
        dest_dir = HOUSE_RAW_DIR / zip_path.stem
        extract_zip(zip_path, dest_dir)


def ingest_house() -> None:
    ensure_dirs([HOUSE_RAW_DIR])
    conn = get_connection()
    init_db(conn)

    _extract_local_zip_files()

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

    downloaded_count = _download_house_ptr_pdfs(fd_rows)
    if downloaded_count:
        print(f"Scaricati {downloaded_count} PTR House automaticamente.")
    else:
        years = ", ".join(str(year) for year in sorted(HOUSE_PTR_DOWNLOAD_YEARS))
        print(f"Download automatico House limitato agli anni: {years}.")

    if not any(HOUSE_RAW_DIR.rglob("*.pdf")):
        print("Nessun PDF trovato in data/raw/house/. Nessun PTR House scaricabile automaticamente dai metadata disponibili.")
        conn.close()
        return

    for pdf_path in iter_ptr_pdfs(HOUSE_RAW_DIR):
        sha = sha256_file(pdf_path)
        if is_file_ingested(conn, str(pdf_path), sha):
            continue
        header, rows = parse_ptr_pdf(pdf_path)
        member = header.get("member") or pdf_path.stem
        filing_date = header.get("filing_date")
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
            resolution = resolve_asset(conn, asset)
            amount_range = normalize_whitespace(row.get("amount_range") or "")
            amount_low, amount_high = parse_amount_range(amount_range)
            source_page = int(row["source_page"]) if row.get("source_page") else None
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
                transaction_date=parse_date(row.get("transaction_date") or ""),
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
                source_hash=make_content_hash(
                    sha,
                    str(index),
                    row.get("transaction_date"),
                    asset,
                    row.get("transaction_type"),
                    amount_range,
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
                    "member": normalize_whitespace(member),
                    "chamber": "House",
                    "filing_date": filing_date,
                    "transaction_date": parse_date(row.get("transaction_date") or ""),
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

    conn.close()


if __name__ == "__main__":
    ingest_house()
