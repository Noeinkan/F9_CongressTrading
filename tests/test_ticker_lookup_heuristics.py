"""Unit tests for disclosure-text ticker heuristics (no network)."""

from src.ticker_lookup import (
    _extract_ticker_from_parentheses,
    _is_generic_equity_name,
    _search_name_variants,
    _simplify_for_equity_search,
    _try_bare_ticker_token_match,
    _try_disclosure_parenthetical_match,
)


def test_simplify_does_not_restore_ptr_type_when_only_common_stock():
    assert _simplify_for_equity_search("Common stock (P)") == "Common stock"
    assert _is_generic_equity_name("Common stock (P)")


def test_simplify_strips_common_stock_and_owner_tag():
    assert _simplify_for_equity_search("MSFT Common Stock [PS]") == "MSFT"
    assert _simplify_for_equity_search("JP Morgan Chase & Co. Common") == "JP Morgan Chase & Co."


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


def test_search_variants_normalize_jp_morgan_and_apostrophe():
    variants = _search_name_variants("JP Morgan Chase & Co.")
    assert any(v.replace(" ", "").lower().startswith("jpmorgan") for v in variants)

    lowes = _search_name_variants("Lowe's Companies, Inc.")
    assert any("'" not in v and "Lowes" in v for v in lowes)
