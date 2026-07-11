from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No live Polygon/OpenFIGI during tests; quieter progress bars."""
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    monkeypatch.setenv("CONGRESS_SKIP_POLYGON_TICKER_DETAILS", "1")
    monkeypatch.setenv("TQDM_DISABLE", "1")
    monkeypatch.delenv("CONGRESS_RE_RESOLVE_TICKERS_BULK", raising=False)
    monkeypatch.delenv("CONGRESS_DISABLE_RE_RESOLVE_OPENFIGI_BATCH", raising=False)


# ---------------------------------------------------------------------------
# Hard guard: tests must NEVER touch the production SQLite
# ---------------------------------------------------------------------------
# Without this, any test that forgets to pass a ``db_path`` to
# ``get_connection()`` (or to ``src.config.DB_PATH``) silently writes to
# ``data/db/congress_trades.sqlite`` — the same file the FastAPI service
# reads on the VPS. We redirect every connection to a per-test tmp SQLite
# so test pollution cannot bleed into the live database.
#
# Production impact: none. ``src.api`` is launched directly by systemd with
# the repo as ``WorkingDirectory``; it never runs under pytest, so the
# monkeypatch below never applies there. Locally it only affects
# ``pytest``, not ``python -m src.api`` or ``python -m src.main ...``.
_PROD_DB_PATH = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "data", "db", "congress_trades.sqlite")
)


@pytest.fixture(autouse=True)
def _isolated_test_db(monkeypatch: pytest.MonkeyPatch, tmp_path, request) -> None:
    """Redirect every SQLite connection to a per-test tmp file.

    Per-test (not session) so failures don't leak across tests. Existing
    fixtures like ``in_memory_db`` / ``seeded_db`` that already point
    ``DB_PATH`` at their own tmp file win because they run *after* this one
    and re-monkeypatch the same attribute. Tests that genuinely need the
    production DB (none today) can opt out with ``@pytest.mark.allow_prod_db``.
    """
    if "allow_prod_db" in request.keywords:
        return

    test_db = tmp_path / "congress_trades.sqlite"
    # Monkeypatch both the module-level constants and every cached binding
    # the codebase imports at module load (``from .config import DB_PATH``
    # style). We patch the source-of-truth attribute on ``src.config`` plus
    # ``src.db`` (which imports DB_PATH for its own default).
    monkeypatch.setattr("src.config.DB_PATH", test_db)
    monkeypatch.setattr("src.db.DB_PATH", test_db)

    # Also patch the cached binding inside any module that already did
    # ``from .config import DB_PATH`` at import time. Iterate src.* lazily
    # so we don't force-import test-only modules here.
    import sys

    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("src.") or module is None:
            continue
        cached = getattr(module, "DB_PATH", None)
        if cached is None:
            continue
        try:
            if os.path.realpath(str(cached)) == _PROD_DB_PATH:
                monkeypatch.setattr(module, "DB_PATH", test_db, raising=False)
        except (TypeError, OSError):
            # Non-path-like binding (e.g. a mock object); skip.
            continue

    # Initialize the schema so tests that read/write immediately work.
    from src.db import get_connection, init_db

    conn = get_connection()
    try:
        init_db(conn)
    finally:
        conn.close()

    yield

    # Guard rail: if anything bypassed the monkeypatch and the test still
    # pointed at the production DB, the prod file's mtime would have been
    # touched. Cheap O(1) stat — only fires if pytest itself recorded a
    # write to the real path, which should never happen.
    try:
        real_prod = _PROD_DB_PATH
        if os.path.exists(real_prod):
            # We can't easily compare mtimes without a baseline, but the
            # ``src.config.DB_PATH`` re-resolution below is the real check.
            pass
    except OSError:
        pass

    # Final assertion: after the test, src.config.DB_PATH must NOT resolve
    # to the production database. If a test somehow unmasked it, fail loud.
    import src.config as config_module

    try:
        resolved = os.path.realpath(str(config_module.DB_PATH))
    except (TypeError, OSError):
        return
    if resolved == _PROD_DB_PATH:
        pytest.fail(
            f"Test {request.nodeid} resolved DB_PATH back to the production "
            f"database ({resolved}). This should never happen with the "
            f"_isolated_test_db autouse fixture in place."
        )