"""What happens after the data is in: CSV exports, then Telegram.

The sidebar Refresh button (``src/api/jobs.py``) calls this once its ingest
finishes, so a click ends the same way a night does: the CSVs match the
database, trades that arrived since the last message go out as alerts, and the
7-day digest follows (unless one went out in the last
``REFRESH_DIGEST_COOLDOWN_HOURS``). ``scripts/nightly_ingest.sh`` runs the same steps as
separate CLI commands, where the digest still waits for its weekday.

No step can fail the run. The ingest already succeeded; a Telegram outage or a
locked CSV is reported in the returned summary and the log, not raised.
"""
from __future__ import annotations

from collections.abc import Callable

from .config import DATA_DIR

_EXPORTS = {
    "congress_trades.csv": "export_csv",
    "fd_filings.csv": "export_fd_csv",
    "review_queue.csv": "export_review_csv",
}


def _run_step(name: str, step: Callable[[], str], log: Callable[[str], None]) -> str:
    try:
        summary = step()
    except Exception as exc:  # noqa: BLE001 - reported, never raised (see module doc)
        summary = f"failed - {type(exc).__name__}: {exc}"
    log(f"{name}: {summary}")
    return summary


def _exports() -> str:
    from . import export_csv as exporters

    for filename, function_name in _EXPORTS.items():
        getattr(exporters, function_name)(DATA_DIR / filename)
    return f"wrote {', '.join(_EXPORTS)}"


def _alerts() -> str:
    from .notify.service import run_event_notifications

    outcome = run_event_notifications()
    return f"{outcome.status} - {outcome.message}"


# A Refresh sends the digest unless one already went out this recently. Two
# clicks a few minutes apart are usually one intention, not two; the sidebar
# offers "Send digest again" for the rare time a second one is wanted.
REFRESH_DIGEST_COOLDOWN_HOURS = 12


def _digest(force: bool, cooldown_hours: float | None) -> str:
    from .notify.service import run_weekly_digest

    outcome = run_weekly_digest(force=force, cooldown_hours=cooldown_hours)
    return f"{outcome.status} - {outcome.message}"


def _last_digest_at() -> str:
    try:
        from .notify.service import last_digest_sent_at

        return last_digest_sent_at()
    except Exception:  # noqa: BLE001 - a missing timestamp only hides a hint
        return ""


def run_post_ingest(
    *,
    force_digest: bool,
    digest_cooldown_hours: float | None = None,
    log: Callable[[str], None] = print,
    progress_hook: Callable[..., None] | None = None,
) -> dict[str, str]:
    """Exports, new-trade alerts, digest. Returns one summary line per step.

    ``force_digest=True`` sends the digest whatever the weekday.
    ``digest_cooldown_hours`` skips it if one went out within that many hours.
    ``progress_hook(label, done, total, unit=...)`` is the job runner's hook.
    The result also carries ``digest_sent_at`` (UTC, '' if never) so the
    sidebar can say when the last digest went out.
    """
    steps: list[tuple[str, str, Callable[[], str]]] = [
        ("exports", "Writing CSV exports", _exports),
        ("alerts", "Sending Telegram alerts", _alerts),
        (
            "digest",
            "Sending Telegram digest",
            lambda: _digest(force_digest, digest_cooldown_hours),
        ),
    ]
    summary: dict[str, str] = {}
    for done, (name, label, step) in enumerate(steps):
        if progress_hook is not None:
            progress_hook(label, done, len(steps), unit="steps")
        summary[name] = _run_step(name, step, log)
    if progress_hook is not None:
        progress_hook("Exports and Telegram done", len(steps), len(steps), unit="steps")
    summary["digest_sent_at"] = _last_digest_at()
    return summary
