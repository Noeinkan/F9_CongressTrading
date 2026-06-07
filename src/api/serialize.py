"""Helpers to turn pandas frames/values into JSON-safe primitives."""
from __future__ import annotations

import math
from typing import Any, cast

import pandas as pd


def iso_date(value: Any) -> str | None:
    """Format a date/Timestamp as YYYY-MM-DD, or None when missing."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if ts is pd.NaT or pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d")


def clean(value: Any) -> Any:
    """Coerce a scalar to a JSON-safe value (NaN/NaT -> None, numpy -> python)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return iso_date(value)
    try:
        if pd.isna(value):  # handles NaT, pandas NA
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):  # numpy scalar
        try:
            return cast(Any, value).item()
        except (ValueError, AttributeError):
            pass
    return value


def records(frame: pd.DataFrame, columns: list[str], *, date_columns: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Convert selected columns of a frame to a list of JSON-safe dicts."""
    if frame.empty:
        return []
    present = [c for c in columns if c in frame.columns]
    out: list[dict[str, Any]] = []
    for _, row in frame[present].iterrows():
        item: dict[str, Any] = {}
        for col in present:
            val = row[col]
            item[col] = iso_date(val) if col in date_columns else clean(val)
        out.append(item)
    return out
