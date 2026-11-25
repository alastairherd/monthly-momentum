"""Deterministic offline report, model holdings, chart, and README generator."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from monthly_momentum.backtest.data import BacktestDataset, load_backtest_dataset
from monthly_momentum.backtest.engine import (
    BacktestConfig,
    BacktestResult,
    SubperiodRow,
    compare_variants,
    run_backtest,
    run_subperiod_summary,
)
from monthly_momentum.chart import generate_performance_chart
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
from monthly_momentum.ranking import write_ranking_csv, write_ranking_history_csv

README_START_MARKER = "<!-- AUTO-GENERATED:START -->"
README_END_MARKER = "<!-- AUTO-GENERATED:END -->"


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


def _build_model_holdings(
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


def _write_performance_csv(
    variants: dict[str, BacktestResult],
    path: Path,
) -> list[dict[str, Any]]:
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
        f"(`{summary['constituents_count']}` active constituents · "
        f"`{summary['latest_eligible_count']}` eligible after the 3-year history & non-negative "
        "3-month return filter). Next trading day action: split this month's contribution "
        "equally across **Top 3** (or **Top 5** for Balanced)."
    )
    lines.append("")
    lines.append("### Standard Strategy Picks (Top 3 — Equal 1/3 Split)")
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
        f"<summary>Full Top 10 for {latest_window} (Cautious Variant & Rule 6 Watchlist)</summary>"
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

    lines.append("## Performance Chart (Mechanistic Simulation)")
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

    ordered_names = [
        "Aggressive (Top 1)",
        "Standard (Top 3)",
        "Standard (Top 3 + Rule 6)",
        "Balanced (Top 5)",
        "Balanced (Top 5 + Rule 6)",
        "Cautious (Top 10)",
        "Cautious (Top 10 + Rule 6)",
    ]
    for name in ordered_names:
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

    if global_summary:
        ftse = global_summary.get("ftse100", {})
        gpool = global_summary.get("global_pool", {})
        g_win = gpool.get("latest_window", latest_window)
        lines.append(f"## Multi-Market & Global Developed Pool ({g_win})")
        lines.append("")
        lines.append(
            "Mechanistic international rankings refreshed alongside S&P 500 from Wikipedia + "
            "Yahoo Finance (note: non-US pools use current index constituents and therefore carry "
            "survivorship bias; see [docs/research.md](docs/research.md))."
        )
        lines.append("")
        if gpool.get("top3"):
            lines.append(
                "### Global Developed Pool Top 3 "
                "(US + UK + Canada + Eurozone, USD FX-converted · "
                f"`{gpool.get('universe_size', 0)}` tickers)"
            )
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

        if ftse.get("top5"):
            f_win = ftse.get("latest_window", latest_window)
            lines.append(f"### FTSE 100 Picks ({f_win} · GBP, 0.50% UK Stamp Duty)")
            lines.append("")
            lines.append("| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return |")
            lines.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
            for item in ftse["top5"][:3]:
                lines.append(
                    f"| #{item['rank']} | **{item['ticker']}** | {item['name']} | "
                    f"{item.get('sector') or '—'} | {_format_pct(item['return_3y_pct'])} | "
                    f"{_format_pct(item['return_3m_pct'])} |"
                )
            ftse_std = ftse.get("variants", {}).get("Standard (Top 3)", {})
            if ftse_std:
                f_start = ftse.get("start_window")
                f_end = ftse.get("latest_window")
                f_bench = ftse.get("benchmark_ftse_tr_etf_xirr_pct")
                bench_txt = f" vs `ISF.L` TR ETF `{f_bench}%`" if f_bench is not None else ""
                lines.append("")
                lines.append(
                    f"- FTSE 100 Top 3 DCA ({f_start}..{f_end}): "
                    f"XIRR `{ftse_std.get('xirr_pct')}%`{bench_txt}, "
                    f"TWR CAGR `{ftse_std.get('twr_cagr_pct')}%`, "
                    f"Max Drawdown `{ftse_std.get('max_drawdown_pct')}%`."
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
    lines.append("## Model Portfolio & Rule 6 Faded-Winner Status")
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

    # Mechanistic Picks by Month/Window
    lines.append("## Mechanistic Stock Picks by Month / Window")
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
            f"<summary>Full Monthly Pick History ({len(rev_windows)} windows: "
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
    """Deterministically build rankings, model holdings, performance, chart, and README."""
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
        # Ensure at least 36 months of stock lookback exist before the first active window.
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

    global_summary_dict: dict[str, Any] | None = None
    global_const = data_dir / "global" / "constituents.csv"
    global_prices = data_dir / "global" / "monthly_prices.csv"
    if global_const.exists() and global_prices.exists():
        from monthly_momentum.markets import build_global_reports

        g_res = build_global_reports(root_dir=root_dir, contribution=contribution)
        global_summary_dict = json.loads(g_res.summary_json_path.read_text(encoding="utf-8"))

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

    model_holdings, rule6_recs = _build_model_holdings(std_res, std_r6_res)
    model_holdings_path = data_dir / "model_holdings.csv"
    write_holdings_csv(model_holdings, model_holdings_path)

    performance_csv_path = data_dir / "performance.csv"
    perf_rows = _write_performance_csv(variants, performance_csv_path)

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
