"""The nightly job must re-fetch the House Clerk's index, like the Refresh button.

``ingest-all`` reads the yearly index already on disk and never downloads it
again. From 12 to 16 September 2026 that froze the House side for four nights:
the Clerk listed six newer filings and every run logged "no new House PTR".
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

from src import download_house_fd
from src.download_house_fd import house_fd_refresh_force_years

NIGHTLY_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nightly_ingest.sh"


def _run_cli(monkeypatch, *argv: str) -> dict:
    calls: list[dict] = []

    def fake_bulk(years, **kwargs):
        calls.append({"years": list(years), **kwargs})
        return list(years)

    monkeypatch.setattr(download_house_fd, "download_house_fd_bulk", fake_bulk)
    monkeypatch.setattr(sys, "argv", ["src.main", *argv])
    from src.main import main

    main()
    assert len(calls) == 1
    return calls[0]


def test_refresh_flag_forces_the_same_years_as_the_refresh_button(monkeypatch):
    call = _run_cli(monkeypatch, "download-house-fd", "--refresh")
    assert call["force_years"] == house_fd_refresh_force_years(datetime.now())
    assert call["overwrite"] is False, "history must not be re-downloaded every night"


def test_without_refresh_an_index_on_disk_is_left_alone(monkeypatch):
    call = _run_cli(monkeypatch, "download-house-fd")
    assert call["force_years"] == set()


@pytest.mark.parametrize("step", ["download-house-fd --refresh", "ingest-all"])
def test_nightly_script_runs_the_step(step):
    assert f"src.main {step}" in NIGHTLY_SCRIPT.read_text(encoding="utf-8")


def test_nightly_script_refreshes_the_index_before_ingesting():
    text = NIGHTLY_SCRIPT.read_text(encoding="utf-8")
    assert text.index("download-house-fd --refresh") < text.index("src.main ingest-all")
