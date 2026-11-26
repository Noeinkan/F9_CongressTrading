"""Senate trades from FMP: poll storage, gap detection, parsing, ingest precedence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import senate_fmp

UUID_A = "99dc7269-2f99-4c8b-8d0c-a3a91328af84"
UUID_B = "9d3510cc-0000-4000-8000-000000000001"


def _row(uuid: str, day: str, *, last="Paul", first="Rand", symbol="NVDA", typ="Purchase", amount="$1,001 - $15,000", owner="Self") -> dict:
    return {
        "symbol": symbol,
        "senateID": "P000603",
        "disclosureDate": "2026-11-25",
        "transactionDate": day,
        "firstName": first,
        "lastName": last,
        "office": f"{last}, {first} (Senator)",
        "owner": owner,
        "assetDescription": "NVIDIA Corporation - Common Stock" if symbol else "Some Private Fund LP",
        "assetType": "Stock",
        "type": typ,
        "amount": amount,
        "comment": "",
        "link": f"https://efdsearch.senate.gov/search/view/ptr/{uuid}/",
    }


def _page(uuid: str, n: int, start: int = 1) -> list[dict]:
    return [_row(uuid, f"2026-11-{start + i:02d}") for i in range(n)]


def test_store_groups_rows_by_filing_and_merges_later_polls(tmp_path: Path) -> None:
    dest = tmp_path / "fmp"
    first = senate_fmp.store_rows([_row(UUID_A, "2026-11-05")], dest_dir=dest, efd_dir=tmp_path)
    assert first.seeded and first.new_rows == 1 and first.new_filings == [UUID_A]

    second = senate_fmp.store_rows(
        [_row(UUID_A, "2026-11-05"), _row(UUID_A, "2026-11-07"), _row(UUID_B, "2026-11-04", last="Blumenthal", first="Richard")],
        dest_dir=dest,
        efd_dir=tmp_path,
    )
    assert second.new_rows == 2 and second.new_filings == [UUID_B]
    doc = json.loads((dest / f"{UUID_A}.json").read_text(encoding="utf-8"))
    assert [t["transactionDate"] for t in doc["trades"]] == ["2026-11-05", "2026-11-07"]
    assert doc["filing_date"] == "2026-11-25"


def test_full_page_of_new_rows_is_a_possible_gap_but_not_on_first_run(tmp_path: Path) -> None:
    dest = tmp_path / "fmp"
    seeded = senate_fmp.store_rows(_page(UUID_A, 25), dest_dir=dest, efd_dir=tmp_path)
    assert seeded.seeded and not seeded.possible_gap

    overlap = senate_fmp.store_rows(_page(UUID_A, 25), dest_dir=dest, efd_dir=tmp_path)
    assert not overlap.possible_gap and overlap.new_rows == 0

    big_filing = [_row(UUID_B, f"2026-10-{d:02d}", last="Tuberville", first="Tommy") for d in range(1, 26)]
    gap = senate_fmp.store_rows(big_filing, dest_dir=dest, efd_dir=tmp_path)
    assert gap.possible_gap
    assert gap.gap_filings == [("Tommy Tuberville", "2026-11-25", f"https://efdsearch.senate.gov/search/view/ptr/{UUID_B}/")]
    assert UUID_B in senate_fmp.gap_alert_detail(gap)


def test_filing_already_on_disk_as_efd_html_is_not_stored(tmp_path: Path) -> None:
    (tmp_path / f"{UUID_A}.html").write_text("<html></html>", encoding="utf-8")
    result = senate_fmp.store_rows([_row(UUID_A, "2026-11-05")], dest_dir=tmp_path / "fmp", efd_dir=tmp_path)
    assert result.already_on_disk == 1 and result.new_rows == 0
    assert not (tmp_path / "fmp" / f"{UUID_A}.json").exists()


def test_parse_matches_the_html_row_contract(tmp_path: Path) -> None:
    dest = tmp_path / "fmp"
    senate_fmp.store_rows(
        [
            _row(UUID_A, "2026-11-05"),
            _row(UUID_A, "2026-11-06", typ="Sale (Partial)", owner="Spouse"),
            _row(UUID_A, "2026-11-07", symbol="", typ="Sale (Full)", owner="Joint"),
        ],
        dest_dir=dest,
        efd_dir=tmp_path,
    )
    header, rows = senate_fmp.parse_senate_fmp_json(dest / f"{UUID_A}.json")
    assert header["member"] == "Rand Paul" and header["filing_date"] == "2026-11-25"
    assert header["source_url"].endswith(f"/{UUID_A}/")
    assert [(r["transaction_type"], r["owner_type"]) for r in rows] == [("P", "self"), ("S (partial)", "spouse"), ("S", "joint")]
    assert rows[0]["asset"] == "NVIDIA Corporation - Common Stock (NVDA)"
    assert rows[2]["asset"] == "Some Private Fund LP"


def test_rows_that_differ_only_by_comment_stay_separate(tmp_path: Path) -> None:
    dest = tmp_path / "fmp"
    a, b = _row(UUID_A, "2026-10-23", symbol=""), _row(UUID_A, "2026-10-23", symbol="")
    a["comment"], b["comment"] = "Underlying Asset of Summa I LLC", "Underlying Asset of Hedge Holdings LLC"
    senate_fmp.store_rows([a, b], dest_dir=dest, efd_dir=tmp_path)
    _, rows = senate_fmp.parse_senate_fmp_json(dest / f"{UUID_A}.json")
    assert [r["asset"] for r in rows] == [
        "Some Private Fund LP [Underlying Asset of Summa I LLC]",
        "Some Private Fund LP [Underlying Asset of Hedge Holdings LLC]",
    ]


def test_fetch_never_leaks_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 402
        text = "Restricted for apikey=SECRET123"

    class _Session:
        def get(self, *_a, **_k):
            return _Resp()

    with pytest.raises(senate_fmp.FmpError) as err:
        senate_fmp.fetch_latest("SECRET123", session=_Session())
    assert "SECRET123" not in str(err.value) and "402" in str(err.value)


def _fake_resolve(_conn, asset: str) -> dict:
    ticker = "NVDA" if "(NVDA)" in asset else None
    return {
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


def _setup_ingest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from src import ingest_senate as ingest_senate_module

    monkeypatch.setattr(ingest_senate_module, "SENATE_RAW_DIR", tmp_path)
    monkeypatch.setattr("src.config.SENATE_RAW_DIR", tmp_path)
    monkeypatch.setattr(ingest_senate_module, "resolve_asset", _fake_resolve)
    monkeypatch.setattr(ingest_senate_module, "senate_efd_auto_download_enabled", lambda: False)
    return ingest_senate_module


def _senate_txn_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transactions tx JOIN filings f ON f.id = tx.filing_id WHERE f.chamber = 'Senate'"
    ).fetchone()[0]


def test_ingest_parses_fmp_files_and_reingests_when_they_grow(tmp_path: Path, monkeypatch) -> None:
    from src.db import get_connection

    module = _setup_ingest(monkeypatch, tmp_path)
    dest = tmp_path / "fmp"
    senate_fmp.store_rows([_row(UUID_A, "2026-11-05")], dest_dir=dest, efd_dir=tmp_path)
    module.ingest_senate()

    senate_fmp.store_rows([_row(UUID_A, "2026-11-05"), _row(UUID_A, "2026-11-07")], dest_dir=dest, efd_dir=tmp_path)
    module.ingest_senate()
    module.ingest_senate()

    conn = get_connection()
    try:
        assert _senate_txn_count(conn) == 2
        filing = conn.execute("SELECT doc_id, source_url FROM filings WHERE chamber = 'Senate'").fetchall()
        assert len(filing) == 1
        assert filing[0][0] == UUID_A and filing[0][1].endswith(f"/{UUID_A}/")
        assert conn.execute("SELECT COUNT(*) FROM trades WHERE chamber = 'Senate'").fetchone()[0] == 2
    finally:
        conn.close()


def test_efd_html_of_the_same_filing_replaces_the_fmp_rows(tmp_path: Path, monkeypatch) -> None:
    from src.db import get_connection

    from tests.test_senate_efd import SAMPLE_PTR_HTML

    module = _setup_ingest(monkeypatch, tmp_path)
    senate_fmp.store_rows([_row(UUID_A, "2026-11-05")], dest_dir=tmp_path / "fmp", efd_dir=tmp_path)
    module.ingest_senate()

    (tmp_path / f"{UUID_A}.html").write_text(SAMPLE_PTR_HTML, encoding="utf-8")
    module.ingest_senate()

    conn = get_connection()
    try:
        paths = {r[0] for r in conn.execute("SELECT raw_document_path FROM filings WHERE chamber = 'Senate'")}
        assert paths == {str(tmp_path / f"{UUID_A}.html")}
        assert conn.execute("SELECT COUNT(*) FROM trades WHERE source_file LIKE '%.json'").fetchone()[0] == 0
    finally:
        conn.close()


def test_fmp_name_reuses_the_efd_member() -> None:
    from src.db import get_connection, init_db, upsert_member

    conn = get_connection()
    try:
        init_db(conn)
        upsert_member(conn, full_name="Mr. Thomas H Tuberville", chamber="Senate", state="AL", party="Republican")
        upsert_member(conn, full_name="Angus S King Jr.", chamber="Senate", state="ME", party="Independent")
        assert senate_fmp.resolve_member_name(conn, "Tommy", "Tuberville") == "Mr. Thomas H Tuberville"
        assert senate_fmp.resolve_member_name(conn, "Angus", "King") == "Angus S King Jr."
        assert senate_fmp.resolve_member_name(conn, "Rand", "Paul") == "Rand Paul"
    finally:
        conn.close()


def test_ingest_poll_failure_alerts_and_parsing_goes_on(tmp_path: Path, monkeypatch) -> None:
    from src.notify import service as notify_service

    module = _setup_ingest(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "fmp_api_key", lambda: "k")

    def _down():
        raise senate_fmp.FmpError("FMP answered HTTP 500")

    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "poll_senate_fmp", _down)
    monkeypatch.setattr(notify_service, "send_notice", lambda title, detail: alerts.append((title, detail)))
    senate_fmp.store_rows([_row(UUID_A, "2026-11-05")], dest_dir=tmp_path / "fmp", efd_dir=tmp_path)

    module.ingest_senate()

    assert alerts and "HTTP 500" in alerts[0][1]
