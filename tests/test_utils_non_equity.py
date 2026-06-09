"""Pure unit tests for the ``is_non_equity_asset`` heuristic.

The flag drives the dashboard's P&L placeholder ("n/a" for bonds, real
numbers for equities) so the helper needs to be stable across the common
raw-asset shapes the PTR/FD parsers emit: ``[GS]`` (Goldman Sachs custody
account), ``[CS]`` (corporate), ``[ST]`` (stock), ``[OT]`` (other),
CUSIP-tagged Treasury notes, etc.
"""
from __future__ import annotations

import pytest

from src.utils import is_non_equity_asset


@pytest.mark.parametrize(
    "ticker,asset_name_raw,expected",
    [
        # Common equities — should NOT be flagged.
        ("AAPL", "Apple Inc. - Common Stock (AAPL) [ST]", False),
        ("MSFT", "Microsoft Corporation - Common", False),
        ("DASH", "DoorDash, Inc. - A", False),
        ("AEIS", "Advanced Energy Industries [AEIS]", False),
        ("FLEX", "Flex Ltd - Ordinary Shares (FLEX) [ST]", False),
        # Treasury notes / bills / bonds.
        ("UTWO", "US Treasury Note 2/15/2033 [GS]", True),
        ("UFIV", "US Treasury Note 5/15/2028 [GS]", True),
        ("BBIB", "U.S. Treasury Bond [GS]", True),
        ("USVN", "US Treasury Note 01/31/27 [GS]", True),
        ("IUSXX", "U. S. Treasury Bills [GS]", True),
        ("FLGV", "2000116760 U.S. Treasury Bond [GS]", True),
        # Bond funds / ETFs.
        ("FEPIX", "Fidelity Advisor Total Bond CL Z [GS]", True),
        ("BND", "Vanguard Total Bond Market [OT]", True),
        ("BNDX", "Vanguard Total Intl Bond ETF [OT]", True),
        ("IGSB", "iShares 1-5 Year Investment Grade Corporate Bond ETF (IGSB) [ST]", True),
        ("JHG", "Janus Henderson Flexible Bond Fund", True),
        ("FBKWX", "FIDELITY ADVISOR TOTAL BOND CL Z (FBKWX) [OT]", True),
        # Municipal / water / hospital / school district issues.
        ("EML", "Eastern Municipal Water District Financing Authority, CA, Water & Wastewater Rev", True),
        ("NWWDF", "New York Liberty Development Corporation Revenue Bonds [GS]", True),
        # Empty / None inputs.
        ("", "", False),
        ("AAPL", "", False),
        ("", "Apple Inc.", False),
    ],
)
def test_is_non_equity_asset(ticker: str, asset_name_raw: str, expected: bool) -> None:
    assert is_non_equity_asset(ticker, asset_name_raw) is expected
