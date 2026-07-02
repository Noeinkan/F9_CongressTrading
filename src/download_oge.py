"""Conservative OGE PDF downloader.

Walks the :mod:`src.oge_source` registry at one request per second, skips files
already present on disk, and fails loudly on a 404 — OGE URLs are stable so a
404 means the registry entry needs human attention (no auto-rescrape).
"""
from __future__ import annotations

import time
from pathlib import Path

import requests
from tqdm import tqdm

from .config import OGE_DOWNLOAD_MIN_INTERVAL_SECONDS, OGE_RAW_DIR, USER_AGENT
from .oge_source import OgeFiling, all_filings, get_filings_for_filer


def _local_path(filing: OgeFiling, dest_dir: Path) -> Path:
    return dest_dir / f"{filing.doc_id}.pdf"


def _download_one(filing: OgeFiling, dest: Path, headers: dict[str, str]) -> None:
    """Download ``filing.url`` to ``dest``.

    Raises ``RuntimeError`` on HTTP 404 (so the caller can fail loud without
    retrying) and on any other non-2xx response.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(filing.url, headers=headers, stream=True, timeout=120) as resp:
        if resp.status_code == 404:
            raise RuntimeError(
                f"OGE doc_id {filing.doc_id} returned 404 (URL: {filing.url}). "
                "The filing is no longer at this URL — update src/oge_source.py."
            )
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        with dest.open("wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as pbar:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))


def download_oge_filings(
    filer_name: str | None = None,
    *,
    dest_dir: Path = OGE_RAW_DIR,
    min_interval_seconds: float = OGE_DOWNLOAD_MIN_INTERVAL_SECONDS,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Download every OGE filing in the registry (or filtered by filer).

    Returns ``(downloaded, already_present)``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT}

    if filer_name:
        filings = get_filings_for_filer(filer_name)
        if not filings:
            print(
                f"OGE: nessun filing registrato per filer {filer_name!r}; "
                "controlla src/oge_source.py."
            )
            return 0, 0
    else:
        filings = all_filings()

    downloaded = 0
    already_present = 0
    for index, filing in enumerate(filings):
        dest = _local_path(filing, dest_dir)
        if dest.exists() and not overwrite:
            already_present += 1
            print(f"  [{index + 1}/{len(filings)}] skip (esiste): {dest.name}")
            continue
        # Enforce the conservative interval between network calls.
        if index > 0:
            time.sleep(max(min_interval_seconds, 0.0))
        print(
            f"  [{index + 1}/{len(filings)}] download {filing.filing_type} "
            f"({filing.filing_date}): {dest.name}"
        )
        _download_one(filing, dest, headers=headers)
        downloaded += 1

    return downloaded, already_present