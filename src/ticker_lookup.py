from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import requests
from rapidfuzz import fuzz
from requests import Response
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException

from .config import (
    OPENFIGI_API_URL,
    OPENFIGI_SEARCH_URL,
    POLYGON_TICKER_SEARCH,
    USER_AGENT,
    house_ingest_skip_external_asset_lookup,
)
from .db import get_asset_resolution, upsert_asset_resolution
from .issuer_enrichment import enrich_issuer_metadata
from .sec_company_tickers import match_sec_company_ticker
from .utils import normalize_key, normalize_whitespace


@dataclass
class RateLimiter:
    min_interval: float
    last_call: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def wait(self) -> None:
        with self._lock:
            elapsed = time.time() - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()

    def backoff(self, delay_seconds: float) -> None:
        with self._lock:
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
DEFAULT_YAHOO_MIN_INTERVAL = float(os.getenv("YAHOO_MIN_INTERVAL_SECONDS", "0.30"))
# OpenFIGI docs: with API key, ~25 mapping requests / 6s; ~0.24s spacing is safe headroom.
DEFAULT_OPENFIGI_MIN_INTERVAL = float(os.getenv("OPENFIGI_MIN_INTERVAL_SECONDS", "0.28"))
DEFAULT_RATE_LIMIT_BACKOFF = float(os.getenv("LOOKUP_RATE_LIMIT_BACKOFF_SECONDS", "60"))
MAX_RATE_LIMIT_RETRY_AFTER = float(os.getenv("LOOKUP_MAX_RATE_LIMIT_RETRY_AFTER_SECONDS", "5"))

POLYGON_LIMITER = RateLimiter(DEFAULT_POLYGON_MIN_INTERVAL)
YAHOO_LIMITER = RateLimiter(DEFAULT_YAHOO_MIN_INTERVAL)
OPENFIGI_LIMITER = RateLimiter(DEFAULT_OPENFIGI_MIN_INTERVAL)


def _build_session() -> requests.Session:
    """Shared session so the thousands of lookup requests reuse keep-alive connections
    instead of paying a fresh TCP/TLS handshake every call."""
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_SESSION = _build_session()

# Disclosure text often includes suffixes that hurt name search; thresholds tuned for PTR noise.
POLYGON_FUZZY_MIN_SCORE = float(os.getenv("POLYGON_FUZZY_MIN_SCORE", "82"))
OPENFIGI_FUZZY_MIN_SCORE = float(os.getenv("OPENFIGI_FUZZY_MIN_SCORE", "78"))

# When the simplified name differs from the raw asset, Polygon is queried with both by default.
# Set POLYGON_SEARCH_RAW_FALLBACK=0 to query only the simplified name (~half the Polygon calls).
POLYGON_SEARCH_RAW_FALLBACK = (
    (os.getenv("POLYGON_SEARCH_RAW_FALLBACK") or "1").strip().lower() in {"1", "true", "yes", "on"}
)

# If set to 1, OpenFIGI name mapping adds securityType2=Common Stock (narrower; can miss ADRs).
OPENFIGI_NAME_STRICT_COMMON_STOCK = (
    (os.getenv("OPENFIGI_NAME_STRICT_COMMON_STOCK") or "").strip().lower() in {"1", "true", "yes", "on"}
)

# Empty-ticker cache rows with these sources are re-tried so improved heuristics/SEC can fill in.
_MATCH_SOURCES_RETRY_EMPTY_TICKER = frozenset(
    {"none", "skipped_external_lookup", "generic_asset_name"}
)

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
        # House PTR transaction-type codes that sometimes leak into asset text as "(P)".
        "P",
        "S",
        "E",
    }
)

# Congresswatch-style exchange-prefixed tickers: "NYSE: AAPL", "NASDAQ:MSFT".
_EXCHANGE_TICKER_RE = re.compile(
    r"\b(?:NYSEARCA|NASDAQ|NYSE|BATS|AMEX|OTC)\s*:\s*"
    r"((?:[A-Z]{1,5}\.[A-Z])|[A-Z]{1,6})\b",
    re.IGNORECASE,
)

# Senate eFD raw lines: "2000070841 SP NextEra Energy, Inc. (NEE) [ST]"
# or owner-code prefix without doc ID: "JT Microsoft Corporation - Common"
_SENATE_DOC_PREFIX_RE = re.compile(r"^\d{7,12}\s+")
_OWNER_CODE_PREFIX_RE = re.compile(r"^(?:SP|JT|DC|CH|SC|SF)\s+", re.IGNORECASE)
_BARE_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")
_GENERIC_EQUITY_NAME_RE = re.compile(
    r"^(?:"
    r"common(?:\s+stock)?|stock|shares?|equity|"
    r"ordinary(?:\s+shares?)?|"
    r"preferred(?:\s+stock)?|"
    r"adr|ads|depositary(?:\s+shares?)?|"
    r"class\s+[a-z]"
    r")$",
    re.IGNORECASE,
)

# Curated disclosure quirks → search/query aliases (tiny, test-driven).
_DISCLOSURE_NAME_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^Facebook(?:\s+Inc\.?)?$", re.I), "Meta Platforms"),
    (re.compile(r"^FB$", re.I), "Meta Platforms"),
    (re.compile(r"^Google(?:\s+Inc\.?)?$", re.I), "Alphabet"),
    # Truncated House lines often drop the leading "JP".
    (re.compile(r"^Morgan Chase(?:\s*&\s*Co\.?)?(?:\s+Common)?$", re.I), "JPMorgan Chase"),
    (re.compile(r"^Westinghouse Air Brake Technologies(?:\s+Corporation)?$", re.I), "Wabtec"),
    (re.compile(r"^Willis Towers Watson(?:\s+Public Limited(?:\s+Company)?)?$", re.I), "Willis Towers Watson"),
    # SEC title is now "SLB LIMITED / NV" after the corporate rename.
    (re.compile(r"^Schlumberger(?:\s+N\.?\s*V\.?)?(?:\s+Limited)?$", re.I), "SLB Limited"),
)


def _strip_senate_and_owner_prefix(asset: str) -> str:
    """Remove Senate eFD doc-ID prefix and owner-code prefix (SP/JT/DC/CH/SC/SF)."""
    s = _SENATE_DOC_PREFIX_RE.sub("", asset)
    s = _OWNER_CODE_PREFIX_RE.sub("", s)
    return normalize_whitespace(s) or asset


def _simplify_for_equity_search(asset: str) -> str:
    """Strip PTR boilerplate so Polygon/OpenFIGI/SEC name search matches issuer lines."""
    s = normalize_whitespace(asset)
    if not s:
        return ""
    s = _strip_senate_and_owner_prefix(s)
    s = re.sub(r"\s*\[[A-Z0-9]{2,4}\]\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*\([A-Z]{1,6}\)\s*$", "", s, flags=re.I)
    # Keep the post-structure form so we never restore raw "(P)" / "[PS]" junk when share-class
    # stripping removes the entire remaining string (e.g. asset text is only "Common stock (P)").
    structural = normalize_whitespace(s).strip(" ,")
    s = structural
    s = re.sub(r"\s*-?\s*Common Stock\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*-?\s*Preferred Stock\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*Common Shares?\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*-?\s*Ordinary Shares?\s*$", "", s, flags=re.I)
    s = re.sub(
        r"\s*-?\s*(?:Sponsored\s+)?(?:ADR|ADS|American\s+Depositary\s+Shares?|Depositary\s+Shares?)\s*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"\s*,?\s*Common$", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*Common$", "", s, flags=re.I)
    s = re.sub(r"\s*-?\s*Class\s+[A-Z]\b.*$", "", s, flags=re.I)
    s = re.sub(r"\s+Class\s+[A-Z]\s+Ordinary(?:\s+Shares?)?\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+Public Limited(?:\s+Company)?\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*-\s*$", "", s)
    s = normalize_whitespace(s).strip(" ,-")
    return s if s else structural


def _is_generic_equity_name(asset: str) -> bool:
    """True when disclosure text has no issuer left — only share-class / type boilerplate."""
    simplified = _simplify_for_equity_search(asset)
    if not simplified:
        return True
    return bool(_GENERIC_EQUITY_NAME_RE.fullmatch(simplified))


def _looks_like_bare_ticker(text: str) -> bool:
    sym = normalize_whitespace(text).upper()
    return bool(sym) and bool(_BARE_TICKER_RE.fullmatch(sym)) and sym not in _PAREN_TICKER_DENYLIST


def _extract_exchange_prefixed_ticker(asset: str) -> str | None:
    """Return ticker from ``NYSE: AAPL`` / ``NASDAQ:MSFT`` style disclosure text."""
    if not asset or ":" not in asset:
        return None
    last: str | None = None
    for m in _EXCHANGE_TICKER_RE.finditer(asset):
        sym = m.group(1).upper()
        if sym in _PAREN_TICKER_DENYLIST:
            continue
        last = sym
    return last


def _try_exchange_prefixed_ticker_match(asset_norm: str) -> AssetMatch | None:
    cleaned = _strip_senate_and_owner_prefix(asset_norm)
    ticker = _extract_exchange_prefixed_ticker(cleaned)
    if not ticker:
        return None
    display = re.sub(
        rf"\b(?:NYSEARCA|NASDAQ|NYSE|BATS|AMEX|OTC)\s*:\s*{re.escape(ticker)}\b",
        "",
        cleaned,
        flags=re.I,
    )
    display = _simplify_for_equity_search(display) or ticker
    return AssetMatch(
        asset_name_normalized=display,
        issuer_name=display,
        ticker=ticker,
        cusip_or_figi=None,
        confidence_score=0.99,
        match_source="disclosure_exchange_ticker",
        resolution_status="exact_match",
    )


def _try_bare_ticker_token_match(asset_norm: str) -> AssetMatch | None:
    """
    Disclosures like ``MSFT Common Stock [PS]`` simplify to a bare symbol. Treat that as an
    exact ticker (do not fuzzy-search — Polygon/OpenFIGI otherwise match leveraged ETFs).
    """
    simplified = _simplify_for_equity_search(asset_norm)
    if not _looks_like_bare_ticker(simplified):
        return None
    sym = simplified.upper()
    return AssetMatch(
        asset_name_normalized=sym,
        issuer_name=sym,
        ticker=sym,
        cusip_or_figi=None,
        confidence_score=0.98,
        match_source="disclosure_ticker_token",
        resolution_status="exact_match",
    )


def _apply_disclosure_aliases(name: str) -> list[str]:
    """Return alias expansions for known disclosure quirks (may be empty)."""
    cleaned = normalize_whitespace(name)
    if not cleaned:
        return []
    out: list[str] = []
    for pattern, alias in _DISCLOSURE_NAME_ALIASES:
        if pattern.fullmatch(cleaned):
            out.append(alias)
    return out


def _search_name_variants(name: str) -> list[str]:
    """Alternate vendor queries when disclosure spelling differs from index names."""
    out: list[str] = []

    def add(value: str) -> None:
        cleaned = normalize_whitespace(value)
        if cleaned and cleaned.casefold() not in {x.casefold() for x in out}:
            out.append(cleaned)

    add(name)
    for alias in _apply_disclosure_aliases(name):
        add(alias)
    # Polygon indexes "JPMorgan Chase"; disclosures often use "JP Morgan" / "J.P. Morgan".
    add(re.sub(r"\bJ\.?\s*P\.?\s*Morgan\b", "JPMorgan", name, flags=re.I))
    # Apostrophes (straight or curly) break some OpenFIGI/Polygon name searches (Lowe's).
    add(name.replace("\u2019", "'"))
    add(name.replace("\u2019", "").replace("'", ""))
    # Legacy "N.V." suffix (e.g. Schlumberger) often missing from modern vendor names.
    add(re.sub(r",?\s+N\.?\s*V\.?\s*$", "", name, flags=re.I))
    # Drop trailing corporate suffixes for SEC/title matching.
    stripped_corp = re.sub(
        r",?\s+(?:Inc\.?|Incorporated|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|Limited|PLC|LLC)\s*$",
        "",
        name,
        flags=re.I,
    )
    add(stripped_corp)
    return out


def _try_sec_company_ticker_match(asset_norm: str) -> AssetMatch | None:
    """Match simplified disclosure name against the local SEC company_tickers index."""
    search_name = _simplify_for_equity_search(asset_norm)
    if not search_name or _is_generic_equity_name(asset_norm):
        return None
    # Keep the SEC query set small — each fuzzy pass scans ~8k titles.
    queries: list[str] = []

    def add(value: str) -> None:
        cleaned = normalize_whitespace(value)
        if cleaned and cleaned.casefold() not in {x.casefold() for x in queries}:
            queries.append(cleaned)

    add(search_name)
    for alias in _apply_disclosure_aliases(search_name):
        add(alias)
    add(search_name.replace("\u2019", "").replace("'", ""))
    add(
        re.sub(
            r",?\s+(?:Inc\.?|Incorporated|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|Limited|PLC|LLC)\s*$",
            "",
            search_name,
            flags=re.I,
        )
    )

    for query in queries:
        hit = match_sec_company_ticker(query)
        if hit is None:
            continue
        if hit.exact:
            return AssetMatch(
                asset_name_normalized=search_name,
                issuer_name=search_name,
                ticker=hit.ticker,
                cusip_or_figi=None,
                confidence_score=0.99,
                match_source="sec_company_tickers",
                resolution_status="exact_match",
            )
        conf = round(hit.score / 100.0, 3)
        return AssetMatch(
            asset_name_normalized=search_name,
            issuer_name=search_name,
            ticker=hit.ticker,
            cusip_or_figi=None,
            confidence_score=conf,
            match_source="sec_company_tickers",
            resolution_status="fuzzy_match",
        )
    return None


_CUSIP_IN_PARENS_RE = re.compile(r"\(([0-9A-Z]{9})\)")


def _first_cusip_token(asset: str) -> str | None:
    """Nine-character CUSIP inside parentheses (distinct from disclosure ticker parens)."""
    for m in _CUSIP_IN_PARENS_RE.finditer(asset.upper()):
        token = m.group(1)
        if re.fullmatch(r"[0-9A-Z]{9}", token):
            return token
    return None


def _asset_resolution_cache_blocks_retry(cached: Any) -> bool:
    """
    When True, treat cache as authoritative and skip Polygon/OpenFIGI.
    Failed lookups (no ticker, source none/skipped) are re-tried so improved heuristics/APIs can fill in.
    """
    if (cached["ticker"] or "").strip():
        return True
    src = (cached["match_source"] or "").strip().lower()
    return src not in _MATCH_SOURCES_RETRY_EMPTY_TICKER


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
    cleaned = _strip_senate_and_owner_prefix(asset_norm)
    ticker = _extract_ticker_from_parentheses(cleaned)
    if not ticker:
        return None
    display_name = _strip_trailing_disclosure_ticker(cleaned, ticker)
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
    key = _strip_senate_and_owner_prefix(key)
    key = re.sub(
        r"\b(class [a-z]|cl [a-z]|common stock|common shares?|common|ordinary shares?|adr|ads)\b",
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
    cleaned_asset = _simplify_for_equity_search(asset)
    asset_name = normalize_whitespace(cleaned_asset).casefold()
    candidate_name = normalize_whitespace(candidate).casefold()
    asset_key = _canonical_company_key(cleaned_asset)
    candidate_key = _canonical_company_key(candidate)
    return max(
        fuzz.ratio(asset_name, candidate_name),
        fuzz.token_sort_ratio(asset_name, candidate_name),
        fuzz.token_set_ratio(asset_key, candidate_key),
    )


def _is_exact_match(asset: str, candidate: str) -> bool:
    cleaned_asset = _simplify_for_equity_search(asset)
    asset_key = normalize_key(cleaned_asset)
    candidate_key = normalize_key(candidate)
    if asset_key and asset_key == candidate_key:
        return True
    canonical_asset = _canonical_company_key(cleaned_asset)
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
        response = _SESSION.request(method, url, **request_kwargs)
    except RequestException:
        return None

    if response.status_code == 429:
        retry_after = _parse_retry_after(response, backoff_seconds)
        if retry_after <= retry_after_cap:
            limiter.backoff(retry_after)
            limiter.wait()
            try:
                response = _SESSION.request(method, url, **request_kwargs)
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
    search_queries: list[str] = []
    simplified = _simplify_for_equity_search(asset)
    if simplified and simplified.casefold() != asset.casefold():
        search_queries.extend(_search_name_variants(simplified))
        # The raw-name retry roughly doubles Polygon calls per asset and rarely matches once the
        # name is simplified. Set POLYGON_SEARCH_RAW_FALLBACK=0 to skip it for a faster run.
        if POLYGON_SEARCH_RAW_FALLBACK:
            search_queries.extend(_search_name_variants(asset))
    else:
        search_queries.extend(_search_name_variants(asset))
    seen_q: set[str] = set()
    best_match: AssetMatch | None = None
    best_score = 0.0
    headers = {"User-Agent": USER_AGENT}
    for search in search_queries:
        qkey = search.casefold()
        if qkey in seen_q:
            continue
        seen_q.add(qkey)
        bare_ticker_query = _looks_like_bare_ticker(search)
        params = {
            "search": search,
            "market": "stocks",
            "active": "true",
            "limit": 10,
            "apiKey": api_key,
        }
        resp = _request_with_rate_limit(
            "GET",
            POLYGON_TICKER_SEARCH,
            limiter=limiter,
            params=params,
            headers=headers,
            timeout=30,
        )
        if resp is None:
            continue
        data = resp.json()
        results = data.get("results", [])
        if not results:
            continue
        for item in results:
            name = normalize_whitespace(item.get("name") or "")
            ticker = normalize_whitespace(item.get("ticker") or "") or None
            if not name or not ticker:
                continue
            # Bare-symbol queries must hit the symbol itself — fuzzy name search otherwise
            # prefers leveraged products ("MSFT" → MSFC / MSFW).
            if bare_ticker_query:
                if ticker.upper() == search.upper():
                    return AssetMatch(
                        asset_name_normalized=name,
                        issuer_name=name,
                        ticker=ticker.upper(),
                        cusip_or_figi=item.get("composite_figi") or None,
                        confidence_score=1.0,
                        match_source="polygon_exact",
                        resolution_status="exact_match",
                    )
                continue
            if _is_exact_match(asset, name) or _is_exact_match(simplified or asset, name):
                return AssetMatch(
                    asset_name_normalized=name,
                    issuer_name=name,
                    ticker=ticker,
                    cusip_or_figi=item.get("composite_figi") or None,
                    confidence_score=1.0,
                    match_source="polygon_exact",
                    resolution_status="exact_match",
                )
            score = max(_match_score(asset, name), _match_score(simplified or asset, name))
            if score >= POLYGON_FUZZY_MIN_SCORE and score > best_score:
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


def _openfigi_choice_rank(asset: str, name: str, ticker: str, fuzzy_score: float) -> tuple[float, int, int, int, int]:
    """
    Higher tuple sorts later under max(): prefer higher fuzzy score, sponsored/ADR lines,
    avoid OTC *F tickers when OpenFIGI returns many near-ties, and avoid obvious option strings.
    """
    name_u = (name or "").upper()
    tu = ticker.upper()
    adr = 1 if ("ADR" in name_u or "DEPOSITARY" in name_u or "SPONSORED" in name_u) else 0
    otc_f = 1 if (len(tu) <= 6 and tu.endswith("F") and tu.isalpha()) else 0
    otc_wf = 1 if re.search(r"[A-Z]{2,4}WF$", tu) else 0
    opt_like = 1 if ("CALL" in name_u or "PUT" in name_u or " FLX" in name_u or "/" in tu) else 0
    return (fuzzy_score, adr, -otc_f, -otc_wf, -opt_like)


def _best_openfigi_match(asset: str, results: list[Any]) -> Optional[AssetMatch]:
    if not results:
        return None
    best_choice: tuple[tuple[float, int, int, int, int], AssetMatch] | None = None
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
            fuzzy_score = 100.0
            match_source = "openfigi_exact"
            res_status = "exact_match"
            conf = 0.99
        else:
            fuzzy_score = _match_score(asset, name or ticker)
            if fuzzy_score < OPENFIGI_FUZZY_MIN_SCORE:
                continue
            match_source = "openfigi_fuzzy"
            res_status = "fuzzy_match"
            conf = round(max(fuzzy_score, OPENFIGI_FUZZY_MIN_SCORE) / 100.0, 3)
        rank = _openfigi_choice_rank(asset, name, ticker, fuzzy_score)
        candidate = AssetMatch(
            asset_name_normalized=name or asset,
            issuer_name=name or asset,
            ticker=ticker,
            cusip_or_figi=item.get("figi") or None,
            confidence_score=conf,
            match_source=match_source,
            resolution_status=res_status,
        )
        if best_choice is None or rank > best_choice[0]:
            best_choice = (rank, candidate)
    return best_choice[1] if best_choice else None


def openfigi_lookup_cusip(cusip: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
    headers = {
        "Content-Type": "application/json",
        "X-OPENFIGI-APIKEY": api_key,
        "User-Agent": USER_AGENT,
    }
    payload = [{"idType": "ID_CUSIP", "idValue": cusip.upper()}]
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
    try:
        data = resp.json()
    except ValueError:
        return None
    if not data or not isinstance(data, list):
        return None
    rows = data[0].get("data", []) if isinstance(data[0], dict) else []
    if not rows:
        return None
    item = rows[0]
    ticker = normalize_whitespace(item.get("ticker") or "") or None
    name = normalize_whitespace(
        item.get("name")
        or item.get("securityDescription")
        or item.get("securityDescription2")
        or ""
    )
    if not ticker:
        return None
    return AssetMatch(
        asset_name_normalized=name or cusip,
        issuer_name=name or cusip,
        ticker=ticker,
        cusip_or_figi=item.get("figi") or None,
        confidence_score=0.995,
        match_source="openfigi_cusip",
        resolution_status="exact_match",
    )


def _openfigi_search_query_variants(asset: str) -> list[str]:
    """OpenFIGI /v3/search often returns empty for long PTR lines; try shorter keyword queries."""
    base = _simplify_for_equity_search(asset)
    parts: list[str] = []
    for variant in _search_name_variants(base or asset):
        parts.append(variant)
    words = [w for w in re.split(r"[\s,]+", base) if len(w) >= 2]
    for n in (6, 4, 3, 2):
        if len(words) >= n:
            parts.append(" ".join(words[:n]))
    if words:
        parts.append(words[0])
    seen: set[str] = set()
    out: list[str] = []
    for q in parts:
        key = q.casefold()
        if key in seen or not q:
            continue
        seen.add(key)
        out.append(q)
    return out


def openfigi_search_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
    """Resolve issuer line via OpenFIGI keyword search (/v3/search); /v3/mapping rejects plain `name` jobs."""
    queries = _openfigi_search_query_variants(asset)
    if not queries:
        return None
    headers = {
        "Content-Type": "application/json",
        "X-OPENFIGI-APIKEY": api_key,
        "User-Agent": USER_AGENT,
    }
    simplified = _simplify_for_equity_search(asset)
    for query in queries:
        payload: dict[str, Any] = {"query": query, "exchCode": "US"}
        if OPENFIGI_NAME_STRICT_COMMON_STOCK:
            payload["securityType2"] = "Common Stock"
        resp = _request_with_rate_limit(
            "POST",
            OPENFIGI_SEARCH_URL,
            limiter=limiter,
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp is None:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("error"):
            continue
        rows = data.get("data") or []
        if not rows:
            continue
        if _looks_like_bare_ticker(query):
            sym = query.upper()
            for item in rows:
                ticker = normalize_whitespace(item.get("ticker") or "") or None
                if ticker and ticker.upper() == sym:
                    name = normalize_whitespace(
                        item.get("name")
                        or item.get("securityDescription")
                        or item.get("securityDescription2")
                        or ""
                    )
                    return AssetMatch(
                        asset_name_normalized=name or sym,
                        issuer_name=name or sym,
                        ticker=sym,
                        cusip_or_figi=item.get("figi") or None,
                        confidence_score=0.99,
                        match_source="openfigi_exact",
                        resolution_status="exact_match",
                    )
            continue
        hit = _best_openfigi_match(simplified or asset, rows)
        if hit is not None:
            return hit
    return None


def openfigi_lookup(asset: str, api_key: str, limiter: RateLimiter) -> Optional[AssetMatch]:
    return openfigi_search_lookup(asset, api_key, limiter)


def openfigi_lookup_batch(assets: list[str], api_key: str, limiter: RateLimiter) -> dict[str, Optional[AssetMatch]]:
    """One /v3/search per asset (same limiter as single lookups)."""
    out: dict[str, Optional[AssetMatch]] = {a: None for a in assets}
    for asset in assets:
        out[asset] = openfigi_search_lookup(asset, api_key, limiter)
    return out


def infer_asset_type(asset: str, ticker: str | None) -> str:
    asset_key = normalize_key(asset)
    asset_raw = (asset or "").casefold()
    if re.search(r"\b(call|put|option|options)\b", asset_key):
        return "option"
    if re.search(r"\b(rila|annuity)\b", asset_key) or "[va]" in asset_raw:
        return "annuity"
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
    commit: bool = True,
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
        commit=commit,
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


def bulk_resolve_unique_assets_for_reconcile(
    conn, assets_unique: Sequence[str], *, commit: bool = True
) -> dict[str, dict[str, Any]]:
    """
    Resolve each distinct asset string once (Polygon + OpenFIGI /v3/search + CUSIP mapping).
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
            if _asset_resolution_cache_blocks_retry(cached):
                out[an] = _resolution_dict_from_cached_row(an, cached)
                continue
        if paren := _try_disclosure_parenthetical_match(an):
            out[an] = _finalize_resolution_from_match(conn, an, paren, issuer_enrich_hint=an, commit=commit)
            continue
        if exchange := _try_exchange_prefixed_ticker_match(an):
            out[an] = _finalize_resolution_from_match(conn, an, exchange, issuer_enrich_hint=an, commit=commit)
            continue
        if bare := _try_bare_ticker_token_match(an):
            out[an] = _finalize_resolution_from_match(conn, an, bare, issuer_enrich_hint=an, commit=commit)
            continue
        if _is_generic_equity_name(an):
            out[an] = _finalize_resolution_from_match(
                conn, an, _manual_review_match(an, "generic_asset_name"), commit=commit
            )
            continue
        if sec := _try_sec_company_ticker_match(an):
            out[an] = _finalize_resolution_from_match(conn, an, sec, issuer_enrich_hint=an, commit=commit)
            continue
        if house_ingest_skip_external_asset_lookup():
            out[an] = _finalize_resolution_from_match(
                conn, an, _manual_review_match(an, "skipped_external_lookup"), commit=commit
            )
            continue

        search_name = _simplify_for_equity_search(an)
        matched: AssetMatch = _manual_review_match(an, "none")
        if openfigi_key:
            cusip = _first_cusip_token(an)
            if cusip:
                c_hit = openfigi_lookup_cusip(cusip, openfigi_key, OPENFIGI_LIMITER)
                if c_hit is not None:
                    out[an] = _finalize_resolution_from_match(conn, an, c_hit, issuer_enrich_hint=an, commit=commit)
                    continue
        if polygon_key:
            hit = polygon_lookup(search_name, polygon_key, POLYGON_LIMITER)
            if hit is not None:
                matched = hit
        if matched.ticker is not None:
            out[an] = _finalize_resolution_from_match(conn, an, matched, commit=commit)
        elif openfigi_key:
            need_openfigi_batch.append(an)
        else:
            out[an] = _finalize_resolution_from_match(conn, an, matched, commit=commit)

    if need_openfigi_batch and openfigi_key:
        search_names = {an: _simplify_for_equity_search(an) for an in need_openfigi_batch}
        batch = openfigi_lookup_batch(
            [search_names[an] for an in need_openfigi_batch], openfigi_key, OPENFIGI_LIMITER
        )
        for an in need_openfigi_batch:
            om = batch.get(search_names[an])
            final_m = om if om is not None else _manual_review_match(an, "none")
            out[an] = _finalize_resolution_from_match(conn, an, final_m, commit=commit)

    return out


def resolve_asset(conn, asset: str, *, commit: bool = True) -> dict[str, Any]:
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
        return _finalize_resolution_from_match(
            conn, asset_norm, paren_match, issuer_enrich_hint=asset_norm, commit=commit
        )

    if exchange_match := _try_exchange_prefixed_ticker_match(asset_norm):
        return _finalize_resolution_from_match(
            conn, asset_norm, exchange_match, issuer_enrich_hint=asset_norm, commit=commit
        )

    if bare_match := _try_bare_ticker_token_match(asset_norm):
        return _finalize_resolution_from_match(
            conn, asset_norm, bare_match, issuer_enrich_hint=asset_norm, commit=commit
        )

    if _is_generic_equity_name(asset_norm):
        return _finalize_resolution_from_match(
            conn, asset_norm, _manual_review_match(asset_norm, "generic_asset_name"), commit=commit
        )

    if cached := get_asset_resolution(conn, asset_norm):
        if _asset_resolution_cache_blocks_retry(cached):
            return _resolution_dict_from_cached_row(asset_norm, cached)

    if sec_match := _try_sec_company_ticker_match(asset_norm):
        return _finalize_resolution_from_match(
            conn, asset_norm, sec_match, issuer_enrich_hint=asset_norm, commit=commit
        )

    polygon_key = os.getenv("POLYGON_API_KEY")
    openfigi_key = os.getenv("OPENFIGI_API_KEY")

    # Use cleaned name (no doc-ID/owner prefixes, no trailing boilerplate) for API queries
    search_name = _simplify_for_equity_search(asset_norm)

    matched_asset: AssetMatch = _manual_review_match(asset_norm, "none")

    if not house_ingest_skip_external_asset_lookup():
        if openfigi_key:
            cusip = _first_cusip_token(asset_norm)
            if cusip:
                cusip_match = openfigi_lookup_cusip(cusip, openfigi_key, OPENFIGI_LIMITER)
                if cusip_match is not None:
                    return _finalize_resolution_from_match(
                        conn, asset_norm, cusip_match, issuer_enrich_hint=asset_norm, commit=commit
                    )
        if polygon_key:
            polygon_match = polygon_lookup(search_name, polygon_key, POLYGON_LIMITER)
            if polygon_match is not None:
                matched_asset = polygon_match

        if matched_asset.ticker is None and openfigi_key:
            openfigi_match = openfigi_lookup(search_name, openfigi_key, OPENFIGI_LIMITER)
            if openfigi_match is not None:
                matched_asset = openfigi_match
    else:
        matched_asset = _manual_review_match(asset_norm, "skipped_external_lookup")

    return _finalize_resolution_from_match(conn, asset_norm, matched_asset, commit=commit)


def lookup_ticker(conn, asset: str) -> Optional[str]:
    return resolve_asset(conn, asset).get("ticker")
