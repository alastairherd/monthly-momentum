"""Live tracker: the real $100/month All World — UK-accessible portfolio since inception.

Unlike the backtests, this follows the strategy forward from the day the repository
started (``inception``). Each month's Top 3 is bought once with equal thirds of
``monthly_amount`` at the first daily close on/after the buy date, and the same cash
is put into the ACWI ETF as the benchmark. Values are marked at daily
dividend-adjusted closes; once the record is older than ``DAILY_MONTHS`` months,
the chart keeps daily detail for the opening stretch and month-end points after it.

State lives in ``data/live``:

* ``tracker.json`` — inception date, settings, and the ledger of monthly buys
  (amount per ticker and buy date; units are derived from the current adjusted series
  so dividends are always handled consistently).
* ``daily_closes.csv`` — daily adjusted closes since inception for every ticker held
  plus the benchmark.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

LIVE_DIR = Path("data") / "live"
TRACKER_JSON = "tracker.json"
DAILY_CLOSES_CSV = "daily_closes.csv"
LIVE_CHART_ASSET = Path("assets") / "live_tracker.png"
DAILY_MONTHS = 6

PriceFetcher = Callable[[Sequence[str], date, date], list[dict[str, str]]]


@dataclass(slots=True)
class LiveBuy:
    """One monthly buy: equal cash into each pick plus the same total into the benchmark."""

    window: str
    date: date
    amounts: dict[str, float]
    benchmark_amount: float


@dataclass(slots=True)
class LiveTracker:
    """Tracker settings and the buy ledger."""

    inception: date
    universe: str = "All World — UK-accessible"
    monthly_amount: float = 100.0
    benchmark: str = "ACWI"
    benchmark_label: str = "ACWI ETF"
    names: dict[str, str] = field(default_factory=dict)
    buys: list[LiveBuy] = field(default_factory=list)
    pending: dict[str, Any] | None = None
    # Dated context shown on the chart, e.g. why the start date matters.
    notes: list[dict[str, str]] = field(default_factory=list)

    @property
    def tickers(self) -> list[str]:
        seen: dict[str, None] = {}
        for buy in self.buys:
            for ticker in buy.amounts:
                seen.setdefault(ticker, None)
        if self.pending:
            for ticker in self.pending.get("tickers", []):
                seen.setdefault(ticker, None)
        return list(seen)


@dataclass(slots=True)
class LivePoint:
    date: date
    holdings: dict[str, float]
    total: float
    benchmark: float
    cash: float


@dataclass(slots=True)
class LiveHolding:
    ticker: str
    name: str
    value: float
    invested: float

    @property
    def return_pct(self) -> float:
        return (self.value / self.invested - 1.0) * 100.0 if self.invested > 0 else 0.0


@dataclass(slots=True)
class LiveSeries:
    points: list[LivePoint]
    holdings: list[LiveHolding]
    daily_through: date | None

    @property
    def latest(self) -> LivePoint:
        return self.points[-1]


# --------------------------------------------------------------------------- state I/O


def load_tracker(path: Path) -> LiveTracker:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return LiveTracker(
        inception=date.fromisoformat(raw["inception"]),
        universe=raw.get("universe", "All World — UK-accessible"),
        monthly_amount=float(raw.get("monthly_amount", 100.0)),
        benchmark=raw.get("benchmark", "ACWI"),
        benchmark_label=raw.get("benchmark_label", "ACWI ETF"),
        names=dict(raw.get("names", {})),
        buys=[
            LiveBuy(
                window=b["window"],
                date=date.fromisoformat(b["date"]),
                amounts={k: float(v) for k, v in b["amounts"].items()},
                benchmark_amount=float(b["benchmark_amount"]),
            )
            for b in raw.get("buys", [])
        ],
        pending=raw.get("pending"),
        notes=list(raw.get("notes", [])),
    )


def save_tracker(tracker: LiveTracker, path: Path) -> None:
    payload: dict[str, Any] = {
        "inception": tracker.inception.isoformat(),
        "universe": tracker.universe,
        "monthly_amount": tracker.monthly_amount,
        "benchmark": tracker.benchmark,
        "benchmark_label": tracker.benchmark_label,
        "names": tracker.names,
        "buys": [
            {
                "window": b.window,
                "date": b.date.isoformat(),
                "amounts": b.amounts,
                "benchmark_amount": b.benchmark_amount,
            }
            for b in tracker.buys
        ],
        "pending": tracker.pending,
        "notes": tracker.notes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_daily_closes(path: Path) -> dict[str, dict[date, float]]:
    out: dict[str, dict[date, float]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out.setdefault(row["ticker"], {})[date.fromisoformat(row["date"])] = float(
                    row["adj_close"]
                )
            except (KeyError, ValueError):
                continue
    return out


def write_daily_closes(closes: Mapping[str, Mapping[date, float]], path: Path) -> None:
    rows = sorted(
        (d.isoformat(), t, px) for t, series in closes.items() for d, px in series.items()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["date", "ticker", "adj_close"])
        for d_s, ticker, px in rows:
            writer.writerow([d_s, ticker, f"{px:.4f}"])


# --------------------------------------------------------------------------- ledger logic


def _first_close_on_or_after(series: Mapping[date, float], day: date) -> date | None:
    candidates = [d for d in series if d >= day]
    return min(candidates) if candidates else None


def queue_window_picks(
    tracker: LiveTracker, window: str, tickers: Sequence[str], names: Mapping[str, str]
) -> bool:
    """Queue a new window's picks for buying. Returns True when something was queued."""
    inception_window = tracker.inception.strftime("%Y-%m")
    if window < inception_window or any(b.window == window for b in tracker.buys):
        return False
    if tracker.pending and tracker.pending.get("window") == window:
        return False
    picks = [t for t in tickers if t][:3]
    if not picks:
        return False
    start = (
        tracker.inception
        if window == inception_window
        else date(int(window[:4]), int(window[5:7]), 1)
    )
    tracker.pending = {"window": window, "tickers": picks, "on_or_after": start.isoformat()}
    for ticker in picks:
        if ticker in names and names[ticker]:
            tracker.names[ticker] = names[ticker]
    return True


def settle_pending(tracker: LiveTracker, closes: Mapping[str, Mapping[date, float]]) -> bool:
    """Turn a queued buy into a ledger entry once every pick and the benchmark has a close."""
    pending = tracker.pending
    if not pending:
        return False
    on_or_after = date.fromisoformat(pending["on_or_after"])
    needed = [*pending["tickers"], tracker.benchmark]
    first_dates = [_first_close_on_or_after(closes.get(t, {}), on_or_after) for t in needed]
    if any(d is None for d in first_dates):
        return False
    # Buy on the first session every leg has traded.
    buy_date = max(d for d in first_dates if d is not None)
    if any(buy_date not in closes.get(t, {}) for t in needed):
        return False
    share = tracker.monthly_amount / len(pending["tickers"])
    tracker.buys.append(
        LiveBuy(
            window=pending["window"],
            date=buy_date,
            amounts={t: round(share, 6) for t in pending["tickers"]},
            benchmark_amount=tracker.monthly_amount,
        )
    )
    tracker.pending = None
    return True


# --------------------------------------------------------------------------- series


def _month_end_sample(dates: Sequence[date]) -> list[date]:
    by_month: dict[tuple[int, int], date] = {}
    for d in dates:
        key = (d.year, d.month)
        if key not in by_month or d > by_month[key]:
            by_month[key] = d
    return sorted(by_month.values())


def _add_months(day: date, months: int) -> date:
    m = day.month - 1 + months
    y = day.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(day.day, 28))


def build_live_series(
    tracker: LiveTracker,
    closes: Mapping[str, Mapping[date, float]],
    *,
    daily_months: int = DAILY_MONTHS,
) -> LiveSeries:
    """Mark the ledger to market at each session where every held leg has a close."""
    if not tracker.buys:
        raise ValueError("The live tracker has no settled buys yet.")

    bench = closes.get(tracker.benchmark, {})
    first_buy = min(b.date for b in tracker.buys)
    all_dates = sorted(d for d in bench if d >= first_buy)

    units: list[tuple[date, str, float]] = []
    bench_units: list[tuple[date, float]] = []
    for buy in tracker.buys:
        for ticker, amount in buy.amounts.items():
            px = closes.get(ticker, {}).get(buy.date)
            if px is None or px <= 0:
                raise ValueError(f"No {buy.date} close for {ticker} to price its buy.")
            units.append((buy.date, ticker, amount / px))
        bpx = bench.get(buy.date)
        if bpx is None or bpx <= 0:
            raise ValueError(f"No {buy.date} close for {tracker.benchmark}.")
        bench_units.append((buy.date, buy.benchmark_amount / bpx))

    points: list[LivePoint] = []
    last_px: dict[str, float] = {}
    for d in all_dates:
        holdings: dict[str, float] = {}
        complete = True
        for buy_date, ticker, u in units:
            if buy_date > d:
                continue
            px = closes.get(ticker, {}).get(d)
            if px is None:
                # Different exchange holiday: carry the last close forward.
                px = last_px.get(ticker)
            if px is None:
                complete = False
                break
            last_px[ticker] = px
            holdings[ticker] = holdings.get(ticker, 0.0) + u * px
        if not complete:
            continue
        bench_val = sum(u * bench[d] for bd, u in bench_units if bd <= d)
        cash = sum(bb.benchmark_amount for bb in tracker.buys if bb.date <= d)
        points.append(
            LivePoint(
                date=d,
                holdings=holdings,
                total=sum(holdings.values()),
                benchmark=bench_val,
                cash=cash,
            )
        )

    if not points:
        raise ValueError("No sessions with complete prices since the first buy.")

    daily_through: date | None = None
    daily_cutoff = _add_months(first_buy, daily_months)
    if points[-1].date > daily_cutoff:
        early = [p for p in points if p.date <= daily_cutoff]
        late = [p for p in points if p.date > daily_cutoff]
        keep = set(_month_end_sample([p.date for p in late])) | {late[-1].date}
        points = early + [p for p in late if p.date in keep]
        daily_through = early[-1].date if early else None

    invested: dict[str, float] = {}
    for buy in tracker.buys:
        for ticker, amount in buy.amounts.items():
            invested[ticker] = invested.get(ticker, 0.0) + amount
    latest = points[-1]
    holdings_now = sorted(
        (
            LiveHolding(
                ticker=t,
                name=tracker.names.get(t, t),
                value=v,
                invested=invested.get(t, 0.0),
            )
            for t, v in latest.holdings.items()
        ),
        key=lambda h: -h.value,
    )
    return LiveSeries(points=points, holdings=holdings_now, daily_through=daily_through)


# --------------------------------------------------------------------------- refresh


def _latest_uk_picks(root_dir: Path) -> tuple[str, list[str], dict[str, str]] | None:
    summary_path = root_dir / "data" / "global" / "summary.json"
    if not summary_path.exists():
        return None
    section = json.loads(summary_path.read_text(encoding="utf-8")).get("acwi_uk_accessible", {})
    window = section.get("latest_window")
    top3 = section.get("top3") or []
    if not window or not top3:
        return None
    tickers = [str(p.get("ticker", "")) for p in top3]
    names = {str(p.get("ticker", "")): str(p.get("name", "")) for p in top3}
    return str(window), tickers, names


def _default_fetcher(tickers: Sequence[str], start: date, end: date) -> list[dict[str, str]]:
    from monthly_momentum.acwi import fetch_yahoo_v8_daily_bars

    return fetch_yahoo_v8_daily_bars(tickers, start=start, end=end)


@dataclass(slots=True)
class TrackResult:
    tracker: LiveTracker
    series: LiveSeries | None
    chart_path: Path | None
    bought_window: str | None
    missing: list[str]


def run_live_tracker(
    root_dir: Path = Path("."),
    *,
    today: date | None = None,
    fetcher: PriceFetcher | None = None,
    render: bool = True,
) -> TrackResult:
    """Queue any new picks, fetch daily closes since inception, settle buys, and redraw."""
    today = today or date.today()
    fetch = fetcher or _default_fetcher
    live_dir = root_dir / LIVE_DIR
    tracker_path = live_dir / TRACKER_JSON
    closes_path = live_dir / DAILY_CLOSES_CSV
    if not tracker_path.exists():
        raise FileNotFoundError(f"{tracker_path} not found; create it with an inception date.")
    tracker = load_tracker(tracker_path)

    picks = _latest_uk_picks(root_dir)
    if picks is not None:
        window, tickers, names = picks
        queue_window_picks(tracker, window, tickers, names)

    closes = load_daily_closes(closes_path)
    wanted = [*tracker.tickers, tracker.benchmark]
    rows = fetch(wanted, tracker.inception - timedelta(days=5), today + timedelta(days=1))
    fetched: dict[str, dict[date, float]] = {}
    for row in rows:
        try:
            d = date.fromisoformat(row["date"])
            fetched.setdefault(row["ticker"], {})[d] = float(row["adj_close"])
        except (KeyError, ValueError):
            continue
    missing = [t for t in wanted if not fetched.get(t)]
    for ticker, fetched_series in fetched.items():
        # A fresh full fetch replaces the ticker's history (adjusted closes shift on
        # dividends); a failed fetch keeps what was committed.
        closes[ticker] = {d: px for d, px in fetched_series.items() if d >= tracker.inception}

    bought_window = tracker.pending.get("window") if tracker.pending else None
    if not settle_pending(tracker, closes):
        bought_window = None

    save_tracker(tracker, tracker_path)
    write_daily_closes(closes, closes_path)

    series: LiveSeries | None = None
    chart_path: Path | None = None
    if tracker.buys:
        series = build_live_series(tracker, closes)
        write_live_summary(tracker, series, live_dir / "summary.json")
        if render:
            from monthly_momentum.chart import generate_live_tracker_chart

            chart_path = generate_live_tracker_chart(tracker, series, root_dir / LIVE_CHART_ASSET)
    return TrackResult(
        tracker=tracker,
        series=series,
        chart_path=chart_path,
        bought_window=bought_window,
        missing=missing,
    )


def write_live_summary(tracker: LiveTracker, series: LiveSeries, path: Path) -> None:
    latest = series.latest
    payload = {
        "inception": tracker.inception.isoformat(),
        "as_of": latest.date.isoformat(),
        "sessions": len(series.points),
        "cash_in": round(latest.cash, 2),
        "portfolio_value": round(latest.total, 2),
        "benchmark_value": round(latest.benchmark, 2),
        "portfolio_return_pct": round((latest.total / latest.cash - 1.0) * 100.0, 2) + 0.0,
        "benchmark_return_pct": round((latest.benchmark / latest.cash - 1.0) * 100.0, 2) + 0.0,
        "holdings": [
            {
                "ticker": h.ticker,
                "name": h.name,
                "invested": round(h.invested, 2),
                "value": round(h.value, 2),
                "return_pct": round(h.return_pct, 2) + 0.0,
            }
            for h in series.holdings
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
