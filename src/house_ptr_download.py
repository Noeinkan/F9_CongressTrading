from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Iterable

import requests
from tqdm import tqdm

from .api.jobs import CancelledError
from .config import (
    HOUSE_PTR_PDF_URL,
    HOUSE_RAW_DIR,
    RAW_DIR,
    USER_AGENT,
    house_ptr_auto_download_enabled,
    house_ptr_auto_download_max_filing_year,
    house_ptr_auto_download_min_filing_year,
    house_ptr_download_min_interval_seconds,
)
from .utils import (
    extract_house_fd_bulk_zip,
    extract_zip,
    house_fd_bulk_zip_needs_extract,
    is_house_fd_bulk_zip_path,
    normalize_whitespace,
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
            # DocID spesso inizia con "200…" (non e l'anno 2002): mostra filing year nella barra.
            pbar_desc = f"{year}/{doc_id}.pdf"
            with dest.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=pbar_desc) as pbar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        return True
    except requests.RequestException:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


def download_house_ptr_pdfs(
    fd_rows: Iterable[dict[str, str | None]],
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[[str, int, int], None] | None = None,
) -> int:
    if not house_ptr_auto_download_enabled():
        return 0

    min_filing_year = house_ptr_auto_download_min_filing_year()
    max_filing_year = house_ptr_auto_download_max_filing_year()
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
        if year < min_filing_year or year > max_filing_year:
            continue
        key = (year, doc_id)
        if key in seen:
            continue
        seen.add(key)
        dest = HOUSE_RAW_DIR / str(year) / f"{doc_id}.pdf"
        if dest.exists():
            continue
        targets.append((year, doc_id, dest))

    interval = house_ptr_download_min_interval_seconds()
    downloaded = 0
    total_targets = len(targets)
    if progress_hook is not None:
        progress_hook("Downloading House PTR PDFs", 0, total_targets, unit="PTR files")
    for i, (year, doc_id, dest) in enumerate(targets):
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()
        if i > 0 and interval > 0:
            time.sleep(interval)
        if _download_house_ptr_pdf(year, doc_id, dest):
            downloaded += 1
            if downloaded % 50 == 0:
                print(f"PTR scaricati finora: {downloaded}...", flush=True)
        if progress_hook is not None:
            progress_hook(
                f"PTR {year}/{doc_id}",
                i + 1,
                total_targets,
                unit="PTR files",
            )
    return downloaded


def extract_local_zip_files() -> None:
    zip_paths = list(HOUSE_RAW_DIR.glob("*.zip")) + list(RAW_DIR.glob("*.zip"))
    for zip_path in zip_paths:
        name = zip_path.name.lower()
        if zip_path.parent == RAW_DIR and "senate" in name:
            continue
        dest_dir = HOUSE_RAW_DIR / zip_path.stem
        if is_house_fd_bulk_zip_path(zip_path):
            if house_fd_bulk_zip_needs_extract(zip_path, dest_dir):
                extract_house_fd_bulk_zip(zip_path, dest_dir)
        else:
            extract_zip(zip_path, dest_dir)
