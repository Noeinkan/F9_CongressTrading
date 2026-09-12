"""Outbound notifications for the tracker (Telegram).

Import the specific module you need — ``service`` for the orchestrated runs the
CLI calls, ``events`` for the detection rules, ``settings`` for the env
contract. Nothing is imported here so ``python -m src.main <other command>``
does not pay for pandas it will not use.

Layout:

===================  ======================================================
``settings.py``      Env-driven thresholds and credentials
``telegram.py``      Delivery, retries, 4096-char splitting, loud failures
``state.py``         High-water mark and cluster log (SQLite, created lazily)
``query.py``         The one query the dashboard does not have: what is new
``events.py``        Detection policy — what is worth a message (pure)
``format.py``        Telegram HTML rendering
``digest.py``        Weekly roundup + pipeline health (pure)
``service.py``       Orchestration called by the CLI
===================  ======================================================
"""
