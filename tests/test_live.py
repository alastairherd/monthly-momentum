"""Tests for Wikipedia S&P 500 parser and yfinance return/monthly-bar extraction."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from monthly_momentum.live import (
    aggregate_completed_monthly_bars,
    compute_returns_from_history,
    extract_yf_price_maps,
    parse_sp500_wikipedia_html,
)


def test_parse_wikipedia_constituents_table() -> None:
    html = """
    <html><body>
      <table class="wikitable sortable" id="constituents">
        <tr>
          <th>Symbol</th><th>Security</th><th>GICS Sector</th>
          <th>GICS Sub-Industry</th><th>Date added</th>
        </tr>
        <tr>
          <td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td>
          <td>Multi-Sector Holdings</td><td>2010-02-16</td>
        </tr>
        <tr>
          <td>AAPL</td><td>Apple Inc.</td><td>Information Technology</td>
          <td>Technology Hardware</td><td>1982-11-30</td>
        </tr>
      </table>
    </body></html>
    """
    records = parse_sp500_wikipedia_html(html)
    assert [r.ticker for r in records] == ["AAPL", "BRK.B"]
    assert records[1].sector == "Financials"
    assert records[1].date_added == "2010-02-16"


def test_compute_returns_uses_adj_for_3y_and_close_for_3m() -> None:
    # Stock doubles on price in 3y, pays big dividend pushing adj_close to 3x (+200%),
    # while price fell -10% in last 3 months.
    close_map = {
        date(2023, 11, 1): 100.0,
        date(2026, 7, 31): 220.0,
        date(2026, 11, 2): 198.0,
    }
    adj_map = {
        date(2023, 11, 1): 80.0,
        date(2026, 7, 31): 215.0,
        date(2026, 11, 2): 240.0,
    }
    ret_3y, ret_3m = compute_returns_from_history(close_map, adj_map, as_of=date(2026, 11, 2))
    assert ret_3y == pytest.approx(200.0)
    assert ret_3m == pytest.approx(-10.0)

    # Stock listed < 3 years ago has missing 3y return.
    short_close = {date(2025, 1, 2): 50.0, date(2026, 7, 31): 60.0, date(2026, 11, 2): 66.0}
    short_adj = {date(2025, 1, 2): 50.0, date(2026, 7, 31): 60.0, date(2026, 11, 2): 66.0}
    s3y, s3m = compute_returns_from_history(short_close, short_adj, as_of=date(2026, 11, 2))
    assert s3y is None
    assert s3m == pytest.approx(10.0)


def test_extract_yf_price_maps_flat_and_multiindex_and_completed_bars() -> None:
    idx = pd.to_datetime(["2026-09-01", "2026-10-01", "2026-11-01", "2026-11-24"])
    flat_df = pd.DataFrame(
        {"Close": [100.0, 110.0, 115.0, 118.0], "Adj Close": [99.0, 109.0, 115.0, 118.0]},
        index=idx,
    )
    flat_maps = extract_yf_price_maps(flat_df, ["BRK-B"])
    assert "BRK-B" in flat_maps
    assert len(flat_maps["BRK-B"][0]) == 4

    cols = pd.MultiIndex.from_tuples(
        [
            ("Close", "AAPL"),
            ("Close", "^SP500TR"),
            ("Adj Close", "AAPL"),
            ("Adj Close", "^SP500TR"),
        ]
    )
    multi_df = pd.DataFrame(
        [
            [200.0, 15000.0, 198.0, 15000.0],
            [210.0, 15400.0, 209.0, 15400.0],
            [215.0, 15900.0, 215.0, 15900.0],
            [220.0, 16176.0, 220.0, 16176.0],
        ],
        index=idx,
        columns=cols,
    )
    multi_maps = extract_yf_price_maps(multi_df, ["AAPL", "^SP500TR"])
    rows = aggregate_completed_monthly_bars(
        multi_maps,
        canonical_by_yahoo={"AAPL": "AAPL", "^SP500TR": "^SP500TR"},
        benchmark_yahoo="^SP500TR",
        as_of=date(2026, 11, 25),
        include_mtd=False,
    )
    # Excludes incomplete 2026-11 (both 2026-11-01 and 2026-11-24 bars), keeps 2026-09 & 2026-10.
    assert [(r["date"], r["ticker"], r["market"]) for r in rows] == [
        ("2026-09-01", "AAPL", "us"),
        ("2026-09-01", "^SP500TR", "benchmark"),
        ("2026-10-01", "AAPL", "us"),
        ("2026-10-01", "^SP500TR", "benchmark"),
    ]
