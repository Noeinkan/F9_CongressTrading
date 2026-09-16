"""The demo's email gate: one verified address, one 45-minute session, a usage log.

One file per job:

- ``settings`` -- every number and switch, from env vars; ``problems()`` stops the start
- ``emails``   -- validation, the canonical form a session is keyed on, throwaway domains
- ``store``    -- visitors, codes, grants, events (SQLite on a Docker volume)
- ``mailer``   -- SMTP through the mail relay, or the console for local runs and tests
- ``relay``    -- the relay itself: the one door out of the sealed demo network
- ``messages`` -- the privacy note and the emails
- ``service``  -- the gate's state and its two hooks (``visitor_for``, ``record``)
- ``gate``     -- the middleware in front of every request, and the sign-in API
- ``admin``    -- the owner's page at ``/admin`` and its CSV exports

Nothing here imports at package level, so ``python -m src.demo.access.relay`` stays
a few lines of stdlib. See ``docs/DEMO.md``.
"""
