"""Unit tests for disclosure-text ticker heuristics (no network)."""

from src.ticker_lookup import (
    _extract_exchange_prefixed_ticker,
    _extract_ticker_from_parentheses,
    _is_generic_equity_name,
    _search_name_variants,
    _simplify_for_equity_search,
    _try_bare_ticker_token_match,
    _try_disclosure_parenthetical_match,
    _try_exchange_prefixed_ticker_match,
    _try_sec_company_ticker_match,
)


def test_simplify_does_not_restore_ptr_type_when_only_common_stock():
    assert _simplify_for_equity_search("Common stock (P)") == "Common stock"
    assert _is_generic_equity_name("Common stock (P)")


def test_simplify_strips_common_stock_and_owner_tag():
    assert _simplify_for_equity_search("MSFT Common Stock [PS]") == "MSFT"
    assert _simplify_for_equity_search("JP Morgan Chase & Co. Common") == "JP Morgan Chase & Co."


def test_simplify_strips_preferred_adr_ordinary_and_trailing_dash():
    assert _simplify_for_equity_search("Acme Corp Preferred Stock") == "Acme Corp"
    assert _simplify_for_equity_search("Toyota Motor Corp Sponsored ADR") == "Toyota Motor Corp"
    assert (
        _simplify_for_equity_search("Nu Holdings Ltd. Class A Ordinary")
        == "Nu Holdings Ltd."
    )
    assert _simplify_for_equity_search("SpringWorks Therapeutics, Inc. -") == (
        "SpringWorks Therapeutics, Inc."
    )
    assert _simplify_for_equity_search("Willis Towers Watson Public Limited") == (
        "Willis Towers Watson"
    )


def test_simplify_strips_asset_type_codes_with_digits():
    assert _simplify_for_equity_search("Allocate Alpha Fund II LP [OT]") == (
        "Allocate Alpha Fund II LP"
    )


def test_bare_ticker_token_from_msft_common_stock():
    match = _try_bare_ticker_token_match("MSFT Common Stock [PS]")
    assert match is not None
    assert match.ticker == "MSFT"
    assert match.match_source == "disclosure_ticker_token"
    assert match.resolution_status == "exact_match"


def test_bare_ticker_not_inferred_from_company_name():
    assert _try_bare_ticker_token_match("Alphabet Inc. - Class A Common Stock") is None
    assert _try_bare_ticker_token_match("CarterBaldwin [PS]") is None


def test_ptr_type_code_not_extracted_as_ticker():
    assert _extract_ticker_from_parentheses("Common stock (P)") is None
    assert _try_disclosure_parenthetical_match("Common stock (P)") is None
    assert _extract_ticker_from_parentheses("Acme Corp (AAPL)") == "AAPL"


def test_exchange_prefixed_ticker_extraction():
    assert _extract_exchange_prefixed_ticker("Apple Inc NYSE: AAPL") == "AAPL"
    assert _extract_exchange_prefixed_ticker("Microsoft NASDAQ:MSFT Common Stock") == "MSFT"
    match = _try_exchange_prefixed_ticker_match("Something NYSE: BRK.B [ST]")
    assert match is not None
    assert match.ticker == "BRK.B"
    assert match.match_source == "disclosure_exchange_ticker"
    assert match.resolution_status == "exact_match"


def test_search_variants_normalize_jp_morgan_and_apostrophe():
    variants = _search_name_variants("JP Morgan Chase & Co.")
    assert any(v.replace(" ", "").lower().startswith("jpmorgan") for v in variants)

    lowes = _search_name_variants("Lowe's Companies, Inc.")
    assert any("'" not in v and "Lowes" in v for v in lowes)


def test_search_variants_alias_truncated_morgan_chase():
    variants = _search_name_variants("Morgan Chase & Co.")
    assert any("JPMorgan" in v for v in variants)


def test_generic_preferred_and_class_only():
    assert _is_generic_equity_name("Preferred Stock")
    assert _is_generic_equity_name("Class A")
    assert not _is_generic_equity_name("Nu Holdings Ltd. Class A Ordinary")


def test_sec_match_uses_fixture_index(monkeypatch):
    from src import ticker_lookup as tl

    fixture = {
        "jpmorgan chase": "JPM",
        "lowes companies": "LOW",
        "slb limited": "SLB",
        "nu holdings": "NU",
    }

    def fake_match(name, **_kwargs):
        from src.sec_company_tickers import match_sec_company_ticker

        return match_sec_company_ticker(name, index=fixture, fuzzy_min_score=90)

    monkeypatch.setattr(tl, "match_sec_company_ticker", fake_match)

    hit = _try_sec_company_ticker_match("Lowe's Companies, Inc. Common")
    assert hit is not None
    assert hit.ticker == "LOW"
    assert hit.match_source == "sec_company_tickers"

    hit2 = _try_sec_company_ticker_match("Morgan Chase & Co. Common")
    assert hit2 is not None
    assert hit2.ticker == "JPM"

    hit3 = _try_sec_company_ticker_match("Schlumberger N.V. Common Stock")
    assert hit3 is not None
    assert hit3.ticker == "SLB"
