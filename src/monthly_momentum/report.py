"""Deterministic offline report, model holdings, chart, and README generator."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from monthly_momentum.backtest.data import BacktestDataset, load_backtest_dataset
from monthly_momentum.backtest.engine import (
    BacktestConfig,
    BacktestResult,
    SubperiodRow,
    build_funding_schedule_comparison,
    build_variants_allocation_payload,
    compare_variants,
    run_backtest,
    run_subperiod_summary,
)
from monthly_momentum.chart import (
    generate_allocation_chart,
    generate_funding_comparison_chart,
    generate_markets_comparison_chart,
    generate_performance_chart,
)
from monthly_momentum.holdings import (
    apply_monthly_run_to_holdings,
    evaluate_rule6,
    write_holdings_csv,
)
from monthly_momentum.models import (
    ACTIVE_STATUSES,
    Holding,
    RankedSecurity,
    Rule6ActionType,
)
from monthly_momentum.normalize import months_between, ticker_match_key
from monthly_momentum.ranking import read_ranking_csv, write_ranking_csv, write_ranking_history_csv

README_START_MARKER = "<!-- AUTO-GENERATED:START -->"
README_END_MARKER = "<!-- AUTO-GENERATED:END -->"

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
class PublicReportSummary:
    """Paths and key figures produced by ``rebuild_public_reports``."""

    latest_window: str
    latest_signal_month: str
    top3_tickers: list[str]
    top1_ticker: str
    top10_tickers: list[str]
    windows_count: int
    latest_ranking_path: Path
    history_ranking_path: Path
    model_holdings_path: Path
    performance_csv_path: Path
    summary_json_path: Path
    chart_path: Path
    readme_path: Path


def _format_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:+.2f}%" if val != 0.0 else "0.00%"


def _format_plain_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.2f}%"


def build_model_holdings(
    standard_result: BacktestResult,
    rule6_result: BacktestResult,
) -> tuple[list[Holding], list[dict[str, Any]]]:
    """Mechanistically replay Top 3 buys + Rule 6 exits into canonical holdings."""
    holdings: list[Holding] = []
    latest_recommendations = []
    for idx, ranking in enumerate(standard_result.rankings_by_window):
        apply_sells = idx < len(standard_result.rankings_by_window) - 1 or (
            len(rule6_result.points[-1].rule6_sells) > 0
        )
        holdings, recs = apply_monthly_run_to_holdings(
            holdings,
            ranking=ranking,
            run_month=ranking.month,
            buy_date=f"{ranking.month}-01",
            apply_rule6_sells=apply_sells,
            rule6_enabled=True,
        )
        if idx == len(standard_result.rankings_by_window) - 1:
            latest_recommendations = recs

    if standard_result.rankings_by_window:
        latest_r = standard_result.rankings_by_window[-1]
        latest_recommendations = evaluate_rule6(
            holdings,
            run_month=latest_r.month,
            top10_tickers=latest_r.top10_tickers,
            enabled=True,
        )

    rec_dicts = [
        {
            "ticker": r.holding.ticker,
            "name": r.holding.name,
            "action": r.action.value,
            "months_out_of_top10": r.months_out_of_top10,
            "next_milestone_month": r.next_milestone_month,
            "status": r.holding.status.value,
            "message": r.message,
        }
        for r in latest_recommendations
    ]
    return holdings, rec_dicts


_build_model_holdings = build_model_holdings


def write_variants_performance_csv(
    variants: dict[str, BacktestResult],
    path: Path,
) -> list[dict[str, Any]]:
    """Serialize all 7 strategy variant monthly equity/NAV trajectories + benchmark."""
    path.parent.mkdir(parents=True, exist_ok=True)
    top1_pts = variants["Aggressive (Top 1)"].points
    top3_pts = variants["Standard (Top 3)"].points
    top3_r6_pts = variants["Standard (Top 3 + Rule 6)"].points
    top5_pts = variants["Balanced (Top 5)"].points
    top5_r6_pts = variants["Balanced (Top 5 + Rule 6)"].points
    top10_pts = variants["Cautious (Top 10)"].points
    top10_r6_pts = variants["Cautious (Top 10 + Rule 6)"].points

    fieldnames = [
        "window_month",
        "signal_month",
        "date",
        "contributed_cum",
        "top1_value",
        "top1_nav",
        "top3_value",
        "top3_nav",
        "top3_rule6_value",
        "top3_rule6_nav",
        "top5_value",
        "top5_nav",
        "top5_rule6_value",
        "top5_rule6_nav",
        "top10_value",
        "top10_nav",
        "top10_rule6_value",
        "top10_rule6_nav",
        "benchmark_value",
        "benchmark_nav",
    ]
    rows: list[dict[str, Any]] = []
    for p1, p3, p3r6, p5, p5r6, p10, p10r6 in zip(
        top1_pts,
        top3_pts,
        top3_r6_pts,
        top5_pts,
        top5_r6_pts,
        top10_pts,
        top10_r6_pts,
        strict=True,
    ):
        rows.append(
            {
                "window_month": p3.window_month,
                "signal_month": p3.signal_month,
                "date": p3.dt.isoformat(),
                "contributed_cum": f"{p3.contributed_cum:.2f}",
                "top1_value": f"{p1.portfolio_value:.2f}",
                "top1_nav": f"{p1.twr_nav:.6f}",
                "top3_value": f"{p3.portfolio_value:.2f}",
                "top3_nav": f"{p3.twr_nav:.6f}",
                "top3_rule6_value": f"{p3r6.portfolio_value:.2f}",
                "top3_rule6_nav": f"{p3r6.twr_nav:.6f}",
                "top5_value": f"{p5.portfolio_value:.2f}",
                "top5_nav": f"{p5.twr_nav:.6f}",
                "top5_rule6_value": f"{p5r6.portfolio_value:.2f}",
                "top5_rule6_nav": f"{p5r6.twr_nav:.6f}",
                "top10_value": f"{p10.portfolio_value:.2f}",
                "top10_nav": f"{p10.twr_nav:.6f}",
                "top10_rule6_value": f"{p10r6.portfolio_value:.2f}",
                "top10_rule6_nav": f"{p10r6.twr_nav:.6f}",
                "benchmark_value": (
                    f"{p3.benchmark_value:.2f}" if p3.benchmark_value is not None else ""
                ),
                "benchmark_nav": (
                    f"{p3.benchmark_nav:.6f}" if p3.benchmark_nav is not None else ""
                ),
            }
        )

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows


_write_performance_csv = write_variants_performance_csv


def _load_nav_series_from_perf_csv(
    path: Path,
    col: str = "top3_nav",
) -> list[tuple[date, float]]:
    if not path.exists():
        return []
    out: list[tuple[date, float]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            dt_s = (row.get("date") or "").strip()
            val_s = (row.get(col) or "").strip()
            if not dt_s or not val_s:
                continue
            try:
                out.append((date.fromisoformat(dt_s), float(val_s)))
            except ValueError:
                continue
    return out


def _group_history_by_window(
    history_path: Path,
) -> list[tuple[str, str, list[RankedSecurity]]]:
    """Read a history CSV and group Top 10 ranked items chronologically by window month."""
    if not history_path.exists():
        return []
    rows = read_ranking_csv(history_path)
    grouped: dict[str, list[RankedSecurity]] = {}
    for item in rows:
        grouped.setdefault(item.month, []).append(item)
    out: list[tuple[str, str, list[RankedSecurity]]] = []
    from monthly_momentum.normalize import add_months

    for win_m in sorted(grouped):
        ranks = sorted(grouped[win_m], key=lambda r: r.rank)
        out.append((win_m, add_months(win_m, -1), ranks))
    return out


def _compute_sensitivity_and_subperiods(
    dataset: BacktestDataset,
    base_cfg: BacktestConfig,
    start_window: str,
    end_window: str,
) -> tuple[dict[str, BacktestResult], list[SubperiodRow]]:
    sensitivity: dict[str, BacktestResult] = {}
    if "NVDA" in dataset.prices:
        for label, top_n, excl in [
            ("Standard (Top 3) — excl. NVDA", 3, ("NVDA",)),
            ("Cautious (Top 10) — excl. NVDA", 10, ("NVDA",)),
            ("Standard (Top 3) — excl. NVDA/AMD/AVGO", 3, ("NVDA", "AMD", "AVGO")),
        ]:
            cfg = BacktestConfig(
                start_month=base_cfg.start_month,
                end_month=base_cfg.end_month,
                monthly_contribution=base_cfg.monthly_contribution,
                top_n=top_n,
                rule6_enabled=False,
                fee_pct=base_cfg.fee_pct,
                sell_fee_pct=base_cfg.sell_fee_pct,
                benchmark_fee_pct=base_cfg.benchmark_fee_pct,
                risk_free_rate=base_cfg.risk_free_rate,
                signal_mode=base_cfg.signal_mode,
                exclude_tickers=excl,
            )
            sensitivity[label] = run_backtest(dataset, cfg, label=label)

    subperiods: list[SubperiodRow] = []
    if months_between(start_window, end_window) >= 120:
        candidate_periods: list[tuple[str, str | None, str | None]] = [
            ("First Decade (2006–2015)", "2006-01", "2015-12"),
            ("Financial Crisis Era (2007–2012)", "2007-01", "2012-12"),
            ("Recent Decade (2016–Latest)", "2016-01", None),
        ]
        valid_periods = [
            (lbl, s, e)
            for lbl, s, e in candidate_periods
            if (s is None or s >= start_window) and (e is None or e <= end_window)
        ]
        if valid_periods:
            subperiods = run_subperiod_summary(dataset, base_cfg, valid_periods)

    return sensitivity, subperiods


def _render_json_variant_table(
    lines: list[str],
    variants_dict: dict[str, Any],
    currency_sym: str,
    ending_key: str,
    bench_name: str,
    bench_ending: float | None,
    bench_xirr: float | None,
    bench_twr: float | None,
    bench_dd: float | None,
    win_col_label: str,
) -> None:
    lines.append(
        f"| Variant | Ending Value | XIRR | TWR CAGR | Max Drawdown | "
        f"Top Holding (%) | {win_col_label} |"
    )
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for label in _ORDERED_VARIANT_LABELS:
        v = variants_dict.get(label)
        if not v:
            continue
        end_val = v.get(ending_key, v.get("ending_value", 0.0))
        top_t = v.get("top_holding_ticker")
        top_w = v.get("top_holding_weight_pct")
        top_h = f"{top_t} ({top_w:.1f}%)" if top_t else "—"
        wr = v.get("rolling_5y_win_rate_pct")
        wc = v.get("rolling_5y_win_count")
        wn = v.get("rolling_5y_windows_count")
        win_str = f"{wr:.1f}% ({wc}/{wn})" if wr is not None and wc is not None else "—"
        lines.append(
            f"| {label} | {currency_sym}{end_val:,.0f} | {_format_plain_pct(v.get('xirr_pct'))} | "
            f"{_format_plain_pct(v.get('twr_cagr_pct'))} | {v.get('max_drawdown_pct', 0.0):.1f}% | "
            f"{top_h} | {win_str} |"
        )
    if bench_ending is not None or bench_xirr is not None:
        b_end_s = f"{currency_sym}{bench_ending:,.0f}" if bench_ending is not None else "—"
        b_dd_s = f"{bench_dd:.1f}%" if bench_dd is not None else "—"
        lines.append(
            f"| {bench_name} | {b_end_s} | {_format_plain_pct(bench_xirr)} | "
            f"{_format_plain_pct(bench_twr)} | {b_dd_s} | Cap-weighted | Baseline |"
        )


def _render_window_history_tables(
    lines: list[str],
    history: list[tuple[str, str, list[RankedSecurity]]],
    heading: str,
    full_label: str,
) -> None:
    if not history:
        return
    rev = list(reversed(history))
    lines.append(f"### {heading}")
    lines.append("")
    lines.append(
        "| Window | Signal Data | Top 3 (Standard Equal Split) | "
        "Top 1 (Aggressive) | Ranks 4–10 (Rule 6 Watchlist) |"
    )
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for win_m, sig_m, ranks in rev[:12]:
        top3_str = ", ".join(f"**{r.ticker}** ({r.return_3y_pct:+.0f}%)" for r in ranks[:3])
        top1_str = ranks[0].ticker if ranks else "—"
        rest_str = ", ".join(r.ticker for r in ranks[3:10]) if len(ranks) > 3 else "—"
        lines.append(f"| {win_m} | {sig_m} | {top3_str} | {top1_str} | {rest_str} |")
    lines.append("")

    if len(rev) > 12:
        lines.append("<details>")
        lines.append(
            f"<summary>{full_label} ({len(rev)} windows: "
            f"{history[0][0]} to {history[-1][0]})</summary>"
        )
        lines.append("")
        lines.append("| Window | Signal Data | Top 3 (Standard) | Top 1 | Ranks 4–10 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for win_m, sig_m, ranks in rev:
            top3_str = ", ".join(r.ticker for r in ranks[:3])
            top1_str = ranks[0].ticker if ranks else "—"
            rest_str = ", ".join(r.ticker for r in ranks[3:10]) if len(ranks) > 3 else "—"
            lines.append(f"| {win_m} | {sig_m} | {top3_str} | {top1_str} | {rest_str} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")


def _render_readme_block(
    summary: dict[str, Any],
    variants: dict[str, BacktestResult],
    sensitivity: dict[str, BacktestResult],
    subperiods: list[SubperiodRow],
    latest_ranking: list[RankedSecurity],
    history_by_window: list[tuple[str, str, int, list[RankedSecurity]]],
    holdings: list[Holding],
    rule6_recs: list[dict[str, Any]],
    global_summary: dict[str, Any] | None = None,
    has_comparison_chart: bool = False,
    ftse_history: list[tuple[str, str, list[RankedSecurity]]] | None = None,
    acwi_uk_history: list[tuple[str, str, list[RankedSecurity]]] | None = None,
    us_alloc_std: dict[str, Any] | None = None,
    global_alloc: dict[str, Any] | None = None,
    funding_comparison: dict[str, Any] | None = None,
) -> str:
    latest_window = summary["latest_window"]
    signal_month = summary["latest_signal_month"]
    contribution = summary["monthly_contribution_gbp"]
    fee_pct = summary["fee_pct"]

    lines: list[str] = []
    lines.append(f"## Latest Mechanistic Picks — {latest_window} Window")
    lines.append("")
    lines.append(
        f"Generated deterministically from completed monthly data through **{signal_month}** "
        f"(`{summary['constituents_count']}` active US constituents · "
        f"`{summary['latest_eligible_count']}` eligible after the 3-year history & non-negative "
        "3-month return filter). Next trading day action: split this month's contribution "
        "equally across **Top 3** (or **Top 5** for Balanced)."
    )
    lines.append("")
    lines.append("### US S&P 500 — Standard Strategy Picks (Top 3 — Equal 1/3 Split)")
    lines.append("")
    lines.append("| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return |")
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
    for item in latest_ranking[:3]:
        lines.append(
            f"| #{item.rank} | **{item.ticker}** | {item.name} | {item.sector or '—'} | "
            f"{_format_pct(item.return_3y_pct)} | {_format_pct(item.return_3m_pct)} |"
        )
    lines.append("")

    if latest_ranking:
        top1 = latest_ranking[0]
        lines.append(
            f"- **Aggressive (Top 1):** **{top1.ticker}** ({top1.name}) — "
            f"`{_format_pct(top1.return_3y_pct)}` 3Y TR, `{_format_pct(top1.return_3m_pct)}` 3M "
            f"*(note: Top 1 historically saw drawdowns up to −76%)*."
        )
    if len(latest_ranking) >= 5:
        top5_tickers = ", ".join(f"**{r.ticker}**" for r in latest_ranking[:5])
        lines.append(f"- **Balanced (Top 5):** {top5_tickers} (equal 1/5 split).")
    lines.append("")

    lines.append("<details>")
    lines.append(
        f"<summary>Full US S&P 500 Top 10 for {latest_window} "
        "(Cautious Variant & Rule 6 Watchlist)</summary>"
    )
    lines.append("")
    lines.append(
        "| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return | Top 3 Buy |"
    )
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: |")
    for item in latest_ranking[:10]:
        buy_flag = "Yes" if item.rank <= 3 else "No"
        lines.append(
            f"| #{item.rank} | {item.ticker} | {item.name} | {item.sector or '—'} | "
            f"{_format_pct(item.return_3y_pct)} | {_format_pct(item.return_3m_pct)} | {buy_flag} |"
        )
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # Cross-market summary & comparison chart when international datasets exist
    if has_comparison_chart and global_summary:
        acwi_uk = global_summary.get("acwi_uk_accessible", {})
        acwi_all = global_summary.get("acwi_all", {})
        ftse = global_summary.get("ftse100", {})
        us_std = variants["Standard (Top 3)"].metrics

        lines.append("## Cross-Market Performance Comparison")
        lines.append("")
        lines.append(
            "![Cross-Market Performance Comparison](assets/performance_markets_comparison.png)"
        )
        lines.append("")
        lines.append(
            "| Universe | Top 3 Picks (`" + latest_window + "`) | Window | "
            "Top 3 XIRR | Top 3 TWR CAGR | Max Drawdown |"
        )
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
        us_p = ", ".join(f"**{r.ticker}**" for r in latest_ranking[:3])
        lines.append(
            f"| US S&P 500 (`{summary['priced_tickers_count']}` stocks) | {us_p} | "
            f"{summary['backtest_start_window']}..{latest_window} | "
            f"{_format_plain_pct(us_std.xirr_pct)} | "
            f"{_format_plain_pct(us_std.twr_cagr_pct)} | {us_std.max_drawdown_pct:.1f}% |"
        )
        if acwi_uk:
            au_p = ", ".join(f"**{r['ticker']}**" for r in acwi_uk.get("top3", []))
            au_s = acwi_uk.get("variants", {}).get("Standard (Top 3)", {})
            u_sz = acwi_uk.get("universe_size", 0)
            lines.append(
                f"| All World — UK-Accessible ACWI (`{u_sz}`) | {au_p} | "
                f"{acwi_uk.get('start_window')}..{acwi_uk.get('latest_window')} | "
                f"{_format_plain_pct(au_s.get('xirr_pct'))} | "
                f"{_format_plain_pct(au_s.get('twr_cagr_pct'))} | "
                f"{au_s.get('max_drawdown_pct', 0.0):.1f}% |"
            )
        if acwi_all:
            aa_p = ", ".join(f"**{r['ticker']}**" for r in acwi_all.get("top3", []))
            aa_s = acwi_all.get("variants", {}).get("Standard (Top 3)", {})
            lines.append(
                f"| All World — Full ACWI (`{acwi_all.get('universe_size', 0)}`) | {aa_p} | "
                f"{acwi_all.get('start_window')}..{acwi_all.get('latest_window')} | "
                f"{_format_plain_pct(aa_s.get('xirr_pct'))} | "
                f"{_format_plain_pct(aa_s.get('twr_cagr_pct'))} | "
                f"{aa_s.get('max_drawdown_pct', 0.0):.1f}% |"
            )
        if ftse:
            f_p = ", ".join(f"**{r['ticker']}**" for r in ftse.get("top5", [])[:3])
            f_s = ftse.get("variants", {}).get("Standard (Top 3)", {})
            lines.append(
                f"| UK FTSE 100 (`{ftse.get('universe_size', 0)}`) | {f_p} | "
                f"{ftse.get('start_window')}..{ftse.get('latest_window')} | "
                f"{_format_plain_pct(f_s.get('xirr_pct'))} | "
                f"{_format_plain_pct(f_s.get('twr_cagr_pct'))} | "
                f"{f_s.get('max_drawdown_pct', 0.0):.1f}% |"
            )
        lines.append("")

    lines.append("## US S&P 500 — Performance Chart (Mechanistic Simulation)")
    lines.append("")
    lines.append("![Monthly Momentum Performance](assets/performance.png)")
    lines.append("")
    lines.append(
        f"Monthly £{contribution:,.0f} DCA simulation across **{summary['windows_count']}** "
        f"windows (**{summary['backtest_start_window']}** to **{latest_window}**, "
        f"`£{summary['total_contributed_gbp']:,.0f}` invested, `{fee_pct:.2f}%` US FX fee on "
        "buys/sells vs `0.00%` `^SP500TR` benchmark):"
    )
    lines.append("")
    lines.append(
        "| Variant | Ending Value | XIRR | TWR CAGR | Max Drawdown | "
        "Top Holding (%) | 5Y Rolling Win vs S&P 500 TR |"
    )
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    for name in _ORDERED_VARIANT_LABELS:
        m = variants[name].metrics
        win_str = (
            f"{m.rolling_5y.win_rate_pct:.1f}% "
            f"({m.rolling_5y.win_count}/{m.rolling_5y.windows_count})"
            if m.rolling_5y
            else "—"
        )
        top_h = (
            f"{m.top_holding_ticker} ({m.top_holding_weight_pct:.1f}%)"
            if m.top_holding_ticker
            else "—"
        )
        lines.append(
            f"| {name} | £{m.ending_value:,.0f} | {_format_plain_pct(m.xirr_pct)} | "
            f"{_format_plain_pct(m.twr_cagr_pct)} | {m.max_drawdown_pct:.1f}% | "
            f"{top_h} | {win_str} |"
        )

    for s_name, s_res in sensitivity.items():
        m = s_res.metrics
        win_str = (
            f"{m.rolling_5y.win_rate_pct:.1f}% "
            f"({m.rolling_5y.win_count}/{m.rolling_5y.windows_count})"
            if m.rolling_5y
            else "—"
        )
        top_h = (
            f"{m.top_holding_ticker} ({m.top_holding_weight_pct:.1f}%)"
            if m.top_holding_ticker
            else "—"
        )
        lines.append(
            f"| *{s_name}* | £{m.ending_value:,.0f} | {_format_plain_pct(m.xirr_pct)} | "
            f"{_format_plain_pct(m.twr_cagr_pct)} | {m.max_drawdown_pct:.1f}% | "
            f"{top_h} | {win_str} |"
        )

    std_m = variants["Standard (Top 3)"].metrics
    if std_m.benchmark_ending_value is not None:
        bench_dd = (
            f"{std_m.benchmark_max_drawdown_pct:.1f}%"
            if std_m.benchmark_max_drawdown_pct is not None
            else "—"
        )
        lines.append(
            f"| S&P 500 Total Return (`^SP500TR`) | £{std_m.benchmark_ending_value:,.0f} | "
            f"{_format_plain_pct(std_m.benchmark_xirr_pct)} | "
            f"{_format_plain_pct(std_m.benchmark_twr_cagr_pct)} | {bench_dd} | Cap-weighted | "
            "Baseline |"
        )
    lines.append("")

    if summary.get("survivorship_warning"):
        lines.append(
            "> **Survivorship-Bias Note:** Constituents lack historical exit dates; pre-snapshot "
            "periods carry survivorship bias."
        )
    else:
        lines.append(
            "> **Historical Dataset Coverage:** Built from point-in-time S&P 500 membership "
            "(`fja05680/sp500` back to 1996 + live Wikipedia updates) and US stock price "
            "histories (`weib08/Stocks-Daily-Price` spliced onto Yahoo Finance, covering "
            f"`{summary['priced_tickers_count']}` active and acquired/delisted S&P 500 tickers; "
            "note that OTC bankruptcy tickers such as `LEHMQ`, `BSC`, `SIVB`, and `FRC` are "
            "absent from the free Hugging Face dataset). See [docs/research.md](docs/research.md) "
            "for the full survivorship-free study."
        )
    lines.append("")

    if subperiods:
        lines.append("### Historical Sub-Period Breakdown (XIRR % / Year)")
        lines.append("")
        lines.append("| Period | Top 1 | Top 3 | Top 5 | Top 10 | S&P 500 TR |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for sp in subperiods:
            lines.append(
                f"| {sp.period_label} ({sp.start_month}..{sp.end_month}) | "
                f"{_format_plain_pct(sp.top1_xirr_pct)} | "
                f"{_format_plain_pct(sp.top3_xirr_pct)} | "
                f"{_format_plain_pct(sp.top5_xirr_pct)} | "
                f"{_format_plain_pct(sp.top10_xirr_pct)} | "
                f"{_format_plain_pct(sp.benchmark_xirr_pct)} |"
            )
        lines.append("")

    # All World (iShares MSCI ACWI) sections
    if global_summary and global_summary.get("acwi_uk_accessible"):
        acwi_uk = global_summary["acwi_uk_accessible"]
        acwi_all = global_summary.get("acwi_all", {})
        au_win = acwi_uk["latest_window"]
        all_sz = acwi_all.get("universe_size", 0)
        uk_sz = acwi_uk.get("universe_size", 0)
        elig_uk = acwi_uk.get("latest_eligible_count", 0)
        lines.append(f"## All World Momentum (iShares MSCI ACWI — {au_win})")
        lines.append("")
        lines.append(
            f"Built from official **iShares MSCI ACWI ETF** holdings (`{all_sz}` "
            "global equities priced across 54 exchanges & 36 currencies converted to USD). "
            f"`{uk_sz}` stocks trade on UK retail Stocks & Shares ISA "
            "exchanges (US, UK, Canada, Western Europe/Nordics); stocks on restricted "
            "or local EM/APAC exchanges are flagged and skipped in the **UK-Accessible** picks."
        )
        lines.append("")
        lines.append(f"### All World — UK-Accessible Picks ({au_win} · `{elig_uk}` eligible)")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Company | Exchange | Currency | "
            "3Y Return (USD) | 3M Return (USD) | UK Access |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :--- |")
        for item in acwi_uk.get("top3", []):
            lines.append(
                f"| #{item['rank']} | **{item['ticker']}** | {item['name']} | "
                f"{item['exchange']} | {item['currency']} | "
                f"{_format_pct(item['return_3y_usd_pct'])} | "
                f"{_format_pct(item['return_3m_usd_pct'])} | {item['uk_access_note']} |"
            )
        lines.append("")
        top10_uk = acwi_uk.get("top10", [])
        if top10_uk:
            t1 = top10_uk[0]
            t1_3y = _format_pct(t1["return_3y_usd_pct"])
            t1_3m = _format_pct(t1["return_3m_usd_pct"])
            lines.append(
                f"- **Aggressive (Top 1):** **{t1['ticker']}** ({t1['name']}) — "
                f"`{t1_3y}` 3Y USD, `{t1_3m}` 3M"
            )
        if len(top10_uk) >= 5:
            t5_s = ", ".join(f"**{r['ticker']}**" for r in top10_uk[:5])
            lines.append(f"- **Balanced (Top 5):** {t5_s}")
        lines.append("")

        flagged = acwi_uk.get("flagged_skipped", [])
        if flagged:
            lines.append(
                "> **Flagged Global Winners Outside UK Retail ISAs (Skipped Here):** "
                + ", ".join(
                    f"#{f['rank']} `{f['ticker']}` ({f['name']}, {f['location']} — "
                    f"{f['exchange']}, `{f['return_3y_usd_pct']:+.1f}%`)"
                    for f in flagged[:5]
                )
            )
        else:
            lines.append(
                "> **UK Accessibility Check:** Every stock in the Full ACWI Top 15 "
                "this month already trades on a UK-ISA-accessible exchange."
            )
        lines.append("")

        lines.append("<details>")
        lines.append(f"<summary>UK-Accessible All World Top 10 for {au_win}</summary>")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Company | Sector | Exchange | "
            "3Y Return (USD) | 3M Return (USD) | Top 3 |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: |")
        for item in top10_uk:
            sec = item["sector"] or "—"
            r3y = _format_pct(item["return_3y_usd_pct"])
            r3m = _format_pct(item["return_3m_usd_pct"])
            t3_flag = "Yes" if item["rank"] <= 3 else "No"
            lines.append(
                f"| #{item['rank']} | {item['ticker']} | {item['name']} | {sec} | "
                f"{item['exchange']} | {r3y} | {r3m} | {t3_flag} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

        lines.append(
            "![All World UK-Accessible Performance](assets/performance_acwi_uk_accessible.png)"
        )
        lines.append("")
        _render_json_variant_table(
            lines,
            acwi_uk.get("variants", {}),
            currency_sym="$",
            ending_key="ending_value",
            bench_name="iShares MSCI ACWI ETF (`ACWI`)",
            bench_ending=acwi_uk.get("benchmark_acwi_ending_value"),
            bench_xirr=acwi_uk.get("benchmark_acwi_xirr_pct"),
            bench_twr=acwi_uk.get("benchmark_acwi_twr_cagr_pct"),
            bench_dd=acwi_uk.get("benchmark_acwi_max_drawdown_pct"),
            win_col_label="5Y Rolling Win vs ACWI ETF",
        )
        lines.append("")

        if acwi_uk_history:
            _render_window_history_tables(
                lines,
                acwi_uk_history,
                heading="All World (UK-Accessible) — Latest 12 Monthly Windows",
                full_label="Full UK-Accessible ACWI Monthly Pick History",
            )

        if acwi_all:
            lines.append(
                f"### All World — Full Unfiltered ACWI ({acwi_all['latest_window']} · "
                f"`{acwi_all.get('universe_size', 0)}` equities)"
            )
            lines.append("")
            lines.append("![All World Full ACWI Performance](assets/performance_acwi.png)")
            lines.append("")
            _render_json_variant_table(
                lines,
                acwi_all.get("variants", {}),
                currency_sym="$",
                ending_key="ending_value",
                bench_name="iShares MSCI ACWI ETF (`ACWI`)",
                bench_ending=acwi_all.get("benchmark_acwi_ending_value"),
                bench_xirr=acwi_all.get("benchmark_acwi_xirr_pct"),
                bench_twr=acwi_all.get("benchmark_acwi_twr_cagr_pct"),
                bench_dd=acwi_all.get("benchmark_acwi_max_drawdown_pct"),
                win_col_label="5Y Rolling Win vs ACWI ETF",
            )
            lines.append("")
            lines.append("<details>")
            lines.append(
                "<summary>Full ACWI Top 15 with UK ISA Accessibility Flags "
                f"({acwi_all['latest_window']})</summary>"
            )
            lines.append("")
            lines.append(
                "| Rank | Ticker | Company | Location | Exchange | "
                "3Y Return (USD) | 3M Return (USD) | UK ISA Accessible |"
            )
            lines.append("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :--- |")
            for item in acwi_all.get("top15", []):
                acc_badge = "Yes" if item["uk_accessible"] else f"**No** — {item['uk_access_note']}"
                lines.append(
                    f"| #{item['rank']} | {item['ticker']} | {item['name']} | "
                    f"{item['location']} | {item['exchange']} | "
                    f"{_format_pct(item['return_3y_usd_pct'])} | "
                    f"{_format_pct(item['return_3m_usd_pct'])} | {acc_badge} |"
                )
            lines.append("")
            lines.append("</details>")
            lines.append("")
    elif global_summary and global_summary.get("global_pool", {}).get("top3"):
        gpool = global_summary["global_pool"]
        g_win = gpool.get("latest_window", latest_window)
        lines.append(f"## Multi-Market & Global Developed Pool ({g_win})")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Company | Index | Currency | 3Y Return (USD) | 3M Return (USD) |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: |")
        for item in gpool["top3"]:
            lines.append(
                f"| #{item['rank']} | **{item['ticker']}** | {item['name']} | "
                f"{item['index']} | {item['currency']} | "
                f"{_format_pct(item['return_3y_usd_pct'])} | "
                f"{_format_pct(item['return_3m_usd_pct'])} |"
            )
        lines.append("")

    # UK FTSE 100 section
    if global_summary and global_summary.get("ftse100", {}).get("top5"):
        ftse = global_summary["ftse100"]
        f_win = ftse.get("latest_window", latest_window)
        lines.append(f"## UK Market — FTSE 100 ({f_win} · GBP, 0.50% Stamp Duty)")
        lines.append("")
        lines.append(
            f"Evaluated across `{ftse.get('universe_size', 0)}` FTSE 100 constituents "
            f"(`{ftse.get('latest_eligible_count', 0)}` eligible in {f_win}, GBP with `0.50%` UK "
            "stamp duty on buys / `0%` on sells)."
        )
        lines.append("")
        lines.append("| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return |")
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
        for item in ftse["top5"][:3]:
            lines.append(
                f"| #{item['rank']} | **{item['ticker']}** | {item['name']} | "
                f"{item.get('sector') or '—'} | {_format_pct(item['return_3y_pct'])} | "
                f"{_format_pct(item['return_3m_pct'])} |"
            )
        lines.append("")
        ftse_top10 = ftse.get("top10", ftse["top5"])
        if ftse_top10:
            lines.append(
                f"- **Aggressive (Top 1):** **{ftse_top10[0]['ticker']}** ({ftse_top10[0]['name']})"
            )
        if len(ftse_top10) >= 5:
            lines.append(
                "- **Balanced (Top 5):** " + ", ".join(f"**{r['ticker']}**" for r in ftse_top10[:5])
            )
        lines.append("")
        lines.append("<details>")
        lines.append(f"<summary>Full FTSE 100 Top 10 for {f_win}</summary>")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return | Top 3 Buy |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: |")
        for item in ftse_top10[:10]:
            lines.append(
                f"| #{item['rank']} | {item['ticker']} | {item['name']} | "
                f"{item.get('sector') or '—'} | {_format_pct(item['return_3y_pct'])} | "
                f"{_format_pct(item['return_3m_pct'])} | {'Yes' if item['rank'] <= 3 else 'No'} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

        lines.append("![UK FTSE 100 Performance](assets/performance_ftse100.png)")
        lines.append("")
        _render_json_variant_table(
            lines,
            ftse.get("variants", {}),
            currency_sym="£",
            ending_key="ending_value_gbp",
            bench_name="FTSE 100 TR ETF (`ISF.L`)",
            bench_ending=ftse.get("benchmark_ftse_tr_etf_ending_value"),
            bench_xirr=ftse.get("benchmark_ftse_tr_etf_xirr_pct"),
            bench_twr=ftse.get("benchmark_ftse_tr_etf_twr_cagr_pct"),
            bench_dd=ftse.get("benchmark_ftse_tr_etf_max_drawdown_pct"),
            win_col_label="5Y Rolling Win vs ISF.L",
        )
        lines.append("")

        if ftse_history:
            _render_window_history_tables(
                lines,
                ftse_history,
                heading="UK FTSE 100 — Latest 12 Monthly Windows",
                full_label="Full FTSE 100 Monthly Pick History",
            )

    if us_alloc_std is not None:
        lines.append("## Portfolio Composition & Concentration Over Time (Standard Top 3)")
        lines.append("")
        lines.append(
            "Because each month buys the current Top 3 and holds previous winners, early "
            "compounding leaders naturally swell into concentrated weights before later "
            "winners join the portfolio."
        )
        lines.append("")
        lines.append(
            "| Universe | Active Stocks | Largest Holding | Top 5 Combined | "
            "Top 10 Combined | Effective N | Top 3 Portfolio Weights Today |"
        )
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")

        alloc_rows: list[tuple[str, dict[str, Any]]] = [("US S&P 500 (20y)", us_alloc_std)]
        if global_alloc:
            for key, lbl in (
                ("acwi_uk_accessible", "All World — UK-Accessible ACWI"),
                ("acwi_all", "All World — Full ACWI"),
                ("ftse100", "UK FTSE 100"),
            ):
                blk = global_alloc.get(key, {}).get("Standard (Top 3)")
                if blk:
                    alloc_rows.append((lbl, blk))

        for lbl, alloc in alloc_rows:
            top3_w = ", ".join(
                f"**{item['ticker']}** ({item['weight_pct']:.1f}%)"
                for item in alloc.get("final_top10", [])[:3]
            )
            lines.append(
                f"| {lbl} | {alloc['final_holdings_count']} | "
                f"**{alloc['final_top1_ticker']}** ({alloc['final_top1_pct']:.1f}%) | "
                f"{alloc['final_top5_pct']:.1f}% | {alloc['final_top10_pct']:.1f}% | "
                f"{alloc['final_effective_n']:.1f} | {top3_w} |"
            )
        lines.append("")
        lines.append("![US S&P 500 Portfolio Allocation Over Time](assets/allocation_sp500.png)")
        lines.append("")
        if global_alloc and global_alloc.get("acwi_uk_accessible"):
            lines.append(
                "![All World UK-Accessible Portfolio Allocation]"
                "(assets/allocation_acwi_uk_accessible.png)"
            )
            lines.append("")
        if global_alloc and global_alloc.get("acwi_all"):
            lines.append("![Full ACWI Portfolio Allocation](assets/allocation_acwi.png)")
            lines.append("")
        if global_alloc and global_alloc.get("ftse100"):
            lines.append("![UK FTSE 100 Portfolio Allocation](assets/allocation_ftse100.png)")
            lines.append("")

        if funding_comparison:
            lines.append(
                "### Funding Schedule Impact: Monthly DCA ($100/mo) vs Lump-Sum Start ($10,000)"
            )
            lines.append("")
            lines.append(
                "- **Monthly DCA is scale-invariant in percentage terms:** Investing `$100/mo` vs "
                "`£500/mo` produces the exact same monthly `%` portfolio weights, XIRR, and TWR "
                "CAGR (ending value scales cleanly by `5x`)."
            )
            lines.append(
                "- **Day-1 lump sums reshape portfolio concentration:** Starting with `$10,000` "
                "(or `£10,000`) invests `100x` a monthly tranche into Month 1's Top 3 and holds "
                "those early winners unless Rule 6 trims stagnant names — sharply reducing "
                "Effective N and creating high sensitivity to Day-1 picks."
            )
            lines.append(
                "- **Rebased TWR Index vs Lump Sum:** Performance charts above plot the **rebased "
                "TWR index** (`start = 10,000`) of the monthly DCA portfolio rather than a Day-1 "
                "lump-sum account."
            )
            lines.append("")
            lines.append(
                "![Funding Schedule Portfolio Comparison](assets/funding_comparison_sp500.png)"
            )
            lines.append("")
            lines.append(
                "| Universe | Schedule | Invested | Ending Value | XIRR | Max DD | "
                "Active N | Eff N | #1 Holding |"
            )
            lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

            schedule_rows: tuple[tuple[str, str], ...] = (
                ("dca_100", "Pure DCA (100/mo)"),
                ("lump_10k_dca_100", "Lump 10k + 100/mo"),
                ("lump_10k_dca_100_r6", "Lump 10k + 100/mo + Rule 6"),
                ("lump_10k_only", "Pure Lump 10k (0/mo)"),
                ("lump_10k_only_r6", "Pure Lump 10k + Rule 6"),
            )
            market_specs: tuple[tuple[str, str, str], ...] = (
                ("sp500", "US S&P 500", "$"),
                ("acwi_uk_accessible", "All World (UK ISA)", "$"),
                ("acwi_all", "All World (Full ACWI)", "$"),
                ("ftse100", "UK FTSE 100", "£"),
            )
            for m_key, m_label, sym in market_specs:
                blk = funding_comparison.get(m_key)
                if not isinstance(blk, dict):
                    continue
                for s_key, s_label in schedule_rows:
                    sc = blk.get(s_key)
                    if not isinstance(sc, dict):
                        continue
                    alloc = sc.get("allocation") or {}
                    top1_t = alloc.get("final_top1_ticker") or "—"
                    top1_w = float(alloc.get("final_top1_pct") or 0.0)
                    eff_n = float(alloc.get("final_effective_n") or 0.0)
                    n_act = int(alloc.get("final_holdings_count") or 0)
                    xirr_s = _format_plain_pct(sc.get("xirr_pct"))
                    lines.append(
                        f"| {m_label} | {s_label} | {sym}{sc['total_contributed']:,.0f} | "
                        f"{sym}{sc['ending_value']:,.0f} | {xirr_s} | "
                        f"{float(sc['max_drawdown_pct']):.1f}% | {n_act} | {eff_n:.1f} | "
                        f"**{top1_t}** ({top1_w:.1f}%) |"
                    )
            lines.append("")

    # Model Portfolio & Rule 6 Status
    active_holdings = [h for h in holdings if h.status in ACTIVE_STATUSES]
    actionable_r6 = [
        r
        for r in rule6_recs
        if r["action"]
        in {
            Rule6ActionType.SELL_THIRD.value,
            Rule6ActionType.SELL_HALF.value,
            Rule6ActionType.SELL_REMAINING.value,
            Rule6ActionType.RESET_TOP10.value,
        }
    ]
    lines.append("## US Model Portfolio & Rule 6 Faded-Winner Status")
    lines.append("")
    lines.append(
        f"- **Active model positions (Standard Top 3 + Rule 6):** `{len(active_holdings)}` "
        f"(tracked in [`data/model_holdings.csv`](data/model_holdings.csv))."
    )
    if actionable_r6:
        for rec in actionable_r6:
            lines.append(
                f"- **Rule 6 Signal ({rec['ticker']}):** `{rec['action']}` — {rec['message']}"
            )
    else:
        lines.append("- **Rule 6 Exit Signals this month:** None triggered.")

    sorted_out = sorted(rule6_recs, key=lambda r: int(r["months_out_of_top10"]), reverse=True)[:5]
    if sorted_out:
        lines.append("")
        lines.append("| Ticker | Company | Months Out of Top 10 | Status | Next Rule 6 Check |")
        lines.append("| :--- | :--- | :---: | :--- | :---: |")
        for rec in sorted_out:
            lines.append(
                f"| {rec['ticker']} | {rec['name']} | {rec['months_out_of_top10']}m | "
                f"`{rec['status']}` | {rec['next_milestone_month'] or '—'} |"
            )
    lines.append("")

    # US S&P 500 Mechanistic Picks by Month/Window
    lines.append("## US S&P 500 — Mechanistic Stock Picks by Month / Window")
    lines.append("")
    lines.append(
        "Every monthly window below is computed mechanistically from `data/monthly_prices.csv` "
        "using the completed prior month's data (`data/rankings/history.csv`)."
    )
    lines.append("")
    lines.append("### Latest 12 Monthly Windows")
    lines.append("")
    lines.append(
        "| Window | Signal Data | Top 3 (Standard Equal Split) | "
        "Top 1 (Aggressive) | Ranks 4–10 (Rule 6 Watchlist) | Eligible |"
    )
    lines.append("| :--- | :--- | :--- | :--- | :--- | :---: |")

    rev_windows = list(reversed(history_by_window))
    for win_m, sig_m, elig_cnt, ranks in rev_windows[:12]:
        top3_str = ", ".join(f"**{r.ticker}** ({r.return_3y_pct:+.0f}%)" for r in ranks[:3])
        top1_str = f"{ranks[0].ticker}" if ranks else "—"
        rest_str = ", ".join(r.ticker for r in ranks[3:10]) if len(ranks) > 3 else "—"
        lines.append(f"| {win_m} | {sig_m} | {top3_str} | {top1_str} | {rest_str} | {elig_cnt} |")
    lines.append("")

    if len(rev_windows) > 12:
        lines.append("<details>")
        lines.append(
            f"<summary>Full US S&P 500 Monthly Pick History ({len(rev_windows)} windows: "
            f"{history_by_window[0][0]} to {history_by_window[-1][0]})</summary>"
        )
        lines.append("")
        lines.append("| Window | Signal Data | Top 3 (Standard) | Top 1 | Ranks 4–10 | Eligible |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :---: |")
        for win_m, sig_m, elig_cnt, ranks in rev_windows:
            top3_str = ", ".join(r.ticker for r in ranks[:3])
            top1_str = ranks[0].ticker if ranks else "—"
            rest_str = ", ".join(r.ticker for r in ranks[3:10]) if len(ranks) > 3 else "—"
            lines.append(
                f"| {win_m} | {sig_m} | {top3_str} | {top1_str} | {rest_str} | {elig_cnt} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def _update_readme_file(readme_path: Path, generated_block: str) -> None:
    replacement = f"{README_START_MARKER}\n\n{generated_block.strip()}\n\n{README_END_MARKER}"
    if readme_path.exists():
        content = readme_path.read_text(encoding="utf-8")
        pattern = re.compile(
            re.escape(README_START_MARKER) + r".*?" + re.escape(README_END_MARKER),
            flags=re.DOTALL,
        )
        if pattern.search(content):
            updated = pattern.sub(lambda _m: replacement, content, count=1)
        else:
            updated = content.rstrip() + "\n\n" + replacement + "\n"
    else:
        updated = "# Monthly Momentum\n\n" + replacement + "\n"
    readme_path.write_text(updated, encoding="utf-8")


def rebuild_public_reports(
    root_dir: Path = Path("."),
    contribution: float = 500.0,
    fee_pct: float = 0.15,
) -> PublicReportSummary:
    """Deterministically build rankings, model holdings, charts, and README offline."""
    data_dir = root_dir / "data"
    history_const_path = data_dir / "constituents_history.csv"
    active_const_path = data_dir / "constituents.csv"
    constituents_path = history_const_path if history_const_path.exists() else active_const_path
    prices_path = data_dir / "monthly_prices.csv"
    snapshots_path = data_dir / "constituent_snapshots.csv"
    events_path = data_dir / "events.csv"

    if not constituents_path.exists() or not prices_path.exists():
        raise FileNotFoundError(
            f"Expected {constituents_path} and {prices_path}. Run `monthly-momentum refresh` first."
        )

    dataset = load_backtest_dataset(
        prices_path=prices_path,
        constituents_path=constituents_path,
        events_path=events_path if events_path.exists() else None,
        benchmark_ticker="^SP500TR",
        snapshots_path=snapshots_path if snapshots_path.exists() else None,
    )

    from monthly_momentum.normalize import add_months as _add_months

    first_equity_months = [min(tmap.keys()) for tmap in dataset.prices.values() if tmap]
    auto_start_month: str | None = None
    if first_equity_months:
        earliest_stock_month = min(first_equity_months)
        auto_start_month = _add_months(earliest_stock_month, 37)

    base_cfg = BacktestConfig(
        start_month=auto_start_month,
        monthly_contribution=contribution,
        top_n=3,
        rule6_enabled=False,
        fee_pct=fee_pct,
        sell_fee_pct=fee_pct,
        benchmark_fee_pct=0.0,
        signal_mode="next_month",
    )
    variant_list = compare_variants(dataset, base_cfg)
    variants = {v.label: v.result for v in variant_list}
    std_res = variants["Standard (Top 3)"]
    std_r6_res = variants["Standard (Top 3 + Rule 6)"]

    latest_pt = std_res.points[-1]
    std_metrics = std_res.metrics

    sensitivity, subperiods = _compute_sensitivity_and_subperiods(
        dataset=dataset,
        base_cfg=base_cfg,
        start_window=std_res.points[0].window_month,
        end_window=latest_pt.window_month,
    )

    latest_ranking_result = std_res.rankings_by_window[-1]
    latest_ranking_path = data_dir / "rankings" / "latest.csv"
    write_ranking_csv(latest_ranking_result, latest_ranking_path, limit=10)

    history_rows: list[RankedSecurity] = []
    history_by_window: list[tuple[str, str, int, list[RankedSecurity]]] = []
    for pt, r_res in zip(std_res.points, std_res.rankings_by_window, strict=True):
        top10 = r_res.top10
        history_rows.extend(top10)
        history_by_window.append((pt.window_month, pt.signal_month, pt.eligible_count, top10))

    history_ranking_path = data_dir / "rankings" / "history.csv"
    write_ranking_history_csv(history_rows, history_ranking_path)

    model_holdings, rule6_recs = build_model_holdings(std_res, std_r6_res)
    model_holdings_path = data_dir / "model_holdings.csv"
    write_holdings_csv(model_holdings, model_holdings_path)

    performance_csv_path = data_dir / "performance.csv"
    perf_rows = write_variants_performance_csv(variants, performance_csv_path)

    variant_summary_json: dict[str, Any] = {}
    for name, res in list(variants.items()) + list(sensitivity.items()):
        m = res.metrics
        variant_summary_json[name] = {
            "ending_value_gbp": round(m.ending_value, 2),
            "xirr_pct": round(m.xirr_pct, 2) if m.xirr_pct is not None else None,
            "twr_cagr_pct": round(m.twr_cagr_pct, 2) if m.twr_cagr_pct is not None else None,
            "max_drawdown_pct": round(m.max_drawdown_pct, 2),
            "top_holding_ticker": m.top_holding_ticker,
            "top_holding_weight_pct": round(m.top_holding_weight_pct, 2),
            "max_single_holding_weight_pct": round(m.max_single_holding_weight_pct, 2),
            "rolling_5y_win_rate_pct": (
                round(m.rolling_5y.win_rate_pct, 2) if m.rolling_5y else None
            ),
            "rule6_exits_count": m.rule6_exits_count,
            "delistings_liquidated_count": m.delistings_liquidated_count,
        }
    if std_metrics.benchmark_ending_value is not None:
        variant_summary_json["S&P 500 TR (^SP500TR)"] = {
            "ending_value_gbp": round(std_metrics.benchmark_ending_value, 2),
            "xirr_pct": (
                round(std_metrics.benchmark_xirr_pct, 2)
                if std_metrics.benchmark_xirr_pct is not None
                else None
            ),
            "twr_cagr_pct": (
                round(std_metrics.benchmark_twr_cagr_pct, 2)
                if std_metrics.benchmark_twr_cagr_pct is not None
                else None
            ),
            "max_drawdown_pct": (
                round(std_metrics.benchmark_max_drawdown_pct, 2)
                if std_metrics.benchmark_max_drawdown_pct is not None
                else None
            ),
        }

    active_constituents_count = len(
        {ticker_match_key(c.ticker) for c in dataset.constituents if c.end_date is None}
    )
    if active_constituents_count == 0:
        active_constituents_count = len({ticker_match_key(c.ticker) for c in dataset.constituents})

    summary_payload: dict[str, Any] = {
        "latest_window": latest_pt.window_month,
        "latest_signal_month": latest_pt.signal_month,
        "backtest_start_window": std_res.points[0].window_month,
        "windows_count": len(std_res.points),
        "months_invested": std_metrics.months_invested,
        "monthly_contribution_gbp": contribution,
        "total_contributed_gbp": round(std_metrics.total_contributed, 2),
        "fee_pct": fee_pct,
        "constituents_count": active_constituents_count,
        "historical_constituent_intervals": len(dataset.constituents),
        "priced_tickers_count": len(dataset.prices),
        "latest_eligible_count": latest_pt.eligible_count,
        "top3_picks": [
            {
                "rank": r.rank,
                "ticker": r.ticker,
                "name": r.name,
                "sector": r.sector,
                "return_3y_pct": round(r.return_3y_pct, 4),
                "return_3m_pct": round(r.return_3m_pct, 4),
            }
            for r in latest_ranking_result.top_picks
        ],
        "top10": [
            {
                "rank": r.rank,
                "ticker": r.ticker,
                "name": r.name,
                "sector": r.sector,
                "return_3y_pct": round(r.return_3y_pct, 4),
                "return_3m_pct": round(r.return_3m_pct, 4),
            }
            for r in latest_ranking_result.top10
        ],
        "variants": variant_summary_json,
        "subperiods": [
            {
                "label": sp.period_label,
                "start_month": sp.start_month,
                "end_month": sp.end_month,
                "top1_xirr_pct": (
                    round(sp.top1_xirr_pct, 2) if sp.top1_xirr_pct is not None else None
                ),
                "top3_xirr_pct": (
                    round(sp.top3_xirr_pct, 2) if sp.top3_xirr_pct is not None else None
                ),
                "top5_xirr_pct": (
                    round(sp.top5_xirr_pct, 2) if sp.top5_xirr_pct is not None else None
                ),
                "top10_xirr_pct": (
                    round(sp.top10_xirr_pct, 2) if sp.top10_xirr_pct is not None else None
                ),
                "benchmark_xirr_pct": (
                    round(sp.benchmark_xirr_pct, 2) if sp.benchmark_xirr_pct is not None else None
                ),
            }
            for sp in subperiods
        ],
        "survivorship_warning": dataset.survivorship_warning,
        "rule6_signals": [r for r in rule6_recs if r["action"] != Rule6ActionType.HOLD.value],
    }

    summary_json_path = data_dir / "summary.json"
    summary_json_path.write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")

    chart_path = root_dir / "assets" / "performance.png"
    generate_performance_chart(perf_rows, summary_payload, chart_path)

    us_alloc_payload = build_variants_allocation_payload(variants)
    (data_dir / "allocation_summary.json").write_text(
        json.dumps(us_alloc_payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    us_alloc_std = us_alloc_payload["Standard (Top 3)"]
    generate_allocation_chart(
        us_alloc_std,
        root_dir / "assets" / "allocation_sp500.png",
        title="How a 20-year US momentum portfolio concentrates into mega-winners",
        subtitle=(
            f"Monthly % weights across held S&P 500 equities (Top 3 Standard · "
            f"{std_res.points[0].window_month} to {latest_pt.window_month}, GBP)"
        ),
        footer_note=(
            "Source: fja05680 S&P 500 membership, weib08 & Yahoo Finance (reinvested dividends). "
            "Weights marked after each month's buys."
        ),
    )

    us_funding = build_funding_schedule_comparison(
        dataset,
        base_cfg,
        lump_sum=10_000.0,
        monthly_dca=100.0,
        top_n=3,
    )
    generate_funding_comparison_chart(
        us_funding,
        root_dir / "assets" / "funding_comparison_sp500.png",
        title="Starting with a $10k lump sum concentrates US holdings far more than $100/mo DCA",
        subtitle=(
            f"Portfolio weight % across S&P 500 Top 3 strategies ({std_res.points[0].window_month} "
            f"to {latest_pt.window_month}, USD)"
        ),
        currency_symbol="$",
        footer_note=(
            "Source: fja05680 S&P 500 membership, weib08 & Yahoo Finance (reinvested dividends, "
            "0.15% FX fee). Pure DCA ($100/mo) and £500/mo share identical % weights."
        ),
    )
    funding_comparison_payload: dict[str, Any] = {"sp500": us_funding}

    global_summary_dict: dict[str, Any] | None = None
    global_alloc_dict: dict[str, Any] | None = None
    global_const = data_dir / "global" / "constituents.csv"
    global_prices = data_dir / "global" / "monthly_prices.csv"
    has_comparison_chart = False
    ftse_history: list[tuple[str, str, list[RankedSecurity]]] | None = None
    acwi_uk_history: list[tuple[str, str, list[RankedSecurity]]] | None = None

    if global_const.exists() and global_prices.exists():
        from monthly_momentum.markets import build_global_reports

        g_res = build_global_reports(root_dir=root_dir, contribution=contribution)
        global_summary_dict = json.loads(g_res.summary_json_path.read_text(encoding="utf-8"))

        global_dir = data_dir / "global"
        strategy_series: dict[str, list[tuple[date, float]]] = {}
        us_series = _load_nav_series_from_perf_csv(performance_csv_path, "top3_nav")
        if us_series:
            strategy_series["US S&P 500 (Top 3)"] = us_series

        acwi_uk_perf = global_dir / "performance_acwi_uk_accessible.csv"
        acwi_uk_series = _load_nav_series_from_perf_csv(acwi_uk_perf, "top3_nav")
        if acwi_uk_series:
            strategy_series["All World — UK-Accessible ACWI (Top 3)"] = acwi_uk_series

        acwi_all_perf = global_dir / "performance_acwi.csv"
        acwi_all_series = _load_nav_series_from_perf_csv(acwi_all_perf, "top3_nav")
        if acwi_all_series:
            strategy_series["All World — Full ACWI (Top 3)"] = acwi_all_series

        ftse_perf = global_dir / "performance_ftse100.csv"
        ftse_series = _load_nav_series_from_perf_csv(ftse_perf, "top3_nav")
        if ftse_series:
            strategy_series["UK FTSE 100 (Top 3)"] = ftse_series

        bench_series: dict[str, list[tuple[date, float]]] = {}
        us_b = _load_nav_series_from_perf_csv(performance_csv_path, "benchmark_nav")
        if us_b:
            bench_series["S&P 500 TR (^SP500TR)"] = us_b
        acwi_b = _load_nav_series_from_perf_csv(acwi_all_perf, "benchmark_nav")
        if acwi_b:
            bench_series["MSCI ACWI ETF (ACWI)"] = acwi_b
        ftse_b = _load_nav_series_from_perf_csv(ftse_perf, "benchmark_nav")
        if ftse_b:
            bench_series["FTSE 100 TR (ISF.L)"] = ftse_b

        if len(strategy_series) >= 2:
            generate_markets_comparison_chart(
                strategy_series,
                bench_series,
                root_dir / "assets" / "performance_markets_comparison.png",
            )
            has_comparison_chart = True

        ftse_history = _group_history_by_window(global_dir / "rankings" / "history_ftse100.csv")
        acwi_uk_history = _group_history_by_window(
            global_dir / "rankings" / "history_acwi_uk_accessible.csv"
        )
        global_alloc_path = global_dir / "allocation_summary.json"
        if global_alloc_path.exists():
            global_alloc_dict = json.loads(global_alloc_path.read_text(encoding="utf-8"))
        global_funding_path = global_dir / "funding_comparison.json"
        if global_funding_path.exists():
            global_funding_data = json.loads(global_funding_path.read_text(encoding="utf-8"))
            for key in ("acwi_uk_accessible", "acwi_all", "ftse100"):
                if key in global_funding_data:
                    funding_comparison_payload[key] = global_funding_data[key]

    (data_dir / "funding_comparison.json").write_text(
        json.dumps(funding_comparison_payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    readme_path = root_dir / "README.md"
    readme_block = _render_readme_block(
        summary=summary_payload,
        variants=variants,
        sensitivity=sensitivity,
        subperiods=subperiods,
        latest_ranking=latest_ranking_result.top10,
        history_by_window=history_by_window,
        holdings=model_holdings,
        rule6_recs=rule6_recs,
        global_summary=global_summary_dict,
        has_comparison_chart=has_comparison_chart,
        ftse_history=ftse_history,
        acwi_uk_history=acwi_uk_history,
        us_alloc_std=us_alloc_std,
        global_alloc=global_alloc_dict,
        funding_comparison=funding_comparison_payload,
    )
    _update_readme_file(readme_path, readme_block)

    return PublicReportSummary(
        latest_window=latest_pt.window_month,
        latest_signal_month=latest_pt.signal_month,
        top3_tickers=[r.ticker for r in latest_ranking_result.top_picks],
        top1_ticker=(
            latest_ranking_result.top_picks[0].ticker if latest_ranking_result.top_picks else ""
        ),
        top10_tickers=[r.ticker for r in latest_ranking_result.top10],
        windows_count=len(std_res.points),
        latest_ranking_path=latest_ranking_path,
        history_ranking_path=history_ranking_path,
        model_holdings_path=model_holdings_path,
        performance_csv_path=performance_csv_path,
        summary_json_path=summary_json_path,
        chart_path=chart_path,
        readme_path=readme_path,
    )
