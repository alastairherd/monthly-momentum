"""Tests for 20-year survivorship-aware US dataset builder and ratio splicing."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from monthly_momentum.live import ConstituentRecord
from monthly_momentum.us20 import (
    build_constituents_history,
    clean_and_collapse_daily_to_monthly,
    extract_sp500_monthly_from_hf,
    splice_price_series,
)


def test_build_constituents_history_closes_removed_and_adds_new() -> None:
    fja_rows = [
        {"ticker": "LEHMQ", "start_date": "1998-01-12", "end_date": "2008-09-17"},
        {"ticker": "OLDCO", "start_date": "2010-01-01", "end_date": ""},
        {"ticker": "AAPL", "start_date": "1996-01-02", "end_date": ""},
    ]
    wiki = [
        ConstituentRecord(
            ticker="AAPL",
            name="Apple Inc.",
            sector="Information Technology",
            date_added="1982-11-30",
        ),
        ConstituentRecord(
            ticker="P", name="Everpure", sector="Information Technology", date_added="2026-09-21"
        ),
    ]
    merged = build_constituents_history(fja_rows, wiki, as_of=date(2026, 11, 25))
    by_t = {r["ticker"]: r for r in merged}

    assert by_t["LEHMQ"]["end_date"] == "2008-09-17"
    assert by_t["OLDCO"]["end_date"] == "2026-11-25"
    assert by_t["AAPL"]["end_date"] == ""
    assert by_t["AAPL"]["name"] == "Apple Inc."
    assert by_t["P"]["start_date"] == "2026-09-21"
    assert by_t["P"]["end_date"] == ""


def test_clean_and_collapse_daily_to_monthly_removes_glitches_keeps_collapse() -> None:
    daily = [
        ("2002-11-29", 10.0, 9.0),  # before min_date
        ("2008-08-29", 16.0, 16.0),
        ("2008-09-02", 15.0, -2788.5),  # corrupt negative adj_close
        ("2008-09-05", 14.0, 500.0),  # isolated 1-day reverting spike glitch
        ("2008-09-08", 14.1, 14.1),
        ("2008-09-17", 0.13, 0.13),  # real collapse intra-month final bar
    ]
    monthly = clean_and_collapse_daily_to_monthly(daily, min_date="2002-12-01")
    assert list(monthly.keys()) == ["2008-08", "2008-09"]
    assert monthly["2008-08"] == (16.0, 16.0)
    assert monthly["2008-09"] == (0.13, 0.13)


def test_splice_price_series_preserves_ratio_continuity() -> None:
    hf = {
        "2014-11": (100.0, 50.0),
        "2014-12": (110.0, 55.0),
        "2015-01": (120.0, 60.0),
    }
    yf = {
        "2014-12": (110.0, 110.0),
        "2015-01": (122.0, 122.0),
    }
    spliced = splice_price_series(hf, yf)
    # 2014-11 HF adj_close (50.0) scales by (110/55 = 2.0) -> 100.0
    assert spliced["2014-11"] == (100.0, 100.0)
    assert spliced["2014-12"] == (110.0, 110.0)
    assert spliced["2015-01"] == (122.0, 122.0)


def test_extract_sp500_monthly_from_local_parquet(tmp_path: Path) -> None:
    shard = tmp_path / "train-00000.parquet"
    table = pa.table(
        {
            "symbol": ["LEH", "AAPL", "AAPL", "OTHER"],
            "date": ["2008-09-17", "2024-01-02", "2024-01-31", "2024-01-31"],
            "close": [0.13, 185.0, 190.0, 10.0],
            "adj_close": [0.13, 184.0, 189.0, 10.0],
        }
    )
    pq.write_table(table, shard)

    extracted = extract_sp500_monthly_from_hf(
        cache_dir=tmp_path,
        target_tickers=["LEHMQ", "AAPL"],
        min_date="2002-12-01",
        parquet_paths=[shard],
    )
    assert extracted["LEHMQ"]["2008-09"] == pytest.approx((0.13, 0.13))
    assert extracted["AAPL"]["2024-01"] == pytest.approx((190.0, 189.0))
    assert "OTHER" not in extracted
