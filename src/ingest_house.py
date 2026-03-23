from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from tqdm import tqdm

from .config import HOUSE_DISCLOSURE_URL, HOUSE_RAW_DIR, RAW_DIR, START_YEAR, USER_AGENT
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


def _discover_house_ptr_links() -> list[tuple[int, str]]:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(HOUSE_DISCLOSURE_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if "ptr" not in href.lower() and "ptr" not in text.lower():
            continue
        if not href.lower().endswith(".zip"):
            continue
        year_match = re.search(r"(20\d{2})", href) or re.search(r"(20\d{2})", text)
        if not year_match:
            continue
        year = int(year_match.group(1))
        if year < START_YEAR:
            continue
        if href.startswith("/"):
            href = "https://disclosures-clerk.house.gov" + href
        links.append((year, href))

    if links:
        return sorted(set(links))

    return _probe_ptr_zip_urls()


def _probe_ptr_zip_urls() -> list[tuple[int, str]]:
    headers = {"User-Agent": USER_AGENT}
    patterns = [
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}PTR.zip",
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}ptr.zip",
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}PTRs.zip",
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}Ptr.zip",
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}.zip",
    ]

    def _url_exists(url: str) -> bool:
        try:
            range_headers = {**headers, "Range": "bytes=0-0"}
            resp = requests.get(url, headers=range_headers, stream=True, timeout=20, allow_redirects=True)
            try:
                return resp.status_code in (200, 206)
            finally:
                resp.close()
        except requests.RequestException:
            return False

    links = []
    current_year = datetime.utcnow().year
    for year in range(START_YEAR, current_year + 1):
        for pattern in patterns:
            url = pattern.format(year=year)
            if _url_exists(url):
                links.append((year, url))
                break
    return links


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
    for fd_path in iter_fd_files(HOUSE_RAW_DIR):
        if fd_path.suffix.lower() not in {".txt", ".xml"}:
            continue
        sha = sha256_file(fd_path)
        if is_file_ingested(conn, str(fd_path), sha):
            continue
        if fd_path.suffix.lower() == ".txt":
            fd_rows.extend(parse_fd_txt(fd_path, "House"))
        else:
            fd_rows.extend(parse_fd_xml(fd_path, "House"))
        mark_file_ingested(conn, str(fd_path), sha)
    if fd_rows:
        insert_fd_filings(conn, fd_rows)
        for row in fd_rows:
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

    links = _discover_house_ptr_links()
    if not links:
        print("Nessun link PTR trovato sul sito House. Uso modalità manuale: inserisci i PDF in data/raw/house/.")
    else:
        for year, url in links:
            year_dir = HOUSE_RAW_DIR / str(year)
            zip_path = HOUSE_RAW_DIR / f"house_ptr_{year}.zip"
            if not zip_path.exists():
                _download_zip(url, zip_path)
            extract_zip(zip_path, year_dir)

    if not any(HOUSE_RAW_DIR.rglob("*.pdf")):
        print("Nessun PDF trovato in data/raw/house/. Aggiungi i PTR manualmente.")
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
