"""Tests for Finviz, Market Chameleon, and canonical screener CSV parsers."""

from __future__ import annotations

from pathlib import Path

from monthly_momentum.parsers import ColumnOverrides, load_screener_csv


def test_load_finviz_csv_with_bom_and_dedup(tmp_path: Path) -> None:
    csv_path = tmp_path / "finviz.csv"
    csv_path.write_text(
        "\ufeffNo.,Ticker,Company,Performance (3 Years),Performance (Quarter)\n"
        "1,NVDA,NVIDIA Corp,850.50%,12.30%\n"
        "2,BRK-B,Berkshire Hathaway,42.10%,-3.20%\n"
        "3,PLTR,Palantir,-,15.00%\n"
        "4,NVDA,NVIDIA Corp,-,-\n",
        encoding="utf-8",
    )

    metrics = load_screener_csv(csv_path, source="auto")
    by_ticker = {m.ticker: m for m in metrics}

    assert len(metrics) == 3
    assert by_ticker["NVDA"].return_3y_pct == 850.50
    assert by_ticker["NVDA"].return_3m_pct == 12.30
    assert by_ticker["NVDA"].return_type == "price_only"
    assert by_ticker["NVDA"].source == "finviz"
    assert by_ticker["BRK.B"].return_3m_pct == -3.20
    assert by_ticker["PLTR"].return_3y_pct is None


def test_load_market_chameleon_csv_parenthesized_negatives(tmp_path: Path) -> None:
    csv_path = tmp_path / "mc.csv"
    csv_path.write_text(
        "Symbol,Company Name,3-Year Total Return,3-Month Total Return\n"
        "AVGO,Broadcom Inc.,+310.25%,+8.40%\n"
        "TSLA,Tesla Inc.,+45.00%,(6.15%)\n",
        encoding="utf-8",
    )

    metrics = load_screener_csv(csv_path, source="auto")
    assert len(metrics) == 2
    assert metrics[0].source == "market_chameleon"
    assert metrics[0].return_type == "total_return"
    assert metrics[0].return_3y_pct == 310.25
    assert metrics[1].return_3m_pct == -6.15


def test_canonical_csv_with_index_filter_and_overrides(tmp_path: Path) -> None:
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text(
        "code,co,idx,r3y,r3m\nAAPL,Apple,S&P 500,80.0,4.0\nAZN.L,AstraZeneca,FTSE 100,60.0,2.0\n",
        encoding="utf-8",
    )

    metrics = load_screener_csv(
        csv_path,
        source="canonical",
        index_filter="FTSE 100",
        col_overrides=ColumnOverrides(
            ticker="code",
            name="co",
            index="idx",
            return_3y="r3y",
            return_3m="r3m",
        ),
    )
    assert len(metrics) == 1
    assert metrics[0].ticker == "AZN.L"
    assert metrics[0].index == "FTSE 100"
