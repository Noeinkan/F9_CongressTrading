"""Exports + Telegram after an ingest (src/post_ingest.py)."""
from __future__ import annotations

from pathlib import Path

from src import post_ingest
from src.notify.service import STATUS_FAILED, STATUS_SENT, RunOutcome


def _patch(monkeypatch, tmp_path: Path, *, alerts=None, digest=None, exports_fail=False):
    written: list[str] = []
    digest_calls: list[bool] = []

    def exporter(path: Path) -> None:
        if exports_fail:
            raise PermissionError("locked by Excel")
        written.append(path.name)

    for name in ("export_csv", "export_fd_csv", "export_review_csv"):
        monkeypatch.setattr(f"src.export_csv.{name}", exporter)
    monkeypatch.setattr(post_ingest, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "src.notify.service.run_event_notifications",
        alerts or (lambda: RunOutcome(status=STATUS_SENT, message="2 event(s)")),
    )

    def fake_digest(*, force: bool = False, cooldown_hours=None) -> RunOutcome:
        digest_calls.append((force, cooldown_hours))
        if digest:
            return digest()
        return RunOutcome(status=STATUS_SENT, message="weekly digest")

    monkeypatch.setattr("src.notify.service.run_weekly_digest", fake_digest)
    monkeypatch.setattr("src.notify.service.last_digest_sent_at", lambda: "2026-09-12T14:02:00Z")
    return written, digest_calls


def test_runs_exports_alerts_then_forced_digest(monkeypatch, tmp_path):
    written, digest_calls = _patch(monkeypatch, tmp_path)
    lines: list[str] = []
    progress: list[tuple[str, int, int]] = []

    summary = post_ingest.run_post_ingest(
        force_digest=True,
        digest_cooldown_hours=12,
        log=lines.append,
        progress_hook=lambda label, done, total, unit="": progress.append((label, done, total)),
    )

    assert [done for _label, done, _total in progress] == [0, 1, 2, 3]
    assert written == ["congress_trades.csv", "fd_filings.csv", "review_queue.csv"]
    assert digest_calls == [(True, 12)]
    assert summary["alerts"] == "sent - 2 event(s)"
    assert summary["digest"] == "sent - weekly digest"
    assert summary["digest_sent_at"] == "2026-09-12T14:02:00Z"
    assert [line.split(":")[0] for line in lines] == ["exports", "alerts", "digest"]


def test_a_failing_step_does_not_stop_the_others(monkeypatch, tmp_path):
    def broken_alerts() -> RunOutcome:
        raise ConnectionError("telegram down")

    _, digest_calls = _patch(monkeypatch, tmp_path, alerts=broken_alerts, exports_fail=True)

    summary = post_ingest.run_post_ingest(force_digest=False, log=lambda _line: None)

    assert summary["exports"].startswith("failed - PermissionError")
    assert summary["alerts"].startswith("failed - ConnectionError")
    assert digest_calls == [(False, None)]
    assert summary["digest"] == "sent - weekly digest"


def test_undelivered_digest_is_reported_not_raised(monkeypatch, tmp_path):
    _patch(
        monkeypatch,
        tmp_path,
        digest=lambda: RunOutcome(status=STATUS_FAILED, message="digest NOT delivered: 401"),
    )
    summary = post_ingest.run_post_ingest(force_digest=True, log=lambda _line: None)
    assert summary["digest"] == "failed - digest NOT delivered: 401"
