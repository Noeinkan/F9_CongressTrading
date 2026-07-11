from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from curl_cffi import requests as crequests

from .config import (
    SENATE_EFD_BASE,
    SENATE_EFD_DOWNLOAD_MIN_INTERVAL_SECONDS,
    SENATE_EFD_FILER_TYPE_SENATOR,
    SENATE_EFD_HOME_URL,
    SENATE_EFD_LANDING_URL,
    SENATE_EFD_REPORT_DATA_URL,
    SENATE_EFD_REPORT_TYPE_PTR,
    SENATE_RAW_DIR,
    senate_efd_download_min_year,
    senate_efd_impersonate,
)
from .api.jobs import CancelledError  # noqa: E402 — single source of truth, no circular import

# efdsearch.senate.gov sits behind Akamai, which 403s plain `requests` on a TLS
# fingerprint before any cookie is set. curl_cffi impersonates a real browser TLS
# handshake and gets through. These extra headers round out the browser profile.
_BROWSER_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

# Report-link cell in the DataTables JSON is an <a href="/search/view/{ptr|paper}/<uuid>/">.
_LINK_RE = re.compile(r'href="(/search/view/(ptr|paper)/([0-9a-fA-F-]+)/?)"')


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


def _build_session() -> crequests.Session:
    # Do NOT set User-Agent here — curl_cffi's impersonate profile owns it (and the
    # matching sec-ch-ua headers); overriding it would break the fingerprint match.
    session = crequests.Session(impersonate=senate_efd_impersonate())
    session.headers.update(_BROWSER_HEADERS)
    return session


def _accept_terms(session: crequests.Session) -> str:
    """GET the landing page for a CSRF cookie, POST the prohibition agreement, return the token."""
    r = session.get(SENATE_EFD_HOME_URL, timeout=30)
    r.raise_for_status()
    token = session.cookies.get("csrftoken")
    if not token:
        raise RuntimeError(
            "efdsearch.senate.gov: no csrftoken cookie after GET "
            f"{SENATE_EFD_HOME_URL} (status {r.status_code}). Likely blocked by Akamai — "
            "run locally (residential IP) and confirm curl_cffi impersonation is active."
        )
    resp = session.post(
        SENATE_EFD_HOME_URL,
        data={"prohibition_agreement": "1", "csrfmiddlewaretoken": token},
        headers={"Referer": SENATE_EFD_HOME_URL, "Origin": SENATE_EFD_BASE},
        timeout=30,
    )
    resp.raise_for_status()
    # Land on the search tab so the AJAX endpoint sees a consistent Referer/cookie.
    session.get(SENATE_EFD_LANDING_URL, timeout=30)
    return session.cookies.get("csrftoken") or token


def _iter_ptr_reports(
    session: crequests.Session,
    token: str,
    *,
    min_year: int,
    page_size: int = 100,
    min_interval_seconds: float = SENATE_EFD_DOWNLOAD_MIN_INTERVAL_SECONDS,
    cancel_event: threading.Event | None = None,
) -> Iterator[dict[str, str]]:
    """Yield one dict per PTR filing (electronic or paper) from the DataTables search endpoint."""
    start = 0
    page = 0
    while True:
        _check_cancel(cancel_event)
        if page > 0 and min_interval_seconds > 0:
            time.sleep(min_interval_seconds)
        payload = {
            "start": str(start),
            "length": str(page_size),
            "report_types": f"[{SENATE_EFD_REPORT_TYPE_PTR}]",
            "filer_types": f"[{SENATE_EFD_FILER_TYPE_SENATOR}]",
            "submitted_start_date": f"01/01/{min_year} 00:00:00",
            "submitted_end_date": "",
            "candidate_state": "",
            "senator_state": "",
            "office_id": "",
            "first_name": "",
            "last_name": "",
            "draw": str(page + 1),
        }
        r = session.post(
            SENATE_EFD_REPORT_DATA_URL,
            data=payload,
            headers={
                "Referer": SENATE_EFD_LANDING_URL,
                "Origin": SENATE_EFD_BASE,
                "X-CSRFToken": token,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            link_html = row[3] if len(row) > 3 else ""
            m = _LINK_RE.search(link_html or "")
            if not m:
                continue
            yield {
                "first_name": (row[0] or "").strip(),
                "last_name": (row[1] or "").strip(),
                "office": (row[2] or "").strip(),
                "url_path": m.group(1),
                "kind": m.group(2),  # 'ptr' (electronic) | 'paper' (scanned GIF)
                "uuid": m.group(3),
                "filing_date": (row[4] or "").strip() if len(row) > 4 else "",
            }
        records_total = int(data.get("recordsTotal") or 0)
        start += page_size
        page += 1
        if start >= records_total:
            break


def _fetch_report_html(session: crequests.Session, url_path: str, dest: Path) -> bool:
    r = session.get(SENATE_EFD_BASE + url_path, headers={"Referer": SENATE_EFD_LANDING_URL}, timeout=60)
    if r.status_code == 404:
        return False
    r.raise_for_status()
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "html" not in ctype:
        return False
    dest.write_text(r.text, encoding="utf-8")
    return True


def download_senate_efd(
    *,
    dest_dir: Path = SENATE_RAW_DIR,
    min_interval_seconds: float = SENATE_EFD_DOWNLOAD_MIN_INTERVAL_SECONDS,
    overwrite: bool = False,
    min_year: int | None = None,
    limit: int | None = None,
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[..., None] | None = None,
) -> tuple[int, int]:
    """
    Scarica i PTR elettronici del Senato da efdsearch.senate.gov in ``dest_dir`` come
    ``<uuid>.html`` (poi ``ingest-senate`` li parsa). Conservativo: accetta i termini una
    volta, pagina la ricerca e attende ``min_interval_seconds`` tra una richiesta di rete
    e l'altra (curl_cffi impersona un browser per superare Akamai).

    I PTR "paper" sono scansioni GIF (non PDF) e non sono parsabili senza OCR: vengono
    contati e saltati. Ritorna ``(downloaded, already_present)``.
    """
    if min_year is None:
        min_year = senate_efd_download_min_year()
    dest_dir.mkdir(parents=True, exist_ok=True)

    session = _build_session()
    token = _accept_terms(session)

    reports = list(
        _iter_ptr_reports(
            session,
            token,
            min_year=min_year,
            min_interval_seconds=min_interval_seconds,
            cancel_event=cancel_event,
        )
    )
    electronic = [rep for rep in reports if rep["kind"] == "ptr"]
    skipped_paper = sum(1 for rep in reports if rep["kind"] == "paper")
    electronic_total = len(electronic)
    if limit is not None:
        electronic = electronic[: max(limit, 0)]

    total = len(electronic)
    limit_note = f", scarico i primi {total}" if limit is not None and total < electronic_total else ""
    print(
        f"Senate eFD: {len(reports)} PTR filings dal {min_year} "
        f"({electronic_total} elettronici, {skipped_paper} paper/GIF saltati{limit_note}).",
        flush=True,
    )
    if progress_hook is not None:
        progress_hook("Downloading Senate PTRs", 0, total, unit="reports")

    downloaded = 0
    already_present = 0
    net_calls = 0
    for index, rep in enumerate(electronic):
        _check_cancel(cancel_event)
        dest = dest_dir / f"{rep['uuid']}.html"
        if dest.exists() and not overwrite:
            already_present += 1
            if progress_hook is not None:
                progress_hook(f"Senate {rep['uuid']} (skip)", index + 1, total, unit="reports")
            continue
        if net_calls > 0 and min_interval_seconds > 0:
            time.sleep(min_interval_seconds)
        net_calls += 1
        try:
            ok = _fetch_report_html(session, rep["url_path"], dest)
        except CancelledError:
            raise
        except Exception as exc:  # network hiccup on one report shouldn't kill the run
            print(f"Senate eFD: errore su {rep['uuid']}: {exc}", flush=True)
            if dest.exists():
                dest.unlink(missing_ok=True)
            continue
        if ok:
            downloaded += 1
        else:
            print(f"Senate eFD: report {rep['uuid']} non disponibile (404/non-HTML), salto.", flush=True)
        if downloaded and downloaded % 50 == 0:
            print(f"  ...{downloaded} PTR scaricati", flush=True)
        if progress_hook is not None:
            progress_hook(f"Senate {rep['uuid']}", index + 1, total, unit="reports")

    print(
        f"Senate eFD completato: {downloaded} scaricati, {already_present} gia presenti, "
        f"{skipped_paper} paper saltati.",
        flush=True,
    )
    return downloaded, already_present
