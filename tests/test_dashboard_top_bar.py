"""Tests for custom dashboard top bar and page dispatch."""
from __future__ import annotations

from src.dashboard_shared.top_bar import (
    DEFAULT_PAGE,
    NAV_ITEMS,
    PAGE_KEYS,
    build_top_bar_html,
    get_page_renderers,
    resolve_active_page,
)


class TestResolveActivePage:
    def test_defaults_to_home(self) -> None:
        assert resolve_active_page(None) == DEFAULT_PAGE
        assert resolve_active_page("") == DEFAULT_PAGE

    def test_known_keys(self) -> None:
        for key, _ in NAV_ITEMS:
            assert resolve_active_page(key) == key

    def test_unknown_falls_back_to_home(self) -> None:
        assert resolve_active_page("not-a-page") == DEFAULT_PAGE


class TestBuildTopBarHtml:
    def test_active_page_gets_aria_current(self) -> None:
        html_out = build_top_bar_html(active_page="members")
        assert 'aria-current="page" data-page="members"' in html_out
        assert 'aria-current="page" data-page="home"' not in html_out

    def test_only_one_active_link(self) -> None:
        html_out = build_top_bar_html(active_page="tickers")
        assert html_out.count('aria-current="page"') == 1

    def test_brand_label_escaped(self) -> None:
        from src.dashboard_shared.top_bar import build_top_bar_brand_html

        html_out = build_top_bar_brand_html(brand="Test & Co")
        assert "Test &amp; Co" in html_out


class TestPageDispatchRegistry:
    def test_registry_covers_all_nav_items(self) -> None:
        renderers = get_page_renderers()
        assert set(renderers.keys()) == PAGE_KEYS
        assert set(renderers.keys()) == {key for key, _ in NAV_ITEMS}

    def test_registry_values_are_callable(self) -> None:
        renderers = get_page_renderers()
        for key in PAGE_KEYS:
            assert callable(renderers[key]), key
