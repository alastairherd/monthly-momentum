"""Tests for the live forward-tracked portfolio."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import pytest

from monthly_momentum.chart import _squarify
from monthly_momentum.tracker import (
    LiveTracker,
    build_live_series,
    load_tracker,
    queue_window_picks,
    run_live_tracker,
    settle_pending,
)


def _seed_repo(root: Path, window: str = "2026-11", picks: Sequence[str] = ("A", "B", "C")) -> None:
    live = root / "data" / "live"
    live.mkdir(parents=True)
    (live / "tracker.json").write_text(
        json.dumps({"inception": "2026-11-25", "buys": [], "pending": None}), encoding="utf-8"
    )
    glob = root / "data" / "global"
    glob.mkdir(parents=True)
    (glob / "summary.json").write_text(
        json.dumps(
            {
                "acwi_uk_accessible": {
                    "latest_window": window,
                    "top3": [{"ticker": t, "name": f"{t} Corp"} for t in picks],
                }
            }
        ),
        encoding="utf-8",
    )


def _fetcher(prices: dict[str, dict[str, float]]):
    def fetch(tickers: Sequence[str], start: date, end: date) -> list[dict[str, str]]:
        return [
            {"date": d, "ticker": t, "adj_close": str(px)}
            for t in tickers
            for d, px in prices.get(t, {}).items()
            if start <= date.fromisoformat(d) <= end
        ]

    return fetch


def test_day_one_is_a_single_point_at_cash(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    prices = {t: {"2026-11-24": 9.0, "2026-11-25": 10.0} for t in ("A", "B", "C", "ACWI")}
    res = run_live_tracker(tmp_path, today=date(2026, 11, 26), fetcher=_fetcher(prices))

    assert res.bought_window == "2026-11"
    assert res.series is not None
    assert [p.date for p in res.series.points] == [date(2026, 11, 25)]
    pt = res.series.latest
    assert pt.total == pytest.approx(100.0)
    assert pt.benchmark == pytest.approx(100.0)
    assert pt.cash == pytest.approx(100.0)
    assert res.chart_path is not None and res.chart_path.exists()
    summary = json.loads((tmp_path / "data" / "live" / "summary.json").read_text())
    assert summary["portfolio_return_pct"] == 0.0


def test_second_close_marks_holdings_and_benchmark(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    prices = {
        "A": {"2026-11-25": 10.0, "2026-11-27": 20.0},
        "B": {"2026-11-25": 10.0, "2026-11-27": 10.0},
        "C": {"2026-11-25": 10.0, "2026-11-27": 5.0},
        "ACWI": {"2026-11-25": 100.0, "2026-11-27": 101.0},
    }
    res = run_live_tracker(tmp_path, today=date(2026, 11, 27), fetcher=_fetcher(prices))
    assert res.series is not None
    pt = res.series.latest
    assert pt.date == date(2026, 11, 27)
    assert pt.holdings["A"] == pytest.approx(200.0 / 3)
    assert pt.total == pytest.approx(100.0 / 3 * (2 + 1 + 0.5))
    assert pt.benchmark == pytest.approx(101.0)
    assert [h.ticker for h in res.series.holdings] == ["A", "B", "C"]

    # Re-running is idempotent: the window is bought exactly once.
    run_live_tracker(tmp_path, today=date(2026, 11, 27), fetcher=_fetcher(prices))
    tracker = load_tracker(tmp_path / "data" / "live" / "tracker.json")
    assert len(tracker.buys) == 1


def test_new_window_waits_for_first_close_of_month() -> None:
    tracker = LiveTracker(inception=date(2026, 11, 25))
    assert queue_window_picks(tracker, "2026-11", ["A", "B", "C"], {})
    closes = {t: {date(2026, 11, 25): 10.0} for t in ("A", "B", "C", "ACWI")}
    assert settle_pending(tracker, closes)

    assert queue_window_picks(tracker, "2026-12", ["A", "D", "E"], {})
    assert not settle_pending(tracker, closes)  # no December close yet
    for t in ("A", "D", "E", "ACWI"):
        closes.setdefault(t, {})[date(2026, 12, 1)] = 12.0
    assert settle_pending(tracker, closes)
    assert tracker.buys[-1].date == date(2026, 12, 1)

    series = build_live_series(tracker, closes)
    assert series.latest.cash == pytest.approx(200.0)
    a = next(h for h in series.holdings if h.ticker == "A")
    assert a.invested == pytest.approx(200.0 / 3)


def test_old_windows_before_inception_are_ignored() -> None:
    tracker = LiveTracker(inception=date(2026, 11, 25))
    assert not queue_window_picks(tracker, "2026-10", ["A", "B", "C"], {})


def test_long_record_switches_to_month_end_after_daily_stretch() -> None:
    tracker = LiveTracker(inception=date(2026, 1, 2))
    queue_window_picks(tracker, "2026-01", ["A"], {})
    days = [date(2026, 1, 2) + timedelta(days=i) for i in range(400)]
    closes = {t: {d: 10.0 + i * 0.01 for i, d in enumerate(days)} for t in ("A", "ACWI")}
    settle_pending(tracker, closes)
    series = build_live_series(tracker, closes, daily_months=6)

    assert series.daily_through is not None
    late = [p.date for p in series.points if p.date > series.daily_through]
    assert len(late) <= 14  # one per month plus the latest close
    assert series.points[-1].date == days[-1]


def test_squarify_preserves_area_and_bounds() -> None:
    vals = [50.0, 30.0, 20.0]
    rects = _squarify(vals, 0.0, 0.0, 1.0, 1.0)
    for v, (x, y, w, h) in zip(vals, rects, strict=True):
        assert w * h == pytest.approx(v / 100.0)
        assert x >= 0.0 and x + w <= 1.0 + 1e-9
        assert y >= 0.0 and y + h <= 1.0 + 1e-9
