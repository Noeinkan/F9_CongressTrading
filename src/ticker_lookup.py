from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests
from rapidfuzz import fuzz

from .config import OPENFIGI_API_URL, POLYGON_TICKER_SEARCH, USER_AGENT
from .db import get_asset_resolution, upsert_asset_resolution
from .issuer_enrichment import enrich_issuer_metadata
from .utils import normalize_key, normalize_whitespace


@dataclass
class RateLimiter:
    min_interval: float
    last_call: float = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


@dataclass
class AssetMatch:
    asset_name_normalized: str
    issuer_name: str
    ticker: str | None
    cusip_or_figi: str | None
    confidence_score: float
    match_source: str
    resolution_status: str


def _canonical_company_key(text: str | None) -> str:
    key = normalize_key(text)
    key = re.sub(
        r"\b(class [a-z]|cl [a-z]|common stock|common shares?|ordinary shares?|adr|ads)\b",
        " ",
        key,
    )
    key = re.sub(
        r"\b(incorporated|inc|corp|corporation|company|co|plc|ltd|limited|sa|nv|the)\b",
        " ",
        key,
    )
    return normalize_whitespace(key)


def _match_score(asset: str, candidate: str) -> float:
    asset_name = normalize_whitespace(asset).casefold()
    candidate_name = normalize_whitespace(candidate).casefold()
    asset_key = _canonical_company_key(asset)
    candidate_key = _canonical_company_key(candidate)
    return max(
        fuzz.ratio(asset_name, candidate_name),
        fuzz.token_sort_ratio(asset_name, candidate_name),
        fuzz.token_set_ratio(asset_key, candidate_key),
    )


def _is_exact_match(asset: str, candidate: str) -> bool:
    asset_key = normalize_key(asset)
    candidate_key = normalize_key(candidate)
    if asset_key and asset_key == candidate_key:
        return True
    canonical_asset = _canonical_company_key(asset)
    canonical_candidate = _canonical_company_key(candidate)
    return bool(canonical_asset and canonical_asset == canonical_candidate)


def _infer_resolution_status(ticker: str | None, confidence: float, status: str | None) -> str:
    if status in {"exact_match", "fuzzy_match", "manual_review"}:
        return status
    if ticker and confidence >= 0.98:
        return "exact_match"
    if ticker:
        return "fuzzy_match"
    return "manual_review"


def _manual_review_match(asset: str, match_source: str) -> AssetMatch:
    return AssetMatch(
        asset_name_normalized=asset,
        issuer_name=asset,
        ticker=None,
        cusip_or_figi=None,
        confidence_score=0.0,
        match_source=match_source,
        resolution_status="manual_review",
    )


def polygon_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
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
    best_match: AssetMatch | None = None
    best_score = 0.0
    for item in results:
        name = normalize_whitespace(item.get("name") or "")
        ticker = normalize_whitespace(item.get("ticker") or "") or None
        if not name or not ticker:
            continue
        if _is_exact_match(asset, name):
            return AssetMatch(
                asset_name_normalized=name,
                issuer_name=name,
                ticker=ticker,
                cusip_or_figi=item.get("composite_figi") or None,
                confidence_score=1.0,
                match_source="polygon_exact",
                resolution_status="exact_match",
            )
        score = _match_score(asset, name)
        if score >= 88.0 and score > best_score:
            best_score = score
            best_match = AssetMatch(
                asset_name_normalized=name,
                issuer_name=name,
                ticker=ticker,
                cusip_or_figi=item.get("composite_figi") or None,
                confidence_score=round(score / 100.0, 3),
                match_source="polygon_fuzzy",
                resolution_status="fuzzy_match",
            )
    return best_match


def openfigi_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
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
    best_match: AssetMatch | None = None
    best_score = 0.0
    for item in results:
        ticker = normalize_whitespace(item.get("ticker") or "") or None
        if not ticker:
            continue
        name = normalize_whitespace(
            item.get("name")
            or item.get("securityDescription")
            or item.get("securityDescription2")
            or ""
        )
        if name and _is_exact_match(asset, name):
            return AssetMatch(
                asset_name_normalized=name,
                issuer_name=name,
                ticker=ticker,
                cusip_or_figi=item.get("figi") or None,
                confidence_score=0.99,
                match_source="openfigi_exact",
                resolution_status="exact_match",
            )
        score = _match_score(asset, name or ticker)
        if score >= 85.0 and score > best_score:
            best_score = score
            best_match = AssetMatch(
                asset_name_normalized=name or asset,
                issuer_name=name or asset,
                ticker=ticker,
                cusip_or_figi=item.get("figi") or None,
                confidence_score=round(max(score, 85.0) / 100.0, 3),
                match_source="openfigi_fuzzy",
                resolution_status="fuzzy_match",
            )
    return best_match


def infer_asset_type(asset: str, ticker: str | None) -> str:
    asset_key = normalize_key(asset)
    if re.search(r"\b(call|put|option|options)\b", asset_key):
        return "option"
    if any(keyword in asset_key for keyword in ("etf", "ishares", "spdr", "invesco", "vanguard", "index fund")):
        return "etf"
    if "fund" in asset_key or "portfolio" in asset_key:
        return "mutual_fund"
    if "bond" in asset_key or "note" in asset_key:
        return "bond"
    if ticker:
        return "equity"
    return "unknown"


def resolve_asset(conn, asset: str) -> dict[str, Any]:
    asset_norm = normalize_whitespace(asset)
    if not asset_norm:
        empty_match = _manual_review_match("", "empty")
        return {
            "asset_name_raw": "",
            "asset_name_normalized": empty_match.asset_name_normalized,
            "issuer_name": empty_match.issuer_name,
            "ticker": empty_match.ticker,
            "cusip_or_figi": empty_match.cusip_or_figi,
            "asset_type": "unknown",
            "sector": "",
            "industry": "",
            "confidence_score": empty_match.confidence_score,
            "match_source": empty_match.match_source,
            "review_status": empty_match.resolution_status,
        }

    cached = get_asset_resolution(conn, asset_norm)
    if cached is not None:
        ticker = cached["ticker"] or None
        confidence = float(cached["confidence_score"] or 0.0)
        review_status = _infer_resolution_status(ticker, confidence, cached["resolution_status"])
        return {
            "asset_name_raw": asset_norm,
            "asset_name_normalized": cached["asset_name_normalized"] or asset_norm,
            "issuer_name": cached["issuer_name"] or asset_norm,
            "ticker": ticker,
            "cusip_or_figi": cached["cusip_or_figi"] or None,
            "asset_type": cached["asset_type"] or infer_asset_type(asset_norm, ticker),
            "sector": cached["sector"] or "",
            "industry": cached["industry"] or "",
            "confidence_score": confidence,
            "match_source": cached["match_source"] or "cache",
            "review_status": review_status,
        }

    polygon_key = os.getenv("POLYGON_API_KEY")
    openfigi_key = os.getenv("OPENFIGI_API_KEY")

    matched_asset: AssetMatch = _manual_review_match(asset_norm, "none")

    if polygon_key:
        polygon_match = polygon_lookup(asset_norm, polygon_key, RateLimiter(0.3))
        if polygon_match is not None:
            matched_asset = polygon_match

    if matched_asset.ticker is None and openfigi_key:
        openfigi_match = openfigi_lookup(asset_norm, openfigi_key, RateLimiter(0.5))
        if openfigi_match is not None:
            matched_asset = openfigi_match

    asset_type = infer_asset_type(matched_asset.asset_name_normalized, matched_asset.ticker)
    issuer_metadata = enrich_issuer_metadata(
        matched_asset.issuer_name,
        matched_asset.ticker,
        asset_type,
    )
    issuer_name = issuer_metadata.get("issuer_name") or matched_asset.issuer_name or asset_norm

    upsert_asset_resolution(
        conn,
        asset_name_raw=asset_norm,
        asset_name_normalized=matched_asset.asset_name_normalized,
        issuer_name=issuer_name,
        ticker=matched_asset.ticker,
        cusip_or_figi=matched_asset.cusip_or_figi,
        asset_type=asset_type,
        sector=issuer_metadata.get("sector"),
        industry=issuer_metadata.get("industry"),
        confidence_score=matched_asset.confidence_score,
        resolution_status=matched_asset.resolution_status,
        match_source=matched_asset.match_source,
    )

    return {
        "asset_name_raw": asset_norm,
        "asset_name_normalized": matched_asset.asset_name_normalized,
        "issuer_name": issuer_name,
        "ticker": matched_asset.ticker,
        "cusip_or_figi": matched_asset.cusip_or_figi,
        "asset_type": asset_type,
        "sector": issuer_metadata.get("sector") or "",
        "industry": issuer_metadata.get("industry") or "",
        "confidence_score": matched_asset.confidence_score,
        "match_source": matched_asset.match_source,
        "review_status": matched_asset.resolution_status,
    }


def lookup_ticker(conn, asset: str) -> Optional[str]:
    return resolve_asset(conn, asset).get("ticker")
