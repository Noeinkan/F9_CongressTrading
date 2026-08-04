"""Local SEC company_tickers.json name → ticker resolution (no API key).

Downloads https://www.sec.gov/files/company_tickers.json into data/cache/
with a TTL, then exact/fuzzy matches normalized company titles.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from rapidfuzz import fuzz, process as rf_process

from .config import CACHE_DIR
from .utils import normalize_key, normalize_whitespace

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_TICKERS_CACHE_PATH = CACHE_DIR / "sec_company_tickers.json"
SEC_COMPANY_TICKERS_TTL_SECONDS = float(
    os.getenv("SEC_COMPANY_TICKERS_TTL_SECONDS", str(7 * 24 * 3600))
)
SEC_FUZZY_MIN_SCORE = float(os.getenv("SEC_COMPANY_TICKERS_FUZZY_MIN_SCORE", "90"))

# SEC asks for a descriptive User-Agent identifying the requester (include contact).
SEC_USER_AGENT = (
    os.getenv("SEC_USER_AGENT")
    or "CongressTrading/1.0 (local research; contact@example.com)"
)


@dataclass(frozen=True)
class SecTickerMatch:
    ticker: str
    title: str
    score: float
    exact: bool


_INDEX: dict[str, str] | None = None  # normalized title → ticker
_TITLES: list[str] | None = None
_TITLE_KEYS: list[str] | None = None
_LOADED_PATH: Path | None = None


def _sec_headers() -> dict[str, str]:
    return {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _cache_is_fresh(path: Path) -> bool:
    if not path.is_file():
        return False
    age = time.time() - path.stat().st_mtime
    return age <= SEC_COMPANY_TICKERS_TTL_SECONDS


def download_sec_company_tickers(
    *,
    cache_path: Path | None = None,
    force: bool = False,
) -> Path:
    """Ensure a local copy of company_tickers.json exists; return its path."""
    path = cache_path or SEC_COMPANY_TICKERS_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force and _cache_is_fresh(path):
        return path

    resp = requests.get(
        SEC_COMPANY_TICKERS_URL,
        headers=_sec_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("SEC company_tickers.json: expected object")
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _parse_tickers_payload(data: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in data.values():
        if not isinstance(row, dict):
            continue
        ticker = normalize_whitespace(str(row.get("ticker") or "")).upper()
        title = normalize_whitespace(str(row.get("title") or ""))
        if not ticker or not title:
            continue
        key = normalize_key(title)
        if key and key not in index:
            index[key] = ticker
    return index


def load_sec_company_tickers_index(
    *,
    cache_path: Path | None = None,
    allow_download: bool = True,
) -> dict[str, str]:
    """Return normalized-title → ticker map (process-cached)."""
    global _INDEX, _TITLES, _TITLE_KEYS, _LOADED_PATH
    path = cache_path or SEC_COMPANY_TICKERS_CACHE_PATH
    if _INDEX is not None and _LOADED_PATH == path:
        return _INDEX

    if allow_download:
        try:
            path = download_sec_company_tickers(cache_path=path)
        except (OSError, requests.RequestException, ValueError, json.JSONDecodeError):
            if not path.is_file():
                _INDEX = {}
                _TITLES = []
                _TITLE_KEYS = []
                _LOADED_PATH = path
                return _INDEX

    if not path.is_file():
        _INDEX = {}
        _TITLES = []
        _TITLE_KEYS = []
        _LOADED_PATH = path
        return _INDEX

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        _INDEX = {}
        _TITLES = []
        _TITLE_KEYS = []
        _LOADED_PATH = path
        return _INDEX

    index = _parse_tickers_payload(data)
    _INDEX = index
    _TITLE_KEYS = list(index.keys())
    # Reconstruct a display title from the key is lossy; keep keys for fuzzy only.
    _TITLES = _TITLE_KEYS
    _LOADED_PATH = path
    return _INDEX


def reset_sec_company_tickers_cache() -> None:
    """Clear process-level index (tests)."""
    global _INDEX, _TITLES, _TITLE_KEYS, _LOADED_PATH
    _INDEX = None
    _TITLES = None
    _TITLE_KEYS = None
    _LOADED_PATH = None


def build_sec_index_from_payload(data: dict[str, Any]) -> dict[str, str]:
    """Test helper: parse a fixture payload without touching disk/network."""
    return _parse_tickers_payload(data)


def match_sec_company_ticker(
    name: str,
    *,
    index: dict[str, str] | None = None,
    fuzzy_min_score: float | None = None,
) -> SecTickerMatch | None:
    """Exact then fuzzy match a company name against the SEC title index."""
    cleaned = normalize_whitespace(name)
    if not cleaned:
        return None
    idx = index if index is not None else load_sec_company_tickers_index()
    if not idx:
        return None

    key = normalize_key(cleaned)
    if key and key in idx:
        return SecTickerMatch(ticker=idx[key], title=cleaned, score=100.0, exact=True)

    cutoff = float(SEC_FUZZY_MIN_SCORE if fuzzy_min_score is None else fuzzy_min_score)
    keys = list(idx.keys())
    if not keys:
        return None

    # Prefer token_set_ratio on normalized keys (handles word reorder / Inc vs Corp).
    result = rf_process.extractOne(
        key,
        keys,
        scorer=fuzz.WRatio,
        score_cutoff=cutoff,
    )
    if result is None:
        return None

    matched_key, score, _ = result
    return SecTickerMatch(
        ticker=idx[matched_key],
        title=matched_key,
        score=float(score),
        exact=False,
    )