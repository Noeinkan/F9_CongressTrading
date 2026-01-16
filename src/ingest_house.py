from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from tqdm import tqdm

from .config import HOUSE_DISCLOSURE_URL, HOUSE_RAW_DIR, RAW_DIR, START_YEAR, USER_AGENT
from .db import get_connection, init_db, insert_fd_filings, insert_trades, is_file_ingested, mark_file_ingested
from .parse_fd import iter_fd_files, parse_fd_txt, parse_fd_xml
from .parse_ptr import iter_ptr_pdfs, parse_ptr_pdf
from .ticker_lookup import lookup_ticker
from .utils import ensure_dirs, extract_zip, normalize_whitespace, parse_date, sha256_file


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
        to_insert = []
        for row in rows:
            asset = normalize_whitespace(row.get("asset") or "")
            if not asset:
                continue
            ticker = lookup_ticker(conn, asset)
            to_insert.append(
                {
                    "member": normalize_whitespace(member),
                    "chamber": "House",
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
    ingest_house()
