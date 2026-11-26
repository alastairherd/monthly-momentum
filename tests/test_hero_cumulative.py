"""Tests for the cumulative hero chart series and its chart renderer."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from monthly_momentum.backtest.data import BacktestDataset, PricePoint
from monthly_momentum.backtest.engine import MonthlyBacktestPoint
from monthly_momentum.chart import generate_hero_cumulative_chart
from monthly_momentum.hero import (
    HeroCumulativeSeries,
    build_hero_cumulative_series,
    load_hero_daily_prices,
)


def _make_point(
    window_month: str,
    *,
    value: float,
    bench: float,
    cash: float,
    weights: dict[str, float],
) -> MonthlyBacktestPoint:
    signal_month = f"{window_month[:4]}-{int(window_month[5:7]) - 1:02d}"
    return MonthlyBacktestPoint(
        signal_month=signal_month,
        window_month=window_month,
        dt=date(int(window_month[:4]), int(window_month[5:7]), 1),
        contributed_cum=cash,
        portfolio_value=value,
        twr_nav=1.0,
        benchmark_value=bench,
        benchmark_nav=1.0,
        top_picks=[],
        top10=[],
        eligible_count=2,
        excluded_count=0,
        rule6_sells=[],
        takeovers=[],
        fees_paid_month=0.0,
        holdings_weights=weights,
    )


def _make_dataset() -> BacktestDataset:
    def _pt(ticker: str, month: str, adj: float, market: str = "us") -> PricePoint:
        return PricePoint(
            dt=date(int(month[:4]), int(month[5:7]), 1),
            month=month,
            ticker=ticker,
            close=adj,
            adj_close=adj,
            market=market,
        )

    prices = {
        "AAA": {m: _pt("AAA", m, 10.0) for m in ("2017-10", "2017-11")},
        "BBB": {m: _pt("BBB", m, 20.0) for m in ("2017-10", "2017-11")},
    }
    benchmark = {m: _pt("ACWI", m, 100.0, market="benchmark_acwi") for m in ("2017-10", "2017-11")}
    return BacktestDataset(
        months=["2017-10", "2017-11"],
        month_dates={
            m: date(2017, 10 if m == "2017-10" else 11, 1) for m in ("2017-10", "2017-11")
        },
        prices=prices,
        benchmark_prices=benchmark,
        constituents=[],
        benchmark_ticker="ACWI",
    )


def _make_daily_prices() -> dict[str, list[tuple[date, float]]]:
    return {
        "ACWI": [
            (date(2017, 10, 31), 100.0),
            (date(2017, 11, 15), 110.0),
            (date(2017, 11, 30), 100.0),
            (date(2017, 12, 15), 105.0),
            (date(2017, 12, 29), 100.0),
        ],
        "AAA": [
            (date(2017, 10, 31), 10.0),
            (date(2017, 11, 15), 12.0),
            (date(2017, 11, 30), 10.0),
            (date(2017, 12, 15), 10.0),
            (date(2017, 12, 29), 10.0),
        ],
        "BBB": [
            (date(2017, 10, 31), 20.0),
            (date(2017, 11, 15), 20.0),
            (date(2017, 11, 30), 20.0),
            (date(2017, 12, 15), 20.0),
            (date(2017, 12, 29), 20.0),
        ],
    }


def _make_points() -> list[MonthlyBacktestPoint]:
    # Contribution of 500 in the engine terms, scaled to 100 for the chart.
    return [
        _make_point(
            "2017-11", value=500.0, bench=500.0, cash=500.0, weights={"AAA": 50.0, "BBB": 50.0}
        ),
        _make_point(
            "2017-12", value=1000.0, bench=1000.0, cash=1000.0, weights={"AAA": 50.0, "BBB": 50.0}
        ),
        _make_point(
            "2018-01", value=1500.0, bench=1500.0, cash=1500.0, weights={"AAA": 50.0, "BBB": 50.0}
        ),
        _make_point(
            "2018-02", value=2000.0, bench=2000.0, cash=2000.0, weights={"AAA": 50.0, "BBB": 50.0}
        ),
        _make_point(
            "2018-03", value=2500.0, bench=2500.0, cash=2500.0, weights={"AAA": 50.0, "BBB": 50.0}
        ),
    ]


def test_hero_series_daily_segment_anchors_and_paths() -> None:
    series = build_hero_cumulative_series(
        points=_make_points(),
        dataset=_make_dataset(),
        daily_prices=_make_daily_prices(),
        scale_to_100=0.2,
        names={"AAA": "Alpha", "BBB": "Beta"},
        daily_windows=2,
    )

    kinds = [pt["kind"] for pt in series.points]
    assert kinds[0] == "anchor"
    assert kinds[-1] == "monthly"

    # First anchor: the first deposit, plotted at the first day of the first window.
    first = series.points[0]
    assert first["date"] == date(2017, 11, 1)
    assert first["kind"] == "anchor"
    assert first["total"] == pytest.approx(100.0)
    assert first["stocks"] == {"AAA": pytest.approx(50.0), "BBB": pytest.approx(50.0)}
    assert first["benchmark"] == pytest.approx(100.0)
    assert first["cash"] == pytest.approx(100.0)

    # Daily path: AAA reprices to 12 on 2017-11-15 while BBB stays at 20.
    by_date = {pt["date"]: pt for pt in series.points}
    mid = by_date[date(2017, 11, 15)]
    assert mid["kind"] == "daily"
    assert mid["stocks"]["AAA"] == pytest.approx(60.0)  # 5 units x 12
    assert mid["stocks"]["BBB"] == pytest.approx(50.0)
    assert mid["total"] == pytest.approx(110.0)
    assert mid["benchmark"] == pytest.approx(110.0)

    # Daily path pre-buy value on the last session of the interval.
    pre_buy = by_date[date(2017, 11, 30)]
    assert pre_buy["total"] == pytest.approx(100.0)

    # Second anchor (post-buy) matches the engine's monthly value exactly.
    second_anchor = by_date[date(2017, 12, 1)]
    assert second_anchor["kind"] == "anchor"
    assert second_anchor["total"] == pytest.approx(200.0)
    assert second_anchor["benchmark"] == pytest.approx(200.0)

    # The 2018-01 anchor is the last daily anchor; later ones are month-to-month.
    third_anchor = by_date[date(2018, 1, 1)]
    assert third_anchor["kind"] == "anchor"
    assert third_anchor["total"] == pytest.approx(300.0)
    assert by_date[date(2018, 2, 1)]["kind"] == "monthly"
    assert series.daily_through == date(2017, 12, 29)

    dates = [pt["date"] for pt in series.points]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))

    assert series.band_tickers == ["AAA", "BBB"]
    assert series.names == {"AAA": "Alpha", "BBB": "Beta"}


def test_hero_series_monthly_fallback_without_daily_prices() -> None:
    daily = {k: v for k, v in _make_daily_prices().items() if k != "AAA"}
    series = build_hero_cumulative_series(
        points=_make_points(),
        dataset=_make_dataset(),
        daily_prices=daily,
        scale_to_100=0.2,
        daily_windows=2,
    )

    assert all(pt["kind"] == "monthly" for pt in series.points)
    assert series.daily_through is None
    assert series.notes and "AAA" in series.notes[0]
    assert len(series.points) == 5
    assert series.points[0]["total"] == pytest.approx(100.0)


def test_hero_series_monthly_only_when_no_benchmark_daily() -> None:
    daily = {k: v for k, v in _make_daily_prices().items() if k != "ACWI"}
    series = build_hero_cumulative_series(
        points=_make_points(),
        dataset=_make_dataset(),
        daily_prices=daily,
        scale_to_100=0.2,
        daily_windows=2,
    )
    assert all(pt["kind"] == "monthly" for pt in series.points)
    assert series.daily_through is None


def test_load_hero_daily_prices_parses_and_sorts(tmp_path: Path) -> None:
    csv_path = tmp_path / "daily.csv"
    csv_path.write_text(
        "date,ticker,adj_close\n"
        "2017-11-01,ACWI,60.0\n"
        "2017-10-31,ACWI,59.0\n"
        "2017-10-31,NVDA,not-a-number\n"
        "2017-10-31,,55.0\n"
        "bad-date,ACWI,58.0\n",
        encoding="utf-8",
    )
    rows = load_hero_daily_prices(csv_path)
    assert list(rows) == ["ACWI"]
    assert rows["ACWI"] == [(date(2017, 10, 31), 59.0), (date(2017, 11, 1), 60.0)]


def test_generate_hero_cumulative_chart_renders_png(tmp_path: Path) -> None:
    series = build_hero_cumulative_series(
        points=_make_points(),
        dataset=_make_dataset(),
        daily_prices=_make_daily_prices(),
        scale_to_100=0.2,
        names={"AAA": "Alpha", "BBB": "Beta"},
        daily_windows=2,
    )
    out = tmp_path / "hero.png"
    result = generate_hero_cumulative_chart(
        series,
        out,
        title="Test hero chart",
        subtitle="Synthetic series",
        footer_note="Source: synthetic data. Not financial advice.",
        benchmark_label="ACWI ETF",
        currency_symbol="$",
    )
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 10_000


def test_generate_hero_cumulative_chart_rejects_empty_series(tmp_path: Path) -> None:
    empty = HeroCumulativeSeries(
        points=[],
        band_tickers=[],
        names={},
        start_window="2017-11",
        latest_window="2017-11",
        daily_through=None,
    )
    with pytest.raises(ValueError):
        generate_hero_cumulative_chart(
            empty,
            tmp_path / "hero.png",
            title="t",
            subtitle="s",
            footer_note="f",
        )


def test_refresh_hero_daily_prices_csv_writes_committed_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monthly_momentum import acwi

    history = tmp_path / "data" / "global" / "rankings" / "history_acwi_uk_accessible.csv"
    history.parent.mkdir(parents=True)
    window_picks = {
        "2017-11": ["NVDA", "AMZN"],
        "2017-12": ["NVDA", "AMZN"],
        "2018-01": ["NVDA", "TAL"],
        "2018-02": ["NVDA", "MU"],
        "2018-03": ["NVDA", "MU"],
    }
    with history.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["month", "rank", "ticker", "name", "index", "selected_for_buy"])
        for window, picks in window_picks.items():
            for rank, ticker in enumerate(picks, start=1):
                writer.writerow([window, str(rank), ticker, ticker, "NASDAQ", "true"])
            writer.writerow([window, "9", "AVGO", "BROADCOM", "NASDAQ", "false"])

    captured: dict[str, object] = {}

    def fake_fetch(
        tickers: list[str], start: date, end: date, max_workers: int = 6
    ) -> list[dict[str, str]]:
        captured["tickers"] = list(tickers)
        captured["start"] = start
        captured["end"] = end
        rows = []
        for day in (date(2017, 10, 31), date(2017, 11, 30), date(2018, 1, 10)):
            for tk in tickers:
                rows.append({"date": day.isoformat(), "ticker": tk, "adj_close": "10.0000"})
        return rows

    monkeypatch.setattr(acwi, "fetch_yahoo_v8_daily_bars", fake_fetch)

    out_path, failed = acwi.refresh_hero_daily_prices_csv(root_dir=tmp_path, daily_windows=2)

    assert failed == []
    assert out_path == tmp_path / "data" / "global" / "daily_prices_first_months.csv"
    assert out_path is not None and out_path.exists()
    # Picks from the first daily_windows + 1 windows, plus the ACWI benchmark.
    assert set(captured["tickers"]) == {"NVDA", "AMZN", "TAL", "ACWI"}  # type: ignore[operator]
    assert "MU" not in captured["tickers"]  # type: ignore[operator]
    # Range covers the month-end before the first window through the last daily month.
    assert captured["start"] == date(2017, 9, 21)
    assert captured["end"] == date(2018, 1, 10)

    with out_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 12
    assert rows[0]["date"] <= rows[-1]["date"]


def test_refresh_hero_daily_prices_csv_skips_without_history(tmp_path: Path) -> None:
    from monthly_momentum import acwi

    out_path, failed = acwi.refresh_hero_daily_prices_csv(root_dir=tmp_path, daily_windows=2)
    assert out_path is None
    assert failed == []


def test_refresh_hero_daily_prices_csv_keeps_existing_on_partial_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from monthly_momentum import acwi

    history = tmp_path / "data" / "global" / "rankings" / "history_acwi_uk_accessible.csv"
    history.parent.mkdir(parents=True)
    with history.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["month", "rank", "ticker", "name", "index", "selected_for_buy"])
        writer.writerow(["2017-11", "1", "NVDA", "NVIDIA", "NASDAQ", "true"])
        writer.writerow(["2017-11", "2", "AMZN", "AMAZON", "NASDAQ", "true"])
        writer.writerow(["2017-12", "1", "NVDA", "NVIDIA", "NASDAQ", "true"])
        writer.writerow(["2017-12", "2", "AMZN", "AMAZON", "NASDAQ", "true"])

    existing = tmp_path / "data" / "global" / "daily_prices_first_months.csv"
    existing.write_text("date,ticker,adj_close\n2017-10-31,ACWI,59.0\n", encoding="utf-8")

    def partial_fetch(
        tickers: list[str], start: date, end: date, max_workers: int = 6
    ) -> list[dict[str, str]]:
        return [{"date": "2017-10-31", "ticker": "ACWI", "adj_close": "59.0"}]

    monkeypatch.setattr(acwi, "fetch_yahoo_v8_daily_bars", partial_fetch)

    out_path, failed = acwi.refresh_hero_daily_prices_csv(root_dir=tmp_path, daily_windows=2)

    assert failed == ["AMZN", "NVDA"]
    assert out_path == existing
    assert existing.read_text(encoding="utf-8").strip().endswith("2017-10-31,ACWI,59.0")
