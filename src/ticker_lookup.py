from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import requests
from rapidfuzz import fuzz
from requests import Response
from requests.exceptions import RequestException

from .config import OPENFIGI_API_URL, POLYGON_TICKER_SEARCH, USER_AGENT, house_ingest_skip_external_asset_lookup
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

    def backoff(self, delay_seconds: float) -> None:
        delay = max(delay_seconds, self.min_interval)
        self.last_call = time.time() + delay - self.min_interval


@dataclass
class AssetMatch:
    asset_name_normalized: str
    issuer_name: str
    ticker: str | None
    cusip_or_figi: str | None
    confidence_score: float
    match_source: str
    resolution_status: str


DEFAULT_POLYGON_MIN_INTERVAL = float(os.getenv("POLYGON_MIN_INTERVAL_SECONDS", "0.28"))
# OpenFIGI docs: with API key, ~25 mapping requests / 6s; ~0.24s spacing is safe headroom.
DEFAULT_OPENFIGI_MIN_INTERVAL = float(os.getenv("OPENFIGI_MIN_INTERVAL_SECONDS", "0.28"))
OPENFIGI_BATCH_SIZE = max(1, min(100, int(os.getenv("OPENFIGI_BATCH_SIZE", "100"))))
DEFAULT_RATE_LIMIT_BACKOFF = float(os.getenv("LOOKUP_RATE_LIMIT_BACKOFF_SECONDS", "60"))
MAX_RATE_LIMIT_RETRY_AFTER = float(os.getenv("LOOKUP_MAX_RATE_LIMIT_RETRY_AFTER_SECONDS", "5"))

POLYGON_LIMITER = RateLimiter(DEFAULT_POLYGON_MIN_INTERVAL)
OPENFIGI_LIMITER = RateLimiter(DEFAULT_OPENFIGI_MIN_INTERVAL)

# House/Senate PTR descriptions often end with "(TICKER) [ST]" or "(BRK.B) [OP]".
_PAREN_TICKER_RE = re.compile(
    r"\(((?:[A-Z]{1,5}\.[A-Z])|[A-Z]{1,6})\)",
    re.IGNORECASE,
)
_PAREN_TICKER_DENYLIST = frozenset(
    {
        "NYSE",
        "NASDAQ",
        "AMEX",
        "ARCA",
        "OTC",
        "ADR",
        "ADS",
        "ETF",
        "THE",
        "CLASS",
        "COMMON",
        "STOCK",
        "SHARE",
        "SHARES",
    }
)


def _extract_ticker_from_parentheses(asset: str) -> str | None:
    """Return a US-style ticker read from the last parenthetical in disclosure text."""
    if not asset or "(" not in asset:
        return None
    last: str | None = None
    for m in _PAREN_TICKER_RE.finditer(asset):
        sym = m.group(1).upper()
        if sym in _PAREN_TICKER_DENYLIST:
            continue
        if len(sym) > 6:
            continue
        last = sym
    return last


def _strip_trailing_disclosure_ticker(asset: str, ticker: str) -> str:
    tail = re.compile(
        rf"\(\s*{re.escape(ticker)}\s*\)\s*(?:\[[^\]]+\])?\s*$",
        re.IGNORECASE,
    )
    stripped = tail.sub("", asset)
    return normalize_whitespace(stripped) or normalize_whitespace(asset)


def _try_disclosure_parenthetical_match(asset_norm: str) -> AssetMatch | None:
    ticker = _extract_ticker_from_parentheses(asset_norm)
    if not ticker:
        return None
    display_name = _strip_trailing_disclosure_ticker(asset_norm, ticker)
    return AssetMatch(
        asset_name_normalized=display_name,
        issuer_name=display_name,
        ticker=ticker,
        cusip_or_figi=None,
        confidence_score=0.99,
        match_source="disclosure_paren",
        resolution_status="exact_match",
    )


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


def _parse_retry_after(response: Response | None, default_seconds: float) -> float:
    if response is None:
        return default_seconds
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return default_seconds
    try:
        return max(float(retry_after), 0.0)
    except ValueError:
        return default_seconds


def _request_with_rate_limit(
    method: str,
    url: str,
    *,
    limiter: RateLimiter,
    retry_after_cap: float = MAX_RATE_LIMIT_RETRY_AFTER,
    backoff_seconds: float = DEFAULT_RATE_LIMIT_BACKOFF,
    **request_kwargs: Any,
) -> Response | None:
    limiter.wait()
    try:
        response = requests.request(method, url, **request_kwargs)
    except RequestException:
        return None

    if response.status_code == 429:
        retry_after = _parse_retry_after(response, backoff_seconds)
        if retry_after <= retry_after_cap:
            limiter.backoff(retry_after)
            limiter.wait()
            try:
                response = requests.request(method, url, **request_kwargs)
            except RequestException:
                return None
        else:
            # Do not push last_call minutes into the future when we skip the retry
            # (that would freeze the next many lookups on this limiter).
            limiter.backoff(limiter.min_interval)
            return None

    try:
        response.raise_for_status()
    except RequestException:
        return None
    return response


def polygon_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
    params = {
        "search": asset,
        "market": "stocks",
        "active": "true",
        "limit": 10,
        "apiKey": api_key,
    }
    headers = {"User-Agent": USER_AGENT}
    resp = _request_with_rate_limit(
        "GET",
        POLYGON_TICKER_SEARCH,
        limiter=limiter,
        params=params,
        headers=headers,
        timeout=30,
    )
    if resp is None:
        return None
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


def _best_openfigi_match(asset: str, results: list[Any]) -> Optional[AssetMatch]:
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


def openfigi_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
    headers = {
        "Content-Type": "application/json",
        "X-OPENFIGI-APIKEY": api_key,
        "User-Agent": USER_AGENT,
    }
    payload = [{"name": asset, "exchCode": "US", "securityType2": "Common Stock"}]
    resp = _request_with_rate_limit(
        "POST",
        OPENFIGI_API_URL,
        limiter=limiter,
        headers=headers,
        json=payload,
        timeout=30,
    )
    if resp is None:
        return None
    data = resp.json()
    if not data:
        return None
    results = data[0].get("data", [])
    return _best_openfigi_match(asset, results)


def openfigi_lookup_batch(assets: list[str], api_key: str, limiter: RateLimiter) -> dict[str, Optional[AssetMatch]]:
    """Up to 100 name-mapping jobs per HTTP request (OpenFIGI authenticated limit)."""
    out: dict[str, Optional[AssetMatch]] = {a: None for a in assets}
    if not assets:
        return out
    headers = {
        "Content-Type": "application/json",
        "X-OPENFIGI-APIKEY": api_key,
        "User-Agent": USER_AGENT,
    }
    for start in range(0, len(assets), OPENFIGI_BATCH_SIZE):
        chunk = assets[start : start + OPENFIGI_BATCH_SIZE]
        payload = [{"name": a, "exchCode": "US", "securityType2": "Common Stock"} for a in chunk]
        timeout = min(120, 25 + 5 * len(chunk))
        resp = _request_with_rate_limit(
            "POST",
            OPENFIGI_API_URL,
            limiter=limiter,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        if resp is None:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        if not isinstance(data, list):
            continue
        for j, asset in enumerate(chunk):
            if j >= len(data):
                break
            block = data[j]
            if not isinstance(block, dict):
                continue
            rows = block.get("data") or []
            out[asset] = _best_openfigi_match(asset, rows)
    return out


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


def _resolution_dict_from_cached_row(asset_norm: str, cached: Any) -> dict[str, Any]:
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


def _finalize_resolution_from_match(
    conn,
    asset_norm: str,
    matched: AssetMatch,
    *,
    issuer_enrich_hint: str | None = None,
) -> dict[str, Any]:
    asset_type = infer_asset_type(matched.asset_name_normalized, matched.ticker)
    enrich_src = issuer_enrich_hint if issuer_enrich_hint is not None else (matched.issuer_name or asset_norm)
    issuer_metadata = enrich_issuer_metadata(
        enrich_src,
        matched.ticker,
        asset_type,
    )
    issuer_name = issuer_metadata.get("issuer_name") or matched.issuer_name or asset_norm
    upsert_asset_resolution(
        conn,
        asset_name_raw=asset_norm,
        asset_name_normalized=matched.asset_name_normalized,
        issuer_name=issuer_name,
        ticker=matched.ticker,
        cusip_or_figi=matched.cusip_or_figi,
        asset_type=asset_type,
        sector=issuer_metadata.get("sector"),
        industry=issuer_metadata.get("industry"),
        confidence_score=matched.confidence_score,
        resolution_status=matched.resolution_status,
        match_source=matched.match_source,
    )
    return {
        "asset_name_raw": asset_norm,
        "asset_name_normalized": matched.asset_name_normalized,
        "issuer_name": issuer_name,
        "ticker": matched.ticker,
        "cusip_or_figi": matched.cusip_or_figi,
        "asset_type": asset_type,
        "sector": issuer_metadata.get("sector") or "",
        "industry": issuer_metadata.get("industry") or "",
        "confidence_score": matched.confidence_score,
        "match_source": matched.match_source,
        "review_status": matched.resolution_status,
    }


def bulk_resolve_unique_assets_for_reconcile(conn, assets_unique: Sequence[str]) -> dict[str, dict[str, Any]]:
    """
    Resolve each distinct asset string once, using batched OpenFIGI name lookups (up to 100 per HTTP call).
    Intended for `re-resolve-tickers`; same DB/cache outcome as sequential resolve_asset for these paths.
    """
    out: dict[str, dict[str, Any]] = {}
    ordered = [normalize_whitespace(x) for x in dict.fromkeys(assets_unique)]
    ordered = [a for a in ordered if a]

    polygon_key = os.getenv("POLYGON_API_KEY") if not house_ingest_skip_external_asset_lookup() else None
    openfigi_key = os.getenv("OPENFIGI_API_KEY") if not house_ingest_skip_external_asset_lookup() else None

    need_openfigi_batch: list[str] = []

    for an in ordered:
        if cached := get_asset_resolution(conn, an):
            out[an] = _resolution_dict_from_cached_row(an, cached)
            continue
        if paren := _try_disclosure_parenthetical_match(an):
            out[an] = _finalize_resolution_from_match(conn, an, paren, issuer_enrich_hint=an)
            continue
        if house_ingest_skip_external_asset_lookup():
            out[an] = _finalize_resolution_from_match(
                conn, an, _manual_review_match(an, "skipped_external_lookup")
            )
            continue

        matched: AssetMatch = _manual_review_match(an, "none")
        if polygon_key:
            hit = polygon_lookup(an, polygon_key, POLYGON_LIMITER)
            if hit is not None:
                matched = hit
        if matched.ticker is not None:
            out[an] = _finalize_resolution_from_match(conn, an, matched)
        elif openfigi_key:
            need_openfigi_batch.append(an)
        else:
            out[an] = _finalize_resolution_from_match(conn, an, matched)

    if need_openfigi_batch and openfigi_key:
        batch = openfigi_lookup_batch(need_openfigi_batch, openfigi_key, OPENFIGI_LIMITER)
        for an in need_openfigi_batch:
            om = batch.get(an)
            final_m = om if om is not None else _manual_review_match(an, "none")
            out[an] = _finalize_resolution_from_match(conn, an, final_m)

    return out


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

    if paren_match := _try_disclosure_parenthetical_match(asset_norm):
        return _finalize_resolution_from_match(conn, asset_norm, paren_match, issuer_enrich_hint=asset_norm)

    if cached := get_asset_resolution(conn, asset_norm):
        return _resolution_dict_from_cached_row(asset_norm, cached)

    polygon_key = os.getenv("POLYGON_API_KEY")
    openfigi_key = os.getenv("OPENFIGI_API_KEY")

    matched_asset: AssetMatch = _manual_review_match(asset_norm, "none")

    if not house_ingest_skip_external_asset_lookup():
        if polygon_key:
            polygon_match = polygon_lookup(asset_norm, polygon_key, POLYGON_LIMITER)
            if polygon_match is not None:
                matched_asset = polygon_match

        if matched_asset.ticker is None and openfigi_key:
            openfigi_match = openfigi_lookup(asset_norm, openfigi_key, OPENFIGI_LIMITER)
            if openfigi_match is not None:
                matched_asset = openfigi_match
    else:
        matched_asset = _manual_review_match(asset_norm, "skipped_external_lookup")

    return _finalize_resolution_from_match(conn, asset_norm, matched_asset)


def lookup_ticker(conn, asset: str) -> Optional[str]:
    return resolve_asset(conn, asset).get("ticker")
