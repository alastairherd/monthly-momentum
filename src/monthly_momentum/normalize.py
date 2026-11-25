"""Ticker, percentage, and calendar-date normalization helpers."""

from __future__ import annotations

import calendar
import math
import re
from datetime import date, timedelta

# Recognized exchange suffixes that should remain dot-separated even in Yahoo Finance.
EXCHANGE_SUFFIXES: frozenset[str] = frozenset(
    {
        "L",
        "TO",
        "V",
        "PA",
        "DE",
        "SW",
        "AS",
        "MI",
        "MC",
        "ST",
        "CO",
        "OL",
        "HE",
        "AX",
        "HK",
        "T",
        "SI",
        "NX",
        "BR",
        "LS",
        "VI",
        "IR",
    }
)

_NULL_PERCENT_TOKENS: frozenset[str] = frozenset(
    {"", "-", "--", "—", "N/A", "NA", "NONE", "NULL", "NAN"}
)
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})(?:-\d{2})?$")
_FLEX_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_FLEX_MONTH_RE = re.compile(r"(\d{4})-(\d{2})")
_FLEX_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")


def normalize_ticker(raw: str) -> str:
    """Normalize a security ticker to canonical uppercase format.

    US share classes written with hyphens (e.g., ``BRK-B``, ``BF-B``) are
    normalized to dot notation (``BRK.B``, ``BF.B``), while exchange suffixes
    such as ``AZN.L`` or ``RY.TO`` and index symbols like ``^SP500TR`` are preserved.
    """
    cleaned = raw.strip().lstrip("$").upper()
    if not cleaned:
        return ""
    if "-" in cleaned and "." not in cleaned and not cleaned.startswith("^"):
        base, suffix = cleaned.rsplit("-", 1)
        if base and len(suffix) == 1 and suffix.isalpha() and suffix not in EXCHANGE_SUFFIXES:
            return f"{base}.{suffix}"
    return cleaned


def ticker_match_key(raw: str) -> str:
    """Return canonical comparison key for cross-source ticker matching."""
    return normalize_ticker(raw)


def to_yahoo_ticker(ticker: str) -> str:
    """Convert canonical ticker to Yahoo Finance symbol format.

    Converts US single-letter share classes (``BRK.B`` -> ``BRK-B``) while
    leaving exchange suffixes like ``AZN.L`` or ``SHOP.TO`` untouched.
    """
    normalized = normalize_ticker(ticker)
    if "." in normalized and not normalized.startswith("^"):
        base, suffix = normalized.rsplit(".", 1)
        if base and len(suffix) == 1 and suffix.isalpha() and suffix not in EXCHANGE_SUFFIXES:
            return f"{base}-{suffix}"
    return normalized


def parse_percent(raw: str | float | int | None) -> float | None:
    """Parse a percentage string or numeric value into a float percentage."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if math.isfinite(val) else None

    text = raw.strip()
    if text.upper() in _NULL_PERCENT_TOKENS:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    text = text.replace("%", "").replace(",", "").replace("+", "").strip()
    if text.upper() in _NULL_PERCENT_TOKENS:
        return None

    try:
        val = float(text)
    except ValueError:
        return None

    if not math.isfinite(val):
        return None
    if negative:
        val = -abs(val)
    return val


def normalize_month(raw: str) -> str:
    """Validate and normalize ``YYYY-MM`` or ``YYYY-MM-DD`` to ``YYYY-MM``."""
    text = raw.strip()
    match = _MONTH_RE.match(text)
    if not match:
        raise ValueError(f"Invalid month format {raw!r}; expected YYYY-MM or YYYY-MM-DD.")
    year = int(match.group(1))
    month = int(match.group(2))
    if not (1900 <= year <= 2100) or not (1 <= month <= 12):
        raise ValueError(f"Month out of valid range: {raw!r}.")
    return f"{year:04d}-{month:02d}"


def months_between(start_month: str, end_month: str) -> int:
    """Return signed integer number of calendar months from ``start_month`` to ``end_month``."""
    s_norm = normalize_month(start_month)
    e_norm = normalize_month(end_month)
    s_year, s_month = int(s_norm[:4]), int(s_norm[5:7])
    e_year, e_month = int(e_norm[:4]), int(e_norm[5:7])
    return (e_year - s_year) * 12 + (e_month - s_month)


def add_months(month: str, delta: int) -> str:
    """Shift a ``YYYY-MM`` month string by ``delta`` calendar months."""
    norm = normalize_month(month)
    year = int(norm[:4])
    mon = int(norm[5:7])
    total = year * 12 + (mon - 1) + delta
    new_year, new_mon_zero = divmod(total, 12)
    return f"{new_year:04d}-{new_mon_zero + 1:02d}"


def subtract_calendar_months(d: date, months: int) -> date:
    """Subtract ``months`` calendar months from ``d``, clamping to valid month end."""
    total = d.year * 12 + (d.month - 1) - months
    new_year, new_mon_zero = divmod(total, 12)
    new_month = new_mon_zero + 1
    max_day = calendar.monthrange(new_year, new_month)[1]
    return date(new_year, new_month, min(d.day, max_day))


def subtract_calendar_years(d: date, years: int) -> date:
    """Subtract ``years`` calendar years from ``d``, handling leap days safely."""
    return subtract_calendar_months(d, years * 12)


def first_weekday_of_month(year: int, month: int) -> date:
    """Return the first weekday (Mon-Fri) of the given calendar month."""
    current = date(year, month, 1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def parse_flexible_date(raw: str) -> date | None:
    """Parse flexible date representations such as Wikipedia's ``Date added`` strings."""
    text = raw.strip()
    if not text:
        return None
    full_match = _FLEX_DATE_RE.search(text)
    if full_match:
        y, m, d = int(full_match.group(1)), int(full_match.group(2)), int(full_match.group(3))
        try:
            return date(y, m, d)
        except ValueError:
            return None
    month_match = _FLEX_MONTH_RE.search(text)
    if month_match:
        y, m = int(month_match.group(1)), int(month_match.group(2))
        if 1 <= m <= 12:
            return date(y, m, 1)
    year_match = _FLEX_YEAR_RE.search(text)
    if year_match:
        return date(int(year_match.group(1)), 1, 1)
    return None
