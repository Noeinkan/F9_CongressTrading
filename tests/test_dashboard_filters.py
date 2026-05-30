"""Tests for src.dashboard_shared.filters — verifies the fragment/sidebar fix
and that pure filter logic narrows data correctly."""
from __future__ import annotations

import ast
import inspect
import textwrap
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Sample data shared across tests
# ---------------------------------------------------------------------------
def _sample_transactions() -> pd.DataFrame:
    rows = [
        {
            "member": "Alice Smith",
            "chamber": "House",
            "party": "D",
            "state": "CA",
            "ticker": "AAPL",
            "transaction_type": "P",
            "transaction_date": pd.Timestamp("2024-06-01"),
            "filing_date": pd.Timestamp("2024-06-15"),
            "asset_type": "Stock",
            "asset_name_raw": "Apple Inc",
            "asset_name_normalized": "Apple Inc",
            "issuer_name": "Apple",
            "amount_low": 10_000,
            "amount_high": 20_000,
            "amount_range_raw": "10k-20k",
            "confidence_score": 0.95,
            "review_status": "resolved",
        },
        {
            "member": "Bob Jones",
            "chamber": "Senate",
            "party": "R",
            "state": "TX",
            "ticker": "MSFT",
            "transaction_type": "S",
            "transaction_date": pd.Timestamp("2024-07-10"),
            "filing_date": pd.Timestamp("2024-07-20"),
            "asset_type": "Stock",
            "asset_name_raw": "Microsoft Corp",
            "asset_name_normalized": "Microsoft Corp",
            "issuer_name": "Microsoft",
            "amount_low": 30_000,
            "amount_high": 70_000,
            "amount_range_raw": "30k-70k",
            "confidence_score": 0.40,
            "review_status": "needs_review",
        },
        {
            "member": "Alice Smith",
            "chamber": "House",
            "party": "D",
            "state": "CA",
            "ticker": "",
            "transaction_type": "P",
            "transaction_date": pd.Timestamp("2024-08-01"),
            "filing_date": pd.Timestamp("2024-08-10"),
            "asset_type": "Other",
            "asset_name_raw": "Private Fund X",
            "asset_name_normalized": "Private Fund X",
            "issuer_name": "",
            "amount_low": 1_000,
            "amount_high": 9_000,
            "amount_range_raw": "1k-9k",
            "confidence_score": 0.20,
            "review_status": "needs_review",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Source-level checks — the actual bug regression guard
# ---------------------------------------------------------------------------

class TestNoSidebarInFilterBody:
    """The original bug: st.sidebar.* calls inside a @st.fragment function.
    These tests inspect the source to ensure it never regresses."""

    def test_apply_filters_has_no_st_sidebar(self):
        """_apply_filters must not call st.sidebar.* — widgets go through
        the st.sidebar context set by _apply_filters_fragment."""
        from src.dashboard_shared.filters import _apply_filters
        source = inspect.getsource(_apply_filters)
        tree = ast.parse(textwrap.dedent(source))

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "sidebar":
                if isinstance(node.value, ast.Name) and node.value.id == "st":
                    violations.append(node.lineno)

        assert violations == [], (
            f"_apply_filters still contains st.sidebar at source lines {violations}. "
            "All Streamlit calls inside the fragment must use plain st.* "
            "(the with-st.sidebar context is set by the wrapper)."
        )

    def test_helper_functions_have_no_st_sidebar(self):
        """Helpers called from within the fragment must also avoid st.sidebar."""
        from src.dashboard_shared import filters as mod
        helpers = [
            mod._sidebar_filter_label,
            mod._sidebar_typeahead_select,
            mod._sidebar_slice_bar,
        ]
        for fn in helpers:
            source = inspect.getsource(fn)
            tree = ast.parse(textwrap.dedent(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "sidebar":
                    if isinstance(node.value, ast.Name) and node.value.id == "st":
                        pytest.fail(
                            f"{fn.__name__} contains st.sidebar (line {node.lineno}). "
                            "Must use plain st.* when called from a fragment."
                        )

    def test_call_site_uses_sidebar_context(self):
        """The call site (setup_dashboard_session) must wrap the fragment
        invocation in 'with st.sidebar:' — Streamlit requires the sidebar
        context to be set by the caller, not inside the fragment."""
        from src.dashboard_shared import session as sess_mod
        source = inspect.getsource(sess_mod.setup_dashboard_session)
        assert "with st.sidebar" in source, (
            "setup_dashboard_session must call _apply_filters_fragment "
            "inside 'with st.sidebar:'"
        )

    def test_fragment_decorator_present(self):
        """_apply_filters_fragment must be decorated with @st.fragment."""
        from src.dashboard_shared.filters import _apply_filters_fragment
        assert hasattr(_apply_filters_fragment, "__wrapped__") or "fragment" in str(
            getattr(_apply_filters_fragment, "__qualname__", "")
        ), "_apply_filters_fragment should be decorated with @st.fragment"


# ---------------------------------------------------------------------------
# 2. Filter logic tests (mocked Streamlit widgets)
# ---------------------------------------------------------------------------

def _make_widget_defaults():
    """Return a dict of sidebar widget key→default-value that _apply_filters uses,
    so that with default values the filter is a no-op (returns all rows)."""
    return {}


def _mock_st():
    """Build a mock st module whose widgets return pass-through defaults."""
    mock = MagicMock()
    mock.markdown = MagicMock()
    mock.expander = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock(return_value=False)))
    mock.button = MagicMock(return_value=False)
    mock.divider = MagicMock()
    mock.warning = MagicMock()
    mock.rerun = MagicMock()

    def date_input_passthrough(label, value=None, **kw):
        return value

    def multiselect_passthrough(label, options, default=None, **kw):
        return default if default is not None else options

    def slider_passthrough(label, min_value=0.0, max_value=1.0, value=0.0, **kw):
        return value

    def selectbox_passthrough(label, options, index=None, **kw):
        return None

    def pills_passthrough(label, options, default=None, **kw):
        return default if default is not None else options

    mock.date_input = date_input_passthrough
    mock.multiselect = multiselect_passthrough
    mock.slider = slider_passthrough
    mock.selectbox = selectbox_passthrough
    mock.pills = pills_passthrough
    mock.columns = lambda spec, **kw: [MagicMock() for _ in (spec if isinstance(spec, list) else range(spec))]
    return mock


class TestApplyFiltersLogic:
    """Test the pure filter logic with mocked Streamlit widgets."""

    def test_default_filters_return_all_rows(self):
        """With default widget values the full dataset should pass through."""
        data = _sample_transactions()
        mock = _mock_st()
        with patch("src.dashboard_shared.filters.st", mock), \
             patch("src.dashboard_shared.filters._copy", return_value="stub"):
            from src.dashboard_shared.filters import _apply_filters
            result = _apply_filters(data)

        assert len(result) == len(data)

    def test_confidence_filter_narrows_rows(self):
        """Setting a high confidence threshold should exclude low-confidence rows."""
        data = _sample_transactions()
        mock = _mock_st()
        mock.slider = lambda label, min_value=0.0, max_value=1.0, value=0.0, **kw: 0.5

        with patch("src.dashboard_shared.filters.st", mock), \
             patch("src.dashboard_shared.filters._copy", return_value="stub"):
            from src.dashboard_shared.filters import _apply_filters
            result = _apply_filters(data)

        assert len(result) < len(data)
        assert (result["confidence_score"] >= 0.5).all()

    def test_chamber_filter_limits_to_house(self):
        """Selecting only 'House' should drop Senate rows."""
        data = _sample_transactions()
        mock = _mock_st()

        def multiselect_house_only(label, options, default=None, **kw):
            if "Chamber" in label:
                return ["House"]
            return default if default is not None else options

        mock.multiselect = multiselect_house_only

        with patch("src.dashboard_shared.filters.st", mock), \
             patch("src.dashboard_shared.filters._copy", return_value="stub"):
            from src.dashboard_shared.filters import _apply_filters
            result = _apply_filters(data)

        assert (result["chamber"] == "House").all()
        assert len(result) == 2


class TestPeriodFilter:
    def test_all_years_and_quarters_returns_full_dataset(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter, _available_years

        years = _available_years(data)
        result = _apply_period_filter(
            data,
            selected_years=years,
            selected_quarters=[1, 2, 3, 4],
            all_years=years,
        )
        assert len(result) == len(data)

    def test_single_quarter_narrows_rows(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter, _available_years

        years = _available_years(data)
        result = _apply_period_filter(
            data,
            selected_years=years,
            selected_quarters=[2],
            all_years=years,
        )
        assert len(result) == 1
        assert result.iloc[0]["member"] == "Alice Smith"

    def test_single_year_narrows_rows(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter

        result = _apply_period_filter(
            data,
            selected_years=[2024],
            selected_quarters=[1, 2, 3, 4],
            all_years=[2024],
        )
        assert len(result) == len(data)

    def test_empty_year_selection_returns_no_rows(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter, _available_years

        years = _available_years(data)
        result = _apply_period_filter(
            data,
            selected_years=[],
            selected_quarters=[1, 2, 3, 4],
            all_years=years,
        )
        assert result.empty

    def test_year_range_selection_inclusive_and_order_independent(self):
        from src.dashboard_shared.filters import _year_range_selection

        years = [2019, 2020, 2021, 2022, 2024]
        assert _year_range_selection(years, 2022, 2020) == [2020, 2021, 2022]
        assert _year_range_selection(years, 2024, 2024) == [2024]
        assert _year_range_selection(years, 2018, 2025) == years
