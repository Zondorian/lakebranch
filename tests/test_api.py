"""Tests for the GUI API serialization helpers (no Docker/FastAPI needed)."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal

# The GUI (FastAPI) deps are optional; skip these tests when they are absent.
pytest = __import__("pytest")
pytest.importorskip("fastapi")

from src.lakebranch.api.app import _json_safe


def test_json_safe_scalars():
    assert _json_safe(None) is None
    assert _json_safe(42) == 42
    assert _json_safe("x") == "x"


def test_json_safe_datetime_and_date():
    assert _json_safe(
        datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)
    ) == "2026-08-01T10:30:00+00:00"
    assert _json_safe(date(2026, 8, 1)) == "2026-08-01"


def test_json_safe_decimal():
    assert _json_safe(Decimal("49.99")) == 49.99


def test_json_safe_nan_to_none():
    assert _json_safe(math.nan) is None
    assert _json_safe(math.inf) is None


def test_json_safe_bytes_decodes():
    assert _json_safe(b"hello") == "hello"
    assert _json_safe(b"\xff\xfe") == "fffe"