"""Offline builder for the cumulative hero chart (holdings + performance vs benchmark).

The chart mixes granularities: the first windows are valued on real daily prices so the
early months show actual market action, while later windows fall back to the monthly
backtest points. Portfolio units are derived from the engine's own monthly outputs, so
the daily path anchors exactly onto the monthly series at every month boundary.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from monthly_momentum.backtest.data import BacktestDataset
from monthly_momentum.backtest.engine import MonthlyBacktestPoint

DEFAULT_DAILY_WINDOWS = 6
HERO_MONTHLY_AMOUNT = 100.0
HERO_CURRENCY = "USD"
HERO_CHART_ASSET = "assets/hero_acwi_uk.png"
HERO_DAILY_CSV = "daily_prices_first_months.csv"
MAX_BAND_TICKERS = 10


@dataclass(slots=True)
class HeroCumulativeSeries:
    """Mixed-granularity portfolio series powering the cumulative hero chart."""

    points: list[dict[str, Any]]
    band_tickers: list[str]
    names: dict[str, str]
    start_window: str
    latest_window: str
    daily_through: date | None
    monthly_amount: float = HERO_MONTHLY_AMOUNT
    currency: str = HERO_CURRENCY
    notes: list[str] = field(default_factory=list)


def load_hero_daily_prices(path: Path) -> dict[str, list[tuple[date, float]]]:
    """Load the committed daily-bars CSV into ``ticker -> sorted (date, adj_close)`` rows."""
    rows: dict[str, list[tuple[date, float]]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw_date = (row.get("date") or "").strip()
            raw_ticker = (row.get("ticker") or "").strip()
            raw_adj = (row.get("adj_close") or "").strip()
            try:
                day = date.fromisoformat(raw_date)
                adj = float(raw_adj)
            except (ValueError, TypeError):
                continue
            if not raw_ticker or adj <= 0.0:
                continue
            rows.setdefault(raw_ticker, []).append((day, adj))
    for ticker in rows:
        rows[ticker].sort(key=lambda item: item[0])
    return rows


def _window_first_date(window_month: str) -> date:
    return date(int(window_month[:4]), int(window_month[5:7]), 1)


def _price_at_or_before(series: list[tuple[date, float]], day: date) -> float | None:
    """Most recent adjusted close at or before ``day`` (carries forward over holidays)."""
    best: float | None = None
    for row_date, value in series:
        if row_date > day:
            break
        best = value
    return best


def _carry_forward_walk(
    series: list[tuple[date, float]], seed_day: date
) -> Callable[[date], float]:
    """Build a day->price lookup that carries the last known close forward.

    The walker is seeded with the last close at or before ``seed_day``, so days before a
    ticker's next session reuse its latest known price. Callers must guarantee a seed
    price exists.
    """
    seed = _price_at_or_before(series, seed_day)
    if seed is None:
        raise ValueError("Carry-forward walk needs a price at or before the seed day.")
    idx = 0
    last = seed

    def walk(day: date) -> float:
        nonlocal idx, last
        while idx < len(series) and series[idx][0] <= day:
            last = series[idx][1]
            idx += 1
        return last

    return walk


def _interval_daily_plans(
    *,
    weights: Mapping[str, float],
    anchor_value: float,
    signal_month: str,
    dataset: BacktestDataset,
    daily_prices: Mapping[str, list[tuple[date, float]]],
    prev_session: date,
) -> dict[str, tuple[str, tuple[float, ...]]]:
    """Derive per-holding valuation plans for one daily interval.

    ``("path", units, scale)`` values a holding from daily prices; ``("flat", value)``
    holds it constant when no reliable daily basis exists.
    """
    plans: dict[str, tuple[str, tuple[float, ...]]] = {}
    for tk, weight in weights.items():
        value_k = weight * anchor_value
        month_pt = dataset.prices.get(tk, {}).get(signal_month)
        ticker_daily = daily_prices.get(tk, [])
        daily_prev = _price_at_or_before(ticker_daily, prev_session)
        if month_pt is None or daily_prev is None or daily_prev <= 0.0:
            plans[tk] = ("flat", (value_k,))
            continue
        units = value_k / month_pt.adj_close
        scale = month_pt.adj_close / daily_prev
        plans[tk] = ("path", (units, scale))
    return plans


def build_hero_cumulative_series(
    *,
    points: Sequence[MonthlyBacktestPoint],
    dataset: BacktestDataset,
    daily_prices: Mapping[str, list[tuple[date, float]]],
    scale_to_100: float,
    names: Mapping[str, str] | None = None,
    daily_windows: int = DEFAULT_DAILY_WINDOWS,
    monthly_amount: float = HERO_MONTHLY_AMOUNT,
) -> HeroCumulativeSeries:
    """Build the mixed-granularity cumulative portfolio series for the hero chart.

    ``points`` are the engine's monthly backtest points (e.g. Standard Top 3). Monthly
    values are scaled by ``scale_to_100`` so the chart speaks in ``monthly_amount`` terms.
    When daily prices cover the first ``daily_windows`` windows (and their holdings),
    those windows are valued on daily prices; everything after stays month-to-month.
    """
    if not points:
        raise ValueError("Cannot build the hero series from an empty backtest result.")

    bench_daily = list(daily_prices.get(dataset.benchmark_ticker, []))

    # Monthly anchors: one per engine point, plotted at the first day of the window month
    # (the engine's monthly bar is the month-end close of the signal month, i.e. the
    # proxy price for the first trading day of the window month).
    anchor_dates: list[date] = []
    anchor_values: list[float] = []
    anchor_bench: list[float | None] = []
    anchor_cash: list[float] = []
    anchor_reserve: list[float] = []
    anchor_weights: list[dict[str, float]] = []
    anchor_signal: list[str] = []
    for pt in points:
        value = float(pt.portfolio_value) * scale_to_100
        anchor_dates.append(_window_first_date(pt.window_month))
        anchor_values.append(value)
        anchor_bench.append(
            float(pt.benchmark_value) * scale_to_100 if pt.benchmark_value is not None else None
        )
        anchor_cash.append(float(pt.contributed_cum) * scale_to_100)
        anchor_reserve.append(float(pt.holdings_weights.get("CASH", 0.0)) / 100.0 * value)
        anchor_weights.append(
            {
                tk: float(w) / 100.0
                for tk, w in pt.holdings_weights.items()
                if tk != "CASH" and float(w) > 0.0
            }
        )
        anchor_signal.append(pt.signal_month)

    interval_count = min(max(daily_windows, 0), len(anchor_dates) - 2)
    needed_tickers: set[str] = set()
    for k in range(interval_count):
        needed_tickers.update(anchor_weights[k])

    daily_ok = interval_count >= 1 and bool(bench_daily)
    missing: list[str] = []
    if daily_ok:
        missing = sorted(tk for tk in needed_tickers if not daily_prices.get(tk))
        if missing:
            daily_ok = False

    series_points: list[dict[str, Any]] = []
    daily_through: date | None = None
    notes: list[str] = []

    def _append_anchor(k: int, kind: str) -> None:
        series_points.append(
            {
                "date": anchor_dates[k],
                "stocks": {tk: w * anchor_values[k] for tk, w in anchor_weights[k].items()},
                "total": anchor_values[k],
                "benchmark": anchor_bench[k],
                "cash": anchor_cash[k],
                "kind": kind,
            }
        )

    if not daily_ok:
        for k in range(len(anchor_dates)):
            _append_anchor(k, "monthly")
        if missing:
            notes.append("Daily detail skipped: no daily prices for " + ", ".join(missing) + ".")
    else:
        last_daily_anchor = interval_count + 1
        for k in range(last_daily_anchor):
            _append_anchor(k, "anchor")
        for k in range(last_daily_anchor, len(anchor_dates)):
            _append_anchor(k, "monthly")

        for k in range(interval_count):
            a_start = anchor_dates[k]
            a_next = anchor_dates[k + 1]
            signal_month = anchor_signal[k]
            path_days = [day for day, _ in bench_daily if a_start < day < a_next]
            if not path_days:
                continue
            daily_through = max(daily_through, path_days[-1]) if daily_through else path_days[-1]

            prev_session = max((day for day, _ in bench_daily if day < a_start), default=a_start)

            # Benchmark plan: engine benchmark value at anchor k / its monthly anchor price.
            units_b: float | None = None
            bench_scale = 1.0
            bench_anchor = anchor_bench[k]
            bench_month_pt = dataset.benchmark_prices.get(signal_month)
            bench_prev = _price_at_or_before(bench_daily, prev_session)
            if (
                bench_anchor is not None
                and bench_month_pt is not None
                and bench_prev is not None
                and bench_prev > 0.0
            ):
                units_b = bench_anchor / bench_month_pt.adj_close
                bench_scale = bench_month_pt.adj_close / bench_prev
            bench_walk = _carry_forward_walk(bench_daily, prev_session)
            bench_flat = anchor_bench[k]

            plans = _interval_daily_plans(
                weights=anchor_weights[k],
                anchor_value=anchor_values[k],
                signal_month=signal_month,
                dataset=dataset,
                daily_prices=daily_prices,
                prev_session=prev_session,
            )
            walks: dict[str, Callable[[date], float]] = {
                tk: _carry_forward_walk(daily_prices.get(tk, []), prev_session)
                for tk, (kind, _args) in plans.items()
                if kind == "path"
            }

            for day in path_days:
                stocks: dict[str, float] = {}
                for tk, (kind, args) in plans.items():
                    if kind == "flat":
                        stocks[tk] = args[0]
                        continue
                    units, scale = args
                    stocks[tk] = units * walks[tk](day) * scale
                bench_val: float | None
                if units_b is not None:
                    bench_val = units_b * bench_walk(day) * bench_scale
                else:
                    bench_val = bench_flat
                series_points.append(
                    {
                        "date": day,
                        "stocks": stocks,
                        "total": sum(stocks.values()) + anchor_reserve[k],
                        "benchmark": bench_val,
                        "cash": anchor_cash[k],
                        "kind": "daily",
                    }
                )

    series_points.sort(key=lambda p: p["date"])

    # Band selection: largest peak weight share across the whole backtest.
    peak_share: dict[str, float] = {}
    final_weight: dict[str, float] = {}
    first_seen: dict[str, str] = {}
    for pt in points:
        for tk, w in pt.holdings_weights.items():
            weight = float(w)
            if tk == "CASH" or weight <= 0.0:
                continue
            peak_share[tk] = max(peak_share.get(tk, 0.0), weight / 100.0)
            final_weight[tk] = weight
            first_seen.setdefault(tk, pt.window_month)
    ranked = sorted(
        peak_share,
        key=lambda tk: (peak_share[tk], final_weight.get(tk, 0.0), tk),
        reverse=True,
    )
    band_tickers = sorted(
        ranked[:MAX_BAND_TICKERS],
        key=lambda tk: (first_seen.get(tk, "9999-99"), -final_weight.get(tk, 0.0), tk),
    )

    all_names = dict(names or {})
    resolved_names = {tk: all_names.get(tk, tk) for tk in band_tickers}

    return HeroCumulativeSeries(
        points=series_points,
        band_tickers=band_tickers,
        names=resolved_names,
        start_window=points[0].window_month,
        latest_window=points[-1].window_month,
        daily_through=daily_through,
        monthly_amount=monthly_amount,
        notes=notes,
    )
