"""Multi-market (FTSE 100, TSX 60, EURO STOXX 50) & FX-converted Global Pool support."""

from __future__ import annotations

import csv
import json
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from monthly_momentum.backtest.data import (
    BacktestDataset,
    ConstituentInterval,
    PricePoint,
    load_backtest_dataset,
)
from monthly_momentum.backtest.engine import BacktestConfig, BacktestResult, compare_variants
from monthly_momentum.live import (
    DEFAULT_USER_AGENT,
    ConstituentRecord,
    _download_yf_batched,
    _WikiTableParser,
    aggregate_completed_monthly_bars,
    write_constituents_csv,
)
from monthly_momentum.normalize import (
    ftse_to_yahoo,
    normalize_ticker,
    subtract_calendar_years,
    ticker_match_key,
    tsx_to_yahoo,
)
from monthly_momentum.ranking import write_ranking_csv
from monthly_momentum.refresh import merge_monthly_price_rows, write_monthly_prices_csv

FTSE100_WIKI_URL = "https://en.wikipedia.org/wiki/FTSE_100_Index"
TSX60_WIKI_URL = "https://en.wikipedia.org/wiki/S%26P/TSX_60"
EUROSTOXX50_WIKI_URL = "https://en.wikipedia.org/wiki/EURO_STOXX_50"

FX_PAIRS: tuple[str, ...] = ("GBPUSD=X", "CADUSD=X", "EURUSD=X")

MARKET_CURRENCY: dict[str, str] = {
    "us": "USD",
    "uk": "GBP",
    "ca": "CAD",
    "eu": "EUR",
}

GLOBAL_ISA_FEE_MAP: dict[str, float] = {
    "us": 0.15,
    "uk": 0.50,
    "ca": 0.15,
    "eu": 0.15,
}


@dataclass(slots=True)
class GlobalRefreshResult:
    """Counts from fetching non-US indices and FX rates."""

    constituents_count: int
    price_rows_count: int
    fx_rows_count: int


@dataclass(slots=True)
class GlobalReportSummary:
    """Outputs from offline FTSE 100 & Global Developed pool analysis."""

    ftse_latest_window: str
    ftse_top3: list[str]
    ftse_result: BacktestResult
    global_latest_window: str
    global_top3: list[dict[str, Any]]
    global_top10: list[dict[str, Any]]
    global_variants: dict[str, BacktestResult]
    summary_json_path: Path


def _fetch_html(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_ftse100_wikipedia_html(html: str) -> list[ConstituentRecord]:
    """Parse Wikipedia's FTSE 100 constituents table into Yahoo ``.L`` symbols."""
    parser = _WikiTableParser()
    parser.feed(html)
    target_rows: list[list[str]] | None = None
    for table in parser.tables:
        if table["id"] == "constituents" and table["rows"]:
            target_rows = table["rows"]
            break
    if not target_rows:
        for table in parser.tables:
            rows = table["rows"]
            if rows and any("ticker" in c.lower() for c in rows[0]):
                target_rows = rows
                break
    if not target_rows or len(target_rows) < 2:
        raise ValueError("Could not parse FTSE 100 constituents table.")

    headers = [h.lower() for h in target_rows[0]]
    comp_idx = next((i for i, h in enumerate(headers) if "company" in h), 0)
    tick_idx = next((i for i, h in enumerate(headers) if "ticker" in h), 1)
    sec_idx = next((i for i, h in enumerate(headers) if "sector" in h or "industry" in h), None)

    records: list[ConstituentRecord] = []
    seen: set[str] = set()
    for row in target_rows[1:]:
        if tick_idx >= len(row):
            continue
        sym = ftse_to_yahoo(row[tick_idx])
        if not sym or sym in seen:
            continue
        seen.add(sym)
        name = row[comp_idx].strip() if comp_idx < len(row) else sym
        sector = row[sec_idx].strip() if sec_idx is not None and sec_idx < len(row) else ""
        records.append(
            ConstituentRecord(
                ticker=sym,
                name=name or sym,
                sector=sector,
                sub_industry="",
                date_added="",
                index="FTSE 100",
            )
        )
    records.sort(key=lambda r: r.ticker)
    return records


def parse_tsx60_wikipedia_html(html: str) -> list[ConstituentRecord]:
    """Parse Wikipedia's S&P/TSX 60 constituents table into Yahoo ``.TO`` symbols."""
    parser = _WikiTableParser()
    parser.feed(html)
    target_rows: list[list[str]] | None = None
    for table in parser.tables:
        rows = table["rows"]
        if rows and len(rows) >= 30 and any("symbol" in c.lower() for c in rows[0]):
            target_rows = rows
            break
    if not target_rows or len(target_rows) < 2:
        raise ValueError("Could not parse S&P/TSX 60 constituents table.")

    headers = [h.lower() for h in target_rows[0]]
    sym_idx = next((i for i, h in enumerate(headers) if "symbol" in h), 0)
    comp_idx = next((i for i, h in enumerate(headers) if "company" in h or "name" in h), 1)
    sec_idx = next((i for i, h in enumerate(headers) if "sector" in h), None)

    records: list[ConstituentRecord] = []
    seen: set[str] = set()
    for row in target_rows[1:]:
        if sym_idx >= len(row):
            continue
        sym = tsx_to_yahoo(row[sym_idx])
        if not sym or sym in seen:
            continue
        seen.add(sym)
        name = row[comp_idx].strip() if comp_idx < len(row) else sym
        sector = row[sec_idx].strip() if sec_idx is not None and sec_idx < len(row) else ""
        records.append(
            ConstituentRecord(
                ticker=sym,
                name=name or sym,
                sector=sector,
                sub_industry="",
                date_added="",
                index="S&P/TSX 60",
            )
        )
    records.sort(key=lambda r: r.ticker)
    return records


def parse_eurostoxx50_wikipedia_html(html: str) -> list[ConstituentRecord]:
    """Parse Wikipedia's EURO STOXX 50 table preserving exchange-suffixed tickers."""
    parser = _WikiTableParser()
    parser.feed(html)
    target_rows: list[list[str]] | None = None
    for table in parser.tables:
        if table["id"] == "constituents" and table["rows"]:
            target_rows = table["rows"]
            break
    if not target_rows:
        for table in parser.tables:
            rows = table["rows"]
            if rows and len(rows) >= 30 and any("ticker" in c.lower() for c in rows[0]):
                target_rows = rows
                break
    if not target_rows or len(target_rows) < 2:
        raise ValueError("Could not parse EURO STOXX 50 constituents table.")

    headers = [h.lower() for h in target_rows[0]]
    tick_idx = next((i for i, h in enumerate(headers) if "ticker" in h), 0)
    name_idx = next((i for i, h in enumerate(headers) if "name" in h or "company" in h), 2)
    sec_idx = next((i for i, h in enumerate(headers) if "sector" in h), None)

    records: list[ConstituentRecord] = []
    seen: set[str] = set()
    for row in target_rows[1:]:
        if tick_idx >= len(row):
            continue
        sym = normalize_ticker(row[tick_idx])
        if not sym or "." not in sym or sym in seen:
            continue
        seen.add(sym)
        name = row[name_idx].strip() if name_idx < len(row) else sym
        sector = row[sec_idx].strip() if sec_idx is not None and sec_idx < len(row) else ""
        records.append(
            ConstituentRecord(
                ticker=sym,
                name=name or sym,
                sector=sector,
                sub_industry="",
                date_added="",
                index="EURO STOXX 50",
            )
        )
    records.sort(key=lambda r: r.ticker)
    return records


def _market_code_for_index(index_name: str) -> str:
    low = index_name.strip().lower()
    if "ftse" in low:
        return "uk"
    if "tsx" in low:
        return "ca"
    if "stoxx" in low:
        return "eu"
    return "us"


def fetch_fx_history(
    pairs: Sequence[str] = FX_PAIRS,
    years: int = 12,
    as_of: date | None = None,
) -> list[dict[str, str]]:
    """Fetch completed monthly FX conversion rates from Yahoo Finance."""
    eff_as_of = as_of or datetime.now(UTC).date()
    start = subtract_calendar_years(eff_as_of, years)
    from datetime import timedelta

    maps = _download_yf_batched(
        list(pairs),
        start=start - timedelta(days=35),
        end=eff_as_of + timedelta(days=2),
        interval="1mo",
        batch_size=10,
    )
    rows = aggregate_completed_monthly_bars(
        maps,
        canonical_by_yahoo={p: p for p in pairs},
        benchmark_yahoo=None,
        as_of=eff_as_of,
        include_mtd=False,
    )
    return [{"date": r["date"], "pair": r["ticker"], "rate": r["close"]} for r in rows]


def _merge_fx_csv(path: Path, fresh_rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[tuple[str, str], dict[str, str]] = {}
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                dt_s = (row.get("date") or "").strip()
                pair = (row.get("pair") or "").strip().upper()
                rate = (row.get("rate") or "").strip()
                if dt_s and pair and rate:
                    merged[(dt_s, pair)] = {"date": dt_s, "pair": pair, "rate": rate}
    for row in fresh_rows:
        merged[(row["date"], row["pair"].upper())] = {
            "date": row["date"],
            "pair": row["pair"].upper(),
            "rate": row["rate"],
        }
    ordered = [merged[k] for k in sorted(merged)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["date", "pair", "rate"])
        writer.writeheader()
        writer.writerows(ordered)
    return ordered


def load_fx_rates(path: Path) -> dict[str, dict[str, float]]:
    """Load monthly FX rates keyed by ``pair -> month -> rate``."""
    fx: dict[str, dict[str, float]] = {}
    if not path.exists():
        return fx
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            pair = (row.get("pair") or "").strip().upper()
            dt_s = (row.get("date") or "").strip()
            if not pair or len(dt_s) < 7:
                continue
            try:
                rate = float(row["rate"])
            except (KeyError, TypeError, ValueError):
                continue
            if rate > 0.0:
                fx.setdefault(pair, {})[dt_s[:7]] = rate
    return fx


def convert_prices_to_currency(
    prices: Mapping[str, Mapping[str, PricePoint]],
    fx_rates: Mapping[str, Mapping[str, float]],
    target_currency: str = "USD",
) -> dict[str, dict[str, PricePoint]]:
    """Convert multi-currency stock prices into a single currency (``USD`` or ``GBP``)."""
    target = target_currency.upper()
    converted: dict[str, dict[str, PricePoint]] = {}

    for tkey, by_month in prices.items():
        out_m: dict[str, PricePoint] = {}
        for m, pt in by_month.items():
            src_curr = MARKET_CURRENCY.get(pt.market, "USD")
            if src_curr == target:
                out_m[m] = pt
                continue

            if src_curr == "USD":
                usd_close, usd_adj = pt.close, pt.adj_close
            else:
                pair = f"{src_curr}USD=X"
                rate_to_usd = fx_rates.get(pair, {}).get(m)
                if not rate_to_usd or rate_to_usd <= 0.0:
                    continue
                usd_close = pt.close * rate_to_usd
                usd_adj = pt.adj_close * rate_to_usd

            if target == "USD":
                final_c, final_a = usd_close, usd_adj
            elif target == "GBP":
                gbp_usd = fx_rates.get("GBPUSD=X", {}).get(m)
                if not gbp_usd or gbp_usd <= 0.0:
                    continue
                final_c, final_a = usd_close / gbp_usd, usd_adj / gbp_usd
            else:
                raise ValueError(f"Unsupported target currency {target_currency!r}.")

            out_m[m] = PricePoint(
                dt=pt.dt,
                month=pt.month,
                ticker=pt.ticker,
                close=final_c,
                adj_close=final_a,
                market=pt.market,
            )
        if out_m:
            converted[tkey] = out_m
    return converted


def refresh_global_markets(
    root_dir: Path = Path("."),
    years: int = 12,
    as_of: date | None = None,
    batch_size: int = 80,
) -> GlobalRefreshResult:
    """Fetch FTSE 100, S&P/TSX 60, EURO STOXX 50 constituents, prices, and FX rates."""
    from datetime import timedelta

    eff_as_of = as_of or datetime.now(UTC).date()
    global_dir = root_dir / "data" / "global"

    ftse = parse_ftse100_wikipedia_html(_fetch_html(FTSE100_WIKI_URL))
    tsx = parse_tsx60_wikipedia_html(_fetch_html(TSX60_WIKI_URL))
    stoxx = parse_eurostoxx50_wikipedia_html(_fetch_html(EUROSTOXX50_WIKI_URL))
    all_intl = ftse + tsx + stoxx
    write_constituents_csv(all_intl, global_dir / "constituents.csv")

    market_by_ticker = {r.ticker: _market_code_for_index(r.index) for r in all_intl}
    benchmarks = {"ISF.L": "benchmark_uk", "^GSPTSE": "benchmark_ca", "^STOXX50E": "benchmark_eu"}
    all_yahoo = list(market_by_ticker.keys()) + list(benchmarks.keys())

    start = subtract_calendar_years(eff_as_of, years) - timedelta(days=35)
    maps = _download_yf_batched(
        all_yahoo,
        start=start,
        end=eff_as_of + timedelta(days=2),
        interval="1mo",
        batch_size=batch_size,
    )
    raw_rows = aggregate_completed_monthly_bars(
        maps,
        canonical_by_yahoo={s: s for s in all_yahoo},
        benchmark_yahoo=None,
        as_of=eff_as_of,
        include_mtd=False,
    )
    fresh_rows: list[dict[str, str]] = []
    for row in raw_rows:
        t = row["ticker"]
        row["market"] = benchmarks.get(t) or market_by_ticker.get(t, "intl")
        fresh_rows.append(row)

    prices_path = global_dir / "monthly_prices.csv"
    merged_prices = merge_monthly_price_rows(prices_path, fresh_rows)
    write_monthly_prices_csv(merged_prices, prices_path)

    fx_fresh = fetch_fx_history(pairs=FX_PAIRS, years=years, as_of=eff_as_of)
    merged_fx = _merge_fx_csv(global_dir / "fx_rates.csv", fx_fresh)

    return GlobalRefreshResult(
        constituents_count=len(all_intl),
        price_rows_count=len(merged_prices),
        fx_rows_count=len(merged_fx),
    )


def build_global_reports(
    root_dir: Path = Path("."),
    contribution: float = 500.0,
) -> GlobalReportSummary:
    """Deterministically evaluate FTSE 100 and the FX-converted Global Developed pool."""
    data_dir = root_dir / "data"
    global_dir = data_dir / "global"
    intl_const_path = global_dir / "constituents.csv"
    intl_prices_path = global_dir / "monthly_prices.csv"
    fx_path = global_dir / "fx_rates.csv"

    if not intl_const_path.exists() or not intl_prices_path.exists():
        raise FileNotFoundError(
            "Global market CSVs missing. Run `monthly-momentum refresh --with-global` first."
        )

    intl_ds = load_backtest_dataset(
        prices_path=intl_prices_path,
        constituents_path=intl_const_path,
        benchmark_ticker="ISF.L",
    )

    # 1. FTSE 100 (GBP, 0.50% UK stamp duty on buys, 0% on sells)
    ftse_constituents = [c for c in intl_ds.constituents if c.index == "FTSE 100"]
    ftse_tickers = {c.ticker for c in ftse_constituents}
    ftse_prices = {t: p for t, p in intl_ds.prices.items() if t in ftse_tickers}
    ftse_months = sorted({m for p in ftse_prices.values() for m in p})
    ftse_ds = BacktestDataset(
        months=ftse_months,
        month_dates={m: intl_ds.month_dates[m] for m in ftse_months if m in intl_ds.month_dates},
        prices=ftse_prices,
        benchmark_prices=intl_ds.benchmark_prices,
        constituents=ftse_constituents,
        constituents_by_ticker={c.ticker: [c] for c in ftse_constituents},
        constituent_meta={c.ticker: c for c in ftse_constituents},
        benchmark_ticker="ISF.L",
        survivorship_warning=True,
    )
    ftse_variants = compare_variants(
        ftse_ds,
        BacktestConfig(
            monthly_contribution=contribution,
            fee_pct=0.50,
            sell_fee_pct=0.0,
            benchmark_fee_pct=0.0,
            signal_mode="next_month",
        ),
    )
    ftse_std = next(v.result for v in ftse_variants if v.label == "Standard (Top 3)")
    write_ranking_csv(
        ftse_std.rankings_by_window[-1],
        global_dir / "rankings" / "latest_ftse100.csv",
        limit=10,
    )

    # 2. Global Developed Pool (US S&P 500 + FTSE 100 + TSX 60 + EURO STOXX 50 -> USD)
    us_const_path = (
        data_dir / "constituents_history.csv"
        if (data_dir / "constituents_history.csv").exists()
        else data_dir / "constituents.csv"
    )
    us_prices_path = data_dir / "monthly_prices.csv"
    us_ds = load_backtest_dataset(
        prices_path=us_prices_path,
        constituents_path=us_const_path,
        benchmark_ticker="^SP500TR",
    )

    fx_rates = load_fx_rates(fx_path)
    intl_usd_prices = convert_prices_to_currency(intl_ds.prices, fx_rates, target_currency="USD")

    # Start global pool once international dataset reaches full coverage (with 36m warmup).
    global_months = [m for m in intl_ds.months if m in us_ds.month_dates]
    global_month_set = set(global_months)
    merged_prices: dict[str, dict[str, PricePoint]] = {}
    for t, by_m in us_ds.prices.items():
        sliced = {m: pt for m, pt in by_m.items() if m in global_month_set}
        if sliced:
            merged_prices[t] = sliced
    for t, by_m in intl_usd_prices.items():
        sliced = {m: pt for m, pt in by_m.items() if m in global_month_set}
        if sliced:
            merged_prices[t] = sliced

    merged_constituents = list(us_ds.constituents) + list(intl_ds.constituents)
    merged_by_ticker: dict[str, list[ConstituentInterval]] = {}
    merged_meta: dict[str, ConstituentInterval] = {}
    for c in merged_constituents:
        merged_by_ticker.setdefault(c.ticker, []).append(c)
        merged_meta[c.ticker] = c

    global_ds = BacktestDataset(
        months=global_months,
        month_dates={m: us_ds.month_dates[m] for m in global_months},
        prices=merged_prices,
        benchmark_prices={
            m: pt for m, pt in us_ds.benchmark_prices.items() if m in global_month_set
        },
        constituents=merged_constituents,
        constituents_by_ticker=merged_by_ticker,
        constituent_meta=merged_meta,
        benchmark_ticker="^SP500TR",
        survivorship_warning=True,
    )

    global_variant_list = compare_variants(
        global_ds,
        BacktestConfig(
            monthly_contribution=contribution,
            fee_pct=0.15,
            sell_fee_pct=0.15,
            benchmark_fee_pct=0.0,
            signal_mode="next_month",
            market_fee_map=GLOBAL_ISA_FEE_MAP,
        ),
    )
    global_variants = {v.label: v.result for v in global_variant_list}
    global_std = global_variants["Standard (Top 3)"]
    global_latest_ranking = global_std.rankings_by_window[-1]
    write_ranking_csv(
        global_latest_ranking,
        global_dir / "rankings" / "latest_global.csv",
        limit=10,
    )

    def _market_currency(ticker: str) -> tuple[str, str]:
        meta = merged_meta.get(ticker_match_key(ticker))
        idx_name = meta.index if meta else "S&P 500"
        mcode = _market_code_for_index(idx_name)
        return idx_name, MARKET_CURRENCY.get(mcode, "USD")

    global_top10_payload: list[dict[str, Any]] = []
    for r in global_latest_ranking.top10:
        idx_name, curr = _market_currency(r.ticker)
        global_top10_payload.append(
            {
                "rank": r.rank,
                "ticker": r.ticker,
                "name": r.name,
                "index": idx_name,
                "currency": curr,
                "return_3y_usd_pct": round(r.return_3y_pct, 2),
                "return_3m_usd_pct": round(r.return_3m_pct, 2),
            }
        )

    ftse_latest_r = ftse_std.rankings_by_window[-1]
    ftse_top5_payload = [
        {
            "rank": r.rank,
            "ticker": r.ticker,
            "name": r.name,
            "sector": r.sector,
            "return_3y_pct": round(r.return_3y_pct, 2),
            "return_3m_pct": round(r.return_3m_pct, 2),
        }
        for r in ftse_latest_r.ranked[:5]
    ]

    summary_payload: dict[str, Any] = {
        "ftse100": {
            "latest_window": ftse_std.points[-1].window_month,
            "start_window": ftse_std.points[0].window_month,
            "windows_count": len(ftse_std.points),
            "top5": ftse_top5_payload,
            "variants": {
                v.label: {
                    "ending_value_gbp": round(v.result.metrics.ending_value, 2),
                    "xirr_pct": (
                        round(v.result.metrics.xirr_pct, 2)
                        if v.result.metrics.xirr_pct is not None
                        else None
                    ),
                    "twr_cagr_pct": (
                        round(v.result.metrics.twr_cagr_pct, 2)
                        if v.result.metrics.twr_cagr_pct is not None
                        else None
                    ),
                    "max_drawdown_pct": round(v.result.metrics.max_drawdown_pct, 2),
                }
                for v in ftse_variants
            },
            "benchmark_ftse_tr_etf_xirr_pct": (
                round(ftse_std.metrics.benchmark_xirr_pct, 2)
                if ftse_std.metrics.benchmark_xirr_pct is not None
                else None
            ),
        },
        "global_pool": {
            "latest_window": global_std.points[-1].window_month,
            "start_window": global_std.points[0].window_month,
            "windows_count": len(global_std.points),
            "universe_size": len(merged_prices),
            "top3": global_top10_payload[:3],
            "top10": global_top10_payload,
            "variants": {
                name: {
                    "ending_value": round(res.metrics.ending_value, 2),
                    "xirr_pct": (
                        round(res.metrics.xirr_pct, 2) if res.metrics.xirr_pct is not None else None
                    ),
                    "twr_cagr_pct": (
                        round(res.metrics.twr_cagr_pct, 2)
                        if res.metrics.twr_cagr_pct is not None
                        else None
                    ),
                    "max_drawdown_pct": round(res.metrics.max_drawdown_pct, 2),
                }
                for name, res in global_variants.items()
            },
            "benchmark_sp500tr_xirr_pct": (
                round(global_std.metrics.benchmark_xirr_pct, 2)
                if global_std.metrics.benchmark_xirr_pct is not None
                else None
            ),
        },
    }

    summary_path = global_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")

    return GlobalReportSummary(
        ftse_latest_window=ftse_std.points[-1].window_month,
        ftse_top3=[r.ticker for r in ftse_latest_r.top_picks],
        ftse_result=ftse_std,
        global_latest_window=global_std.points[-1].window_month,
        global_top3=global_top10_payload[:3],
        global_top10=global_top10_payload,
        global_variants=global_variants,
        summary_json_path=summary_path,
    )
