"""One-off: verify Polygon + OpenFIGI keys; not part of CLI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import requests

import src.config  # noqa: F401 — loads .env
from src.config import OPENFIGI_API_URL, POLYGON_TICKER_SEARCH, USER_AGENT


def main() -> int:
    poly = os.getenv("POLYGON_API_KEY", "").strip()
    if not poly:
        print("FAIL: POLYGON_API_KEY mancante o vuoto")
        return 1
    r = requests.get(
        POLYGON_TICKER_SEARCH,
        params={
            "search": "Apple Inc",
            "market": "stocks",
            "active": "true",
            "limit": 3,
            "apiKey": poly,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    res = data.get("results") or []
    if not res:
        print("FAIL: Polygon results vuoto")
        return 1
    print("OK Polygon:", res[0].get("ticker"), "-", (res[0].get("name") or "")[:50])

    of = os.getenv("OPENFIGI_API_KEY", "").strip()
    if not of:
        print("SKIP OpenFIGI: OPENFIGI_API_KEY non impostata")
        return 0
    r2 = requests.post(
        OPENFIGI_API_URL,
        headers={
            "Content-Type": "application/json",
            "X-OPENFIGI-APIKEY": of,
            "User-Agent": USER_AGENT,
        },
        json=[{"idType": "TICKER", "idValue": "AAPL", "exchCode": "US"}],
        timeout=30,
    )
    r2.raise_for_status()
    body = r2.json()
    if not body or not body[0].get("data"):
        print("FAIL: OpenFIGI senza data")
        return 1
    row = body[0]["data"][0]
    print("OK OpenFIGI:", row.get("ticker"), str(row.get("figi", ""))[:12])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as e:
        print("FAIL richiesta HTTP:", e)
        raise SystemExit(1)
