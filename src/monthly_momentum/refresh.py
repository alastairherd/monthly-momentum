"""Public data refresh orchestrator (Wikipedia + Yahoo Finance -> committed reports)."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from monthly_momentum.live import (
    ConstituentRecord,
    fetch_monthly_price_history,
    fetch_sp500_constituents,
    write_constituents_csv,
)
from monthly_momentum.normalize import add_months, normalize_month, normalize_ticker
from monthly_momentum.report import PublicReportSummary, rebuild_public_reports

PRICE_COLUMNS: list[str] = ["date", "ticker", "close", "adj_close", "market"]
SNAPSHOT_COLUMNS: list[str] = ["snapshot_month", "ticker", "name", "sector", "index"]


@dataclass(slots=True)
class RefreshResult:
    """Result summary from a live public refresh run."""

    constituents_count: int
    price_rows_count: int
    snapshot_month: str
    report: PublicReportSummary


def _splice_ticker_bars(
    existing_bars: Mapping[str, tuple[float, float, str]],
    fresh_bars: Mapping[str, tuple[float, float, str]],
) -> dict[str, tuple[float, float, str]]:
    """Ratio-splice existing historical bars onto fresh Yahoo bars at earliest overlap."""
    if not fresh_bars:
        return dict(existing_bars)
    if not existing_bars:
        return dict(fresh_bars)

    overlap = sorted(set(existing_bars) & set(fresh_bars))
    out: dict[str, tuple[float, float, str]] = {}
    if overlap:
        ov = overlap[0]
        old_c, old_a, _ = existing_bars[ov]
        new_c, new_a, _ = fresh_bars[ov]
        c_scale = (new_c / old_c) if old_c > 0.0 and new_c > 0.0 else 1.0
        a_scale = (new_a / old_a) if old_a > 0.0 and new_a > 0.0 else 1.0
        for dt_s, (c_v, a_v, mkt) in existing_bars.items():
            if dt_s < ov:
                out[dt_s] = (c_v * c_scale, a_v * a_scale, mkt)
        for dt_s, vals in fresh_bars.items():
            out[dt_s] = vals
    else:
        out.update(existing_bars)
        out.update(fresh_bars)

    return out


def merge_monthly_price_rows(
    existing_path: Path,
    fresh_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    """Ratio-splice fresh monthly bars with existing CSV rows preserving removed tickers."""
    existing_by_ticker: dict[str, dict[str, tuple[float, float, str]]] = {}
    if existing_path.exists():
        with existing_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                dt_str = (row.get("date") or "").strip()
                ticker = normalize_ticker(row.get("ticker") or "")
                if not dt_str or not ticker:
                    continue
                try:
                    c_val = float(row["close"])
                    a_val = float(row["adj_close"])
                except (KeyError, TypeError, ValueError):
                    continue
                mkt = (row.get("market") or "us").strip()
                existing_by_ticker.setdefault(ticker, {})[dt_str] = (c_val, a_val, mkt)

    fresh_by_ticker: dict[str, dict[str, tuple[float, float, str]]] = {}
    for row in fresh_rows:
        dt_str = row["date"].strip()
        ticker = normalize_ticker(row["ticker"])
        if not dt_str or not ticker:
            continue
        fresh_by_ticker.setdefault(ticker, {})[dt_str] = (
            float(row["close"]),
            float(row["adj_close"]),
            row["market"],
        )

    merged_rows: list[dict[str, str]] = []
    for ticker in sorted(set(existing_by_ticker) | set(fresh_by_ticker)):
        combined = _splice_ticker_bars(
            existing_by_ticker.get(ticker, {}),
            fresh_by_ticker.get(ticker, {}),
        )
        for dt_str, (c_v, a_v, mkt) in combined.items():
            merged_rows.append(
                {
                    "date": dt_str,
                    "ticker": ticker,
                    "close": f"{c_v:.4f}",
                    "adj_close": f"{a_v:.4f}",
                    "market": mkt,
                }
            )

    merged_rows.sort(key=lambda r: (r["date"], r["ticker"]))
    return merged_rows


def write_monthly_prices_csv(rows: Sequence[dict[str, str]], path: Path) -> None:
    """Write normalized monthly price bars to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PRICE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def update_constituent_snapshots(
    snapshots_path: Path,
    snapshot_month: str,
    records: Sequence[ConstituentRecord],
) -> None:
    """Record point-in-time constituent membership for ``snapshot_month``."""
    norm_month = normalize_month(snapshot_month)
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    if snapshots_path.exists():
        with snapshots_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                m_raw = (row.get("snapshot_month") or "").strip()
                t_raw = normalize_ticker(row.get("ticker") or "")
                if not m_raw or not t_raw:
                    continue
                m = normalize_month(m_raw)
                if m == norm_month:
                    continue
                by_key[(m, t_raw)] = {
                    "snapshot_month": m,
                    "ticker": t_raw,
                    "name": (row.get("name") or t_raw).strip(),
                    "sector": (row.get("sector") or "").strip(),
                    "index": (row.get("index") or "S&P 500").strip(),
                }

    for rec in records:
        by_key[(norm_month, rec.ticker)] = {
            "snapshot_month": norm_month,
            "ticker": rec.ticker,
            "name": rec.name,
            "sector": rec.sector,
            "index": rec.index,
        }

    snapshots_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [by_key[k] for k in sorted(by_key)]
    with snapshots_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SNAPSHOT_COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)


def run_public_refresh(
    root_dir: Path = Path("."),
    years: int | None = None,
    as_of: date | None = None,
    include_mtd: bool = False,
    contribution: float = 500.0,
    fee_pct: float = 0.15,
    batch_size: int = 100,
    with_global: bool | None = None,
) -> RefreshResult:
    """Fetch public S&P 500 (and optional global) data and regenerate reports."""
    from monthly_momentum.markets import refresh_global_markets
    from monthly_momentum.us20 import update_history_from_wiki

    eff_as_of = as_of or datetime.now(UTC).date()
    data_dir = root_dir / "data"
    prices_path = data_dir / "monthly_prices.csv"
    history_path = data_dir / "constituents_history.csv"

    eff_years = years if years is not None else (4 if history_path.exists() else 12)

    constituents = fetch_sp500_constituents()
    constituents_path = data_dir / "constituents.csv"
    write_constituents_csv(constituents, constituents_path)
    update_history_from_wiki(history_path, constituents, as_of=eff_as_of)

    fresh_prices = fetch_monthly_price_history(
        constituents=constituents,
        benchmark_ticker="^SP500TR",
        years=eff_years,
        as_of=eff_as_of,
        include_mtd=include_mtd,
        batch_size=batch_size,
    )
    if not fresh_prices:
        raise RuntimeError("Yahoo Finance returned zero monthly price rows.")

    merged_prices = merge_monthly_price_rows(prices_path, fresh_prices)
    write_monthly_prices_csv(merged_prices, prices_path)

    latest_bar_month = max(r["date"][:7] for r in merged_prices)
    snapshot_window = add_months(latest_bar_month, 1)
    snapshots_path = data_dir / "constituent_snapshots.csv"
    update_constituent_snapshots(snapshots_path, snapshot_window, constituents)

    run_global = (
        with_global
        if with_global is not None
        else (data_dir / "global" / "constituents.csv").exists()
    )
    if run_global:
        global_years = (
            max(eff_years, 4) if (data_dir / "global" / "monthly_prices.csv").exists() else 12
        )
        refresh_global_markets(
            root_dir=root_dir,
            years=global_years,
            as_of=eff_as_of,
            batch_size=min(batch_size, 80),
        )

    report = rebuild_public_reports(
        root_dir=root_dir,
        contribution=contribution,
        fee_pct=fee_pct,
        picks_updated_on=datetime.now(UTC).date(),
    )

    return RefreshResult(
        constituents_count=len(constituents),
        price_rows_count=len(merged_prices),
        snapshot_month=snapshot_window,
        report=report,
    )
