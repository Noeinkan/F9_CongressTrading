"""FastAPI service exposing the congress-trading analytics as JSON.

This package is the clean boundary that replaces the Streamlit dashboard:
*no Streamlit imports are allowed anywhere under ``src/api``*. It reuses the
pure-Python analytics in ``src.dashboard_shared.analytics`` /
``kpi_sparklines`` / ``constants`` and the database layer in ``src.db``, but
loads and prepares data through its own Streamlit-free ``repository`` module.
"""
