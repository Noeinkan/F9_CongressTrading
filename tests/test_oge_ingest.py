"""Tests for the OGE Executive (278-T + 278e) ingest pipeline.

These tests build minimal single-page PDFs by hand (no extra dependencies)
and exercise the parser + ingest against an in-memory SQLite database.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# --------------------------------------------------------------------------- #
# Minimal PDF fixture (handcrafted — no extra deps)
# --------------------------------------------------------------------------- #
def _make_pdf(path: Path, lines: list[str]) -> None:
    """Write a single-page PDF containing ``lines`` as wrapped text at 12pt.

    pdfplumber reads these fine; ``extract_table`` returns ``None`` because
    there are no explicit column boundaries — this routes the parser through
    the text-fallback path which is what these tests exercise.
    """
    # Wrap each line as a ``(text) Tj`` operation. Use 50pt left margin and
    # step down 14pt per line.
    operations = ["BT /F1 12 Tf 50 750 Td"]
    for index, line in enumerate(lines):
        if index == 0:
            operations.append(f"({_escape(line)}) Tj")
        else:
            operations.append(f"0 -14 Td ({_escape(line)}) Tj")
    operations.append("ET")
    content = " ".join(operations).encode("latin-1", errors="replace")
    content_length = len(content)

    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length " + str(content_length).encode() + b">>stream\n"
        + content
        + b"\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"0000000010 00000 n \n0000000060 00000 n \n"
        b"0000000110 00000 n \n0000000210 00000 n \n0000000320 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n400\n%%EOF\n"
    )
    path.write_bytes(body)


def _escape(value: str) -> str:
    """Escape a string for the ``(text)`` PDF literal form."""
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# --------------------------------------------------------------------------- #
# Parser unit tests
# --------------------------------------------------------------------------- #
def test_parse_278t_normalizes_description_codes(tmp_path: Path) -> None:
    """278-T Description codes P/S/E map to P (Buy) / S (Sell) / E (Exchange)."""
    from src.parse_oge import parse_oge_278t

    pdf = tmp_path / "278t.pdf"
    _make_pdf(
        pdf,
        [
            "OGE Form 278-T (Periodic Transaction Report)",
            "Filer Name: Donald J. Trump",
            "Filing Date: 02/26/2026",
            "Asset Description Date Amount",
            "Apple Inc P 02/15/2026 $1,001 - $15,000",
            "Microsoft Corp S 02/16/2026 $15,001 - $50,000",
            "Alphabet Inc E 02/17/2026 $50,001 - $100,000",
        ],
    )

    header, rows = parse_oge_278t(pdf)
    assert header["form_type"] == "OGE278T"
    # At least the trailing text-fallback rows should land in the output;
    # table extraction may add duplicates from the header row, so just assert
    # the canonical codes appear.
    types = {row["transaction_type"] for row in rows}
    assert "P (Buy)" in types
    assert "S (Sell)" in types
    assert "E (Exchange)" in types


def test_parse_278t_owner_code_mapping(tmp_path: Path) -> None:
    """Owner prefixes SP/DC/Filer map to spouse/dependent/filer."""
    from src.parse_oge import parse_oge_278t

    pdf = tmp_path / "278t_owner.pdf"
    _make_pdf(
        pdf,
        [
            "OGE Form 278-T",
            "Filer Name: Donald J. Trump",
            "Filing Date: 04/20/2026",
            "SP Bond Series A P 04/15/2026 $1,001 - $15,000",
            "DC Mutual Fund P 04/16/2026 $15,001 - $50,000",
            "Filer Treasury Note S 04/17/2026 $50,001 - $100,000",
        ],
    )
    _, rows = parse_oge_278t(pdf)
    by_owner = {row["owner_type"] for row in rows}
    assert {"spouse", "dependent", "filer"}.issubset(by_owner)


def test_parse_278e_extracts_holdings(tmp_path: Path) -> None:
    """278e holdings rows include asset name + owner."""
    from src.parse_oge import parse_oge_278e

    pdf = tmp_path / "278e.pdf"
    _make_pdf(
        pdf,
        [
            "OGE Form 278e (Annual Report)",
            "Filer Name: Donald J. Trump",
            "Filing Date: 05/15/2025",
            "Asset Owner Value",
            "Apple Inc Filer $1,001 - $15,000",
            "Treasury Bond Spouse $15,001 - $50,000",
        ],
    )
    header, holdings = parse_oge_278e(pdf)
    assert header["form_type"] == "OGE278e"
    # text-fallback rows for each line above
    owners = {row["owner_type"] for row in holdings}
    assert "filer" in owners or "spouse" in owners


def test_parse_unknown_form_raises(tmp_path: Path) -> None:
    """Neither 278-T nor 278e → ValueError."""
    from src.parse_oge import parse_oge_278e, parse_oge_278t

    pdf = tmp_path / "bogus.pdf"
    _make_pdf(pdf, ["Random disclosure document"])
    with pytest.raises(ValueError):
        parse_oge_278t(pdf)
    with pytest.raises(ValueError):
        parse_oge_278e(pdf)


# --------------------------------------------------------------------------- #
# Ingest integration tests (in-memory DB)
# --------------------------------------------------------------------------- #
@pytest.fixture
def in_memory_db(monkeypatch):
    """Patch DB_PATH to a tmp file (sqlite :memory: can't be shared by the
    process-pool workers used by the safe parser wrappers, but the unsafe
    parsers + ingest helpers work fine on a tmp file)."""
    from src import config

    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    monkeypatch.setattr(config, "DB_PATH", tmp_path)
    # Initialize schema.
    from src.db import get_connection, init_db

    conn = get_connection()
    init_db(conn)
    conn.close()
    yield tmp_path
    if tmp_path.exists():
        tmp_path.unlink()


def test_ingest_oge_278t_creates_member_filing_transaction(in_memory_db, tmp_path, monkeypatch):
    """Happy path: one 278-T PDF → 1 member, 1 filing, N transactions."""
    from src import ingest_oge as ingest_oge_module
    from src.db import get_connection
    from src.ingest_oge import ingest_oge

    # Patch the OGE_RAW_DIR binding inside the ingest module (it imports
    # the constant from .config at module load time, so we have to override
    # the local binding as well).
    monkeypatch.setattr(ingest_oge_module, "OGE_RAW_DIR", tmp_path)
    monkeypatch.setattr("src.config.OGE_RAW_DIR", tmp_path)

    pdf = tmp_path / "TESTDOC1234567890ABCDEF1234567890AB.pdf"
    _make_pdf(
        pdf,
        [
            "OGE Form 278-T",
            "Filer Name: Donald J. Trump",
            "Filing Date: 02/26/2026",
            "Asset Description Date Amount",
            "Apple Inc P 02/15/2026 $1,001 - $15,000",
            "Microsoft Corp S 02/16/2026 $15,001 - $50,000",
        ],
    )

    ingest_oge(filer_name="Donald J. Trump")

    conn = get_connection()
    try:
        member_row = conn.execute(
            "SELECT * FROM members WHERE chamber = 'Executive' AND full_name = ?",
            ("Donald J. Trump",),
        ).fetchone()
        assert member_row is not None
        assert member_row["chamber"] == "Executive"

        filing_row = conn.execute(
            "SELECT * FROM filings WHERE chamber = 'Executive' AND filing_type = 'OGE278T'"
        ).fetchone()
        assert filing_row is not None

        txn_rows = conn.execute(
            "SELECT * FROM transactions WHERE filing_id = ?", (filing_row["id"],)
        ).fetchall()
        assert len(txn_rows) >= 1
        chamber_check = conn.execute(
            """
            SELECT m.chamber
            FROM transactions t
            JOIN filings f ON f.id = t.filing_id
            JOIN members m ON m.id = f.member_id
            WHERE t.filing_id = ?
            """,
            (filing_row["id"],),
        ).fetchall()
        assert all(r["chamber"] == "Executive" for r in chamber_check)
    finally:
        conn.close()


def test_ingest_oge_278e_creates_executive_holdings(in_memory_db, tmp_path, monkeypatch):
    """278e PDF → rows in the new executive_holdings table."""
    from src import ingest_oge as ingest_oge_module
    from src.db import get_connection
    from src.ingest_oge import ingest_oge

    monkeypatch.setattr(ingest_oge_module, "OGE_RAW_DIR", tmp_path)
    monkeypatch.setattr("src.config.OGE_RAW_DIR", tmp_path)

    pdf = tmp_path / "278E_ANNUAL_ABCDEF1234567890ABCDEF12345678.pdf"
    _make_pdf(
        pdf,
        [
            "OGE Form 278e",
            "Filer Name: Donald J. Trump",
            "Filing Date: 05/15/2025",
            "Asset Owner Value",
            "Apple Inc Filer $1,001 - $15,000",
            "Treasury Bond Spouse $15,001 - $50,000",
        ],
    )
    ingest_oge(filer_name="Donald J. Trump")

    conn = get_connection()
    try:
        filing_row = conn.execute(
            "SELECT * FROM filings WHERE chamber = 'Executive' AND filing_type = 'OGE278e'"
        ).fetchone()
        assert filing_row is not None

        holding_rows = conn.execute(
            "SELECT * FROM executive_holdings WHERE filing_id = ?", (filing_row["id"],)
        ).fetchall()
        assert len(holding_rows) >= 1
        txn_count = conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE filing_id = ?",
            (filing_row["id"],),
        ).fetchone()["c"]
        assert txn_count == 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Downloader (no real network)
# --------------------------------------------------------------------------- #
def test_download_oge_skips_existing_files(tmp_path: Path, monkeypatch) -> None:
    """If the file already exists on disk, download_oge_filings must not
    issue a network request — it counts the file as 'already present'."""
    from src import config, oge_source
    from src import download_oge as download_oge_module
    from src.download_oge import download_oge_filings

    monkeypatch.setattr(config, "OGE_RAW_DIR", tmp_path)
    monkeypatch.setattr(download_oge_module, "OGE_RAW_DIR", tmp_path)

    for filing in oge_source.TRUMP_OGE_FILINGS:
        (tmp_path / f"{filing.doc_id}.pdf").write_bytes(b"%PDF-1.4 stub")

    with patch("src.download_oge.requests.get") as mock_get:
        downloaded, already_present = download_oge_filings(
            filer_name="Donald J. Trump",
            dest_dir=tmp_path,
        )

    assert downloaded == 0
    assert already_present == len(oge_source.TRUMP_OGE_FILINGS)
    mock_get.assert_not_called()


def test_download_oge_fails_loud_on_404(tmp_path: Path, monkeypatch) -> None:
    """A 404 from OGE must raise (no silent skip, no retry)."""
    from src import config
    from src import download_oge as download_oge_module
    from src.download_oge import download_oge_filings

    monkeypatch.setattr(config, "OGE_RAW_DIR", tmp_path)
    monkeypatch.setattr(download_oge_module, "OGE_RAW_DIR", tmp_path)

    class _FakeResponse:
        status_code = 404
        headers: dict = {}

        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *exc):
            return False

        def raise_for_status(self_inner):
            from requests import HTTPError

            raise HTTPError("404 not found")

    with patch("src.download_oge.requests.get", return_value=_FakeResponse()):
        with patch("src.download_oge.time.sleep"):
            with pytest.raises(RuntimeError, match="404"):
                download_oge_filings(filer_name="Donald J. Trump", dest_dir=tmp_path)


def test_download_oge_calls_network_when_file_missing(tmp_path: Path, monkeypatch) -> None:
    """When the file is absent, the downloader hits the network and writes to disk."""
    from src import config, oge_source
    from src import download_oge as download_oge_module
    from src.download_oge import download_oge_filings

    monkeypatch.setattr(config, "OGE_RAW_DIR", tmp_path)
    monkeypatch.setattr(download_oge_module, "OGE_RAW_DIR", tmp_path)

    pdf_bytes = b"%PDF-1.4 dummy content"

    class _FakeResponse:
        status_code = 200
        headers = {"Content-Length": str(len(pdf_bytes))}

        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *exc):
            return False

        def raise_for_status(self_inner):
            return None

        def iter_content(self_inner, chunk_size):
            yield pdf_bytes

    with patch("src.download_oge.requests.get", return_value=_FakeResponse()):
        with patch("src.download_oge.time.sleep"):
            downloaded, already_present = download_oge_filings(
                filer_name="Donald J. Trump",
                dest_dir=tmp_path,
            )

    assert downloaded == len(oge_source.TRUMP_OGE_FILINGS)
    assert already_present == 0
    written = list(tmp_path.glob("*.pdf"))
    assert written, "downloader did not write any PDFs"