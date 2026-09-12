"""Where a message can send the reader.

After any alert the next question is "what else has this member traded?" or
"who else is in this ticker?", and the dashboard already answers both. So names
and tickers link into it. The base address comes from
``CONGRESS_DASHBOARD_URL``; left unset, the same text goes out without links.

Paths mirror ``frontend/src/utils/entityLinks.ts`` — change both together.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape as _html_escape
from urllib.parse import quote

from .telegram import escape


def _query(value: str) -> str:
    return quote(value.strip(), safe="")


@dataclass(frozen=True)
class DashboardLinks:
    base_url: str = ""

    @property
    def base(self) -> str:
        url = (self.base_url or "").strip().rstrip("/")
        return url if url.lower().startswith(("http://", "https://")) else ""

    def home(self) -> str:
        return f"{self.base}/" if self.base else ""

    def member(self, name: str) -> str:
        if not self.base or not (name or "").strip():
            return ""
        return f"{self.base}/members?member={_query(name)}"

    def ticker(self, symbol: str) -> str:
        if not self.base or not (symbol or "").strip():
            return ""
        return f"{self.base}/tickers?ticker={_query(symbol.upper())}"

    def raw(self) -> str:
        return f"{self.base}/raw" if self.base else ""


def anchor(url: str, label: str) -> str:
    """``<a>`` for Telegram HTML, or the escaped label alone when there is no URL."""
    url = (url or "").strip()
    text = escape(label)
    if not url.lower().startswith(("http://", "https://")):
        return text
    return f'<a href="{_html_escape(url, quote=True)}">{text}</a>'
