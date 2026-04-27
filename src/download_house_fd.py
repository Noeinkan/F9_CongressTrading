from __future__ import annotations

from pathlib import Path

import requests
from tqdm import tqdm

from .config import HOUSE_FD_BULK_ZIP_URL, HOUSE_RAW_DIR, START_YEAR, USER_AGENT
from .utils import ensure_dirs, extract_house_fd_bulk_zip, house_fd_bulk_zip_needs_extract


def _fd_bulk_url(year: int) -> str:
    return HOUSE_FD_BULK_ZIP_URL.format(year=year)


def fd_bulk_zip_path(year: int) -> Path:
    return HOUSE_RAW_DIR / f"{year}FD.zip"


def fd_bulk_extract_dir(year: int) -> Path:
    return HOUSE_RAW_DIR / f"{year}FD"


def _download_zip(url: str, dest: Path, *, headers: dict[str, str]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=headers, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "zip" not in ctype and "octet-stream" not in ctype:
            raise RuntimeError(f"Unexpected Content-Type for {url}: {ctype!r}")
        total = int(resp.headers.get("Content-Length", 0))
        with dest.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as pbar:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))


def download_house_fd_bulk(
    years: list[int],
    *,
    overwrite: bool = False,
    extract: bool = True,
) -> list[int]:
    """
    Scarica gli zip annuali FD del Clerk della House (bulk metadata) e opzionalmente li estrae in
    data/raw/house/<year>FD/ (stessa struttura che si ottiene con zip manuali).

    Verifica i termini d'uso del sito disclosures-clerk.house.gov prima di automatizzare download ripetuti.
    """
    ensure_dirs([HOUSE_RAW_DIR])
    headers = {"User-Agent": USER_AGENT}
    completed: list[int] = []

    for year in sorted(set(years)):
        url = _fd_bulk_url(year)
        dest_zip = fd_bulk_zip_path(year)
        dest_dir = fd_bulk_extract_dir(year)
        dest_txt = dest_dir / f"{year}FD.txt"

        stale_vs_zip = (
            extract
            and dest_zip.exists()
            and house_fd_bulk_zip_needs_extract(dest_zip, dest_dir)
        )

        if stale_vs_zip and not overwrite:
            print(
                f"House FD {year}: metadata su disco non coincide con {dest_zip.name}; "
                f"ri-estraggo senza riscaricare."
            )
            extract_house_fd_bulk_zip(dest_zip, dest_dir)
            print(f"Estratto in {dest_dir}")
            completed.append(year)
            continue

        if not overwrite and dest_txt.exists() and dest_zip.exists() and not stale_vs_zip:
            print(f"Salto {year}: presente {dest_txt} e allineato allo zip")
            continue

        need_download = overwrite or not dest_zip.exists()
        if need_download:
            try:
                print(f"Scarico {year} da {url}")
                _download_zip(url, dest_zip, headers=headers)
            except requests.HTTPError as exc:
                print(f"Errore HTTP per anno {year}: {exc}")
                if dest_zip.exists():
                    dest_zip.unlink(missing_ok=True)
                continue
            except Exception as exc:
                print(f"Errore download anno {year}: {exc}")
                if dest_zip.exists():
                    dest_zip.unlink(missing_ok=True)
                continue
        elif extract and not dest_txt.exists():
            print(f"Uso zip esistente per {year}: {dest_zip}")

        if extract:
            extract_house_fd_bulk_zip(dest_zip, dest_dir)
            print(f"Estratto in {dest_dir}")

        completed.append(year)

    return completed
