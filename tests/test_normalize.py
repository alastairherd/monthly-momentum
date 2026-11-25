"""Tests for ticker, percentage, and calendar normalization helpers."""

from __future__ import annotations

from datetime import date

import pytest

from monthly_momentum.normalize import (
    add_months,
    first_weekday_of_month,
    months_between,
    normalize_month,
    normalize_ticker,
    parse_flexible_date,
    parse_percent,
    subtract_calendar_months,
    subtract_calendar_years,
    to_yahoo_ticker,
)


def test_normalize_and_yahoo_ticker_mapping() -> None:
    assert normalize_ticker("  $brk-b ") == "BRK.B"
    assert normalize_ticker("BF-B") == "BF.B"
    assert normalize_ticker("azn.l") == "AZN.L"
    assert normalize_ticker("ry.to") == "RY.TO"
    assert normalize_ticker("^sp500tr") == "^SP500TR"

    assert to_yahoo_ticker("BRK.B") == "BRK-B"
    assert to_yahoo_ticker("BF.B") == "BF-B"
    assert to_yahoo_ticker("AZN.L") == "AZN.L"
    assert to_yahoo_ticker("RY.TO") == "RY.TO"
    assert to_yahoo_ticker("^SP500TR") == "^SP500TR"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("145.23%", 145.23),
        ("+12.5%", 12.5),
        ("-4.2%", -4.2),
        ("(4.2%)", -4.2),
        ("1,234.5%", 1234.5),
        ("0.00%", 0.0),
        (42, 42.0),
        (0.0, 0.0),
        ("", None),
        ("-", None),
        ("--", None),
        ("N/A", None),
        ("nan", None),
        (None, None),
        (True, None),
    ],
)
def test_parse_percent(raw: str | float | int | None, expected: float | None) -> None:
    assert parse_percent(raw) == expected


def test_month_and_calendar_date_helpers() -> None:
    assert normalize_month("2026-11-02") == "2026-11"
    assert normalize_month("2026-11") == "2026-11"
    with pytest.raises(ValueError):
        normalize_month("2026-13")

    assert months_between("2020-01", "2026-01") == 72
    assert months_between("2026-02", "2026-01") == -1
    assert add_months("2026-11", 2) == "2027-01"
    assert add_months("2026-02", -3) == "2025-11"

    # Leap-year Feb 29 handling
    assert subtract_calendar_years(date(2024, 2, 29), 3) == date(2021, 2, 28)
    assert subtract_calendar_months(date(2024, 5, 31), 3) == date(2024, 2, 29)
    assert first_weekday_of_month(2026, 11) == date(2026, 11, 2)
    assert parse_flexible_date("2012-12-03 (approx)") == date(2012, 12, 3)
    assert parse_flexible_date("1957") == date(1957, 1, 1)
