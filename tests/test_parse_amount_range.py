"""Disclosure amount parsing and bound repair."""
from __future__ import annotations

import pandas as pd

from src.api._home_analytics import _dedupe_cumulative_trades
from src.utils import coerce_amount_bounds, parse_amount_range


def test_exact_amount_with_cents_not_split():
    assert parse_amount_range("$584.22") == (584, 584)
    assert parse_amount_range("$1,118.07") == (1_118, 1_118)
    assert parse_amount_range("$15.00") == (15, 15)


def test_standard_bucket_range():
    assert parse_amount_range("$1,001 - $15,000") == (1_001, 15_000)
    assert parse_amount_range("$15,001 - $50,000") == (15_001, 50_000)


def test_truncated_bucket_high_repaired():
    assert parse_amount_range("$15,001 - 5") == (15_001, 50_000)
    assert parse_amount_range("$15,001 - 08") == (15_001, 50_000)
    assert parse_amount_range("$250,001 - 5") == (250_001, 500_000)
    assert parse_amount_range("$5,000,001 - 2000") == (5_000_001, 25_000_000)


def test_coerce_prefers_raw_over_bad_stored_bounds():
    lo, hi = coerce_amount_bounds(584.0, 22.0, "$584.22")
    assert lo == 584.0
    assert hi == 584.0
    lo, hi = coerce_amount_bounds(15_001.0, 5.0, "$15,001 - 5")
    assert lo == 15_001.0
    assert hi == 50_000.0


def test_dedupe_keeps_spouse_and_distinct_asset_labels():
    frame = pd.DataFrame(
        [
            {
                "member": "A",
                "transaction_date": "2024-01-01",
                "transaction_type": "P",
                "amount_low": 1001,
                "amount_high": 15000,
                "filing_date": "2024-02-01",
                "owner_type": "",
                "asset_name_raw": "Microsoft Corporation - Common",
            },
            {
                "member": "A",
                "transaction_date": "2024-01-01",
                "transaction_type": "P",
                "amount_low": 1001,
                "amount_high": 15000,
                "filing_date": "2024-02-01",
                "owner_type": "spouse",
                "asset_name_raw": "SP Microsoft Corporation - Common",
            },
            {
                "member": "A",
                "transaction_date": "2024-01-01",
                "transaction_type": "P",
                "amount_low": 1001,
                "amount_high": 15000,
                "filing_date": "2024-02-01",
                "owner_type": "",
                "asset_name_raw": "Microsoft Corporation - Common",
            },
        ]
    )
    out = _dedupe_cumulative_trades(frame)
    assert len(out) == 2


def test_dedupe_keeps_identical_looking_rows_with_distinct_source_hash():
    frame = pd.DataFrame(
        [
            {
                "member": "A",
                "transaction_date": "2024-01-01",
                "transaction_type": "P",
                "amount_low": 100001,
                "amount_high": 100001,
                "filing_date": "2024-02-01",
                "owner_type": "",
                "asset_name_raw": "Amazon.com, Inc. - Common Stock",
                "source_hash": "hash-a",
            },
            {
                "member": "A",
                "transaction_date": "2024-01-01",
                "transaction_type": "P",
                "amount_low": 100001,
                "amount_high": 100001,
                "filing_date": "2024-02-01",
                "owner_type": "",
                "asset_name_raw": "Amazon.com, Inc. - Common Stock",
                "source_hash": "hash-b",
            },
            {
                "member": "A",
                "transaction_date": "2024-01-01",
                "transaction_type": "P",
                "amount_low": 100001,
                "amount_high": 100001,
                "filing_date": "2024-02-01",
                "owner_type": "",
                "asset_name_raw": "Amazon.com, Inc. - Common Stock",
                "source_hash": "hash-a",
            },
        ]
    )
    out = _dedupe_cumulative_trades(frame)
    assert len(out) == 2
    assert set(out["source_hash"]) == {"hash-a", "hash-b"}
