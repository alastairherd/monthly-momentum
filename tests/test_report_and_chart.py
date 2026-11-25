"""Tests for deterministic public report, chart generation, README update, and refresh merge."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from monthly_momentum.live import ConstituentRecord
from monthly_momentum.normalize import add_months
from monthly_momentum.refresh import merge_monthly_price_rows, update_constituent_snapshots
from monthly_momentum.report import README_END_MARKER, README_START_MARKER, rebuild_public_reports


def _seed_public_repo(root: Path) -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    months = [add_months("2022-01", i) for i in range(48)]  # 48 months -> 12 windows

    with (data_dir / "constituents.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["ticker", "name", "sector", "sub_industry", "date_added", "index"]
        )
        w.writeheader()
        for t, s in [
            ("AAA", "Tech"),
            ("BBB", "Health Care"),
            ("CCC", "Industrials"),
            ("DDD", "Financials"),
        ]:
            w.writerow(
                {
                    "ticker": t,
                    "name": f"{t} Corp",
                    "sector": s,
                    "sub_industry": s,
                    "date_added": "2015-01-01",
                    "index": "S&P 500",
                }
            )

    with (data_dir / "monthly_prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "ticker", "close", "adj_close", "market"])
        w.writeheader()
        rates = {"AAA": 1.04, "BBB": 1.03, "CCC": 1.02, "DDD": 1.01}
        for i, m in enumerate(months):
            dt = f"{m}-01"
            for t, r in rates.items():
                p = 100.0 * (r**i)
                w.writerow(
                    {
                        "date": dt,
                        "ticker": t,
                        "close": f"{p:.4f}",
                        "adj_close": f"{p:.4f}",
                        "market": "us",
                    }
                )
            bp = 1000.0 * (1.008**i)
            w.writerow(
                {
                    "date": dt,
                    "ticker": "^SP500TR",
                    "close": f"{bp:.4f}",
                    "adj_close": f"{bp:.4f}",
                    "market": "benchmark",
                }
            )

    (root / "README.md").write_text(
        f"# Monthly Momentum\n\n{README_START_MARKER}\nPLACEHOLDER_OLD_CONTENT\n"
        f"{README_END_MARKER}\n\n## Footer\nKeep me.\n",
        encoding="utf-8",
    )


def test_rebuild_public_reports_and_idempotency(tmp_path: Path) -> None:
    _seed_public_repo(tmp_path)
    summary = rebuild_public_reports(root_dir=tmp_path)

    assert summary.latest_signal_month == "2025-12"
    assert summary.latest_window == "2026-01"
    assert summary.top3_tickers == ["AAA", "BBB", "CCC"]
    assert summary.windows_count == 12

    assert summary.latest_ranking_path.exists()
    assert summary.history_ranking_path.exists()
    assert summary.model_holdings_path.exists()
    assert summary.performance_csv_path.exists()
    assert summary.summary_json_path.exists()
    assert summary.chart_path.exists()
    hero_path = tmp_path / "assets" / "hero_vs_sp500.png"
    assert hero_path.exists()
    assert hero_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    # Check PNG magic header.
    assert summary.chart_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    summary_data = json.loads(summary.summary_json_path.read_text(encoding="utf-8"))
    assert summary_data["latest_window"] == "2026-01"
    assert [p["ticker"] for p in summary_data["top3_picks"]] == ["AAA", "BBB", "CCC"]
    assert "Balanced (Top 5)" in summary_data["variants"]

    readme_text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Latest Mechanistic Picks — 2026-01 Window" in readme_text
    assert "Balanced (Top 5)" in readme_text
    assert "assets/hero_vs_sp500.png" in readme_text
    assert "assets/performance.png" in readme_text
    assert "## Footer\nKeep me." in readme_text
    assert "PLACEHOLDER_OLD_CONTENT" not in readme_text

    # Re-running offline report produces identical JSON and README text.
    rebuild_public_reports(root_dir=tmp_path)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == readme_text
    assert json.loads(summary.summary_json_path.read_text(encoding="utf-8")) == summary_data


def test_merge_prices_preserves_removed_tickers_and_snapshots(tmp_path: Path) -> None:
    prices_path = tmp_path / "monthly_prices.csv"
    prices_path.write_text(
        "date,ticker,close,adj_close,market\n"
        "2026-09-01,OLDCO,50.0000,50.0000,us\n"
        "2026-09-01,AAPL,200.0000,200.0000,us\n",
        encoding="utf-8",
    )
    merged = merge_monthly_price_rows(
        prices_path,
        [
            {
                "date": "2026-10-01",
                "ticker": "AAPL",
                "close": "210.0000",
                "adj_close": "210.0000",
                "market": "us",
            }
        ],
    )
    assert {(r["date"], r["ticker"]) for r in merged} == {
        ("2026-09-01", "AAPL"),
        ("2026-09-01", "OLDCO"),
        ("2026-10-01", "AAPL"),
    }

    snap_path = tmp_path / "constituent_snapshots.csv"
    update_constituent_snapshots(
        snap_path,
        "2026-11",
        [ConstituentRecord(ticker="AAPL", name="Apple", sector="Tech")],
    )
    update_constituent_snapshots(
        snap_path,
        "2026-12",
        [ConstituentRecord(ticker="MSFT", name="Microsoft", sector="Tech")],
    )
    content = snap_path.read_text(encoding="utf-8")
    assert "2026-11,AAPL" in content
    assert "2026-12,MSFT" in content
