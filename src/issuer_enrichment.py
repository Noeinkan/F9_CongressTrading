from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import requests

from .config import POLYGON_TICKER_DETAILS, USER_AGENT
from .utils import normalize_key, normalize_whitespace


SECTOR_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Technology", ("software", "semiconductor", "chip", "cloud", "cyber", "artificial intelligence", "technology", "data center")),
    ("Healthcare", ("health", "biotech", "pharma", "pharmaceutical", "medical", "therapeutic", "diagnostic")),
    ("Financials", ("bank", "capital", "financial", "insurance", "credit", "payment", "asset management")),
    ("Energy", ("energy", "oil", "gas", "solar", "uranium", "pipeline", "petroleum")),
    ("Industrials", ("aerospace", "defense", "industrial", "manufacturing", "transport", "rail", "construction")),
    ("Communication Services", ("telecom", "communication", "media", "advertising", "streaming", "wireless")),
    ("Consumer Discretionary", ("retail", "apparel", "automotive", "e commerce", "consumer discretionary", "restaurant", "travel")),
    ("Consumer Staples", ("beverage", "food", "household", "consumer staples", "grocery", "tobacco")),
    ("Utilities", ("utility", "electric", "water", "power")),
    ("Real Estate", ("reit", "real estate", "property", "mortgage")),
    ("Materials", ("mining", "chemical", "materials", "steel", "copper", "lithium")),
]


def _classify_sector(text: str) -> str:
    normalized = normalize_key(text)
    for sector, keywords in SECTOR_RULES:
        if any(keyword in normalized for keyword in keywords):
            return sector
    return ""


def infer_sector_industry(asset_name: str, issuer_name: str, asset_type: str, raw_industry: str | None = None) -> tuple[str, str]:
    industry = normalize_whitespace(raw_industry or "")
    combined_text = normalize_whitespace(" ".join(part for part in (industry, issuer_name, asset_name) if part))
    sector = _classify_sector(combined_text)

    if asset_type == "etf":
        industry = industry or "Exchange Traded Fund"
        sector = sector or "Funds"
    elif asset_type == "mutual_fund":
        industry = industry or "Mutual Fund"
        sector = sector or "Funds"
    elif asset_type == "bond":
        industry = industry or "Fixed Income"
        sector = sector or "Fixed Income"
    elif asset_type == "option":
        industry = industry or "Listed Option"
        sector = sector or _classify_sector(normalize_whitespace(f"{issuer_name} {asset_name}")) or "Derivatives"
    else:
        industry = industry or ""
        sector = sector or "Unknown"

    return sector, industry


@lru_cache(maxsize=2048)
def _fetch_polygon_ticker_details_cached(ticker: str, api_key: str) -> dict[str, Any] | None:
    headers = {"User-Agent": USER_AGENT}
    url = POLYGON_TICKER_DETAILS.format(ticker=quote(ticker, safe=""))
    resp = requests.get(url, params={"apiKey": api_key}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("results")
    return result if isinstance(result, dict) else None


def fetch_polygon_ticker_details(ticker: str | None) -> dict[str, Any] | None:
    if not ticker:
        return None
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        return None
    try:
        return _fetch_polygon_ticker_details_cached(ticker, api_key)
    except requests.RequestException:
        return None


def enrich_issuer_metadata(asset_name: str, ticker: str | None, asset_type: str) -> dict[str, str]:
    details = fetch_polygon_ticker_details(ticker)
    polygon_name = normalize_whitespace((details or {}).get("name") or "")
    sic_description = normalize_whitespace((details or {}).get("sic_description") or "")

    issuer_name = polygon_name or normalize_whitespace(asset_name)
    sector, industry = infer_sector_industry(
        asset_name=asset_name,
        issuer_name=issuer_name,
        asset_type=asset_type,
        raw_industry=sic_description,
    )

    return {
        "issuer_name": issuer_name,
        "sector": sector,
        "industry": industry,
    }