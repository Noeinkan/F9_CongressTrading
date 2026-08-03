"""OGE and House transaction-type classification helpers."""
from __future__ import annotations

import pandas as pd

from src.api._patterns_analytics import (
    add_trade_categories,
    signed_trade_ceiling,
    signed_trade_floor,
    signed_trade_notional,
)
from src.api.repository import (
    is_buy_transaction_type,
    is_exchange_transaction_type,
    is_sell_transaction_type,
    transaction_type_display_label,
)


def test_house_codes():
    assert is_buy_transaction_type("P")
    assert is_sell_transaction_type("S")
    assert is_sell_transaction_type("S (partial)")
    assert is_exchange_transaction_type("E")
    assert not is_buy_transaction_type("S")
    assert not is_sell_transaction_type("P")


def test_oge_codes():
    assert is_buy_transaction_type("P (Buy)")
    assert is_sell_transaction_type("S (Sell)")
    assert is_exchange_transaction_type("E (Exchange)")


def test_display_labels_oge():
    assert transaction_type_display_label("P (Buy)") == "Buy"
    assert transaction_type_display_label("S (Sell)") == "Sell"
    assert transaction_type_display_label("E (Exchange)") == "Exchange"
    assert transaction_type_display_label("P") == "Buy"
    assert transaction_type_display_label("S (partial)") == "Sell (partial)"


def test_signed_trade_notional_oge_buy():
    row = pd.Series(
        {
            "transaction_type": "P (Buy)",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }
    )
    assert signed_trade_notional(row) > 0


def test_signed_trade_notional_oge_sell():
    row = pd.Series(
        {
            "transaction_type": "S (Sell)",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }
    )
    assert signed_trade_notional(row) < 0


def test_signed_trade_floor_ceiling_buy():
    row = pd.Series(
        {
            "transaction_type": "P",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }
    )
    assert signed_trade_floor(row) == 1000.0
    assert signed_trade_ceiling(row) == 15000.0


def test_signed_trade_floor_ceiling_sell_widens_downward():
    """Sells: floor is -amount_high (more negative); ceiling is -amount_low."""
    row = pd.Series(
        {
            "transaction_type": "S",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }
    )
    assert signed_trade_floor(row) == -15000.0
    assert signed_trade_ceiling(row) == -1000.0
    assert signed_trade_floor(row) < signed_trade_ceiling(row)


def test_signed_trade_floor_ceiling_unknown_is_zero():
    row = pd.Series(
        {
            "transaction_type": "E",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }
    )
    assert signed_trade_floor(row) == 0.0
    assert signed_trade_ceiling(row) == 0.0


def test_add_trade_categories_oge():
    frame = pd.DataFrame(
        [
            {
                "transaction_type": "P (Buy)",
                "asset_type": "stock",
                "asset_name_raw": "Apple",
                "asset_name_normalized": "apple",
                "issuer_name": "Apple",
                "party": "R",
            },
            {
                "transaction_type": "E (Exchange)",
                "asset_type": "stock",
                "asset_name_raw": "Apple",
                "asset_name_normalized": "apple",
                "issuer_name": "Apple",
                "party": "D",
            },
        ]
    )
    out = add_trade_categories(frame)
    assert bool(out.iloc[0]["is_buy"]) is True
    assert bool(out.iloc[0]["is_sell"]) is False
    assert bool(out.iloc[1]["is_buy"]) is False
    assert int(out["transaction_type"].map(is_exchange_transaction_type).sum()) == 1
