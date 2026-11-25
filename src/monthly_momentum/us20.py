"""20-year survivorship-aware US S&P 500 dataset builder and ratio splicer."""

from __future__ import annotations

import csv
import io
import math
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from monthly_momentum.live import (
    DEFAULT_USER_AGENT,
    ConstituentRecord,
    fetch_monthly_price_history,
    fetch_sp500_constituents,
    write_constituents_csv,
)
from monthly_momentum.normalize import add_months, normalize_ticker, parse_flexible_date
from monthly_momentum.refresh import (
    PRICE_COLUMNS,
    merge_monthly_price_rows,
    update_constituent_snapshots,
    write_monthly_prices_csv,
)
from monthly_momentum.report import PublicReportSummary, rebuild_public_reports

FJA_SP500_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
HF_PARQUET_URLS: tuple[str, ...] = tuple(
    f"https://huggingface.co/datasets/weib08/Stocks-Daily-Price/resolve/main/data/train-0000{i}-of-00004.parquet"
    for i in range(4)
)

# Safe symbol aliases mapping fja05680 historical symbols to weib08 symbols without
# colliding with unrelated active companies (e.g. WAMUQ vs WM Waste Management).
HISTORICAL_SYMBOL_ALIASES: dict[str, tuple[str, ...]] = {
    "ABK": ("ABK", "ABKFQ"),
    "CC": ("CC", "CCTYQ"),
    "FNM": ("FNM", "FNMA"),
    "FRC": ("FRC", "FRCB"),
    "FRE": ("FRE", "FMCC"),
    "LEHMQ": ("LEHMQ", "LEH"),
    "SIVB": ("SIVB", "SIVBQ"),
}

CONSTITUENT_HISTORY_COLUMNS: list[str] = [
    "ticker",
    "start_date",
    "end_date",
    "index",
    "name",
    "sector",
]


@dataclass(slots=True)
class US20BuildResult:
    """Summary of a full 20-year survivorship-aware US dataset build."""

    history_rows_count: int
    active_constituents_count: int
    hf_tickers_matched: int
    yahoo_tickers_matched: int
    price_rows_count: int
    report: PublicReportSummary


def _symbol_candidates(canonical_ticker: str) -> list[str]:
    norm = normalize_ticker(canonical_ticker)
    cands: list[str] = [norm, norm.replace(".", "-"), norm.replace("-", ".")]
    for alias in HISTORICAL_SYMBOL_ALIASES.get(norm, ()):
        if alias not in cands:
            cands.append(alias)
    return list(dict.fromkeys(cands))


def fetch_fja_sp500_intervals(
    url: str = FJA_SP500_URL,
    timeout: float = 20.0,
) -> list[dict[str, str]]:
    """Fetch historical S&P 500 membership intervals (1996-present) from fja05680/sp500."""
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    rows: list[dict[str, str]] = []
    for raw in csv.DictReader(io.StringIO(text)):
        t = normalize_ticker(raw.get("ticker") or "")
        if not t:
            continue
        rows.append(
            {
                "ticker": t,
                "start_date": (raw.get("start_date") or "").strip(),
                "end_date": (raw.get("end_date") or "").strip(),
            }
        )
    return rows


def build_constituents_history(
    fja_rows: Sequence[Mapping[str, str]],
    wiki_records: Sequence[ConstituentRecord],
    as_of: date,
) -> list[dict[str, str]]:
    """Merge historical S&P 500 intervals with current Wikipedia active constituents."""
    wiki_by_ticker = {r.ticker: r for r in wiki_records}
    merged: list[dict[str, str]] = []
    open_tickers: set[str] = set()

    for row in fja_rows:
        t = normalize_ticker(row.get("ticker") or "")
        if not t:
            continue
        start_s = (row.get("start_date") or "").strip() or "1996-01-02"
        end_s = (row.get("end_date") or "").strip()
        wiki = wiki_by_ticker.get(t)

        if not end_s:
            if t in wiki_by_ticker:
                open_tickers.add(t)
            else:
                # Ticker exited S&P 500 after the latest static fja05680 snapshot.
                end_s = as_of.isoformat()

        merged.append(
            {
                "ticker": t,
                "start_date": start_s,
                "end_date": end_s,
                "index": "S&P 500",
                "name": wiki.name if wiki else t,
                "sector": wiki.sector if wiki else "",
            }
        )

    for t, wiki in sorted(wiki_by_ticker.items()):
        if t not in open_tickers:
            parsed_add = parse_flexible_date(wiki.date_added)
            start_s = parsed_add.isoformat() if parsed_add else as_of.isoformat()
            merged.append(
                {
                    "ticker": t,
                    "start_date": start_s,
                    "end_date": "",
                    "index": wiki.index or "S&P 500",
                    "name": wiki.name,
                    "sector": wiki.sector,
                }
            )

    merged.sort(key=lambda r: (r["ticker"], r["start_date"], r["end_date"]))
    return merged


def write_constituents_history_csv(rows: Sequence[Mapping[str, str]], path: Path) -> None:
    """Persist historical S&P 500 membership intervals to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CONSTITUENT_HISTORY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CONSTITUENT_HISTORY_COLUMNS})


def clean_and_collapse_daily_to_monthly(
    daily_rows: Sequence[tuple[str, float, float]],
    min_date: str = "2002-12-01",
) -> dict[str, tuple[float, float]]:
    """Clean invalid/glitch daily bars and collapse to end-of-month ``(close, adj_close)``.

    Removes non-positive or non-finite values and isolated 1-2 day reverting
    price glitches (>5x or <0.2x relative to both neighboring days) while
    preserving genuine corporate collapses such as Lehman Brothers or SVB.
    """
    filtered: list[tuple[str, float, float]] = []
    for dt_s, close_v, adj_v in daily_rows:
        if dt_s < min_date:
            continue
        if (
            close_v is None
            or adj_v is None
            or not math.isfinite(close_v)
            or not math.isfinite(adj_v)
            or close_v <= 0.0
            or adj_v <= 0.0
        ):
            continue
        filtered.append((dt_s, float(close_v), float(adj_v)))

    if not filtered:
        return {}

    filtered.sort(key=lambda x: x[0])

    # Remove isolated 1-day reverting glitches in adj_close or close.
    cleaned: list[tuple[str, float, float]] = []
    n = len(filtered)
    for i, item in enumerate(filtered):
        if 0 < i < n - 1:
            prev_adj = filtered[i - 1][2]
            next_adj = filtered[i + 1][2]
            cur_adj = item[2]
            neighbors_close = (
                max(prev_adj, next_adj) / min(prev_adj, next_adj) <= 2.0
                if min(prev_adj, next_adj) > 0.0
                else False
            )
            if neighbors_close and (
                cur_adj > 5.0 * max(prev_adj, next_adj) or cur_adj < 0.2 * min(prev_adj, next_adj)
            ):
                continue
        cleaned.append(item)

    by_month: dict[str, tuple[str, float, float]] = {}
    for dt_s, close_v, adj_v in cleaned:
        month = dt_s[:7]
        prev = by_month.get(month)
        if prev is None or dt_s >= prev[0]:
            by_month[month] = (dt_s, close_v, adj_v)

    return {m: (vals[1], vals[2]) for m, vals in sorted(by_month.items())}


def splice_price_series(
    historical_bars: Mapping[str, tuple[float, float]],
    yahoo_bars: Mapping[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Ratio-splice historical bars onto Yahoo Finance bars at earliest overlap."""
    if not yahoo_bars:
        return dict(historical_bars)
    if not historical_bars:
        return dict(yahoo_bars)

    overlap = sorted(set(historical_bars) & set(yahoo_bars))
    out: dict[str, tuple[float, float]] = {}
    if overlap:
        ov = overlap[0]
        h_close, h_adj = historical_bars[ov]
        y_close, y_adj = yahoo_bars[ov]
        close_scale = (y_close / h_close) if h_close > 0.0 and y_close > 0.0 else 1.0
        adj_scale = (y_adj / h_adj) if h_adj > 0.0 and y_adj > 0.0 else 1.0
        for m, (c_v, a_v) in historical_bars.items():
            if m < ov:
                out[m] = (c_v * close_scale, a_v * adj_scale)
        for m, vals in yahoo_bars.items():
            out[m] = vals
    else:
        out.update(historical_bars)
        out.update(yahoo_bars)

    return {m: out[m] for m in sorted(out)}


def _download_hf_parquet_shards(
    cache_dir: Path,
    urls: Sequence[str] = HF_PARQUET_URLS,
) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for idx, url in enumerate(urls):
        dest = cache_dir / f"train-0000{idx}-of-00004.parquet"
        if not dest.exists() or dest.stat().st_size == 0:
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as resp, dest.open("wb") as out_fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out_fh.write(chunk)
        paths.append(dest)
    return paths


def extract_sp500_monthly_from_hf(
    cache_dir: Path,
    target_tickers: Sequence[str],
    min_date: str = "2002-12-01",
    parquet_paths: Sequence[Path] | None = None,
) -> dict[str, dict[str, tuple[float, float]]]:
    """Stream Hugging Face Parquet shards and return monthly bars keyed by canonical ticker."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    shards = (
        list(parquet_paths) if parquet_paths is not None else _download_hf_parquet_shards(cache_dir)
    )

    candidate_to_canonical: dict[str, list[str]] = {}
    all_symbols: set[str] = set()
    for t in target_tickers:
        norm = normalize_ticker(t)
        for cand in _symbol_candidates(norm):
            all_symbols.add(cand)
            candidate_to_canonical.setdefault(cand, []).append(norm)

    pa_symbols = pa.array(sorted(all_symbols), type=pa.string())
    daily_by_symbol: dict[str, list[tuple[str, float, float]]] = {}

    for shard_path in shards:
        table = pq.read_table(
            shard_path,
            columns=["symbol", "date", "close", "adj_close"],
        )
        sym_col = pc.cast(table["symbol"], pa.string())
        dt_col = pc.cast(table["date"], pa.string())
        mask = pc.and_(
            pc.is_in(sym_col, value_set=pa_symbols),
            pc.greater_equal(dt_col, min_date),
        )
        filtered = table.filter(mask)
        if filtered.num_rows == 0:
            continue

        syms = filtered["symbol"].to_pylist()
        dts = filtered["date"].to_pylist()
        closes = filtered["close"].to_pylist()
        adjs = filtered["adj_close"].to_pylist()
        for sym, dt_v, cls_v, adj_v in zip(syms, dts, closes, adjs, strict=True):
            if sym is None or dt_v is None or cls_v is None or adj_v is None:
                continue
            daily_by_symbol.setdefault(str(sym), []).append(
                (str(dt_v)[:10], float(cls_v), float(adj_v))
            )

    monthly_by_symbol = {
        sym: clean_and_collapse_daily_to_monthly(rows, min_date=min_date)
        for sym, rows in daily_by_symbol.items()
    }

    result: dict[str, dict[str, tuple[float, float]]] = {}
    for t in target_tickers:
        norm = normalize_ticker(t)
        for cand in _symbol_candidates(norm):
            bars = monthly_by_symbol.get(cand)
            if bars:
                result[norm] = bars
                break

    return result


def build_us20_dataset(
    root_dir: Path = Path("."),
    cache_dir: Path | None = None,
    as_of: date | None = None,
    min_date: str = "2002-12-01",
    batch_size: int = 100,
    contribution: float = 500.0,
    fee_pct: float = 0.15,
) -> US20BuildResult:
    """Build 20-year survivorship-aware US S&P 500 dataset and regenerate reports."""
    eff_as_of = as_of or datetime.now(UTC).date()
    eff_cache = cache_dir or (root_dir / "data" / "raw" / "hf_cache")
    data_dir = root_dir / "data"

    wiki_records = fetch_sp500_constituents()
    write_constituents_csv(wiki_records, data_dir / "constituents.csv")

    fja_rows = fetch_fja_sp500_intervals()
    history_rows = build_constituents_history(fja_rows, wiki_records, as_of=eff_as_of)
    write_constituents_history_csv(history_rows, data_dir / "constituents_history.csv")

    all_tickers = sorted({r["ticker"] for r in history_rows})
    raw_hf_monthly = extract_sp500_monthly_from_hf(
        cache_dir=eff_cache,
        target_tickers=all_tickers,
        min_date=min_date,
    )

    # Guard against reused tickers (e.g., 2014 Weibo 'WB' matching 1996-2009 Wachovia 'WB')
    # by verifying HF monthly bars overlap at least one membership interval for that ticker.
    intervals_by_ticker: dict[str, list[tuple[str, str]]] = {}
    for row in history_rows:
        s_m = (row.get("start_date") or "1900-01-01")[:7]
        e_m = (row.get("end_date") or "2100-12-31")[:7]
        intervals_by_ticker.setdefault(row["ticker"], []).append((s_m, e_m))

    hf_monthly: dict[str, dict[str, tuple[float, float]]] = {}
    for t, bars in raw_hf_monthly.items():
        ivs = intervals_by_ticker.get(t, [])
        valid_bars = {
            m: vals
            for m, vals in bars.items()
            if any(add_months(s_m, -40) <= m <= e_m for s_m, e_m in ivs)
        }
        if valid_bars:
            hf_monthly[t] = valid_bars

    # Fetch 12y monthly bars for current S&P 500 constituents and 25y benchmark ^SP500TR.
    yf_stock_rows = fetch_monthly_price_history(
        constituents=wiki_records,
        benchmark_ticker="",
        years=12,
        as_of=eff_as_of,
        include_mtd=False,
        batch_size=batch_size,
    )
    yf_bench_rows = fetch_monthly_price_history(
        constituents=[],
        benchmark_ticker="^SP500TR",
        years=25,
        as_of=eff_as_of,
        include_mtd=False,
        batch_size=1,
    )

    yf_by_ticker: dict[str, dict[str, tuple[float, float]]] = {}
    for row in yf_stock_rows + yf_bench_rows:
        t = row["ticker"]
        m = row["date"][:7]
        yf_by_ticker.setdefault(t, {})[m] = (float(row["close"]), float(row["adj_close"]))

    cutoff_month = eff_as_of.strftime("%Y-%m")
    final_rows: list[dict[str, str]] = []
    for t in sorted(set(hf_monthly) | set(yf_by_ticker)):
        market = "benchmark" if t == "^SP500TR" else "us"
        hist_bars = {m: vals for m, vals in hf_monthly.get(t, {}).items() if m < cutoff_month}
        spliced = splice_price_series(hist_bars, yf_by_ticker.get(t, {}))
        for m, (cls_v, adj_v) in spliced.items():
            final_rows.append(
                {
                    "date": f"{m}-01",
                    "ticker": t,
                    "close": f"{cls_v:.4f}",
                    "adj_close": f"{adj_v:.4f}",
                    "market": market,
                }
            )

    final_rows.sort(key=lambda r: (r["date"], r["ticker"]))
    prices_path = data_dir / "monthly_prices.csv"
    # Use merge helper if an earlier custom ticker existed outside this run, otherwise clean write.
    write_monthly_prices_csv(final_rows, prices_path)

    latest_bar_month = max(r["date"][:7] for r in final_rows)
    snapshot_window = add_months(latest_bar_month, 1)
    update_constituent_snapshots(
        data_dir / "constituent_snapshots.csv",
        snapshot_month=snapshot_window,
        records=wiki_records,
    )

    report = rebuild_public_reports(
        root_dir=root_dir,
        contribution=contribution,
        fee_pct=fee_pct,
    )

    return US20BuildResult(
        history_rows_count=len(history_rows),
        active_constituents_count=len(wiki_records),
        hf_tickers_matched=len(hf_monthly),
        yahoo_tickers_matched=len(yf_by_ticker),
        price_rows_count=len(final_rows),
        report=report,
    )


def update_history_from_wiki(
    history_path: Path,
    wiki_records: Sequence[ConstituentRecord],
    as_of: date,
) -> None:
    """Update open intervals in ``constituents_history.csv`` from fresh Wikipedia roster."""
    if not history_path.exists():
        return
    with history_path.open("r", encoding="utf-8-sig", newline="") as fh:
        existing = list(csv.DictReader(fh))
    fja_style = [
        {
            "ticker": r.get("ticker") or "",
            "start_date": r.get("start_date") or "",
            "end_date": r.get("end_date") or "",
        }
        for r in existing
    ]
    updated = build_constituents_history(fja_style, wiki_records, as_of=as_of)
    write_constituents_history_csv(updated, history_path)


__all__ = [
    "CONSTITUENT_HISTORY_COLUMNS",
    "FJA_SP500_URL",
    "HF_PARQUET_URLS",
    "PRICE_COLUMNS",
    "US20BuildResult",
    "build_constituents_history",
    "build_us20_dataset",
    "clean_and_collapse_daily_to_monthly",
    "extract_sp500_monthly_from_hf",
    "fetch_fja_sp500_intervals",
    "merge_monthly_price_rows",
    "splice_price_series",
    "update_history_from_wiki",
    "write_constituents_history_csv",
]
