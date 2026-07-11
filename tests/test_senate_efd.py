"""Tests for the Senate eFD downloader + electronic-PTR HTML parser + ingest.

The downloader talks to efdsearch.senate.gov via curl_cffi (browser impersonation
to get past Akamai); here we replace the session with a scripted fake, so no
network and no curl_cffi behavior is exercised. The HTML fixture below is a trimmed
copy of a real electronic PTR page.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# A trimmed but faithful electronic PTR page: filer in <h2 class="filedReport">,
# "Filed MM/DD/YYYY" line, and the transactions table with the real column order.
SAMPLE_PTR_HTML = """<!DOCTYPE HTML><html><head><title>eFD</title></head><body>
  <h1 class="mb-2">Periodic Transaction Report for 07/02/2026</h1>
  <h2 class="filedReport">The Honorable Gary C Peters (Peters, Gary)</h2>
  <p class="muted"><strong class="noWrap">Filed 07/02/2026 @ 4:18 PM</strong></p>
  <table class="table table-striped">
    <thead><tr class="header">
      <th scope="col">#</th><th scope="col">Transaction Date</th><th scope="col">Owner</th>
      <th scope="col">Ticker</th><th scope="col">Asset Name</th><th scope="col">Asset Type</th>
      <th scope="col">Type</th><th scope="col">Amount</th><th scope="col">Comment</th>
    </tr></thead>
    <tbody>
      <tr><td>1</td><td>06/29/2026</td><td>Self</td>
          <td><a href="https://finance.yahoo.com/quote/T">T</a></td>
          <td>AT&amp;T Inc.</td><td>Stock</td><td>Purchase</td><td>$1,001 - $15,000</td><td>--</td></tr>
      <tr><td>2</td><td>06/30/2026</td><td>Spouse</td>
          <td>--</td><td>Some Municipal Bond</td><td>Corporate Bond</td>
          <td>Sale (Partial)</td><td>$15,001 - $50,000</td><td>note</td></tr>
      <tr><td>3</td><td></td><td>Joint</td>
          <td>MSFT</td><td>Microsoft Corp</td><td>Stock</td><td>Exchange</td><td>$1,001 - $15,000</td><td>--</td></tr>
    </tbody>
  </table>
</body></html>"""


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def test_parse_senate_ptr_html_header_and_rows(tmp_path: Path) -> None:
    from src.parse_ptr import parse_senate_ptr_html

    path = tmp_path / "sample.html"
    path.write_text(SAMPLE_PTR_HTML, encoding="utf-8")
    header, rows = parse_senate_ptr_html(path)

    assert header["member"] == "Gary C Peters"  # honorific + parenthetical stripped
    assert header["filing_date"] == "2026-07-02"
    assert len(rows) == 3

    r0, r1, r2 = rows
    # Purchase -> P, explicit ticker embedded so resolve_asset can pick it up
    assert r0["transaction_type"] == "P"
    assert r0["asset"] == "AT&T Inc. (T)"
    assert r0["owner_type"] == "self"
    assert r0["amount_range"] == "$1,001 - $15,000"
    assert r0["source_page"] is None
    assert r0["parse_warning"] is None

    # Sale (Partial) -> "S (partial)"; no ticker ("--") so asset stays bare
    assert r1["transaction_type"] == "S (partial)"
    assert r1["asset"] == "Some Municipal Bond"
    assert r1["owner_type"] == "spouse"

    # Exchange -> E; missing transaction date -> warning
    assert r2["transaction_type"] == "E"
    assert r2["transaction_date"] is None
    assert r2["parse_warning"] == "missing_transaction_date"
    assert r2["owner_type"] == "joint"


def test_parse_senate_ptr_html_no_table(tmp_path: Path) -> None:
    from src.parse_ptr import parse_senate_ptr_html

    path = tmp_path / "empty.html"
    path.write_text("<html><body><h1>Nothing here</h1></body></html>", encoding="utf-8")
    header, rows = parse_senate_ptr_html(path)
    assert rows == []


# --------------------------------------------------------------------------- #
# Downloader (scripted fake session — no network)
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, status=200, headers=None, text="", json_data=None):
        self.status_code = status
        self.headers = headers or {}
        self.text = text
        self._json = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class _FakeSession:
    """Routes efdsearch requests: home/landing GETs, terms POST, report/data POST, PTR HTML GET."""

    def __init__(self, rows, html=SAMPLE_PTR_HTML):
        from src import config

        self.cookies = {"csrftoken": "tok123"}
        self.rows = rows
        self.html = html
        self.posts: list[tuple[str, dict]] = []
        self._report_url = config.SENATE_EFD_REPORT_DATA_URL

    def get(self, url, **kwargs):
        if "/search/view/ptr/" in url:
            return _FakeResp(200, {"Content-Type": "text/html; charset=utf-8"}, text=self.html)
        return _FakeResp(200, {"Content-Type": "text/html"}, text="")

    def post(self, url, data=None, **kwargs):
        self.posts.append((url, data or {}))
        if url == self._report_url:
            return _FakeResp(
                200,
                {"Content-Type": "application/json"},
                json_data={"recordsTotal": len(self.rows), "data": self.rows},
            )
        return _FakeResp(200, {"Content-Type": "text/html"}, text="")


def _row(uuid: str, kind: str = "ptr", date: str = "07/02/2026") -> list:
    return [
        "Gary",
        "Peters",
        "Peters, Gary (Senator)",
        f'<a href="/search/view/{kind}/{uuid}/" target="_blank">PTR for {date}</a>',
        date,
    ]


def test_download_senate_writes_electronic_and_skips_paper(tmp_path: Path, monkeypatch) -> None:
    from src import download_senate_efd as dl

    rows = [_row("aa11"), _row("dd44", kind="paper"), _row("bb22")]
    fake = _FakeSession(rows)
    monkeypatch.setattr(dl, "_build_session", lambda: fake)
    monkeypatch.setattr(dl.time, "sleep", lambda *a, **k: None)

    downloaded, already_present = dl.download_senate_efd(dest_dir=tmp_path, min_year=2024)

    assert downloaded == 2  # two electronic PTRs
    assert already_present == 0
    written = sorted(p.name for p in tmp_path.glob("*.html"))
    assert written == ["aa11.html", "bb22.html"]  # paper skipped, no dd44.*
    assert not list(tmp_path.glob("dd44*"))

    # Terms were accepted programmatically.
    terms_posts = [d for (u, d) in fake.posts if d.get("prohibition_agreement") == "1"]
    assert terms_posts, "prohibition agreement was not POSTed"


def test_download_senate_skips_existing(tmp_path: Path, monkeypatch) -> None:
    from src import download_senate_efd as dl

    (tmp_path / "aa11.html").write_text("already here", encoding="utf-8")
    fake = _FakeSession([_row("aa11"), _row("bb22")])
    monkeypatch.setattr(dl, "_build_session", lambda: fake)
    monkeypatch.setattr(dl.time, "sleep", lambda *a, **k: None)

    downloaded, already_present = dl.download_senate_efd(dest_dir=tmp_path, min_year=2024)

    assert downloaded == 1
    assert already_present == 1
    assert (tmp_path / "aa11.html").read_text(encoding="utf-8") == "already here"  # untouched


def test_download_senate_limit(tmp_path: Path, monkeypatch) -> None:
    from src import download_senate_efd as dl

    fake = _FakeSession([_row("aa11"), _row("bb22"), _row("cc33")])
    monkeypatch.setattr(dl, "_build_session", lambda: fake)
    monkeypatch.setattr(dl.time, "sleep", lambda *a, **k: None)

    downloaded, _ = dl.download_senate_efd(dest_dir=tmp_path, min_year=2024, limit=1)
    assert downloaded == 1
    assert len(list(tmp_path.glob("*.html"))) == 1


# --------------------------------------------------------------------------- #
# Ingest integration (tmp-file DB; no network resolver)
# --------------------------------------------------------------------------- #
@pytest.fixture
def in_memory_db(monkeypatch):
    from src import config

    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    monkeypatch.setattr(config, "DB_PATH", tmp_path)
    from src.db import get_connection, init_db

    conn = get_connection()
    init_db(conn)
    conn.close()
    yield tmp_path
    if tmp_path.exists():
        tmp_path.unlink()


def _fake_resolve(conn, asset, **kwargs):
    """Deterministic resolver: ticker in trailing parens -> exact_match, else manual_review."""
    import re

    m = re.search(r"\(([A-Z]{1,5})\)\s*$", asset or "")
    ticker = m.group(1) if m else None
    return {
        "asset_name_raw": asset,
        "asset_name_normalized": asset,
        "issuer_name": asset,
        "ticker": ticker,
        "cusip_or_figi": None,
        "asset_type": "equity" if ticker else "unknown",
        "sector": "",
        "industry": "",
        "confidence_score": 1.0 if ticker else 0.0,
        "match_source": "disclosure_paren" if ticker else "none",
        "review_status": "exact_match" if ticker else "manual_review",
    }


def test_ingest_senate_parses_electronic_html(in_memory_db, tmp_path, monkeypatch) -> None:
    from src import ingest_senate as ingest_senate_module
    from src.db import get_connection
    from src.ingest_senate import ingest_senate

    monkeypatch.setattr(ingest_senate_module, "SENATE_RAW_DIR", tmp_path)
    monkeypatch.setattr("src.config.SENATE_RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_senate_module, "resolve_asset", _fake_resolve)
    monkeypatch.setattr(ingest_senate_module, "senate_efd_auto_download_enabled", lambda: False)

    (tmp_path / "uuid-a.html").write_text(SAMPLE_PTR_HTML, encoding="utf-8")

    ingest_senate()

    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM transactions tx JOIN filings f ON f.id=tx.filing_id "
            "WHERE f.chamber='Senate'"
        ).fetchone()[0]
        assert n == 3
        member = conn.execute(
            "SELECT m.full_name FROM members m JOIN filings f ON f.member_id=m.id "
            "WHERE f.chamber='Senate' LIMIT 1"
        ).fetchone()[0]
        assert member == "Gary C Peters"
        types = {
            r[0]
            for r in conn.execute(
                "SELECT tx.transaction_type FROM transactions tx JOIN filings f "
                "ON f.id=tx.filing_id WHERE f.chamber='Senate'"
            )
        }
        assert types == {"P", "S (partial)", "E"}
        # The AT&T row had an embedded ticker -> resolved.
        tickers = {
            r[0]
            for r in conn.execute(
                "SELECT tx.ticker FROM transactions tx JOIN filings f ON f.id=tx.filing_id "
                "WHERE f.chamber='Senate' AND tx.ticker IS NOT NULL AND tx.ticker != ''"
            )
        }
        assert "T" in tickers and "MSFT" in tickers
    finally:
        conn.close()


def test_ingest_senate_is_idempotent(in_memory_db, tmp_path, monkeypatch) -> None:
    from src import ingest_senate as ingest_senate_module
    from src.db import get_connection
    from src.ingest_senate import ingest_senate

    monkeypatch.setattr(ingest_senate_module, "SENATE_RAW_DIR", tmp_path)
    monkeypatch.setattr("src.config.SENATE_RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_senate_module, "resolve_asset", _fake_resolve)
    monkeypatch.setattr(ingest_senate_module, "senate_efd_auto_download_enabled", lambda: False)

    (tmp_path / "uuid-a.html").write_text(SAMPLE_PTR_HTML, encoding="utf-8")
    ingest_senate()
    ingest_senate()  # second run: file already ingested (sha match) -> no duplicates

    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM transactions tx JOIN filings f ON f.id=tx.filing_id "
            "WHERE f.chamber='Senate'"
        ).fetchone()[0]
        assert n == 3
    finally:
        conn.close()
