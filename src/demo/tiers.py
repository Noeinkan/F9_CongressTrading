"""What a demo visitor may do: open, locked, removed. One list, on the server.

- **Open** -- every read: Home, Senate, Members, Tickers, Patterns, the Raw table,
  the Review queue. They are local reads from the frozen snapshot, so a visit
  costs nothing and nothing is metered.
- **Locked** -- visible in the app, refused here. The CSV downloads (the dataset
  in portable form) and the Review-queue actions. ``/api/demo/status`` hands this
  list to the client, so the button, the wall and the server describe the same
  thing; the client never repeats these strings.
- **Removed** -- not in the demo process at all: the admin router (refresh /
  ingest, deploy, the Telegram digest) is never registered while ``DEMO_MODE`` is
  on (:func:`src.api.app.create_app`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LockedFeature:
    key: str
    label: str
    message: str
    # (method, path); a path ending in "/" matches as a prefix.
    routes: tuple[tuple[str, str], ...]

    def matches(self, method: str, path: str) -> bool:
        method = "GET" if method.upper() == "HEAD" else method.upper()
        path = path.rstrip("/") or "/"
        for want_method, want_path in self.routes:
            if method != want_method:
                continue
            if want_path.endswith("/") and path.startswith(want_path):
                return True
            if path == want_path:
                return True
        return False

    def public(self) -> dict[str, str]:
        return {"feature": self.key, "label": self.label, "message": self.message}


LOCKED_FEATURES: tuple[LockedFeature, ...] = (
    LockedFeature(
        key="csv_export",
        label="CSV downloads",
        message=(
            "Downloading the dataset comes with full access. Every table and chart stays open "
            "on screen for the rest of your session."
        ),
        routes=(("GET", "/api/home/net_trade.csv"), ("GET", "/api/raw/export.csv")),
    ),
    LockedFeature(
        key="review_actions",
        label="Review-queue actions",
        message=(
            "Resolving, accepting and dismissing review rows comes with full access. "
            "The queue itself stays open to read."
        ),
        routes=(("POST", "/api/review/items/"),),
    ),
)

REMOVED_FEATURES = ("disclosure refresh / ingest", "deploy controls", "Telegram alerts and digest")


def locked_feature(method: str, path: str) -> LockedFeature | None:
    for feature in LOCKED_FEATURES:
        if feature.matches(method, path):
            return feature
    return None


def public_locked() -> list[dict[str, str]]:
    return [feature.public() for feature in LOCKED_FEATURES]
