"""Public data refresh orchestrator (Wikipedia + Yahoo Finance -> committed reports)."""

from __future__ import annotations

import csv
from collections.abc import Sequence
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


def merge_monthly_price_rows(
    existing_path: Path,
    fresh_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge fresh monthly bars with existing CSV rows so removed tickers keep history."""
    merged: dict[tuple[str, str], dict[str, str]] = {}
    if existing_path.exists():
        with existing_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                dt_str = (row.get("date") or "").strip()
                ticker = normalize_ticker(row.get("ticker") or "")
                if not dt_str or not ticker:
                    continue
                merged[(dt_str, ticker)] = {
                    "date": dt_str,
                    "ticker": ticker,
                    "close": (row.get("close") or "").strip(),
                    "adj_close": (row.get("adj_close") or "").strip(),
                    "market": (row.get("market") or "us").strip(),
                }

    for row in fresh_rows:
        dt_str = row["date"].strip()
        ticker = normalize_ticker(row["ticker"])
        if not dt_str or not ticker:
            continue
        merged[(dt_str, ticker)] = {
            "date": dt_str,
            "ticker": ticker,
            "close": row["close"],
            "adj_close": row["adj_close"],
            "market": row["market"],
        }

    return [merged[key] for key in sorted(merged)]


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
    years: int = 12,
    as_of: date | None = None,
    include_mtd: bool = False,
    contribution: float = 500.0,
    fee_pct: float = 0.15,
    batch_size: int = 100,
) -> RefreshResult:
    """Fetch public S&P 500 data and regenerate committed rankings, chart, and README."""
    eff_as_of = as_of or datetime.now(UTC).date()
    data_dir = root_dir / "data"

    constituents = fetch_sp500_constituents()
    constituents_path = data_dir / "constituents.csv"
    write_constituents_csv(constituents, constituents_path)

    fresh_prices = fetch_monthly_price_history(
        constituents=constituents,
        benchmark_ticker="^SP500TR",
        years=years,
        as_of=eff_as_of,
        include_mtd=include_mtd,
        batch_size=batch_size,
    )
    if not fresh_prices:
        raise RuntimeError("Yahoo Finance returned zero monthly price rows.")

    prices_path = data_dir / "monthly_prices.csv"
    merged_prices = merge_monthly_price_rows(prices_path, fresh_prices)
    write_monthly_prices_csv(merged_prices, prices_path)

    latest_bar_month = max(r["date"][:7] for r in merged_prices)
    snapshot_window = add_months(latest_bar_month, 1)
    snapshots_path = data_dir / "constituent_snapshots.csv"
    update_constituent_snapshots(snapshots_path, snapshot_window, constituents)

    report = rebuild_public_reports(
        root_dir=root_dir,
        contribution=contribution,
        fee_pct=fee_pct,
    )

    return RefreshResult(
        constituents_count=len(constituents),
        price_rows_count=len(merged_prices),
        snapshot_month=snapshot_window,
        report=report,
    )
