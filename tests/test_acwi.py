"""Tests for iShares MSCI ACWI parsing, UK ISA flagging, sanitizer, FX, and multi-market charts."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from monthly_momentum.acwi import (
    AcwiConstituent,
    classify_uk_accessibility,
    map_acwi_ticker,
    parse_ishares_acwi_csv,
    sanitize_monthly_bars,
    write_acwi_constituents_csv,
)
from monthly_momentum.backtest.data import PricePoint
from monthly_momentum.markets import convert_prices_to_currency
from monthly_momentum.normalize import add_months
from monthly_momentum.report import README_END_MARKER, README_START_MARKER, rebuild_public_reports


def _acwi_csv_row(
    ticker: str,
    name: str,
    sector: str,
    asset_class: str,
    weight: str,
    location: str,
    exchange: str,
    market_curr: str,
) -> str:
    return (
        f'"{ticker}","{name}","{sector}","{asset_class}","100","{weight}",'
        f'"100","10","10","{location}","{exchange}","USD","1.00","{market_curr}","-"'
    )


def test_parse_ishares_acwi_csv_and_ticker_mapping() -> None:
    sample_csv = "\n".join(
        [
            "iShares MSCI ACWI ETF",
            'Fund Holdings as of,"Nov 23, 2026"',
            "Inception Date,Mar 26 2008",
            "",
            "Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,"
            "Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date",
            _acwi_csv_row(
                "AAPL", "APPLE", "Tech", "Equity", "5.35", "United States", "NASDAQ", "USD"
            ),
            _acwi_csv_row(
                "BRK B",
                "BERKSHIRE CLASS B",
                "Financials",
                "Equity",
                "1.50",
                "United States",
                "NYSE",
                "USD",
            ),
            _acwi_csv_row(
                "700",
                "TENCENT",
                "Comm",
                "Equity",
                "0.90",
                "China",
                "Hong Kong Exchanges And Clearing Ltd",
                "HKD",
            ),
            _acwi_csv_row(
                "2330", "TSMC", "Tech", "Equity", "1.59", "Taiwan", "Taiwan Stock Exchange", "TWD"
            ),
            _acwi_csv_row(
                "NOVO B",
                "NOVO NORDISK B",
                "Health",
                "Equity",
                "0.75",
                "Denmark",
                "Omx Nordic Exchange Copenhagen A/S",
                "DKK",
            ),
            _acwi_csv_row(
                "RR.",
                "ROLLS ROYCE",
                "Ind",
                "Equity",
                "0.35",
                "United Kingdom",
                "London Stock Exchange",
                "GBP",
            ),
            _acwi_csv_row("CASH", "USD CASH", "Cash", "Cash", "0.01", "United States", "-", "USD"),
            _acwi_csv_row(
                "HOLX",
                "HOLOGIC",
                "Health",
                "Equity",
                "0.00",
                "United States",
                "NO MARKET (E.G. UNLISTED)",
                "USD",
            ),
        ]
    )
    as_of_label, items, total_eq = parse_ishares_acwi_csv(sample_csv)
    assert as_of_label == "Nov 23, 2026"
    assert total_eq == 7
    by_t = {c.ticker: c for c in items}
    assert "AAPL" in by_t and by_t["AAPL"].uk_accessible is True
    assert "BRK.B" in by_t and by_t["BRK.B"].market == "us"
    assert "0700.HK" in by_t and by_t["0700.HK"].uk_accessible is False
    assert "2330.TW" in by_t and by_t["2330.TW"].uk_accessible is False
    assert "NOVO-B.CO" in by_t and by_t["NOVO-B.CO"].uk_accessible is True
    assert "RR.L" in by_t and by_t["RR.L"].market == "uk" and by_t["RR.L"].uk_accessible is True
    assert "HOLX" not in by_t


def test_map_acwi_ticker_edge_cases_and_accessibility() -> None:
    assert map_acwi_ticker("700", "Hong Kong Exchanges And Clearing Ltd") == "0700.HK"
    assert map_acwi_ticker("BT.A", "London Stock Exchange") == "BT-A.L"
    assert map_acwi_ticker("NDA FI", "Nasdaq Omx Helsinki Ltd.") == "NDA-FI.HE"
    assert map_acwi_ticker("DELTA.R", "Stock Exchange Of Thailand") == "DELTA.BK"
    assert map_acwi_ticker("BIMAS.E", "Istanbul Stock Exchange") == "BIMAS.IS"
    assert map_acwi_ticker("WALMEX*", "Bolsa Mexicana De Valores") == "WALMEX.MX"
    assert map_acwi_ticker("BAAKOMB", "Prague Stock Exchange") == "KOMB.PR"
    assert map_acwi_ticker("532483", "Bse Ltd") == "CANBK.NS"

    ok_us, _ = classify_uk_accessibility("NASDAQ", "United States")
    assert ok_us is True
    ok_eu, _ = classify_uk_accessibility("Xetra", "Germany")
    assert ok_eu is True
    ok_in, note_in = classify_uk_accessibility("National Stock Exchange Of India", "India")
    assert ok_in is False
    assert "India" in note_in or "Non-UK ISA" in note_in
    ok_ru, note_ru = classify_uk_accessibility("London Stock Exchange", "Russian Federation")
    assert ok_ru is False
    assert "Russia" in note_ru


def test_sanitize_monthly_bars_and_fx_conversion() -> None:
    # 1. Isolated 100x single-bar spike-and-revert gets removed, while smooth 4x growth stays.
    bars = [
        ("2022-01-01", 10.0, 10.0),
        ("2022-02-01", 11.0, 11.0),
        ("2022-03-01", 1100.0, 1100.0),  # 100x glitch
        ("2022-04-01", 12.0, 12.0),
        ("2022-05-01", 18.0, 18.0),
    ]
    cleaned = sanitize_monthly_bars(bars)
    assert [b[0] for b in cleaned] == ["2022-01-01", "2022-02-01", "2022-04-01", "2022-05-01"]

    # 2. Step-function 100x unit change truncates pre-break history cleanly.
    step_bars = [
        ("2020-01-01", 5.0, 5.0),
        ("2020-02-01", 5.2, 5.2),
        ("2020-03-01", 520.0, 520.0),
        ("2020-04-01", 530.0, 530.0),
    ]
    step_clean = sanitize_monthly_bars(step_bars)
    assert [b[0] for b in step_clean] == ["2020-03-01", "2020-04-01"]

    # 3. USD{CCY}=X direct FX division with per-ticker quote_currency.
    prices = {
        "2330.TW": {
            "2026-10": PricePoint(
                dt=date(2026, 10, 1),
                month="2026-10",
                ticker="2330.TW",
                close=1000.0,
                adj_close=1200.0,
                market="intl",
            )
        }
    }
    fx = {"USDTWD=X": {"2026-10": 32.0}}
    usd = convert_prices_to_currency(
        prices, fx, target_currency="USD", currency_by_ticker={"2330.TW": "TWD"}
    )
    assert usd["2330.TW"]["2026-10"].close == pytest.approx(31.25)
    assert usd["2330.TW"]["2026-10"].adj_close == pytest.approx(37.5)


def test_end_to_end_acwi_uk_flagging_and_all_market_charts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    global_dir = data_dir / "global"
    global_dir.mkdir(parents=True, exist_ok=True)
    months = [add_months("2021-01", i) for i in range(60)]  # 2021-01..2025-12 -> 24 windows

    # Seed US repo files
    with (data_dir / "constituents.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["ticker", "name", "sector", "sub_industry", "date_added", "index"]
        )
        w.writeheader()
        for t in ("US1", "US2", "US3", "US4"):
            w.writerow(
                {
                    "ticker": t,
                    "name": f"{t} Corp",
                    "sector": "Tech",
                    "sub_industry": "Tech",
                    "date_added": "2015-01-01",
                    "index": "S&P 500",
                }
            )

    with (data_dir / "monthly_prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "ticker", "close", "adj_close", "market"])
        w.writeheader()
        rates = {"US1": 1.03, "US2": 1.025, "US3": 1.02, "US4": 1.01}
        for i, m in enumerate(months):
            dt = f"{m}-01"
            for t, r in rates.items():
                p = 100.0 * (r**i)
                w.writerow(
                    {
                        "date": dt,
                        "ticker": t,
                        "close": f"{p:.4f}",
                        "adj_close": f"{p:.4f}",
                        "market": "us",
                    }
                )
            bp = 1000.0 * (1.008**i)
            w.writerow(
                {
                    "date": dt,
                    "ticker": "^SP500TR",
                    "close": f"{bp:.4f}",
                    "adj_close": f"{bp:.4f}",
                    "market": "benchmark",
                }
            )

    # Seed FTSE 100 files
    with (global_dir / "constituents.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["ticker", "name", "sector", "sub_industry", "date_added", "index"]
        )
        w.writeheader()
        for t in ("UK1.L", "UK2.L", "UK3.L", "UK4.L"):
            w.writerow(
                {
                    "ticker": t,
                    "name": f"{t} plc",
                    "sector": "Industrials",
                    "sub_industry": "",
                    "date_added": "",
                    "index": "FTSE 100",
                }
            )

    with (global_dir / "monthly_prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "ticker", "close", "adj_close", "market"])
        w.writeheader()
        uk_rates = {"UK1.L": 1.025, "UK2.L": 1.02, "UK3.L": 1.015, "UK4.L": 1.005}
        for i, m in enumerate(months):
            dt = f"{m}-01"
            for t, r in uk_rates.items():
                p = 100.0 * (r**i)
                w.writerow(
                    {
                        "date": dt,
                        "ticker": t,
                        "close": f"{p:.4f}",
                        "adj_close": f"{p:.4f}",
                        "market": "uk",
                    }
                )
            bp = 1000.0 * (1.006**i)
            w.writerow(
                {
                    "date": dt,
                    "ticker": "ISF.L",
                    "close": f"{bp:.4f}",
                    "adj_close": f"{bp:.4f}",
                    "market": "benchmark_uk",
                }
            )

    # Seed ACWI files: EM non-UK-accessible stock 2330.TW is #1 fastest grower!
    acwi_consts = [
        AcwiConstituent(
            ticker="2330.TW",
            raw_ticker="2330",
            name="TSMC",
            sector="Info Tech",
            location="Taiwan",
            exchange="Taiwan Stock Exchange",
            market_currency="TWD",
            quote_currency="TWD",
            weight_pct=1.6,
            market="intl",
            uk_accessible=False,
            uk_access_note="Non-UK ISA exchange (Taiwan Stock Exchange)",
        ),
        AcwiConstituent(
            ticker="US1",
            raw_ticker="US1",
            name="US1 Corp",
            sector="Tech",
            location="United States",
            exchange="NASDAQ",
            market_currency="USD",
            quote_currency="USD",
            weight_pct=3.0,
            market="us",
            uk_accessible=True,
            uk_access_note="UK ISA (US)",
        ),
        AcwiConstituent(
            ticker="ASML.AS",
            raw_ticker="ASML",
            name="ASML",
            sector="Tech",
            location="Netherlands",
            exchange="Euronext Amsterdam",
            market_currency="EUR",
            quote_currency="EUR",
            weight_pct=0.8,
            market="eu",
            uk_accessible=True,
            uk_access_note="UK ISA (Europe)",
        ),
        AcwiConstituent(
            ticker="UK1.L",
            raw_ticker="UK1.",
            name="UK1 plc",
            sector="Industrials",
            location="United Kingdom",
            exchange="London Stock Exchange",
            market_currency="GBP",
            quote_currency="GBP",
            weight_pct=0.5,
            market="uk",
            uk_accessible=True,
            uk_access_note="UK ISA (UK LSE)",
        ),
    ]
    write_acwi_constituents_csv(acwi_consts, global_dir / "acwi_constituents.csv")

    with (global_dir / "fx_rates.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "pair", "rate"])
        w.writeheader()
        for m in months:
            dt = f"{m}-01"
            w.writerow({"date": dt, "pair": "USDTWD=X", "rate": "32.0"})
            w.writerow({"date": dt, "pair": "USDEUR=X", "rate": "0.9"})
            w.writerow({"date": dt, "pair": "USDGBP=X", "rate": "0.8"})

    with (global_dir / "acwi_monthly_prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "ticker", "close", "adj_close", "market"])
        w.writeheader()
        acwi_rates = {"2330.TW": 1.045, "ASML.AS": 1.028, "UK1.L": 1.025}
        for i, m in enumerate(months):
            dt = f"{m}-01"
            for t, r in acwi_rates.items():
                p = 100.0 * (r**i)
                w.writerow(
                    {
                        "date": dt,
                        "ticker": t,
                        "close": f"{p:.4f}",
                        "adj_close": f"{p:.4f}",
                        "market": "intl" if t == "2330.TW" else ("eu" if t == "ASML.AS" else "uk"),
                    }
                )
            bp = 100.0 * (1.007**i)
            w.writerow(
                {
                    "date": dt,
                    "ticker": "ACWI",
                    "close": f"{bp:.4f}",
                    "adj_close": f"{bp:.4f}",
                    "market": "benchmark_acwi",
                }
            )

    (tmp_path / "README.md").write_text(
        f"# Monthly Momentum\n\n{README_START_MARKER}\nOLD\n{README_END_MARKER}\n",
        encoding="utf-8",
    )

    rebuild_public_reports(root_dir=tmp_path)

    for chart_name in (
        "hero_vs_sp500.png",
        "performance.png",
        "performance_markets_comparison.png",
        "performance_ftse100.png",
        "performance_acwi.png",
        "performance_acwi_uk_accessible.png",
        "allocation_sp500.png",
        "allocation_ftse100.png",
        "allocation_acwi.png",
        "allocation_acwi_uk_accessible.png",
        "funding_comparison_sp500.png",
    ):
        p = tmp_path / "assets" / chart_name
        assert p.exists(), f"Missing {chart_name}"
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    assert (data_dir / "allocation_summary.json").exists()
    assert (global_dir / "allocation_summary.json").exists()
    funding_path = data_dir / "funding_comparison.json"
    assert funding_path.exists()
    funding_data = json.loads(funding_path.read_text(encoding="utf-8"))
    assert {"sp500", "acwi_uk_accessible", "acwi_all", "ftse100"} <= set(funding_data.keys())

    gsummary = json.loads((global_dir / "summary.json").read_text(encoding="utf-8"))
    # Full ACWI picks 2330.TW #1 and flags it; UK-Accessible ACWI picks US1, ASML.AS, UK1.L.
    assert gsummary["acwi_all"]["top3"][0]["ticker"] == "2330.TW"
    assert gsummary["acwi_all"]["top3"][0]["uk_accessible"] is False
    assert [f["ticker"] for f in gsummary["acwi_all"]["flagged_non_uk_in_top15"]] == ["2330.TW"]
    assert [r["ticker"] for r in gsummary["acwi_uk_accessible"]["top3"]] == [
        "US1",
        "ASML.AS",
        "UK1.L",
    ]
    assert "2330.TW" not in [r["ticker"] for r in gsummary["acwi_uk_accessible"]["top10"]]

    readme_text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "assets/hero_vs_sp500.png" in readme_text
    assert "assets/performance_markets_comparison.png" in readme_text
    assert "assets/performance_acwi_uk_accessible.png" in readme_text
    assert "assets/performance_acwi.png" in readme_text
    assert "assets/performance_ftse100.png" in readme_text
    assert "Flagged Global Winners Outside UK Retail ISAs" in readme_text
    assert "2330.TW" in readme_text
