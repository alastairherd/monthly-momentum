"""Backtesting dataset loaders supporting canonical, Norgate, EODHD, and public CSVs."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from monthly_momentum.normalize import normalize_month, parse_flexible_date, ticker_match_key


@dataclass(slots=True)
class PricePoint:
    """Monthly price observation with both price close and dividend-adjusted close."""

    dt: date
    month: str
    ticker: str
    close: float
    adj_close: float
    market: str = "us"


@dataclass(slots=True)
class ConstituentInterval:
    """Point-in-time index membership interval for a ticker."""

    ticker: str
    start_date: date
    end_date: date | None
    index: str = "S&P 500"
    name: str = ""
    sector: str = ""


@dataclass(slots=True)
class CorporateEvent:
    """Corporate action or delisting event during the backtest window."""

    dt: date
    ticker: str
    event_type: str
    cash_per_share: float | None = None
    delist_return_pct: float | None = None
    notes: str = ""


@dataclass(slots=True)
class BacktestDataset:
    """Loaded market prices, point-in-time index constituents, and corporate events."""

    months: list[str]
    month_dates: dict[str, date]
    prices: dict[str, dict[str, PricePoint]]
    benchmark_prices: dict[str, PricePoint]
    constituents: list[ConstituentInterval]
    constituent_meta: dict[str, ConstituentInterval] = field(default_factory=dict)
    snapshots_by_month: dict[str, set[str]] = field(default_factory=dict)
    events: list[CorporateEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    benchmark_ticker: str = "^SP500TR"
    survivorship_warning: bool = False

    def is_member(self, ticker_key: str, month: str, dt: date) -> bool:
        """Return whether ``ticker_key`` was an index constituent in ``month``/``dt``."""
        if month in self.snapshots_by_month:
            return ticker_key in self.snapshots_by_month[month]
        intervals = [c for c in self.constituents if c.ticker == ticker_key]
        if not intervals:
            return False
        for iv in intervals:
            if iv.start_date <= dt and (iv.end_date is None or dt <= iv.end_date):
                return True
        return False


def _header_lookup(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        return {}
    return {" ".join(h.strip().lower().split()): h for h in fieldnames}


def _col(header_map: dict[str, str], *aliases: str) -> str | None:
    for alias in aliases:
        if alias in header_map:
            return header_map[alias]
    return None


def _parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip().replace(",", "")
    if not text or text.upper() in {"NA", "N/A", "NAN", "-", "NONE", "NULL"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_prices_csv(
    path: Path,
    benchmark_ticker: str | None = None,
) -> tuple[dict[str, dict[str, PricePoint]], dict[str, PricePoint], dict[str, date]]:
    prices: dict[str, dict[str, PricePoint]] = {}
    benchmark_prices: dict[str, PricePoint] = {}
    month_dates: dict[str, date] = {}
    bench_key = ticker_match_key(benchmark_ticker) if benchmark_ticker else None

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        hmap = _header_lookup(list(reader.fieldnames) if reader.fieldnames else None)
        date_col = _col(hmap, "date", "timestamp")
        ticker_col = _col(hmap, "ticker", "symbol", "code")
        close_col = _col(hmap, "close", "price")
        adj_col = _col(hmap, "adj_close", "adj close", "adjusted_close", "adjusted close")
        market_col = _col(hmap, "market", "exchange")

        if not date_col or not ticker_col or (not close_col and not adj_col):
            raise ValueError(
                f"Prices CSV {path} must contain date, ticker, and close/adj_close columns."
            )

        # Keep first trading date encountered per (ticker, YYYY-MM) when resampling daily data.
        for row in reader:
            raw_date = (row.get(date_col) or "").strip()
            dt = parse_flexible_date(raw_date)
            if dt is None:
                continue
            month = dt.strftime("%Y-%m")
            raw_ticker = (row.get(ticker_col) or "").strip()
            tkey = ticker_match_key(raw_ticker)
            if not tkey:
                continue

            close_val = _parse_float(row.get(close_col)) if close_col else None
            adj_val = _parse_float(row.get(adj_col)) if adj_col else None
            if close_val is None and adj_val is not None:
                close_val = adj_val
            if adj_val is None and close_val is not None:
                adj_val = close_val
            if close_val is None or adj_val is None or close_val <= 0.0 or adj_val <= 0.0:
                continue

            market = ((row.get(market_col) or "").strip().lower() if market_col else "") or "us"
            pt = PricePoint(
                dt=dt,
                month=month,
                ticker=tkey,
                close=close_val,
                adj_close=adj_val,
                market=market,
            )

            is_bench = market == "benchmark" or (bench_key is not None and tkey == bench_key)
            if is_bench:
                prev_b = benchmark_prices.get(month)
                if prev_b is None or dt < prev_b.dt:
                    benchmark_prices[month] = pt
            else:
                tmap = prices.setdefault(tkey, {})
                prev_p = tmap.get(month)
                if prev_p is None or dt < prev_p.dt:
                    tmap[month] = pt

            prev_md = month_dates.get(month)
            if prev_md is None or dt < prev_md:
                month_dates[month] = dt

    return prices, benchmark_prices, month_dates


def _load_constituents_intervals(
    path: Path,
) -> tuple[list[ConstituentInterval], dict[str, ConstituentInterval]]:
    intervals: list[ConstituentInterval] = []
    meta: dict[str, ConstituentInterval] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        hmap = _header_lookup(list(reader.fieldnames) if reader.fieldnames else None)
        t_col = _col(hmap, "ticker", "symbol")
        s_col = _col(hmap, "start_date", "date_added", "date added", "from_date")
        e_col = _col(hmap, "end_date", "removed_date", "exit_date", "to_date")
        i_col = _col(hmap, "index")
        n_col = _col(hmap, "name", "security", "company")
        sec_col = _col(hmap, "sector", "gics sector")

        if not t_col:
            raise ValueError(f"Constituents CSV {path} must contain a ticker/symbol column.")

        for row in reader:
            tkey = ticker_match_key(row.get(t_col) or "")
            if not tkey:
                continue
            raw_start = (row.get(s_col) or "").strip() if s_col else ""
            raw_end = (row.get(e_col) or "").strip() if e_col else ""
            start_dt = parse_flexible_date(raw_start) or date(1900, 1, 1)
            end_dt = parse_flexible_date(raw_end) if raw_end else None

            iv = ConstituentInterval(
                ticker=tkey,
                start_date=start_dt,
                end_date=end_dt,
                index=((row.get(i_col) or "").strip() if i_col else "") or "S&P 500",
                name=((row.get(n_col) or "").strip() if n_col else "") or tkey,
                sector=(row.get(sec_col) or "").strip() if sec_col else "",
            )
            intervals.append(iv)
            meta[tkey] = iv

    return intervals, meta


def _load_snapshots_csv(path: Path) -> dict[str, set[str]]:
    snapshots: dict[str, set[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        hmap = _header_lookup(list(reader.fieldnames) if reader.fieldnames else None)
        m_col = _col(hmap, "snapshot_month", "month")
        t_col = _col(hmap, "ticker", "symbol")
        if not m_col or not t_col:
            return {}
        for row in reader:
            raw_m = (row.get(m_col) or "").strip()
            tkey = ticker_match_key(row.get(t_col) or "")
            if not raw_m or not tkey:
                continue
            month = normalize_month(raw_m)
            snapshots.setdefault(month, set()).add(tkey)
    return snapshots


def _load_events_csv(path: Path) -> list[CorporateEvent]:
    events: list[CorporateEvent] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        hmap = _header_lookup(list(reader.fieldnames) if reader.fieldnames else None)
        d_col = _col(hmap, "date", "event_date")
        t_col = _col(hmap, "ticker", "symbol")
        type_col = _col(hmap, "event_type", "type")
        cash_col = _col(hmap, "cash_per_share", "cash")
        ret_col = _col(hmap, "delist_return_pct", "return_pct")
        notes_col = _col(hmap, "notes")
        if not d_col or not t_col or not type_col:
            raise ValueError(
                f"Events CSV {path} must contain date, ticker, and event_type columns."
            )
        for row in reader:
            dt = parse_flexible_date(row.get(d_col) or "")
            tkey = ticker_match_key(row.get(t_col) or "")
            ev_type = (row.get(type_col) or "").strip().lower()
            if dt is None or not tkey or not ev_type:
                continue
            events.append(
                CorporateEvent(
                    dt=dt,
                    ticker=tkey,
                    event_type=ev_type,
                    cash_per_share=_parse_float(row.get(cash_col)) if cash_col else None,
                    delist_return_pct=_parse_float(row.get(ret_col)) if ret_col else None,
                    notes=(row.get(notes_col) or "").strip() if notes_col else "",
                )
            )
    events.sort(key=lambda e: (e.dt, e.ticker))
    return events


def load_backtest_dataset(
    prices_path: Path,
    constituents_path: Path,
    events_path: Path | None = None,
    benchmark_path: Path | None = None,
    benchmark_ticker: str | None = "^SP500TR",
    snapshots_path: Path | None = None,
) -> BacktestDataset:
    """Load prices, index constituent intervals, snapshots, events, and benchmark."""
    prices, benchmark_prices, month_dates = _load_prices_csv(
        prices_path, benchmark_ticker=benchmark_ticker
    )
    if benchmark_path is not None and benchmark_path.exists():
        extra_p, extra_b, extra_md = _load_prices_csv(
            benchmark_path, benchmark_ticker=benchmark_ticker
        )
        if extra_b:
            benchmark_prices.update(extra_b)
        elif benchmark_ticker and ticker_match_key(benchmark_ticker) in extra_p:
            benchmark_prices.update(extra_p[ticker_match_key(benchmark_ticker)])
        elif len(extra_p) == 1:
            benchmark_prices.update(next(iter(extra_p.values())))
        for m, dt in extra_md.items():
            month_dates.setdefault(m, dt)

    constituents, constituent_meta = _load_constituents_intervals(constituents_path)
    snapshots_by_month = (
        _load_snapshots_csv(snapshots_path)
        if snapshots_path is not None and snapshots_path.exists()
        else {}
    )
    events = (
        _load_events_csv(events_path) if events_path is not None and events_path.exists() else []
    )

    all_months = sorted(month_dates.keys())
    warnings: list[str] = []
    has_exits = any(c.end_date is not None for c in constituents)
    if not has_exits and not events:
        warnings.append(
            "Survivorship-bias notice: constituents contain no historical exit dates "
            "and no delisting/takeover events file was supplied."
        )

    return BacktestDataset(
        months=all_months,
        month_dates=month_dates,
        prices=prices,
        benchmark_prices=benchmark_prices,
        constituents=constituents,
        constituent_meta=constituent_meta,
        snapshots_by_month=snapshots_by_month,
        events=events,
        warnings=warnings,
        benchmark_ticker=benchmark_ticker or "^SP500TR",
        survivorship_warning=not has_exits and not events,
    )
