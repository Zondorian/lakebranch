"""
Lakebranch — JSON-safe serialization helpers
============================================

Shared utilities for converting pandas / PyArrow / numpy / datetime values
into plain JSON-serializable Python values.

Used by both the GUI API (``src.lakebranch.api.app``) and the SQL query
engine (``src.lakebranch.sql``) so CLI and API results serialize identically.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    """Convert a pandas/arrow/scalar value into a JSON-serializable Python value."""
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (float,)) and (math.isnan(value) or math.isinf(value)):
        return None
    # pandas Timestamps and numpy scalar types (int64, float64, bool, …)
    # expose .item() / .isoformat() conveniences.
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except (ValueError, TypeError):
            pass
    converter = getattr(value, "item", None)
    if callable(converter):
        try:
            converted = converter()
        except (ValueError, TypeError):
            return str(value)
        return json_safe(converted)
    return value


def df_to_rows(df) -> list[dict[str, Any]]:
    """Convert a pandas DataFrame into a list of JSON-safe row dicts."""
    df = df.where(pd_notnull(df), None)  # NaN → None
    records = df.to_dict(orient="records")
    return [{k: json_safe(v) for k, v in row.items()} for row in records]


def pd_notnull(df):
    """Return a boolean mask mask of non-null entries (NaN-aware).

    Kept as a separate helper so this module does not hard-import pandas at
    import time; ``df_to_rows`` only needs it at call time.
    """
    import pandas as pd

    return pd.notnull(df)