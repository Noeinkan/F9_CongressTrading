"""Public demo mode: a frozen, read-only slice of the dashboard for strangers.

Everything demo-specific lives here so the rest of ``src/`` stays unaware of it.
The seams into the app are three lines in :mod:`src.api.app` (middleware +
router) and the ``CONGRESS_DB_PATH`` override in :mod:`src.config`.

Off unless ``DEMO_MODE`` is set — see ``docs/DEMO.md``.
"""
