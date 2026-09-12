"""Column-wise signed trade amounts.

Same rules as the per-row ``signed_trade_notional`` / ``signed_trade_floor`` /
``signed_trade_ceiling`` in ``_patterns_analytics``, computed over a whole
frame at once. The per-row versions stay the readable reference;
``tests/test_signed_amounts.py`` holds the two in agreement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .repository import is_buy_transaction_type, is_sell_transaction_type


def _positive_amounts(frame: pd.DataFrame, column: str) -> pd.Series:
    """Column as float; missing, non-numeric and non-positive values become NaN."""
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return values.where(values > 0)


def _trade_sign(frame: pd.DataFrame) -> pd.Series:
    """+1 for buys, -1 for sells, 0 for anything else (buy wins a tie)."""
    if "transaction_type" not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    kinds = frame["transaction_type"]
    is_buy = kinds.map(is_buy_transaction_type).astype(bool)
    is_sell = kinds.map(is_sell_transaction_type).astype(bool)
    return pd.Series(np.where(is_buy, 1.0, np.where(is_sell, -1.0, 0.0)), index=frame.index)


def signed_trade_notional_series(frame: pd.DataFrame) -> pd.Series:
    """Midpoint of the disclosed range, signed by direction (0 when unknown)."""
    if frame.empty:
        return pd.Series(dtype=float, index=frame.index)
    low = _positive_amounts(frame, "amount_low")
    high = _positive_amounts(frame, "amount_high")
    midpoint = ((low + high) / 2).fillna(low).fillna(high)
    sign = _trade_sign(frame)
    # np.where rather than midpoint * sign: a sell with no amount must be 0.0, not -0.0.
    signed = np.where(midpoint.notna() & (sign != 0), midpoint * sign, 0.0)
    return pd.Series(signed, index=frame.index)


def signed_trade_bounds_series(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(floor, ceiling) of each trade's signed range.

    Buys span ``+low .. +high``; sells span ``-high .. -low``. A missing side
    collapses onto the other; swapped bounds are put back in order.
    """
    if frame.empty:
        empty = pd.Series(dtype=float, index=frame.index)
        return empty, empty.copy()
    low = _positive_amounts(frame, "amount_low")
    high = _positive_amounts(frame, "amount_high")
    low, high = low.fillna(high), high.fillna(low)
    lower = np.fmin(low, high)
    upper = np.fmax(low, high)
    sign = _trade_sign(frame)
    buy = lower.notna() & (sign > 0)
    sell = lower.notna() & (sign < 0)
    floor = pd.Series(np.where(buy, lower, np.where(sell, -upper, 0.0)), index=frame.index)
    ceiling = pd.Series(np.where(buy, upper, np.where(sell, -lower, 0.0)), index=frame.index)
    return floor, ceiling
