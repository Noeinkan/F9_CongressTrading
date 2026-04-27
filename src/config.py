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


def house_ingest_skip_external_asset_lookup() -> bool:
    """
    Se true, durante l'ingest non vengono chiamati Polygon/OpenFIGI per asset non in cache
    (solo manual_review locale, molto piu veloce su migliaia di righe). Utile per completare
    prima il caricamento PDF/DB; poi si possono raffinare i ticker in un secondo passaggio.
    """
    v = (os.getenv("HOUSE_INGEST_SKIP_EXTERNAL_ASSET_LOOKUP") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}

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
OPENFIGI_API_URL = "https://api.openfigi.com/v3/mapping"
