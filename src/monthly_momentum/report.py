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
    benchmark_relative_series,
    generate_allocation_chart,
    generate_benchmark_relative_chart,
    generate_funding_comparison_chart,
    generate_hero_vs_sp500_chart,
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
BENCHMARK_RELATIVE_CHART = "assets/performance_vs_benchmark.png"

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


def _render_hero_and_takeaways(
    lines: list[str],
    *,
    summary: dict[str, Any],
    variants: dict[str, BacktestResult],
    global_summary: dict[str, Any] | None,
    us_alloc_std: dict[str, Any] | None,
    global_alloc: dict[str, Any] | None,
    hero_stats: dict[str, Any] | None,
) -> None:
    std_m = variants["Standard (Top 3)"].metrics
    contribution = float(summary.get("monthly_contribution_gbp") or 500.0)
    scale = (100.0 / contribution) if contribution > 0.0 else 1.0
    us20_end = std_m.ending_value * scale
    sp20_end = (
        std_m.benchmark_ending_value * scale if std_m.benchmark_ending_value is not None else None
    )
    us20_in = std_m.total_contributed * scale
    us20_xirr = std_m.xirr_pct or 0.0
    sp20_xirr = std_m.benchmark_xirr_pct or 0.0

    lines.append("## At a Glance: Why This Works (and the Catch)")
    lines.append("")
    lines.append("![Monthly Momentum $100/month vs S&P 500 Tracker](assets/hero_vs_sp500.png)")
    lines.append("")

    c9 = (hero_stats or {}).get("common_9y")
    if c9 and c9.get("acwi_uk"):
        uk9 = c9["acwi_uk"]
        sp9 = c9.get("sp500")
        ab9 = c9.get("acwi_bench")
        parts_9y = [
            f"**${uk9['ending_value']:,.0f}** ({uk9['xirr_pct']:.1f}%/yr) in **All World (UK ISA)**"
        ]
        if sp9:
            ratio9 = uk9["ending_value"] / sp9["ending_value"] if sp9["ending_value"] > 0 else 0.0
            parts_9y.append(
                f"vs **${sp9['ending_value']:,.0f}** ({sp9['xirr_pct']:.1f}%/yr) in an S&P 500 "
                f"tracker (**{ratio9:.1f}x**)"
            )
        if ab9:
            parts_9y.append(
                f"and **${ab9['ending_value']:,.0f}** ({ab9['xirr_pct']:.1f}%/yr) "
                "in an MSCI ACWI ETF"
            )
        edge_9y = " ".join(parts_9y)
    else:
        edge_9y = ""

    sp20_txt = ""
    if sp20_end and sp20_end > 0:
        ratio20 = us20_end / sp20_end
        sp20_txt = (
            f"vs **${sp20_end:,.0f}** ({sp20_xirr:.1f}%/yr) in the S&P 500 (**{ratio20:.1f}x**)"
        )
    us20_sentence = (
        f"Over the full survivorship-aware **20-year US stress test** (${us20_in:,.0f} put in), "
        f"Top 3 reached **${us20_end:,.0f}** ({us20_xirr:.1f}%/yr) {sp20_txt}."
    )
    if edge_9y:
        lines.append(
            "- **The edge (`$100/month`):** Over the shared 9-year global window, `$100/mo` "
            f"grew to {edge_9y}. {us20_sentence}"
        )
    else:
        lines.append(f"- **The edge (`$100/month`):** {us20_sentence}")

    lines.append(
        "- **Why it works:** Buying current winners and holding without stop-losses lets rare "
        "multi-baggers (`AAPL`, `NVDA`, `AMD`, `ARGX.BR`, `GAW.L`) compound uncapped, while small "
        "equal monthly buys keep individual losers immaterial."
    )

    us_top5_pct = f"{us_alloc_std['final_top5_pct']:.0f}%" if us_alloc_std else "~75%"
    uk_std = (
        (global_summary or {})
        .get("acwi_uk_accessible", {})
        .get("variants", {})
        .get("Standard (Top 3)", {})
    )
    uk_dd = uk_std.get("max_drawdown_pct")
    dd_range = (
        f"**{uk_dd:.0f}%** to **{std_m.max_drawdown_pct:.0f}%**"
        if uk_dd is not None
        else f"**{std_m.max_drawdown_pct:.0f}%**"
    )
    uk_top5_w = (
        (global_alloc or {})
        .get("acwi_uk_accessible", {})
        .get("Standard (Top 3)", {})
        .get("final_top5_pct")
    )
    conc_txt = f"{uk_top5_w:.0f}%–{us_top5_pct}" if uk_top5_w is not None else us_top5_pct
    lines.append(
        f"- **The catch:** Expect stomach-churning drops ({dd_range} peak-to-trough), heavy "
        f"top-5 concentration (**{conc_txt}** of portfolio value), and multi-year lagging spells "
        "(e.g. 2022–2023 drawdowns, or 2009–2018 outside the US). Best run as a **minority "
        "satellite slice (e.g., 10–25%)** inside a tax-free Stocks & Shares ISA alongside a core "
        "tracker."
    )
    lines.append(
        "- **Monthly DCA vs. Lump Sum:** `$100/mo` and `£500/mo` produce identical `%` portfolio "
        "weights and annualized returns (only totals scale). Dropping a `$10,000` lump sum on "
        "Day 1 locks `100x` a monthly buy into Month 1's Top 3 — shrinking Effective N to "
        "`1.1–2.8` unless phased in or rotated by **Rule 6**."
    )
    lines.append("")


def _render_option_guide(
    lines: list[str],
    *,
    summary: dict[str, Any],
    variants: dict[str, BacktestResult],
    global_summary: dict[str, Any] | None,
    hero_stats: dict[str, Any] | None,
) -> None:
    std_m = variants["Standard (Top 3)"].metrics
    contribution = float(summary.get("monthly_contribution_gbp") or 500.0)
    scale = (100.0 / contribution) if contribution > 0.0 else 1.0
    us20_end = std_m.ending_value * scale
    us20_xirr = std_m.xirr_pct

    lines.append("## Which Option Is Best?")
    lines.append("")

    c9 = (hero_stats or {}).get("common_9y")
    if global_summary and global_summary.get("acwi_uk_accessible"):
        au = global_summary["acwi_uk_accessible"]
        aa = global_summary.get("acwi_all", {})
        ft = global_summary.get("ftse100", {})
        au_s = au.get("variants", {}).get("Standard (Top 3)", {})
        aa_s = aa.get("variants", {}).get("Standard (Top 3)", {})
        ft_s = ft.get("variants", {}).get("Standard (Top 3)", {})

        us9_str = (
            f"${c9['us_top3']['ending_value']:,.0f} ({c9['us_top3']['xirr_pct']:.1f}%)"
            if c9 and c9.get("us_top3")
            else "—"
        )
        uk9_end = (au_s.get("ending_value") or 0.0) * scale
        aa9_end = (aa_s.get("ending_value") or 0.0) * scale
        ft9_end = (ft_s.get("ending_value_gbp") or 0.0) * scale
        uk9_x = _format_plain_pct(au_s.get("xirr_pct"))
        aa9_x = _format_plain_pct(aa_s.get("xirr_pct"))
        ft9_x = _format_plain_pct(ft_s.get("xirr_pct"))

        lines.append(
            "| Strategy Option (Standard Top 3) | Best For | Shared 9Y (`$100/mo`) | "
            "Full 20Y (`$100/mo`) | Worst Drop | Verdict |"
        )
        lines.append("| :--- | :--- | :---: | :---: | :---: | :--- |")
        lines.append(
            f"| **All World — UK ISA** (`{au.get('universe_size', 0)}` stocks) | "
            f"UK retail Stocks & Shares ISA | **${uk9_end:,.0f}** ({uk9_x}) | — | "
            f"{au_s.get('max_drawdown_pct', 0.0):.1f}% | "
            "**Best everyday pick** — global breadth, skips inaccessible EM shares |"
        )
        lines.append(
            f"| **US S&P 500** (`{summary['priced_tickers_count']}` stocks) | "
            f"Maximum historical confidence | {us9_str} | "
            f"**${us20_end:,.0f}** ({_format_plain_pct(us20_xirr)}) | "
            f"{std_m.max_drawdown_pct:.1f}% | "
            "**Most battle-tested** — survivorship-free across 2008 & delistings |"
        )
        if aa:
            lines.append(
                f"| All World — Full ACWI (`{aa.get('universe_size', 0)}` stocks) | "
                f"Global institutional benchmark | ${aa9_end:,.0f} ({aa9_x}) | — | "
                f"{aa_s.get('max_drawdown_pct', 0.0):.1f}% | "
                "Reference only — includes local TW/KR/CN shares |"
            )
        if ft:
            lines.append(
                f"| UK FTSE 100 (`{ft.get('universe_size', 0)}` stocks) | "
                f"GBP-only / lower drawdown | £{ft9_end:,.0f} ({ft9_x}) | — | "
                f"{ft_s.get('max_drawdown_pct', 0.0):.1f}% | "
                "Beats FTSE 100 TR, lower growth after 0.50% stamp duty |"
            )
        lines.append("")
        if c9 and c9.get("us_top3") and c9.get("acwi_uk"):
            uk_v = c9["acwi_uk"]["ending_value"]
            us_v = c9["us_top3"]["ending_value"]
            win_span = f"{c9['start_window']}–{c9['end_window']}"
            lines.append(
                "> **Why did `All World (UK ISA)` look so much higher than `US S&P 500` "
                "in raw headline tables?** Different start years. Over the exact same 9-year "
                f"window (`{win_span}`), All World UK ISA (`${uk_v:,.0f}`) and US S&P 500 "
                f"(`${us_v:,.0f}`) delivered nearly identical returns — while the 20-year US "
                "figure (`21.9%`) includes the 2008 financial crash and 2010s grind. All World "
                "(UK ISA) edges ahead practically by spreading across Europe & Canada with "
                "shallower drawdowns."
            )
            lines.append("")
    else:
        lines.append("| Variant | `$100/mo` Ending Value | XIRR | Worst Drop | Verdict |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for lbl in (
            "Standard (Top 3)",
            "Standard (Top 3 + Rule 6)",
            "Balanced (Top 5)",
            "Cautious (Top 10)",
        ):
            m = variants[lbl].metrics
            verdict = "Recommended core rule" if lbl == "Standard (Top 3)" else "Optional variant"
            lines.append(
                f"| **{lbl}** | ${m.ending_value * scale:,.0f} | {_format_plain_pct(m.xirr_pct)} "
                f"| {m.max_drawdown_pct:.1f}% | {verdict} |"
            )
        lines.append("")

    lines.append(
        "- **How many stocks per month (`Top 3` vs `Top 5` vs `Top 10`)?** **Top 3** captures "
        "most of `Top 1`'s upside without single-stock lottery risk. **Top 5 (`Balanced`)** or "
        "**Top 10 (`Cautious`)** spreads buys wider at lower return. See `Balanced (Top 5)` and "
        "all variants in Deep Dive 1."
    )
    lines.append(
        "- **Should you use Rule 6 (6/7/8-year faded-winner trim)?** Optional for pure monthly "
        "DCA, **essential if starting with a large Day-1 lump sum**: once a stock stays outside "
        "the Top 10 for 6/7/8 years, Rule 6 trims 1/3 -> 1/2 -> all and recycles proceeds into "
        "fresh leaders (pausing immediately if it re-enters the Top 10)."
    )
    lines.append("")


def _render_how_it_works(lines: list[str]) -> None:
    lines.append("## How It Works (5 Minutes a Month)")
    lines.append("")
    lines.append(
        "1. **Pick one universe:** Either **All World (UK ISA)** *(best all-rounder)* or "
        "**US S&P 500** *(20y survivorship-aware baseline)*."
    )
    lines.append(
        "2. **Read this month's Top 3:** Ranked automatically after month-end by "
        "**3-year total return (incl. dividends)**, discarding any stock down over the last "
        "3 months."
    )
    lines.append(
        "3. **Buy equally on the 1st trading day:** Split that month's contribution into three "
        "equal fractional buys (even if you already own those stocks)."
    )
    lines.append(
        "4. **Hold without stop-losses:** Every stop-loss rule tested destroyed returns by shaking "
        "out future multi-baggers (`NVDA` fell −85% after 2008). Only trim via **Rule 6** after "
        "6–8 years outside the Top 10."
    )
    lines.append("")


def _render_picks_overview(
    lines: list[str],
    summary: dict[str, Any],
    global_summary: dict[str, Any] | None,
) -> None:
    lines.extend(["## This month's picks", ""])
    lines.append(f"**Latest window:** {summary['latest_window']}.")
    if updated_on := summary.get("picks_updated_on"):
        lines.append(f"**Last updated:** {updated_on} (UTC).")
    lines.extend(["", "| Universe | Window | Top 3 |", "| :--- | :--- | :--- |"])

    markets = global_summary or {}
    rows = [
        ("All World — UK-accessible", markets.get("acwi_uk_accessible"), "top3"),
        ("US S&P 500", summary, "top3_picks"),
        ("UK FTSE 100", markets.get("ftse100"), "top5"),
        ("All World — Full ACWI", markets.get("acwi_all"), "top3"),
    ]
    for label, market, picks_key in rows:
        if market is None:
            continue
        tickers = ", ".join(f"**{pick['ticker']}**" for pick in market[picks_key][:3])
        lines.append(f"| {label} | {market['latest_window']} | {tickers or '—'} |")

    lines.extend(
        [
            "",
            "[See the rankings and returns](#latest-pick-details).",
            "For monthly alerts, choose **Watch → Custom → Releases** on GitHub.",
            "",
        ]
    )


def _render_latest_picks_section(
    lines: list[str],
    *,
    summary: dict[str, Any],
    latest_ranking: list[RankedSecurity],
    global_summary: dict[str, Any] | None,
) -> None:
    latest_window = summary["latest_window"]
    signal_month = summary["latest_signal_month"]

    lines.append("## Latest pick details")
    lines.append("")
    lines.append(
        f"Computed deterministically from completed data through **{signal_month}**. "
        "Split this month's deposit equally across your chosen universe's **Top 3**."
    )
    lines.append("")

    if global_summary and global_summary.get("acwi_uk_accessible"):
        au = global_summary["acwi_uk_accessible"]
        au_win = au["latest_window"]
        au_elig = au.get("latest_eligible_count", 0)
        lines.append(f"### All World — UK-Accessible Top 3 (`{au_elig}` eligible · {au_win})")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Company | Exchange | 3Y Return (USD) | 3M Return (USD) | UK Access |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :--- |")
        for item in au.get("top3", []):
            r3y = _format_pct(item["return_3y_usd_pct"])
            r3m = _format_pct(item["return_3m_usd_pct"])
            lines.append(
                f"| #{item['rank']} | **{item['ticker']}** | {item['name']} | "
                f"{item['exchange']} | {r3y} | {r3m} | {item['uk_access_note']} |"
            )
        lines.append("")

        top10_uk = au.get("top10", [])
        if len(top10_uk) >= 5:
            uk_t5_s = ", ".join(f"**{r['ticker']}**" for r in top10_uk[:5])
            lines.append(
                f"- **Top 1 (Aggressive):** **{top10_uk[0]['ticker']}** · "
                f"**Balanced (Top 5):** {uk_t5_s}"
            )
            lines.append("")

        flagged = au.get("flagged_skipped", [])
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
                "> **UK Accessibility Check:** Every stock in the Full ACWI Top 15 this month "
                "trades on a UK-ISA exchange."
            )
        lines.append("")

        if top10_uk:
            lines.append("<details>")
            lines.append(f"<summary>Full All World (UK-Accessible) Top 10 for {au_win}</summary>")
            lines.append("")
            lines.append(
                "| Rank | Ticker | Company | Sector | Exchange | "
                "3Y Return (USD) | 3M Return (USD) | Top 3 |"
            )
            lines.append("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: |")
            for item in top10_uk:
                sec = item.get("sector") or "—"
                r3y = _format_pct(item["return_3y_usd_pct"])
                r3m = _format_pct(item["return_3m_usd_pct"])
                buy_flag = "Yes" if item["rank"] <= 3 else "No"
                lines.append(
                    f"| #{item['rank']} | {item['ticker']} | {item['name']} | {sec} | "
                    f"{item['exchange']} | {r3y} | {r3m} | {buy_flag} |"
                )
            lines.append("")
            lines.append("</details>")
            lines.append("")

    us_elig = summary["latest_eligible_count"]
    us_cnt = summary["constituents_count"]
    lines.append(f"### US S&P 500 — Top 3 (`{us_elig}` eligible of {us_cnt} · {latest_window})")
    lines.append("")
    lines.append("| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return |")
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
    for item in latest_ranking[:3]:
        lines.append(
            f"| #{item.rank} | **{item.ticker}** | {item.name} | {item.sector or '—'} | "
            f"{_format_pct(item.return_3y_pct)} | {_format_pct(item.return_3m_pct)} |"
        )
    lines.append("")
    if latest_ranking and len(latest_ranking) >= 5:
        lines.append(
            f"- **Aggressive (Top 1):** **{latest_ranking[0].ticker}** · "
            f"**Balanced (Top 5):** {', '.join(f'**{r.ticker}**' for r in latest_ranking[:5])} "
            "*(Top 1 historically saw drawdowns up to −76%)*."
        )
        lines.append("")

    lines.append("<details>")
    lines.append(
        f"<summary>Full US S&amp;P 500 Top 10 for {latest_window} "
        "(Cautious Variant &amp; Rule 6 Watchlist)</summary>"
    )
    lines.append("")
    lines.append(
        "| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return | Top 3 Buy |"
    )
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: |")
    for item in latest_ranking[:10]:
        lines.append(
            f"| #{item.rank} | {item.ticker} | {item.name} | {item.sector or '—'} | "
            f"{_format_pct(item.return_3y_pct)} | {_format_pct(item.return_3m_pct)} | "
            f"{'Yes' if item.rank <= 3 else 'No'} |"
        )
    lines.append("")
    lines.append("</details>")
    lines.append("")

    if global_summary and global_summary.get("ftse100", {}).get("top5"):
        ftse = global_summary["ftse100"]
        ft_top5 = ftse["top5"]
        lines.append(
            f"- **UK FTSE 100 Top 3 ({ftse.get('latest_window', latest_window)}):** "
            + ", ".join(
                f"**{r['ticker']}** ({r['name']}, `{_format_pct(r['return_3y_pct'])}` 3Y)"
                for r in ft_top5[:3]
            )
            + " — see Deep Dive 3 below."
        )
        lines.append("")


def _render_deep_dive_sections(
    lines: list[str],
    *,
    summary: dict[str, Any],
    variants: dict[str, BacktestResult],
    sensitivity: dict[str, BacktestResult],
    subperiods: list[SubperiodRow],
    latest_ranking: list[RankedSecurity],
    history_by_window: list[tuple[str, str, int, list[RankedSecurity]]],
    holdings: list[Holding],
    rule6_recs: list[dict[str, Any]],
    global_summary: dict[str, Any] | None,
    has_comparison_chart: bool,
    has_benchmark_relative_chart: bool,
    ftse_history: list[tuple[str, str, list[RankedSecurity]]] | None,
    acwi_uk_history: list[tuple[str, str, list[RankedSecurity]]] | None,
    us_alloc_std: dict[str, Any] | None,
    global_alloc: dict[str, Any] | None,
    funding_comparison: dict[str, Any] | None,
) -> None:
    latest_window = summary["latest_window"]
    contribution = summary["monthly_contribution_gbp"]
    fee_pct = summary["fee_pct"]

    lines.append("## Guide to the Charts & Deep-Dive Reports")
    lines.append("")
    lines.append("| Chart File | What It Answers |")
    lines.append("| :--- | :--- |")
    lines.append(
        "| [`assets/hero_vs_sp500.png`](assets/hero_vs_sp500.png) | "
        "**The big picture:** how much `$100/mo` grows to vs. S&P 500 & ACWI trackers |"
    )
    if has_benchmark_relative_chart:
        lines.append(
            f"| [`{BENCHMARK_RELATIVE_CHART}`]({BENCHMARK_RELATIVE_CHART}) | "
            "How far each Top 3 strategy finished ahead of or behind its own benchmark |"
        )
    if has_comparison_chart:
        lines.append(
            "| [`assets/performance_markets_comparison.png`]"
            "(assets/performance_markets_comparison.png) | "
            "**Head-to-head markets:** US, All World UK ISA, Full ACWI & UK FTSE 100 since 2017 |"
        )
    lines.append(
        "| [`assets/performance*.png`](assets/performance.png) | "
        "**Variant comparison:** Top 1 / Top 3 / Rule 6 / Top 5 / Top 10 TWR curves + drawdowns |"
    )
    if us_alloc_std is not None:
        lines.append(
            "| [`assets/allocation_*.png`](assets/allocation_sp500.png) | "
            "**What you end up owning:** how portfolio `%` weights concentrate over time |"
        )
    if funding_comparison:
        lines.append(
            "| [`assets/funding_comparison_sp500.png`](assets/funding_comparison_sp500.png) | "
            "**DCA vs. Lump Sum:** why dropping `$10k` on Day 1 concentrates holdings far more |"
        )
    lines.append("")

    if has_benchmark_relative_chart:
        lines.append(f"![Top 3 strategies vs. their own benchmarks]({BENCHMARK_RELATIVE_CHART})")
        lines.append("")
        lines.append(
            "All lines use the same months. The chart divides each portfolio's cumulative "
            "growth factor by its benchmark's, using time-weighted returns. "
            "For example, a strategy up 20% against a benchmark up 10% sits at +9.1% "
            "(1.20 ÷ 1.10 − 1)."
        )
        lines.append("")

    if has_comparison_chart and global_summary:
        acwi_uk = global_summary.get("acwi_uk_accessible", {})
        acwi_all = global_summary.get("acwi_all", {})
        ftse = global_summary.get("ftse100", {})
        us_std = variants["Standard (Top 3)"].metrics

        lines.append(
            "![Cross-Market Performance Comparison](assets/performance_markets_comparison.png)"
        )
        lines.append("")
        lines.append(
            f"| Universe | Top 3 Picks (`{latest_window}`) | Window | "
            "Top 3 XIRR | Top 3 TWR CAGR | Max Drawdown |"
        )
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
        us_p = ", ".join(f"**{r.ticker}**" for r in latest_ranking[:3])
        lines.append(
            f"| US S&P 500 (`{summary['priced_tickers_count']}` stocks) | {us_p} | "
            f"{summary['backtest_start_window']}..{latest_window} | "
            f"{_format_plain_pct(us_std.xirr_pct)} | {_format_plain_pct(us_std.twr_cagr_pct)} | "
            f"{us_std.max_drawdown_pct:.1f}% |"
        )
        if acwi_uk:
            au_p = ", ".join(f"**{r['ticker']}**" for r in acwi_uk.get("top3", []))
            au_s = acwi_uk.get("variants", {}).get("Standard (Top 3)", {})
            au_x = _format_plain_pct(au_s.get("xirr_pct"))
            au_twr = _format_plain_pct(au_s.get("twr_cagr_pct"))
            lines.append(
                f"| All World — UK-Accessible ACWI (`{acwi_uk.get('universe_size', 0)}`) | "
                f"{au_p} | {acwi_uk.get('start_window')}..{acwi_uk.get('latest_window')} | "
                f"{au_x} | {au_twr} | {au_s.get('max_drawdown_pct', 0.0):.1f}% |"
            )
        if acwi_all:
            aa_p = ", ".join(f"**{r['ticker']}**" for r in acwi_all.get("top3", []))
            aa_s = acwi_all.get("variants", {}).get("Standard (Top 3)", {})
            aa_x = _format_plain_pct(aa_s.get("xirr_pct"))
            aa_twr = _format_plain_pct(aa_s.get("twr_cagr_pct"))
            lines.append(
                f"| All World — Full ACWI (`{acwi_all.get('universe_size', 0)}`) | "
                f"{aa_p} | {acwi_all.get('start_window')}..{acwi_all.get('latest_window')} | "
                f"{aa_x} | {aa_twr} | {aa_s.get('max_drawdown_pct', 0.0):.1f}% |"
            )
        if ftse:
            f_p = ", ".join(f"**{r['ticker']}**" for r in ftse.get("top5", [])[:3])
            f_s = ftse.get("variants", {}).get("Standard (Top 3)", {})
            f_x = _format_plain_pct(f_s.get("xirr_pct"))
            f_twr = _format_plain_pct(f_s.get("twr_cagr_pct"))
            lines.append(
                f"| UK FTSE 100 (`{ftse.get('universe_size', 0)}`) | "
                f"{f_p} | {ftse.get('start_window')}..{ftse.get('latest_window')} | "
                f"{f_x} | {f_twr} | {f_s.get('max_drawdown_pct', 0.0):.1f}% |"
            )
        lines.append("")

    # Deep Dive 1: US S&P 500
    lines.append("<details>")
    lines.append(
        "<summary>Deep Dive 1 — US S&amp;P 500 (20-Year Survivorship-Aware Backtest, "
        f"{summary['backtest_start_window']}..{latest_window})</summary>"
    )
    lines.append("")
    lines.append("![Monthly Momentum Performance](assets/performance.png)")
    lines.append("")
    lines.append(
        f"Monthly £{contribution:,.0f} DCA simulation across **{summary['windows_count']}** "
        f"windows (**{summary['backtest_start_window']}** to **{latest_window}**, "
        f"`£{summary['total_contributed_gbp']:,.0f}` invested, `{fee_pct:.2f}%` US FX fee vs "
        "`0.00%` `^SP500TR`):"
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
            f"{_format_plain_pct(std_m.benchmark_twr_cagr_pct)} | "
            f"{bench_dd} | Cap-weighted | Baseline |"
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
            f"histories (`weib08/Stocks-Daily-Price` + Yahoo Finance, "
            f"`{summary['priced_tickers_count']}` active and delisted tickers; OTC bankruptcy "
            "tickers such as `LEHMQ`, `BSC`, `SIVB`, and `FRC` are absent). See "
            "[docs/research.md](docs/research.md)."
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
                f"{_format_plain_pct(sp.top1_xirr_pct)} | {_format_plain_pct(sp.top3_xirr_pct)} | "
                f"{_format_plain_pct(sp.top5_xirr_pct)} | {_format_plain_pct(sp.top10_xirr_pct)} | "
                f"{_format_plain_pct(sp.benchmark_xirr_pct)} |"
            )
        lines.append("")

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
    lines.append("### US Model Portfolio & Rule 6 Faded-Winner Status")
    lines.append("")
    lines.append(
        f"- **Active model positions (Standard Top 3 + Rule 6):** `{len(active_holdings)}` "
        "([`data/model_holdings.csv`](data/model_holdings.csv))."
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

    lines.append("### US S&P 500 — Latest 12 Monthly Windows")
    lines.append("")
    lines.append(
        "| Window | Signal Data | Top 3 (Standard Equal Split) | Top 1 | Ranks 4–10 | Eligible |"
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
            f"<summary>Full US S&amp;P 500 Pick History ({len(rev_windows)} windows: "
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

    lines.append("</details>")
    lines.append("")

    # Deep Dive 2: All World (MSCI ACWI)
    if global_summary and global_summary.get("acwi_uk_accessible"):
        acwi_uk = global_summary["acwi_uk_accessible"]
        acwi_all = global_summary.get("acwi_all", {})
        uk_cnt = acwi_uk.get("universe_size", 0)
        all_cnt = acwi_all.get("universe_size", 0)
        lines.append("<details>")
        lines.append(
            "<summary>Deep Dive 2 — All World (iShares MSCI ACWI: "
            f"UK ISA `{uk_cnt}` vs Full `{all_cnt}`)</summary>"
        )
        lines.append("")
        lines.append(
            f"Built from **iShares MSCI ACWI ETF** holdings (`{all_cnt}` global "
            f"equities converted to USD). `{uk_cnt}` stocks trade on UK retail "
            "Stocks & Shares ISA exchanges (US, UK, Canada, Western Europe/Nordics)."
        )
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
                f"`{all_cnt}` equities)"
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
            lines.append(
                "| Rank | Ticker | Company | Location | Exchange | "
                "3Y Return (USD) | 3M Return (USD) | UK ISA Accessible |"
            )
            lines.append("| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :--- |")
            for item in acwi_all.get("top15", []):
                acc_badge = "Yes" if item["uk_accessible"] else f"**No** — {item['uk_access_note']}"
                lines.append(
                    f"| #{item['rank']} | {item['ticker']} | {item['name']} | {item['location']} | "
                    f"{item['exchange']} | {_format_pct(item['return_3y_usd_pct'])} | "
                    f"{_format_pct(item['return_3m_usd_pct'])} | {acc_badge} |"
                )
            lines.append("")

        lines.append("</details>")
        lines.append("")

    # Deep Dive 3: UK FTSE 100
    if global_summary and global_summary.get("ftse100", {}).get("top5"):
        ftse = global_summary["ftse100"]
        f_win = ftse.get("latest_window", latest_window)
        lines.append("<details>")
        lines.append(
            f"<summary>Deep Dive 3 — UK Market (FTSE 100 · GBP with 0.50% Stamp Duty, "
            f"{f_win})</summary>"
        )
        lines.append("")
        lines.append(
            f"Evaluated across `{ftse.get('universe_size', 0)}` FTSE 100 constituents "
            f"(`{ftse.get('latest_eligible_count', 0)}` eligible in {f_win}, `0.50%` stamp duty "
            "on buys / `0%` on sells)."
        )
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
        ftse_top10 = ftse.get("top10", ftse["top5"])
        lines.append(f"### FTSE 100 Top 10 ({f_win})")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return | Top 3 Buy |"
        )
        lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: |")
        for item in ftse_top10[:10]:
            sec = item.get("sector") or "—"
            r3y = _format_pct(item["return_3y_pct"])
            r3m = _format_pct(item["return_3m_pct"])
            buy_flag = "Yes" if item["rank"] <= 3 else "No"
            lines.append(
                f"| #{item['rank']} | {item['ticker']} | {item['name']} | {sec} | "
                f"{r3y} | {r3m} | {buy_flag} |"
            )
        lines.append("")
        if ftse_history:
            _render_window_history_tables(
                lines,
                ftse_history,
                heading="UK FTSE 100 — Latest 12 Monthly Windows",
                full_label="Full FTSE 100 Monthly Pick History",
            )
        lines.append("</details>")
        lines.append("")

    # Deep Dive 4: Portfolio Composition & Concentration
    if us_alloc_std is not None:
        lines.append("<details>")
        lines.append(
            "<summary>Deep Dive 4 — Portfolio Composition Over Time "
            "(% Weights &amp; Concentration)</summary>"
        )
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
        lines.append("</details>")
        lines.append("")

    # Deep Dive 5: Funding Schedule Impact
    if funding_comparison:
        lines.append("<details>")
        lines.append(
            "<summary>Deep Dive 5 — Funding Schedule Impact: Monthly DCA ($100/mo) "
            "vs. Day-1 Lump Sum ($10,000)</summary>"
        )
        lines.append("")
        lines.append(
            "- **Monthly DCA is scale-invariant in percentage terms:** Investing `$100/mo` vs "
            "`£500/mo` produces the exact same monthly `%` portfolio weights, XIRR, and TWR CAGR "
            "(totals scale `5x`)."
        )
        lines.append(
            "- **Day-1 lump sums reshape portfolio concentration:** Starting with `$10,000` "
            "(or `£10,000`) invests `100x` a monthly tranche into Month 1's Top 3 and holds "
            "those early winners unless Rule 6 trims stagnant names."
        )
        lines.append(
            "- **Rebased TWR Index vs. Lump Sum:** Variant charts plot the **rebased TWR index** "
            "(`start = 10,000`) of the monthly DCA portfolio rather than a Day-1 lump-sum account."
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
                lines.append(
                    f"| {m_label} | {s_label} | {sym}{sc['total_contributed']:,.0f} | "
                    f"{sym}{sc['ending_value']:,.0f} | {_format_plain_pct(sc.get('xirr_pct'))} | "
                    f"{float(sc['max_drawdown_pct']):.1f}% | {n_act} | {eff_n:.1f} | "
                    f"**{top1_t}** ({top1_w:.1f}%) |"
                )
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
    has_benchmark_relative_chart: bool = False,
    ftse_history: list[tuple[str, str, list[RankedSecurity]]] | None = None,
    acwi_uk_history: list[tuple[str, str, list[RankedSecurity]]] | None = None,
    us_alloc_std: dict[str, Any] | None = None,
    global_alloc: dict[str, Any] | None = None,
    funding_comparison: dict[str, Any] | None = None,
    hero_stats: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    _render_picks_overview(lines, summary, global_summary)
    _render_hero_and_takeaways(
        lines,
        summary=summary,
        variants=variants,
        global_summary=global_summary,
        us_alloc_std=us_alloc_std,
        global_alloc=global_alloc,
        hero_stats=hero_stats,
    )
    _render_option_guide(
        lines,
        summary=summary,
        variants=variants,
        global_summary=global_summary,
        hero_stats=hero_stats,
    )
    _render_how_it_works(lines)
    _render_latest_picks_section(
        lines,
        summary=summary,
        latest_ranking=latest_ranking,
        global_summary=global_summary,
    )
    _render_deep_dive_sections(
        lines,
        summary=summary,
        variants=variants,
        sensitivity=sensitivity,
        subperiods=subperiods,
        latest_ranking=latest_ranking,
        history_by_window=history_by_window,
        holdings=holdings,
        rule6_recs=rule6_recs,
        global_summary=global_summary,
        has_comparison_chart=has_comparison_chart,
        has_benchmark_relative_chart=has_benchmark_relative_chart,
        ftse_history=ftse_history,
        acwi_uk_history=acwi_uk_history,
        us_alloc_std=us_alloc_std,
        global_alloc=global_alloc,
        funding_comparison=funding_comparison,
    )
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
    *,
    picks_updated_on: date | None = None,
) -> PublicReportSummary:
    """Deterministically build rankings, model holdings, charts, and README offline."""
    data_dir = root_dir / "data"
    history_const_path = data_dir / "constituents_history.csv"
    active_const_path = data_dir / "constituents.csv"
    constituents_path = history_const_path if history_const_path.exists() else active_const_path
    prices_path = data_dir / "monthly_prices.csv"
    snapshots_path = data_dir / "constituent_snapshots.csv"
    events_path = data_dir / "events.csv"
    summary_json_path = data_dir / "summary.json"

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

    if picks_updated_on is not None:
        summary_payload["picks_updated_on"] = picks_updated_on.isoformat()
    elif summary_json_path.exists():
        # An offline rebuild keeps the recorded date for the same picks window.
        try:
            previous = json.loads(summary_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None
        if (
            isinstance(previous, dict)
            and previous.get("latest_window") == latest_pt.window_month
            and previous.get("picks_updated_on")
        ):
            summary_payload["picks_updated_on"] = previous["picks_updated_on"]

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
    g_res: Any = None
    global_const = data_dir / "global" / "constituents.csv"
    global_prices = data_dir / "global" / "monthly_prices.csv"
    has_comparison_chart = False
    has_benchmark_relative_chart = False
    ftse_history: list[tuple[str, str, list[RankedSecurity]]] | None = None
    acwi_uk_history: list[tuple[str, str, list[RankedSecurity]]] | None = None

    if global_const.exists() and global_prices.exists():
        from monthly_momentum.markets import build_global_reports

        g_res = build_global_reports(root_dir=root_dir, contribution=contribution)
        global_summary_dict = json.loads(g_res.summary_json_path.read_text(encoding="utf-8"))

        global_dir = data_dir / "global"
        market_sources = (
            ("US S&P 500 (Top 3)", performance_csv_path, "S&P 500 TR (^SP500TR)"),
            (
                "All World — UK-Accessible ACWI (Top 3)",
                global_dir / "performance_acwi_uk_accessible.csv",
                "MSCI ACWI ETF (ACWI)",
            ),
            (
                "All World — Full ACWI (Top 3)",
                global_dir / "performance_acwi.csv",
                "MSCI ACWI ETF (ACWI)",
            ),
            (
                "UK FTSE 100 (Top 3)",
                global_dir / "performance_ftse100.csv",
                "FTSE 100 TR (ISF.L)",
            ),
        )
        strategy_series: dict[str, list[tuple[date, float]]] = {}
        benchmarks_by_market: dict[str, list[tuple[date, float]]] = {}
        bench_series: dict[str, list[tuple[date, float]]] = {}
        for market, path, benchmark in market_sources:
            if points := _load_nav_series_from_perf_csv(path):
                strategy_series[market] = points
            if points := _load_nav_series_from_perf_csv(path, "benchmark_nav"):
                benchmarks_by_market[market] = points
                bench_series[benchmark] = points

        if len(strategy_series) >= 2:
            generate_markets_comparison_chart(
                strategy_series,
                bench_series,
                root_dir / "assets" / "performance_markets_comparison.png",
            )
            has_comparison_chart = True

        relative_series = benchmark_relative_series(strategy_series, benchmarks_by_market)
        if len(relative_series) >= 2:
            generate_benchmark_relative_chart(relative_series, root_dir / BENCHMARK_RELATIVE_CHART)
            has_benchmark_relative_chart = True

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

    scale_to_100 = (100.0 / contribution) if contribution > 0.0 else 1.0
    us_full_points: list[dict[str, Any]] = [
        {
            "d": pt.dt,
            "window_month": pt.window_month,
            "cash": pt.contributed_cum * scale_to_100,
            "strategy": pt.portfolio_value * scale_to_100,
            "sp500": (
                pt.benchmark_value * scale_to_100 if pt.benchmark_value is not None else None
            ),
        }
        for pt in std_res.points
    ]

    common_9y_chart: dict[str, Any] | None = None
    common_9y_stats: dict[str, Any] | None = None
    if global_summary_dict and global_summary_dict.get("acwi_uk_accessible") and g_res is not None:
        acwi_uk_std = g_res.global_variants.get("Standard (Top 3)")
        if acwi_uk_std and acwi_uk_std.points:
            uk_pts = acwi_uk_std.points
            acwi_start_win = uk_pts[0].window_month
            acwi_end_win = uk_pts[-1].window_month
            uk_dates = [pt.dt for pt in uk_pts]
            uk_vals = [pt.portfolio_value * scale_to_100 for pt in uk_pts]
            uk_cash = [pt.contributed_cum * scale_to_100 for pt in uk_pts]
            uk_xirr = acwi_uk_std.metrics.xirr_pct

            common_9y_chart = {
                "start_window": acwi_start_win,
                "end_window": acwi_end_win,
                "acwi_uk": {
                    "dates": uk_dates,
                    "values": uk_vals,
                    "cash": uk_cash,
                    "xirr_pct": uk_xirr,
                },
            }
            common_9y_stats = {
                "start_window": acwi_start_win,
                "end_window": acwi_end_win,
                "acwi_uk": {
                    "ending_value": uk_vals[-1],
                    "xirr_pct": uk_xirr or 0.0,
                },
            }

            acwi_bench_pts = [
                (pt.dt, pt.benchmark_value * scale_to_100)
                for pt in uk_pts
                if pt.benchmark_value is not None
            ]
            if acwi_bench_pts:
                ab_xirr = acwi_uk_std.metrics.benchmark_xirr_pct
                common_9y_chart["acwi_bench"] = {
                    "dates": [d for d, _ in acwi_bench_pts],
                    "values": [v for _, v in acwi_bench_pts],
                    "xirr_pct": ab_xirr,
                }
                common_9y_stats["acwi_bench"] = {
                    "ending_value": acwi_bench_pts[-1][1],
                    "xirr_pct": ab_xirr or 0.0,
                }

            try:
                us_common_res = run_backtest(
                    dataset,
                    BacktestConfig(
                        start_month=acwi_start_win,
                        end_month=acwi_end_win,
                        monthly_contribution=100.0,
                        top_n=3,
                        rule6_enabled=False,
                        fee_pct=fee_pct,
                        sell_fee_pct=fee_pct,
                        benchmark_fee_pct=0.0,
                        signal_mode="next_month",
                    ),
                )
            except ValueError:
                us_common_res = None

            if us_common_res is not None and us_common_res.points:
                u9_pts = us_common_res.points
                u9_xirr = us_common_res.metrics.xirr_pct
                common_9y_chart["us_top3"] = {
                    "dates": [pt.dt for pt in u9_pts],
                    "values": [pt.portfolio_value for pt in u9_pts],
                    "xirr_pct": u9_xirr,
                }
                common_9y_stats["us_top3"] = {
                    "ending_value": u9_pts[-1].portfolio_value,
                    "xirr_pct": u9_xirr or 0.0,
                }
                sp9_pts = [
                    (pt.dt, pt.benchmark_value) for pt in u9_pts if pt.benchmark_value is not None
                ]
                if sp9_pts:
                    sp9_xirr = us_common_res.metrics.benchmark_xirr_pct
                    common_9y_chart["sp500"] = {
                        "dates": [d for d, _ in sp9_pts],
                        "values": [v for _, v in sp9_pts],
                        "xirr_pct": sp9_xirr,
                    }
                    common_9y_stats["sp500"] = {
                        "ending_value": sp9_pts[-1][1],
                        "xirr_pct": sp9_xirr or 0.0,
                    }

    generate_hero_vs_sp500_chart(
        us_full_points,
        root_dir / "assets" / "hero_vs_sp500.png",
        us_full_xirr_pct=std_metrics.xirr_pct,
        sp500_full_xirr_pct=std_metrics.benchmark_xirr_pct,
        common_9y=common_9y_chart,
        monthly_amount=100.0,
        currency_symbol="$",
    )
    hero_stats_payload: dict[str, Any] | None = (
        {"common_9y": common_9y_stats} if common_9y_stats is not None else None
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
        has_benchmark_relative_chart=has_benchmark_relative_chart,
        ftse_history=ftse_history,
        acwi_uk_history=acwi_uk_history,
        us_alloc_std=us_alloc_std,
        global_alloc=global_alloc_dict,
        funding_comparison=funding_comparison_payload,
        hero_stats=hero_stats_payload,
    )
    _update_readme_file(readme_path, readme_block)
    summary_json_path.write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")

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
