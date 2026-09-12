"""Dollar amounts as a phone screen should show them.

Congress discloses buckets, never exact amounts, so every figure here is a
range or a floor. Kept apart from ``src/api/_format`` on purpose: dashboard
tiles keep one decimal everywhere ("$250.0K") so columns line up, while a chat
message wants the shortest honest string ("$250K").
"""
from __future__ import annotations

import math

_UNITS = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))


def _positive(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or number <= 0:
        return None
    return number


def compact_usd(value: object) -> str:
    """``$15K``, ``$2.5M``, ``$800``; empty string when missing or zero."""
    number = _positive(value)
    if number is None:
        return ""
    for size, suffix in _UNITS:
        if number >= size:
            digits = f"{number / size:.1f}".rstrip("0").rstrip(".")
            return f"${digits}{suffix}"
    return f"${number:,.0f}"


def disclosed_range(low: object, high: object) -> str:
    """``$100K–$250K`` for a bucket; ``$500K+`` when only the floor survived.

    About 1,900 stored rows carry a floor with no ceiling (the PDF line was cut
    after "$500,001"). Printing "$500K–$500K" claims a precision the filing
    does not have.
    """
    lo, hi = compact_usd(low), compact_usd(high)
    if lo and hi and lo != hi:
        return f"{lo}–{hi}"
    if lo:
        return f"{lo}+"
    return hi
