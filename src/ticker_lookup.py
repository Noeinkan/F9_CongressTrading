from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import requests
from rapidfuzz import fuzz

from .config import OPENFIGI_API_URL, POLYGON_TICKER_SEARCH, USER_AGENT
from .db import get_ticker_cache, upsert_ticker_cache
from .utils import normalize_whitespace


@dataclass
class RateLimiter:
    min_interval: float
    last_call: float = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


def polygon_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[str]:
    limiter.wait()
    params = {
        "search": asset,
        "market": "stocks",
        "active": "true",
        "limit": 10,
        "apiKey": api_key,
    }
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(POLYGON_TICKER_SEARCH, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        return None
    asset_norm = normalize_whitespace(asset).lower()
    best = None
    best_score = 0
    for item in results:
        name = normalize_whitespace(item.get("name") or "").lower()
        ticker = item.get("ticker")
        if not ticker:
            continue
        score = fuzz.partial_ratio(asset_norm, name)
        if score > best_score:
            best = ticker
            best_score = score
    return best


def openfigi_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[str]:
    limiter.wait()
    headers = {
        "Content-Type": "application/json",
        "X-OPENFIGI-APIKEY": api_key,
        "User-Agent": USER_AGENT,
    }
    payload = [{"name": asset, "exchCode": "US", "securityType2": "Common Stock"}]
    resp = requests.post(OPENFIGI_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    results = data[0].get("data", [])
    if not results:
        return None
    return results[0].get("ticker")


def lookup_ticker(conn, asset: str) -> Optional[str]:
    asset_norm = normalize_whitespace(asset)
    if not asset_norm:
        return None

    cached = get_ticker_cache(conn, asset_norm)
    if cached is not None:
        return cached

    polygon_key = os.getenv("POLYGON_API_KEY")
    openfigi_key = os.getenv("OPENFIGI_API_KEY")

    ticker = None
    source = None

    if polygon_key:
        ticker = polygon_lookup(asset_norm, polygon_key, RateLimiter(0.3))
        if ticker:
            source = "polygon"

    if ticker is None and openfigi_key:
        ticker = openfigi_lookup(asset_norm, openfigi_key, RateLimiter(0.5))
        if ticker:
            source = "openfigi"

    if source is None:
        source = "none"

    upsert_ticker_cache(conn, asset_norm, ticker, source)
    return ticker
