"""Live S&P 500 constituent and Yahoo Finance return/price fetching."""

from __future__ import annotations

import csv
import math
import time
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from monthly_momentum.models import SecurityMetric
from monthly_momentum.normalize import (
    normalize_month,
    normalize_ticker,
    parse_flexible_date,
    subtract_calendar_months,
    subtract_calendar_years,
    ticker_match_key,
    to_yahoo_ticker,
)

WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
DEFAULT_USER_AGENT = "monthly-momentum/0.1.0 (https://github.com/alastairherd/monthly-momentum)"
CONSTITUENT_COLUMNS: list[str] = [
    "ticker",
    "name",
    "sector",
    "sub_industry",
    "date_added",
    "index",
]


@dataclass(slots=True)
class ConstituentRecord:
    """Index constituent metadata row."""

    ticker: str
    name: str
    sector: str = ""
    sub_industry: str = ""
    date_added: str = ""
    index: str = "S&P 500"


class _WikiTableParser(HTMLParser):
    """Lightweight stdlib HTML parser extracting Wikipedia wikitable rows."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[dict[str, Any]] = []
        self._table_depth = 0
        self._in_target = False
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                css_class = attr_map.get("class") or ""
                table_id = attr_map.get("id") or ""
                if table_id == "constituents" or "wikitable" in css_class:
                    self._in_target = True
                    self.tables.append({"id": table_id, "rows": []})
        elif self._in_target and self._table_depth == 1:
            if tag == "tr":
                self._current_row = []
            elif tag in {"td", "th"} and self._current_row is not None:
                self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._table_depth == 1 and self._in_target:
                self._in_target = False
            self._table_depth = max(0, self._table_depth - 1)
        elif self._in_target and self._table_depth == 1:
            if tag in {"td", "th"} and self._current_cell is not None:
                assert self._current_row is not None
                text = " ".join("".join(self._current_cell).split())
                self._current_row.append(text)
                self._current_cell = None
            elif tag == "tr" and self._current_row is not None:
                if self._current_row:
                    self.tables[-1]["rows"].append(self._current_row)
                self._current_row = None


def parse_sp500_wikipedia_html(html: str, index: str = "S&P 500") -> list[ConstituentRecord]:
    """Parse Wikipedia's S&P 500 constituents table HTML into ConstituentRecord entries."""
    parser = _WikiTableParser()
    parser.feed(html)

    selected_rows: list[list[str]] | None = None
    for table in parser.tables:
        if table["id"] == "constituents" and table["rows"]:
            selected_rows = table["rows"]
            break
    if selected_rows is None:
        for table in parser.tables:
            rows = table["rows"]
            if rows and any(col.lower() in {"symbol", "ticker"} for col in rows[0]):
                selected_rows = rows
                break

    if not selected_rows or len(selected_rows) < 2:
        raise ValueError("Could not find S&P 500 constituents table in Wikipedia HTML.")

    header_row = [h.strip().lower() for h in selected_rows[0]]

    def _idx(candidates: tuple[str, ...]) -> int | None:
        for c in candidates:
            if c in header_row:
                return header_row.index(c)
        return None

    sym_idx = _idx(("symbol", "ticker"))
    sec_idx = _idx(("security", "company", "name"))
    sector_idx = _idx(("gics sector", "sector"))
    sub_idx = _idx(("gics sub-industry", "sub-industry", "gics sub industry"))
    added_idx = _idx(("date added", "date first added"))

    if sym_idx is None:
        raise ValueError(f"Wikipedia table missing Symbol/Ticker column: {selected_rows[0]!r}")

    records: list[ConstituentRecord] = []
    seen: set[str] = set()
    for row in selected_rows[1:]:
        if sym_idx >= len(row):
            continue
        ticker = normalize_ticker(row[sym_idx])
        if not ticker:
            continue
        key = ticker_match_key(ticker)
        if key in seen:
            continue
        seen.add(key)

        name = row[sec_idx].strip() if sec_idx is not None and sec_idx < len(row) else ticker
        sector = row[sector_idx].strip() if sector_idx is not None and sector_idx < len(row) else ""
        sub_ind = row[sub_idx].strip() if sub_idx is not None and sub_idx < len(row) else ""
        raw_added = row[added_idx].strip() if added_idx is not None and added_idx < len(row) else ""
        parsed_added = parse_flexible_date(raw_added)
        date_added = parsed_added.isoformat() if parsed_added else raw_added

        records.append(
            ConstituentRecord(
                ticker=ticker,
                name=name or ticker,
                sector=sector,
                sub_industry=sub_ind,
                date_added=date_added,
                index=index,
            )
        )

    records.sort(key=lambda r: r.ticker)
    return records


def fetch_sp500_constituents(
    timeout: float = 20.0,
    url: str = WIKIPEDIA_SP500_URL,
) -> list[ConstituentRecord]:
    """Fetch the live S&P 500 constituent roster from Wikipedia."""
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_sp500_wikipedia_html(html, index="S&P 500")


def load_constituents_csv(path: Path, default_index: str = "S&P 500") -> list[ConstituentRecord]:
    """Load index constituents from a local CSV file."""
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"Constituents CSV {path} has no header row.")
        header_map = {" ".join(h.strip().lower().split()): h for h in reader.fieldnames}

        def _col(*aliases: str) -> str | None:
            for a in aliases:
                if a in header_map:
                    return header_map[a]
            return None

        t_col = _col("ticker", "symbol")
        if t_col is None:
            raise ValueError(f"Constituents CSV {path} needs a ticker or symbol column.")
        n_col = _col("name", "security", "company", "company name")
        s_col = _col("sector", "gics sector")
        sub_col = _col("sub_industry", "gics sub-industry")
        d_col = _col("date_added", "date added", "start_date")
        i_col = _col("index")

        records: list[ConstituentRecord] = []
        seen: set[str] = set()
        for row in reader:
            ticker = normalize_ticker(row.get(t_col) or "")
            if not ticker:
                continue
            key = ticker_match_key(ticker)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                ConstituentRecord(
                    ticker=ticker,
                    name=((row.get(n_col) or "").strip() if n_col else "") or ticker,
                    sector=(row.get(s_col) or "").strip() if s_col else "",
                    sub_industry=(row.get(sub_col) or "").strip() if sub_col else "",
                    date_added=(row.get(d_col) or "").strip() if d_col else "",
                    index=((row.get(i_col) or "").strip() if i_col else "") or default_index,
                )
            )
    return records


def write_constituents_csv(records: list[ConstituentRecord], path: Path) -> None:
    """Persist index constituent records deterministically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: r.ticker)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CONSTITUENT_COLUMNS)
        writer.writeheader()
        for rec in ordered:
            writer.writerow(
                {
                    "ticker": rec.ticker,
                    "name": rec.name,
                    "sector": rec.sector,
                    "sub_industry": rec.sub_industry,
                    "date_added": rec.date_added,
                    "index": rec.index,
                }
            )


def _to_date_float_map(
    series: Sequence[tuple[date, float]] | Mapping[date, float],
) -> dict[date, float]:
    items = series.items() if isinstance(series, Mapping) else series
    result: dict[date, float] = {}
    for dt, val in items:
        if val is not None and math.isfinite(val) and val > 0.0:
            result[dt] = float(val)
    return result


def _find_on_or_before(
    sorted_dates: list[date],
    target: date,
    max_gap_days: int,
) -> date | None:
    chosen: date | None = None
    for d in sorted_dates:
        if d <= target:
            chosen = d
        else:
            break
    if chosen is None:
        return None
    if (target - chosen).days > max_gap_days:
        return None
    return chosen


def compute_returns_from_history(
    close_series: Sequence[tuple[date, float]] | Mapping[date, float],
    adj_close_series: Sequence[tuple[date, float]] | Mapping[date, float],
    as_of: date | None = None,
    max_gap_days: int = 15,
) -> tuple[float | None, float | None]:
    """Compute (3y_total_return_pct, 3m_price_return_pct) from price histories.

    Uses ``adj_close`` for the 3-year total return (including dividends) and
    ``close`` for the 3-month price return filter per Rule 3.
    """
    close_map = _to_date_float_map(close_series)
    adj_map = _to_date_float_map(adj_close_series)
    common_dates = sorted(set(close_map) & set(adj_map))
    if as_of is not None:
        common_dates = [d for d in common_dates if d <= as_of]
    if not common_dates:
        return None, None

    latest = common_dates[-1]
    target_3y = subtract_calendar_years(latest, 3)
    target_3m = subtract_calendar_months(latest, 3)

    adj_dates = sorted(d for d in adj_map if d <= latest)
    cls_dates = sorted(d for d in close_map if d <= latest)

    d_3y = _find_on_or_before(adj_dates, target_3y, max_gap_days=max_gap_days)
    d_3m = _find_on_or_before(cls_dates, target_3m, max_gap_days=max_gap_days)

    ret_3y: float | None = None
    if d_3y is not None and adj_map[d_3y] > 0.0:
        ret_3y = (adj_map[latest] / adj_map[d_3y] - 1.0) * 100.0

    ret_3m: float | None = None
    if d_3m is not None and close_map[d_3m] > 0.0:
        ret_3m = (close_map[latest] / close_map[d_3m] - 1.0) * 100.0

    return ret_3y, ret_3m


def _coerce_index_date(idx_val: Any) -> date | None:
    if hasattr(idx_val, "date"):
        res = idx_val.date()
        if isinstance(res, date):
            return res
    if isinstance(idx_val, date):
        return idx_val
    try:
        return date.fromisoformat(str(idx_val)[:10])
    except ValueError:
        return None


def extract_yf_price_maps(
    df: Any,
    yahoo_tickers: Sequence[str],
) -> dict[str, tuple[dict[date, float], dict[date, float]]]:
    """Extract per-ticker ``(close_map, adj_close_map)`` from a yfinance DataFrame."""
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return {}

    result: dict[str, tuple[dict[date, float], dict[date, float]]] = {}
    is_multi = isinstance(df.columns, pd.MultiIndex)

    def _series_to_map(series: Any) -> dict[date, float]:
        out: dict[date, float] = {}
        if series is None:
            return out
        for idx, val in series.items():
            dt = _coerce_index_date(idx)
            if dt is None:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if math.isfinite(num) and num > 0.0:
                out[dt] = num
        return out

    if not is_multi:
        if len(yahoo_tickers) == 1 and ("Close" in df.columns or "Adj Close" in df.columns):
            close_s = df["Close"] if "Close" in df.columns else df.get("Adj Close")
            adj_s = df["Adj Close"] if "Adj Close" in df.columns else close_s
            c_map = _series_to_map(close_s)
            a_map = _series_to_map(adj_s)
            if c_map or a_map:
                result[yahoo_tickers[0]] = (c_map, a_map)
        return result

    level0 = set(df.columns.get_level_values(0))
    level1 = set(df.columns.get_level_values(1))

    for sym in yahoo_tickers:
        close_s = None
        adj_s = None
        if "Close" in level0 or "Adj Close" in level0:
            if ("Close", sym) in df.columns:
                close_s = df[("Close", sym)]
            if ("Adj Close", sym) in df.columns:
                adj_s = df[("Adj Close", sym)]
        elif sym in level0 and ("Close" in level1 or "Adj Close" in level1):
            sub = df[sym]
            if "Close" in sub.columns:
                close_s = sub["Close"]
            if "Adj Close" in sub.columns:
                adj_s = sub["Adj Close"]

        if close_s is None and adj_s is not None:
            close_s = adj_s
        if adj_s is None and close_s is not None:
            adj_s = close_s

        if close_s is not None and adj_s is not None:
            c_map = _series_to_map(close_s)
            a_map = _series_to_map(adj_s)
            if c_map and a_map:
                result[sym] = (c_map, a_map)

    return result


def _download_yf_batched(
    yahoo_tickers: Sequence[str],
    start: date,
    end: date,
    interval: str,
    batch_size: int = 100,
    pause_seconds: float = 0.2,
) -> dict[str, tuple[dict[date, float], dict[date, float]]]:
    import yfinance as yf

    all_maps: dict[str, tuple[dict[date, float], dict[date, float]]] = {}
    unique_syms = list(dict.fromkeys(yahoo_tickers))

    for i in range(0, len(unique_syms), batch_size):
        batch = unique_syms[i : i + batch_size]
        df = yf.download(
            tickers=batch if len(batch) > 1 else batch[0],
            start=start.isoformat(),
            end=end.isoformat(),
            interval=interval,
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=True,
        )
        extracted = extract_yf_price_maps(df, batch)
        all_maps.update(extracted)

        missing = [sym for sym in batch if sym not in extracted]
        if missing and len(batch) > 1:
            for sub_start in range(0, len(missing), 20):
                sub_batch = missing[sub_start : sub_start + 20]
                retry_df = yf.download(
                    tickers=sub_batch if len(sub_batch) > 1 else sub_batch[0],
                    start=start.isoformat(),
                    end=end.isoformat(),
                    interval=interval,
                    auto_adjust=False,
                    actions=False,
                    progress=False,
                    threads=True,
                )
                all_maps.update(extract_yf_price_maps(retry_df, sub_batch))

        if pause_seconds > 0 and i + batch_size < len(unique_syms):
            time.sleep(pause_seconds)

    return all_maps


def fetch_live_metrics(
    constituents: Sequence[ConstituentRecord],
    index: str = "S&P 500",
    as_of: date | None = None,
    batch_size: int = 100,
) -> list[SecurityMetric]:
    """Fetch 3-year total return and 3-month price return for live ranking via yfinance."""
    eff_as_of = as_of or datetime.now(UTC).date()
    start = subtract_calendar_years(eff_as_of, 3) - timedelta(days=30)
    end = eff_as_of + timedelta(days=1)

    yahoo_by_canonical = {c.ticker: to_yahoo_ticker(c.ticker) for c in constituents}
    maps = _download_yf_batched(
        list(yahoo_by_canonical.values()),
        start=start,
        end=end,
        interval="1d",
        batch_size=batch_size,
    )

    metrics: list[SecurityMetric] = []
    for c in constituents:
        ysym = yahoo_by_canonical[c.ticker]
        if ysym in maps:
            c_map, a_map = maps[ysym]
            ret_3y, ret_3m = compute_returns_from_history(c_map, a_map, as_of=eff_as_of)
        else:
            ret_3y, ret_3m = None, None
        metrics.append(
            SecurityMetric(
                ticker=c.ticker,
                name=c.name,
                index=c.index or index,
                return_3y_pct=ret_3y,
                return_3m_pct=ret_3m,
                return_type="total_return",
                source="yfinance",
                sector=c.sector,
            )
        )
    return metrics


def write_raw_metrics_csv(metrics: Sequence[SecurityMetric], path: Path, month: str) -> None:
    """Save raw fetched constituent return metrics to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    norm_month = normalize_month(month)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "month",
                "ticker",
                "name",
                "index",
                "sector",
                "return_3y_pct",
                "return_3m_pct",
                "return_type",
                "source",
            ],
        )
        writer.writeheader()
        for m in metrics:
            writer.writerow(
                {
                    "month": norm_month,
                    "ticker": m.ticker,
                    "name": m.name,
                    "index": m.index,
                    "sector": m.sector,
                    "return_3y_pct": (
                        f"{m.return_3y_pct:.4f}" if m.return_3y_pct is not None else ""
                    ),
                    "return_3m_pct": (
                        f"{m.return_3m_pct:.4f}" if m.return_3m_pct is not None else ""
                    ),
                    "return_type": m.return_type,
                    "source": m.source,
                }
            )


def aggregate_completed_monthly_bars(
    price_maps: Mapping[str, tuple[Mapping[date, float], Mapping[date, float]]],
    canonical_by_yahoo: Mapping[str, str],
    benchmark_yahoo: str | None = "^SP500TR",
    as_of: date | None = None,
    include_mtd: bool = False,
) -> list[dict[str, str]]:
    """Collapse Yahoo monthly bars into completed ``YYYY-MM-01`` rows per ticker.

    Yahoo ``1mo`` downloads include both ``YYYY-MM-01`` and an in-progress
    mid-month bar. Grouping by ``YYYY-MM``, taking the latest valid bar, and
    excluding the active month unless ``include_mtd=True`` guarantees idempotent
    completed-month snapshots with zero lookahead.
    """
    eff_as_of = as_of or datetime.now(UTC).date()
    cutoff_month = eff_as_of.strftime("%Y-%m")

    rows_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for ysym, (c_map, a_map) in price_maps.items():
        canonical = canonical_by_yahoo.get(ysym, ysym)
        market = "benchmark" if benchmark_yahoo and ysym == benchmark_yahoo else "us"

        by_month: dict[str, tuple[date, float, float]] = {}
        for dt in sorted(set(c_map) & set(a_map)):
            month_key = dt.strftime("%Y-%m")
            if not include_mtd and month_key >= cutoff_month:
                continue
            by_month[month_key] = (dt, c_map[dt], a_map[dt])

        for month_key, (_dt, close_val, adj_val) in by_month.items():
            bar_date = f"{month_key}-01"
            rows_by_key[(bar_date, canonical)] = {
                "date": bar_date,
                "ticker": canonical,
                "close": f"{close_val:.4f}",
                "adj_close": f"{adj_val:.4f}",
                "market": market,
            }

    return [rows_by_key[k] for k in sorted(rows_by_key)]


def fetch_monthly_price_history(
    constituents: Sequence[ConstituentRecord],
    benchmark_ticker: str = "^SP500TR",
    years: int = 12,
    as_of: date | None = None,
    include_mtd: bool = False,
    batch_size: int = 100,
) -> list[dict[str, str]]:
    """Fetch completed monthly ``Close`` and ``Adj Close`` bars via yfinance."""
    eff_as_of = as_of or datetime.now(UTC).date()
    start = subtract_calendar_years(eff_as_of, years) - timedelta(days=35)
    end = eff_as_of + timedelta(days=2)

    canonical_by_yahoo: dict[str, str] = {to_yahoo_ticker(c.ticker): c.ticker for c in constituents}
    if benchmark_ticker:
        canonical_by_yahoo[benchmark_ticker] = benchmark_ticker

    maps = _download_yf_batched(
        list(canonical_by_yahoo.keys()),
        start=start,
        end=end,
        interval="1mo",
        batch_size=batch_size,
    )
    return aggregate_completed_monthly_bars(
        maps,
        canonical_by_yahoo=canonical_by_yahoo,
        benchmark_yahoo=benchmark_ticker,
        as_of=eff_as_of,
        include_mtd=include_mtd,
    )
