"""Multi-market (FTSE 100, TSX 60, EURO STOXX 50, MSCI ACWI All World) & FX support."""

from __future__ import annotations

import csv
import json
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from monthly_momentum.acwi import (
    AcwiConstituent,
    AcwiRefreshResult,
    load_acwi_constituents_csv,
    refresh_acwi_market,
)
from monthly_momentum.backtest.data import (
    BacktestDataset,
    ConstituentInterval,
    PricePoint,
    load_backtest_dataset,
)
from monthly_momentum.backtest.engine import BacktestConfig, BacktestResult, compare_variants
from monthly_momentum.chart import generate_performance_chart
from monthly_momentum.holdings import write_holdings_csv
from monthly_momentum.live import (
    DEFAULT_USER_AGENT,
    ConstituentRecord,
    _download_yf_batched,
    _WikiTableParser,
    aggregate_completed_monthly_bars,
    write_constituents_csv,
)
from monthly_momentum.models import RankedSecurity, RankingResult
from monthly_momentum.normalize import (
    add_months,
    ftse_to_yahoo,
    normalize_ticker,
    subtract_calendar_years,
    ticker_match_key,
    tsx_to_yahoo,
)
from monthly_momentum.ranking import write_ranking_csv, write_ranking_history_csv
from monthly_momentum.refresh import merge_monthly_price_rows, write_monthly_prices_csv

FTSE100_WIKI_URL = "https://en.wikipedia.org/wiki/FTSE_100_Index"
TSX60_WIKI_URL = "https://en.wikipedia.org/wiki/S%26P/TSX_60"
EUROSTOXX50_WIKI_URL = "https://en.wikipedia.org/wiki/EURO_STOXX_50"

FX_PAIRS: tuple[str, ...] = ("GBPUSD=X", "CADUSD=X", "EURUSD=X", "USDGBP=X", "USDCAD=X", "USDEUR=X")

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
    "intl": 0.15,
}

_ORDERED_VARIANT_LABELS: tuple[str, ...] = (
    "Aggressive (Top 1)",
    "Standard (Top 3)",
    "Standard (Top 3 + Rule 6)",
    "Balanced (Top 5)",
    "Balanced (Top 5 + Rule 6)",
    "Cautious (Top 10)",
    "Cautious (Top 10 + Rule 6)",
)


@dataclass(slots=True)
class GlobalRefreshResult:
    """Counts from fetching non-US indices, ACWI, and FX rates."""

    constituents_count: int
    price_rows_count: int
    fx_rows_count: int
    acwi_result: AcwiRefreshResult | None = None


@dataclass(slots=True)
class GlobalReportSummary:
    """Outputs from offline FTSE 100 & All-World ACWI pool analysis."""

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


def merge_fx_csv(path: Path, fresh_rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Merge and sort monthly FX pair rows cleanly on disk."""
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


_merge_fx_csv = merge_fx_csv


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
    currency_by_ticker: Mapping[str, str] | None = None,
) -> dict[str, dict[str, PricePoint]]:
    """Convert multi-currency stock prices into ``USD`` or ``GBP``.

    Supports both ``USD{CCY}=X`` (divide local price by rate) and legacy
    ``{CCY}USD=X`` (multiply local price by rate).
    """
    target = target_currency.upper()
    converted: dict[str, dict[str, PricePoint]] = {}

    for tkey, by_month in prices.items():
        explicit_curr = currency_by_ticker.get(tkey) if currency_by_ticker else None
        out_m: dict[str, PricePoint] = {}
        for m, pt in by_month.items():
            src_curr = (
                explicit_curr.upper() if explicit_curr else MARKET_CURRENCY.get(pt.market, "USD")
            )
            if src_curr == target:
                out_m[m] = pt
                continue

            if src_curr == "USD":
                usd_close, usd_adj = pt.close, pt.adj_close
            else:
                usd_pair = f"USD{src_curr}=X"
                cross_pair = f"{src_curr}USD=X"
                usd_rate = fx_rates.get(usd_pair, {}).get(m)
                if usd_rate and usd_rate > 0.0:
                    usd_close = pt.close / usd_rate
                    usd_adj = pt.adj_close / usd_rate
                else:
                    cross_rate = fx_rates.get(cross_pair, {}).get(m)
                    if not cross_rate or cross_rate <= 0.0:
                        continue
                    usd_close = pt.close * cross_rate
                    usd_adj = pt.adj_close * cross_rate

            if target == "USD":
                final_c, final_a = usd_close, usd_adj
            elif target == "GBP":
                usd_gbp = fx_rates.get("USDGBP=X", {}).get(m)
                if usd_gbp and usd_gbp > 0.0:
                    final_c, final_a = usd_close * usd_gbp, usd_adj * usd_gbp
                else:
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
    include_acwi: bool = True,
) -> GlobalRefreshResult:
    """Fetch FTSE 100, S&P/TSX 60, EURO STOXX 50, ACWI All World, and FX rates."""
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
    merged_fx = merge_fx_csv(global_dir / "fx_rates.csv", fx_fresh)

    acwi_res: AcwiRefreshResult | None = None
    if include_acwi:
        acwi_res = refresh_acwi_market(root_dir=root_dir, years=years, as_of=eff_as_of)
        merged_fx_count = acwi_res.fx_rows_count
    else:
        merged_fx_count = len(merged_fx)

    return GlobalRefreshResult(
        constituents_count=len(all_intl),
        price_rows_count=len(merged_prices),
        fx_rows_count=merged_fx_count,
        acwi_result=acwi_res,
    )


def _serialize_variants_summary(
    variants: Mapping[str, BacktestResult],
    currency_key: str = "ending_value",
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for label in _ORDERED_VARIANT_LABELS:
        if label not in variants:
            continue
        m = variants[label].metrics
        payload[label] = {
            currency_key: round(m.ending_value, 2),
            "xirr_pct": round(m.xirr_pct, 2) if m.xirr_pct is not None else None,
            "twr_cagr_pct": round(m.twr_cagr_pct, 2) if m.twr_cagr_pct is not None else None,
            "max_drawdown_pct": round(m.max_drawdown_pct, 2),
            "top_holding_ticker": m.top_holding_ticker,
            "top_holding_weight_pct": round(m.top_holding_weight_pct, 2),
            "max_single_holding_weight_pct": round(m.max_single_holding_weight_pct, 2),
            "rolling_5y_win_rate_pct": (
                round(m.rolling_5y.win_rate_pct, 2) if m.rolling_5y else None
            ),
            "rolling_5y_win_count": m.rolling_5y.win_count if m.rolling_5y else None,
            "rolling_5y_windows_count": m.rolling_5y.windows_count if m.rolling_5y else None,
            "rule6_exits_count": m.rule6_exits_count,
            "delistings_liquidated_count": m.delistings_liquidated_count,
        }
    return payload


def _serialize_ranking_rows(
    ranking: RankingResult,
    acwi_meta: Mapping[str, AcwiConstituent],
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in ranking.ranked[:limit]:
        meta = acwi_meta.get(ticker_match_key(item.ticker))
        rows.append(
            {
                "rank": item.rank,
                "ticker": item.ticker,
                "name": meta.name if meta else item.name,
                "sector": (meta.sector if meta else item.sector) or "",
                "location": meta.location if meta else "",
                "exchange": meta.exchange if meta else "",
                "index": meta.exchange if meta else item.index,
                "currency": meta.quote_currency if meta else "USD",
                "return_3y_usd_pct": round(item.return_3y_pct, 2),
                "return_3m_usd_pct": round(item.return_3m_pct, 2),
                "uk_accessible": meta.uk_accessible if meta else True,
                "uk_access_note": meta.uk_access_note if meta else "",
                "selected_for_buy": item.selected_for_buy,
            }
        )
    return rows


def _write_acwi_enriched_ranking_csv(
    ranking: RankingResult,
    acwi_meta: Mapping[str, AcwiConstituent],
    path: Path,
    limit: int = 25,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "month",
        "rank",
        "ticker",
        "name",
        "index",
        "sector",
        "location",
        "exchange",
        "currency",
        "return_3y_pct",
        "return_3m_pct",
        "uk_accessible",
        "uk_access_note",
        "selected_for_buy",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for item in ranking.ranked[:limit]:
            meta = acwi_meta.get(ticker_match_key(item.ticker))
            writer.writerow(
                {
                    "month": item.month,
                    "rank": str(item.rank),
                    "ticker": item.ticker,
                    "name": meta.name if meta else item.name,
                    "index": item.index,
                    "sector": (meta.sector if meta else item.sector) or "",
                    "location": meta.location if meta else "",
                    "exchange": meta.exchange if meta else "",
                    "currency": meta.quote_currency if meta else "USD",
                    "return_3y_pct": f"{item.return_3y_pct:.4f}",
                    "return_3m_pct": f"{item.return_3m_pct:.4f}",
                    "uk_accessible": "true" if (meta.uk_accessible if meta else True) else "false",
                    "uk_access_note": meta.uk_access_note if meta else "",
                    "selected_for_buy": "true" if item.selected_for_buy else "false",
                }
            )


def _history_rows_from_result(std_res: BacktestResult) -> list[RankedSecurity]:
    rows: list[RankedSecurity] = []
    for r_res in std_res.rankings_by_window:
        rows.extend(r_res.top10)
    return rows


def _build_acwi_subsection(
    root_dir: Path,
    us_ds: BacktestDataset,
    fx_rates: Mapping[str, Mapping[str, float]],
    contribution: float,
) -> dict[str, Any] | None:
    from monthly_momentum.report import build_model_holdings, write_variants_performance_csv

    data_dir = root_dir / "data"
    global_dir = data_dir / "global"
    acwi_const_path = global_dir / "acwi_constituents.csv"
    acwi_prices_path = global_dir / "acwi_monthly_prices.csv"
    if not acwi_const_path.exists() or not acwi_prices_path.exists():
        return None

    acwi_constituents = load_acwi_constituents_csv(acwi_const_path)
    if not acwi_constituents:
        return None

    acwi_raw_ds = load_backtest_dataset(
        prices_path=acwi_prices_path,
        constituents_path=acwi_const_path,
        benchmark_ticker="ACWI",
        snapshots_path=global_dir / "acwi_snapshots.csv",
    )
    if len(acwi_raw_ds.months) <= 36:
        return None

    acwi_months = list(acwi_raw_ds.months)
    acwi_month_set = set(acwi_months)
    acwi_by_ticker = {c.ticker: c for c in acwi_constituents}

    # Combine ACWI prices with data/monthly_prices.csv for any US holdings omitted from ACWI CSV.
    combined_local_prices: dict[str, dict[str, PricePoint]] = {}
    currency_by_ticker: dict[str, str] = {}
    for c in acwi_constituents:
        currency_by_ticker[c.ticker] = c.quote_currency or c.market_currency or "USD"
        p_map: dict[str, PricePoint] = {}
        if c.ticker in acwi_raw_ds.prices:
            p_map.update(acwi_raw_ds.prices[c.ticker])
        elif c.market == "us" and c.ticker in us_ds.prices:
            for m, pt in us_ds.prices[c.ticker].items():
                if m in acwi_month_set:
                    p_map[m] = pt
        if p_map:
            combined_local_prices[c.ticker] = p_map

    usd_prices = convert_prices_to_currency(
        combined_local_prices,
        fx_rates,
        target_currency="USD",
        currency_by_ticker=currency_by_ticker,
    )

    all_intervals: list[ConstituentInterval] = []
    all_by_ticker: dict[str, list[ConstituentInterval]] = {}
    all_meta: dict[str, ConstituentInterval] = {}
    uk_acc_intervals: list[ConstituentInterval] = []
    uk_acc_by_ticker: dict[str, list[ConstituentInterval]] = {}
    uk_acc_meta: dict[str, ConstituentInterval] = {}

    for c in acwi_constituents:
        if c.ticker not in usd_prices:
            continue
        iv = ConstituentInterval(
            ticker=c.ticker,
            start_date=date(1900, 1, 1),
            end_date=None,
            index=c.exchange or c.index,
            name=c.name,
            sector=c.sector,
        )
        all_intervals.append(iv)
        all_by_ticker[c.ticker] = [iv]
        all_meta[c.ticker] = iv
        if c.uk_accessible:
            uk_acc_intervals.append(iv)
            uk_acc_by_ticker[c.ticker] = [iv]
            uk_acc_meta[c.ticker] = iv

    first_months = [min(tmap.keys()) for tmap in usd_prices.values() if tmap]
    auto_start = add_months(min(first_months), 37) if first_months else None
    common_cfg = BacktestConfig(
        start_month=auto_start,
        monthly_contribution=contribution,
        fee_pct=0.15,
        sell_fee_pct=0.15,
        benchmark_fee_pct=0.0,
        signal_mode="next_month",
        market_fee_map=GLOBAL_ISA_FEE_MAP,
    )

    has_snapshots = bool(acwi_raw_ds.snapshots_by_month)
    all_ds = BacktestDataset(
        months=acwi_months,
        month_dates=acwi_raw_ds.month_dates,
        prices=usd_prices,
        benchmark_prices=acwi_raw_ds.benchmark_prices,
        constituents=all_intervals,
        constituents_by_ticker=all_by_ticker,
        constituent_meta=all_meta,
        snapshots_by_month=acwi_raw_ds.snapshots_by_month,
        benchmark_ticker="ACWI",
        survivorship_warning=not has_snapshots,
    )
    all_var_list = compare_variants(all_ds, common_cfg)
    all_variants = {v.label: v.result for v in all_var_list}
    all_std = all_variants["Standard (Top 3)"]
    all_latest_r = all_std.rankings_by_window[-1]

    perf_all_rows = write_variants_performance_csv(
        all_variants, global_dir / "performance_acwi.csv"
    )
    _write_acwi_enriched_ranking_csv(
        all_latest_r, acwi_by_ticker, global_dir / "rankings" / "latest_acwi_all.csv", limit=25
    )
    write_ranking_history_csv(
        _history_rows_from_result(all_std), global_dir / "rankings" / "history_acwi_all.csv"
    )

    all_chart_meta = {
        "start_window": all_std.points[0].window_month,
        "latest_window": all_std.points[-1].window_month,
        "latest_signal_month": all_std.points[-1].signal_month,
        "fee_pct": 0.15,
        "survivorship_warning": True,
    }
    generate_performance_chart(
        perf_all_rows,
        all_chart_meta,
        root_dir / "assets" / "performance_acwi.png",
        title="Full iShares MSCI ACWI momentum vs MSCI ACWI ETF",
        subtitle=(
            f"All World Full ACWI ({len(all_intervals)} priced equities, USD) · "
            f"{all_std.points[0].window_month} to {all_std.points[-1].window_month} "
            f"(signal {all_std.points[-1].signal_month}) · 3Y TR ranked, 3M >= 0%"
        ),
        benchmark_label="iShares MSCI ACWI ETF (ACWI)",
        benchmark_short_label="ACWI ETF",
        currency_symbol="$",
        footer_note=(
            "Source: iShares MSCI ACWI holdings & Yahoo Finance (USD-converted). "
            "Current-roster survivorship bias applies. Not financial advice."
        ),
    )

    # UK-Accessible ACWI subset
    uk_prices = {t: p for t, p in usd_prices.items() if t in uk_acc_meta}
    uk_snapshots = {
        m: {t for t in tickers if t in uk_acc_meta}
        for m, tickers in acwi_raw_ds.snapshots_by_month.items()
    }
    uk_ds = BacktestDataset(
        months=acwi_months,
        month_dates=acwi_raw_ds.month_dates,
        prices=uk_prices,
        benchmark_prices=acwi_raw_ds.benchmark_prices,
        constituents=uk_acc_intervals,
        constituents_by_ticker=uk_acc_by_ticker,
        constituent_meta=uk_acc_meta,
        snapshots_by_month=uk_snapshots,
        benchmark_ticker="ACWI",
        survivorship_warning=not has_snapshots,
    )
    uk_var_list = compare_variants(uk_ds, common_cfg)
    uk_variants = {v.label: v.result for v in uk_var_list}
    uk_std = uk_variants["Standard (Top 3)"]
    uk_std_r6 = uk_variants["Standard (Top 3 + Rule 6)"]
    uk_latest_r = uk_std.rankings_by_window[-1]

    perf_uk_rows = write_variants_performance_csv(
        uk_variants, global_dir / "performance_acwi_uk_accessible.csv"
    )
    _write_acwi_enriched_ranking_csv(
        uk_latest_r,
        acwi_by_ticker,
        global_dir / "rankings" / "latest_acwi_uk_accessible.csv",
        limit=10,
    )
    write_ranking_csv(uk_latest_r, global_dir / "rankings" / "latest_global.csv", limit=10)
    write_ranking_history_csv(
        _history_rows_from_result(uk_std),
        global_dir / "rankings" / "history_acwi_uk_accessible.csv",
    )
    uk_holdings, uk_r6_recs = build_model_holdings(uk_std, uk_std_r6)
    write_holdings_csv(uk_holdings, global_dir / "model_holdings_acwi_uk_accessible.csv")

    uk_chart_meta = {
        "start_window": uk_std.points[0].window_month,
        "latest_window": uk_std.points[-1].window_month,
        "latest_signal_month": uk_std.points[-1].signal_month,
        "fee_pct": 0.15,
        "survivorship_warning": True,
    }
    generate_performance_chart(
        perf_uk_rows,
        uk_chart_meta,
        root_dir / "assets" / "performance_acwi_uk_accessible.png",
        title="All World (UK-ISA accessible) momentum outpaces MSCI ACWI",
        subtitle=(
            f"UK-Accessible ACWI ({len(uk_acc_intervals)} US/UK/CA/EU equities, USD) · "
            f"{uk_std.points[0].window_month} to {uk_std.points[-1].window_month} "
            f"(signal {uk_std.points[-1].signal_month}) · 0.50% UK / 0.15% FX fee"
        ),
        benchmark_label="iShares MSCI ACWI ETF (ACWI)",
        benchmark_short_label="ACWI ETF",
        currency_symbol="$",
        footer_note=(
            "Source: iShares ACWI filtered to UK ISA exchanges (US/UK/CA/Western Europe/Nordics) "
            "& Yahoo Finance. Current-roster survivorship bias applies."
        ),
    )

    all_top15 = _serialize_ranking_rows(all_latest_r, acwi_by_ticker, limit=15)
    uk_top10 = _serialize_ranking_rows(uk_latest_r, acwi_by_ticker, limit=10)
    flagged_in_top15 = [row for row in all_top15 if not row["uk_accessible"]]

    return {
        "acwi_all": {
            "latest_window": all_std.points[-1].window_month,
            "latest_signal_month": all_std.points[-1].signal_month,
            "start_window": all_std.points[0].window_month,
            "windows_count": len(all_std.points),
            "universe_size": len(usd_prices),
            "mapped_constituents": len(acwi_constituents),
            "latest_eligible_count": all_std.points[-1].eligible_count,
            "uk_accessible_count": len(uk_acc_intervals),
            "non_uk_accessible_count": len(all_intervals) - len(uk_acc_intervals),
            "top3": all_top15[:3],
            "top15": all_top15,
            "flagged_non_uk_in_top15": flagged_in_top15,
            "variants": _serialize_variants_summary(all_variants, currency_key="ending_value"),
            "benchmark_acwi_xirr_pct": (
                round(all_std.metrics.benchmark_xirr_pct, 2)
                if all_std.metrics.benchmark_xirr_pct is not None
                else None
            ),
            "benchmark_acwi_twr_cagr_pct": (
                round(all_std.metrics.benchmark_twr_cagr_pct, 2)
                if all_std.metrics.benchmark_twr_cagr_pct is not None
                else None
            ),
            "benchmark_acwi_ending_value": (
                round(all_std.metrics.benchmark_ending_value, 2)
                if all_std.metrics.benchmark_ending_value is not None
                else None
            ),
            "benchmark_acwi_max_drawdown_pct": (
                round(all_std.metrics.benchmark_max_drawdown_pct, 2)
                if all_std.metrics.benchmark_max_drawdown_pct is not None
                else None
            ),
            "chart_path": "assets/performance_acwi.png",
        },
        "acwi_uk_accessible": {
            "latest_window": uk_std.points[-1].window_month,
            "latest_signal_month": uk_std.points[-1].signal_month,
            "start_window": uk_std.points[0].window_month,
            "windows_count": len(uk_std.points),
            "universe_size": len(uk_prices),
            "latest_eligible_count": uk_std.points[-1].eligible_count,
            "top3": uk_top10[:3],
            "top10": uk_top10,
            "flagged_skipped": flagged_in_top15,
            "variants": _serialize_variants_summary(uk_variants, currency_key="ending_value"),
            "benchmark_acwi_xirr_pct": (
                round(uk_std.metrics.benchmark_xirr_pct, 2)
                if uk_std.metrics.benchmark_xirr_pct is not None
                else None
            ),
            "benchmark_acwi_twr_cagr_pct": (
                round(uk_std.metrics.benchmark_twr_cagr_pct, 2)
                if uk_std.metrics.benchmark_twr_cagr_pct is not None
                else None
            ),
            "benchmark_acwi_ending_value": (
                round(uk_std.metrics.benchmark_ending_value, 2)
                if uk_std.metrics.benchmark_ending_value is not None
                else None
            ),
            "benchmark_acwi_max_drawdown_pct": (
                round(uk_std.metrics.benchmark_max_drawdown_pct, 2)
                if uk_std.metrics.benchmark_max_drawdown_pct is not None
                else None
            ),
            "rule6_signals": [r for r in uk_r6_recs if r["action"] != "hold"],
            "chart_path": "assets/performance_acwi_uk_accessible.png",
        },
        "_variants_uk": uk_variants,
        "_top10_uk": uk_top10,
    }


def build_global_reports(
    root_dir: Path = Path("."),
    contribution: float = 500.0,
) -> GlobalReportSummary:
    """Deterministically evaluate FTSE 100 and the FX-converted All-World pools."""
    from monthly_momentum.report import build_model_holdings, write_variants_performance_csv

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
    ftse_variants_list = compare_variants(
        ftse_ds,
        BacktestConfig(
            monthly_contribution=contribution,
            fee_pct=0.50,
            sell_fee_pct=0.0,
            benchmark_fee_pct=0.0,
            signal_mode="next_month",
        ),
    )
    ftse_variants = {v.label: v.result for v in ftse_variants_list}
    ftse_std = ftse_variants["Standard (Top 3)"]
    ftse_std_r6 = ftse_variants["Standard (Top 3 + Rule 6)"]
    ftse_latest_r = ftse_std.rankings_by_window[-1]

    write_ranking_csv(ftse_latest_r, global_dir / "rankings" / "latest_ftse100.csv", limit=10)
    write_ranking_history_csv(
        _history_rows_from_result(ftse_std),
        global_dir / "rankings" / "history_ftse100.csv",
    )
    ftse_holdings, _ = build_model_holdings(ftse_std, ftse_std_r6)
    write_holdings_csv(ftse_holdings, global_dir / "model_holdings_ftse100.csv")
    perf_ftse_rows = write_variants_performance_csv(
        ftse_variants, global_dir / "performance_ftse100.csv"
    )

    ftse_chart_meta = {
        "start_window": ftse_std.points[0].window_month,
        "latest_window": ftse_std.points[-1].window_month,
        "latest_signal_month": ftse_std.points[-1].signal_month,
        "fee_pct": 0.50,
        "survivorship_warning": True,
    }
    generate_performance_chart(
        perf_ftse_rows,
        ftse_chart_meta,
        root_dir / "assets" / "performance_ftse100.png",
        title="UK FTSE 100 momentum beats the index after stamp duty",
        subtitle=(
            f"FTSE 100 ({len(ftse_prices)} priced equities, GBP) · "
            f"{ftse_std.points[0].window_month} to {ftse_std.points[-1].window_month} "
            f"(signal {ftse_std.points[-1].signal_month}) · 0.50% UK stamp duty on buys"
        ),
        benchmark_label="FTSE 100 TR ETF (ISF.L)",
        benchmark_short_label="FTSE 100 TR",
        currency_symbol="£",
        footer_note=(
            "Source: Wikipedia FTSE 100 & Yahoo Finance (reinvested dividends, GBP). "
            "Current-roster survivorship bias applies. Not financial advice."
        ),
    )

    # 2. Load US dataset & FX rates
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

    # 3. Prefer full iShares MSCI ACWI All-World if downloaded; keep legacy global_pool fallback.
    acwi_bundle = _build_acwi_subsection(
        root_dir=root_dir,
        us_ds=us_ds,
        fx_rates=fx_rates,
        contribution=contribution,
    )

    ftse_top10_payload = [
        {
            "rank": r.rank,
            "ticker": r.ticker,
            "name": r.name,
            "sector": r.sector,
            "return_3y_pct": round(r.return_3y_pct, 2),
            "return_3m_pct": round(r.return_3m_pct, 2),
        }
        for r in ftse_latest_r.ranked[:10]
    ]

    summary_payload: dict[str, Any] = {
        "ftse100": {
            "latest_window": ftse_std.points[-1].window_month,
            "latest_signal_month": ftse_std.points[-1].signal_month,
            "start_window": ftse_std.points[0].window_month,
            "windows_count": len(ftse_std.points),
            "universe_size": len(ftse_prices),
            "latest_eligible_count": ftse_std.points[-1].eligible_count,
            "top5": ftse_top10_payload[:5],
            "top10": ftse_top10_payload,
            "variants": _serialize_variants_summary(ftse_variants, currency_key="ending_value_gbp"),
            "benchmark_ftse_tr_etf_xirr_pct": (
                round(ftse_std.metrics.benchmark_xirr_pct, 2)
                if ftse_std.metrics.benchmark_xirr_pct is not None
                else None
            ),
            "benchmark_ftse_tr_etf_twr_cagr_pct": (
                round(ftse_std.metrics.benchmark_twr_cagr_pct, 2)
                if ftse_std.metrics.benchmark_twr_cagr_pct is not None
                else None
            ),
            "benchmark_ftse_tr_etf_ending_value": (
                round(ftse_std.metrics.benchmark_ending_value, 2)
                if ftse_std.metrics.benchmark_ending_value is not None
                else None
            ),
            "benchmark_ftse_tr_etf_max_drawdown_pct": (
                round(ftse_std.metrics.benchmark_max_drawdown_pct, 2)
                if ftse_std.metrics.benchmark_max_drawdown_pct is not None
                else None
            ),
            "chart_path": "assets/performance_ftse100.png",
        }
    }

    if acwi_bundle is not None:
        summary_payload["acwi_all"] = acwi_bundle["acwi_all"]
        summary_payload["acwi_uk_accessible"] = acwi_bundle["acwi_uk_accessible"]
        global_variants: dict[str, BacktestResult] = acwi_bundle["_variants_uk"]
        global_std = global_variants["Standard (Top 3)"]
        global_top10_payload: list[dict[str, Any]] = acwi_bundle["_top10_uk"]
        summary_payload["global_pool"] = {
            "source": "ishares_msci_acwi_uk_accessible",
            "latest_window": acwi_bundle["acwi_uk_accessible"]["latest_window"],
            "start_window": acwi_bundle["acwi_uk_accessible"]["start_window"],
            "windows_count": acwi_bundle["acwi_uk_accessible"]["windows_count"],
            "universe_size": acwi_bundle["acwi_uk_accessible"]["universe_size"],
            "top3": global_top10_payload[:3],
            "top10": global_top10_payload,
            "variants": acwi_bundle["acwi_uk_accessible"]["variants"],
            "benchmark_acwi_xirr_pct": acwi_bundle["acwi_uk_accessible"]["benchmark_acwi_xirr_pct"],
        }
    else:
        intl_usd_prices = convert_prices_to_currency(
            intl_ds.prices, fx_rates, target_currency="USD"
        )
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

        global_top10_payload = []
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

        summary_payload["global_pool"] = {
            "latest_window": global_std.points[-1].window_month,
            "start_window": global_std.points[0].window_month,
            "windows_count": len(global_std.points),
            "universe_size": len(merged_prices),
            "top3": global_top10_payload[:3],
            "top10": global_top10_payload,
            "variants": _serialize_variants_summary(global_variants, currency_key="ending_value"),
            "benchmark_sp500tr_xirr_pct": (
                round(global_std.metrics.benchmark_xirr_pct, 2)
                if global_std.metrics.benchmark_xirr_pct is not None
                else None
            ),
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
