from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

import requests
from tqdm import tqdm

from .config import HOUSE_FD_BULK_ZIP_URL, HOUSE_RAW_DIR, START_YEAR, USER_AGENT
from .utils import ensure_dirs, extract_house_fd_bulk_zip, house_fd_bulk_zip_needs_extract
from .api.jobs import CancelledError  # noqa: E402 — single source of truth, no circular import


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


def _fd_bulk_url(year: int) -> str:
    return HOUSE_FD_BULK_ZIP_URL.format(year=year)


def fd_bulk_zip_path(year: int) -> Path:
    return HOUSE_RAW_DIR / f"{year}FD.zip"


def fd_bulk_extract_dir(year: int) -> Path:
    return HOUSE_RAW_DIR / f"{year}FD"


def house_fd_refresh_force_years(now: datetime | None = None) -> set[int]:
    """Years whose FD bulk zip should be re-fetched even when overwrite=False.

    Always includes the current calendar year so Refresh discovers new FilingType=P
    rows. In January–February also includes the previous year (Clerk bulk for Y-1
    can still change early in Y).
    """
    now = now or datetime.now()
    years = {now.year}
    if now.month <= 2 and now.year - 1 >= START_YEAR:
        years.add(now.year - 1)
    return years


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
    force_extract: bool = False,
    force_years: Iterable[int] | None = None,
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[[str, int, int], None] | None = None,
) -> list[int]:
    """
    Scarica gli zip annuali FD del Clerk della House (bulk metadata) e opzionalmente li estrae in
    data/raw/house/<year>FD/ (stessa struttura che si ottiene con zip manuali).

    Verifica i termini d'uso del sito disclosures-clerk.house.gov prima di automatizzare download ripetuti.

    - overwrite=True: riscarica lo zip anche se esiste gia localmente. Forza inoltre la re-estrazione
      completa dei file top-level (equivalente a force_extract=True) perche l'utente ha esplicitamente
      chiesto di rinfrescare.
    - force_years: anni da riscaricare anche se overwrite=False (usato dal Refresh per l'anno corrente).
    - force_extract=True: dopo l'estrazione, wipe completo dei file top-level dello zip nella dest_dir
      e ri-estrai. Sicuro ma piu lento: utile quando i metadata locali sembrano allineati ma in realta
      sono vecchi (succede se la detection basata sulla dimensione del TXT matcha con la dimensione di
      un TXT precedente; raro ma lo abbiamo visto).
    - cancel_event: opzionale threading.Event osservato tra un anno e l'altro; quando
      viene settato dal background runner la funzione solleva CancelledError.
    """
    ensure_dirs([HOUSE_RAW_DIR])
    headers = {"User-Agent": USER_AGENT}
    completed: list[int] = []
    force_year_set = {int(y) for y in (force_years or ())}

    sorted_years = sorted(set(years))
    total_years = len(sorted_years)
    if progress_hook is not None:
        progress_hook("Downloading House FD metadata", 0, total_years, unit="years")

    for year_index, year in enumerate(sorted_years):
        def _report_year_progress() -> None:
            if progress_hook is not None:
                progress_hook(
                    f"House FD {year}",
                    year_index + 1,
                    total_years,
                    unit="years",
                )

        _check_cancel(cancel_event)
        url = _fd_bulk_url(year)
        dest_zip = fd_bulk_zip_path(year)
        dest_dir = fd_bulk_extract_dir(year)
        dest_txt = dest_dir / f"{year}FD.txt"

        # Per-year overwrite: global flag, or this year is in the incremental refresh set.
        year_overwrite = bool(overwrite or year in force_year_set)
        # When l'utente chiede overwrite (o force_years), i TXT/XML sul disco devono
        # aggiornarsi: zipfile.extractall su Windows a volte non sovrascrive, quindi
        # forziamo wipe + re-estrazione. Costo: ~ms.
        year_force_extract = bool(force_extract or year_overwrite)

        stale_vs_zip = (
            extract
            and dest_zip.exists()
            and house_fd_bulk_zip_needs_extract(dest_zip, dest_dir)
        )

        if stale_vs_zip and not year_overwrite:
            print(
                f"House FD {year}: metadata su disco non coincide con {dest_zip.name}; "
                f"ri-estraggo senza riscaricare."
            )
            extract_house_fd_bulk_zip(dest_zip, dest_dir, force=year_force_extract)
            print(f"Estratto in {dest_dir}")
            completed.append(year)
            _report_year_progress()
            continue

        # force_extract alone (no overwrite): wipe + re-extract existing zip, no re-download.
        if year_force_extract and not year_overwrite and extract and dest_zip.exists():
            print(f"House FD {year}: force_extract attivo, wipe + re-estrazione di {dest_dir}.")
            extract_house_fd_bulk_zip(dest_zip, dest_dir, force=True)
            print(f"Estratto in {dest_dir}")
            completed.append(year)
            _report_year_progress()
            continue

        if not year_overwrite and dest_txt.exists() and dest_zip.exists() and not stale_vs_zip:
            print(f"Salto {year}: presente {dest_txt} e allineato allo zip")
            _report_year_progress()
            continue

        need_download = year_overwrite or not dest_zip.exists()
        if need_download:
            try:
                print(f"Scarico {year} da {url}")
                _download_zip(url, dest_zip, headers=headers)
            except requests.HTTPError as exc:
                print(f"Errore HTTP per anno {year}: {exc}")
                if dest_zip.exists():
                    dest_zip.unlink(missing_ok=True)
                _report_year_progress()
                continue
            except Exception as exc:
                print(f"Errore download anno {year}: {exc}")
                if dest_zip.exists():
                    dest_zip.unlink(missing_ok=True)
                _report_year_progress()
                continue
        elif extract and not dest_txt.exists():
            print(f"Uso zip esistente per {year}: {dest_zip}")

        if extract:
            extract_house_fd_bulk_zip(dest_zip, dest_dir, force=year_force_extract)
            print(f"Estratto in {dest_dir}")

        completed.append(year)
        _report_year_progress()

    return completed
