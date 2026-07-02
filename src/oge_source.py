"""OGE Executive disclosure registry.

Hard-coded list of known OGE 278-T (periodic transactions) and 278e (annual)
PDFs for the U.S. President (and any future Executive filers we add). Adding
a new filer = append an :class:`OgeFiling` entry to a module-level constant.

The downloader (``src.api.oge_source.download_oge_filings`` / CLI
``download-oge``) walks this list at 1 req/sec; if a ``doc_id`` returns 404 we
fail loudly without retrying, because OGE URLs are stable — a stale URL means
the entry needs human attention.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OgeFiling:
    """One known OGE disclosure PDF.

    Attributes
    ----------
    filer_name:
        Display name used for ``members.full_name`` (e.g. "Donald J. Trump").
    filing_type:
        ``"OGE278T"`` for periodic transaction reports,
        ``"OGE278e"`` for the annual asset/income report.
    filing_date:
        ISO date (``YYYY-MM-DD``) for the disclosure. Best-effort — OGE does
        not always expose this in the URL, so a sensible default is fine.
    doc_id:
        The 32-char hex OGE document id (extracted from the URL or
        registry). Used as the local filename ``<doc_id>.pdf``.
    url:
        Full public URL under ``extapps2.oge.gov/201/Presiden.nsf/...``.
    source_path:
        Absolute path on disk once downloaded (filled in by the downloader).
    """

    filer_name: str
    filing_type: str  # 'OGE278T' or 'OGE278e'
    filing_date: str  # ISO date string
    doc_id: str
    url: str
    source_path: str = ""

    def is_periodic(self) -> bool:
        return self.filing_type == "OGE278T"

    def is_annual(self) -> bool:
        return self.filing_type == "OGE278e"


# ---------------------------------------------------------------------------
# Trump filings registry
# ---------------------------------------------------------------------------
# Public under 5 U.S.C. § 13107.  These URLs are the ones OGE publishes on the
# Presidential Disclosures page; they are stable but if one returns 404 we do
# not auto-rescrape — fail loud and let the operator update the registry.
TRUMP_OGE_FILINGS: list[OgeFiling] = [
    OgeFiling(
        filer_name="Donald J. Trump",
        filing_type="OGE278e",
        filing_date="2025-05-15",
        doc_id="4EC9A8E6DD078F2985258CA9002C9377",
        url=(
            "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/"
            "4EC9A8E6DD078F2985258CA9002C9377/%24FILE/"
            "Trump%2C%20Donald%20J.%202025%20Annual%20278.pdf"
        ),
    ),
    OgeFiling(
        filer_name="Donald J. Trump",
        filing_type="OGE278T",
        filing_date="2026-02-26",
        doc_id="174165F6E1E120B185258DB000347F54",
        url=(
            "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/"
            "174165F6E1E120B185258DB000347F54/$FILE/"
            "Donald%20J.%20Trump%202.26.2026%20278-T%20(1).pdf"
        ),
    ),
    OgeFiling(
        filer_name="Donald J. Trump",
        filing_type="OGE278T",
        filing_date="2026-04-20",
        doc_id="CD75555856A7D2E485258DE4002DD4A0",
        url=(
            "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/"
            "CD75555856A7D2E485258DE4002DD4A0/$FILE/"
            "Donald-J-Trump-4.20.2026-278T.pdf"
        ),
    ),
    OgeFiling(
        filer_name="Donald J. Trump",
        filing_type="OGE278T",
        filing_date="2026-05-08",
        doc_id="5326D3AF5BE7C25385258DF7002DD1B7",
        url=(
            "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/"
            "5326D3AF5BE7C25385258DF7002DD1B7/$FILE/"
            "Trump,%20Donald%20J.-05.08.2026-278T.pdf"
        ),
    ),
]


def get_filings_for_filer(filer_name: str) -> list[OgeFiling]:
    """Return the list of OGE filings for ``filer_name`` (case-insensitive)."""
    target = filer_name.strip().casefold()
    return [f for f in TRUMP_OGE_FILINGS if f.filer_name.casefold() == target]


def all_filings() -> list[OgeFiling]:
    """All known filings across every registered filer."""
    return list(TRUMP_OGE_FILINGS)