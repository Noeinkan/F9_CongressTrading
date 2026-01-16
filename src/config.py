from __future__ import annotations

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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

HOUSE_DISCLOSURE_URL = "https://disclosures-clerk.house.gov/PublicDisclosure/FinancialDisclosure"

POLYGON_TICKER_SEARCH = "https://api.polygon.io/v3/reference/tickers"
OPENFIGI_API_URL = "https://api.openfigi.com/v3/mapping"
