"""Column-wise signed amounts must agree exactly with the per-row reference rules."""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from src.api._patterns_analytics import (
    signed_trade_ceiling,
    signed_trade_floor,
    signed_trade_notional,
)
from src.api._signed_amounts import signed_trade_bounds_series, signed_trade_notional_series

_TYPES = ["P", "S", "S (partial)", "E", "P (Buy)", "S (Sell)", "E (Exchange)", "unknown", "", None, np.nan]
_AMOUNTS = [1001.0, 15000.0, 584.22, 0.0, -50.0, None, np.nan, "250000", "n/a"]


def _grid() -> pd.DataFrame:
    rows = [
        {"transaction_type": tt, "amount_low": lo, "amount_high": hi}
        for tt, lo, hi in itertools.product(_TYPES, _AMOUNTS, _AMOUNTS)
    ]
    return pd.DataFrame(rows, dtype=object)


def _assert_same(actual: pd.Series, expected: pd.Series) -> None:
    for got, want in zip(actual.tolist(), expected.tolist(), strict=True):
        assert got == want
        # A sell with no amount must be 0.0, not -0.0 (it would print as "-$0").
        assert math.copysign(1.0, got) == math.copysign(1.0, want)


def test_notional_matches_row_rule() -> None:
    frame = _grid()
    _assert_same(signed_trade_notional_series(frame), frame.apply(signed_trade_notional, axis=1))


def test_bounds_match_row_rules() -> None:
    frame = _grid()
    floor, ceiling = signed_trade_bounds_series(frame)
    _assert_same(floor, frame.apply(signed_trade_floor, axis=1))
    _assert_same(ceiling, frame.apply(signed_trade_ceiling, axis=1))


def test_keeps_the_frame_index() -> None:
    frame = _grid().iloc[::7].copy()
    assert signed_trade_notional_series(frame).index.equals(frame.index)
    floor, ceiling = signed_trade_bounds_series(frame)
    assert floor.index.equals(frame.index) and ceiling.index.equals(frame.index)


def test_empty_and_missing_columns() -> None:
    assert signed_trade_notional_series(pd.DataFrame()).empty
    floor, ceiling = signed_trade_bounds_series(pd.DataFrame())
    assert floor.empty and ceiling.empty

    no_type = pd.DataFrame({"amount_low": [1000.0], "amount_high": [2000.0]})
    assert signed_trade_notional_series(no_type).tolist() == [0.0]
