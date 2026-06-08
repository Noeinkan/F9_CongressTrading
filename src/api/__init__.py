"""FastAPI service exposing the congress-trading analytics as JSON.

No Streamlit imports are allowed anywhere under ``src/api``. Data loading and
analytics live in ``repository.py``, ``_constants.py``, ``_format.py``,
``_sparklines.py``, and the ``_*_analytics`` modules.
"""
