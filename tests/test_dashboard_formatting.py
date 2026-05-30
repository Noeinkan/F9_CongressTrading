from __future__ import annotations



import math



import pandas as pd



from src.dashboard_shared.formatting import (
    add_disclosed_range_column,
    format_count,
    format_currency_compact,
    format_currency_full,
    format_cumulative_net_label,
    format_disclosed_range,
    format_percent,
)





def test_format_count_and_percent():

    assert format_count(12345) == "12,345"

    assert format_count(None) == "—"

    assert format_percent(0.876) == "88%"

    assert format_percent(0.876, decimals=1) == "87.6%"





def test_format_currency_variants():

    assert format_currency_full(12345.6) == "$12,346"

    assert format_currency_compact(1_250_000) == "$1.2M"

    assert format_currency_compact(-4_200) == "-$4.2K"

    assert format_currency_compact(0) == "—"

    assert format_currency_full(math.nan) == "—"

    assert format_cumulative_net_label(0) == "$0 net"

    assert format_cumulative_net_label(-4200) == "-$4.2K net"

    assert format_cumulative_net_label(16001) == "$16.0K net"





def test_format_disclosed_range_and_column():

    assert format_disclosed_range(1001, 15000) == "$1.0K – $15.0K"

    frame = pd.DataFrame({"amount_low_sum": [1000.0], "amount_high_sum": [2_500_000.0]})

    out = add_disclosed_range_column(frame)

    assert out["disclosed_range"].tolist() == ["$1.0K – $2.5M"]

