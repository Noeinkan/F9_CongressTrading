from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
HOUSE_RAW_DIR = RAW_DIR / "house"
SENATE_RAW_DIR = RAW_DIR / "senate"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "congress_trades.sqlite"
CACHE_DIR = DATA_DIR / "cache"

START_YEAR = 2022

# Anno di filing (colonna Year nei metadata FD) minimo per l'autodownload PTR dal Clerk
# quando HOUSE_PTR_AUTO_DOWNLOAD_MIN_YEAR non e impostato. Evita scaricare anni vecchi
# solo perche sono presenti cartelle tipo 2020FD/ in data/raw/house/.
HOUSE_PTR_AUTO_DOWNLOAD_MIN_FILING_YEAR_DEFAULT = 2023


def house_ptr_auto_download_enabled() -> bool:
    """HOUSE_PTR_AUTO_DOWNLOAD=0|false|no disattiva il download PTR dal Clerk durante ingest-house."""
    v = (os.getenv("HOUSE_PTR_AUTO_DOWNLOAD") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def house_ptr_auto_download_max_filing_year() -> int:
    """Ultimo anno di filing (colonna Year nei metadata FD) incluso nell'autodownload. Default: anno solare corrente."""
    raw = (os.getenv("HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR") or "").strip()
    if raw.isdigit():
        return int(raw)
    return datetime.now().year


def house_ptr_auto_download_min_filing_year() -> int:
    """Primo anno di filing incluso nell'autodownload PTR. Default: HOUSE_PTR_AUTO_DOWNLOAD_MIN_FILING_YEAR_DEFAULT."""
    raw = (os.getenv("HOUSE_PTR_AUTO_DOWNLOAD_MIN_YEAR") or "").strip()
    if raw.isdigit():
        return int(raw)
    return HOUSE_PTR_AUTO_DOWNLOAD_MIN_FILING_YEAR_DEFAULT


def house_ptr_download_min_interval_seconds() -> float:
    return float(os.getenv("HOUSE_PTR_DOWNLOAD_MIN_INTERVAL_SECONDS", "0.2"))


def house_ingest_force_reparse_pdfs() -> bool:
    """Se true, riesegue il parsing di ogni PDF PTR anche se gia in files_ingested (aggiorna transazioni via upsert)."""
    v = (os.getenv("HOUSE_INGEST_FORCE_REPARSE_PDFS") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def house_coverage_min_year() -> int:
    """Primo anno solare incluso in verify-house-coverage (default 2023). Env: HOUSE_COVERAGE_MIN_YEAR."""
    raw = (os.getenv("HOUSE_COVERAGE_MIN_YEAR") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 2023


def house_coverage_max_filing_lag_days() -> int:
    """Soglia giorni: se MAX(filing_date) PTR in fd_filings e piu vecchio, segnala possibile bulk non aggiornato."""
    raw = (os.getenv("HOUSE_COVERAGE_MAX_FILING_LAG_DAYS") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 75


def house_ingest_skip_external_asset_lookup() -> bool:
    """
    Se true, durante l'ingest non vengono chiamati Polygon/OpenFIGI per asset non in cache
    (solo manual_review locale, molto piu veloce su migliaia di righe). Utile per completare
    prima il caricamento PDF/DB; poi si possono raffinare i ticker in un secondo passaggio.
    """
    v = (os.getenv("HOUSE_INGEST_SKIP_EXTERNAL_ASSET_LOOKUP") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def app_username() -> str:
    return (os.getenv("APP_USERNAME") or "").strip()


def app_password() -> str:
    return os.getenv("APP_PASSWORD") or ""


def app_auth_required() -> bool:
    """True when APP_PASSWORD is set (login gate enabled)."""
    return bool(app_password().strip())

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

HOUSE_DISCLOSURE_URL = "https://disclosures-clerk.house.gov/PublicDisclosure/FinancialDisclosure"
HOUSE_FD_BULK_ZIP_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

POLYGON_TICKER_SEARCH = "https://api.polygon.io/v3/reference/tickers"
POLYGON_TICKER_DETAILS = "https://api.polygon.io/v3/reference/tickers/{ticker}"
# Daily aggregates (ms from/to, America/New_York session dates in response `t`).
POLYGON_AGGS_DAY = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{from_ms}/{to_ms}"
OPENFIGI_API_URL = "https://api.openfigi.com/v3/mapping"
# Name / keyword resolution (FIGI mapping jobs use idType/idValue; plain-name jobs are not accepted).
OPENFIGI_SEARCH_URL = "https://api.openfigi.com/v3/search"

YAHOO_HISTORY_PERIOD_FALLBACK = "5y"
YAHOO_REQUEST_TIMEOUT = 30


def price_cache_source() -> str:
    """Which SQLite bar cache the API reads: ``yahoo`` or ``polygon``."""
    v = (os.getenv("PRICE_CACHE_SOURCE") or "yahoo").strip().lower()
    return v if v in {"yahoo", "polygon"} else "yahoo"


def price_cache_parallel_workers() -> int:
    raw = (os.getenv("PRICE_CACHE_PARALLEL_WORKERS") or "4").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


try:
    from dotenv import load_dotenv

    # Repo-root `.env` (gitignored). Does not override variables already set in the environment.
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass
