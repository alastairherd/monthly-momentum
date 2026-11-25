"""Performance chart rendering using headless Matplotlib."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def _compute_drawdown_pct(navs: Sequence[float]) -> list[float]:
    peak = 0.0
    out: list[float] = []
    for v in navs:
        if v > peak:
            peak = v
        out.append(((v / peak) - 1.0) * 100.0 if peak > 0.0 else 0.0)
    return out


def _make_currency_formatter(symbol: str) -> mticker.FuncFormatter:
    def _fmt(val: float, _pos: Any) -> str:
        if val >= 1_000_000:
            return f"{symbol}{val / 1_000_000:.1f}M"
        if val >= 1_000:
            return f"{symbol}{val:,.0f}"
        return f"{symbol}{val:.0f}"

    return mticker.FuncFormatter(_fmt)


def generate_performance_chart(
    performance_rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    output_path: Path,
    *,
    title: str = "Monthly Index Momentum vs S&P 500 Total Return",
    subtitle: str | None = None,
    benchmark_label: str = "S&P 500 Total Return (^SP500TR)",
    benchmark_short_label: str = "S&P 500 TR",
    currency_symbol: str = "£",
    footer_note: str | None = None,
) -> Path:
    """Render a dual-panel TWR growth and drawdown comparison PNG chart."""
    if not performance_rows:
        raise ValueError("Cannot generate performance chart from empty performance rows.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dates = [date.fromisoformat(str(r["date"])) for r in performance_rows]
    dates_num: Any = mdates.date2num(dates)
    top1_growth = [float(r["top1_nav"]) * 10_000.0 for r in performance_rows]
    top3_growth = [float(r["top3_nav"]) * 10_000.0 for r in performance_rows]
    top3_r6_growth = [float(r["top3_rule6_nav"]) * 10_000.0 for r in performance_rows]
    has_top5 = all(r.get("top5_nav") not in (None, "") for r in performance_rows)
    top5_growth = [float(r["top5_nav"]) * 10_000.0 for r in performance_rows] if has_top5 else []
    top10_growth = [float(r["top10_nav"]) * 10_000.0 for r in performance_rows]

    has_bench = all(r.get("benchmark_nav") not in (None, "") for r in performance_rows)
    bench_growth = (
        [float(r["benchmark_nav"]) * 10_000.0 for r in performance_rows] if has_bench else []
    )

    top1_dd = _compute_drawdown_pct([float(r["top1_nav"]) for r in performance_rows])
    top3_dd = _compute_drawdown_pct([float(r["top3_nav"]) for r in performance_rows])
    bench_dd = (
        _compute_drawdown_pct([float(r["benchmark_nav"]) for r in performance_rows])
        if has_bench
        else []
    )

    fig = plt.figure(figsize=(11.8, 7.4), dpi=180, facecolor="#ffffff")
    gs = fig.add_gridspec(2, 1, height_ratios=[2.15, 1.05], hspace=0.16)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    for ax in (ax_top, ax_bot):
        ax.set_facecolor("#ffffff")
        ax.grid(True, which="major", linestyle="-", linewidth=0.6, color="#e2e8f0", alpha=0.9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.tick_params(colors="#334155", labelsize=9.5)

    # Top panel: Time-weighted growth of 10,000.
    ax_top.plot(
        dates_num,
        top3_growth,
        color="#2563eb",
        linewidth=2.4,
        label=f"Standard (Top 3) — {currency_symbol}{top3_growth[-1]:,.0f}",
        zorder=5,
    )
    ax_top.plot(
        dates_num,
        top3_r6_growth,
        color="#7c3aed",
        linewidth=1.5,
        linestyle="-.",
        label=f"Top 3 + Rule 6 — {currency_symbol}{top3_r6_growth[-1]:,.0f}",
        zorder=6,
    )
    if top5_growth:
        ax_top.plot(
            dates_num,
            top5_growth,
            color="#0891b2",
            linewidth=1.8,
            label=f"Balanced (Top 5) — {currency_symbol}{top5_growth[-1]:,.0f}",
            zorder=4,
        )
    ax_top.plot(
        dates_num,
        top10_growth,
        color="#059669",
        linewidth=1.8,
        label=f"Cautious (Top 10) — {currency_symbol}{top10_growth[-1]:,.0f}",
        zorder=3,
    )
    ax_top.plot(
        dates_num,
        top1_growth,
        color="#d97706",
        linewidth=1.4,
        linestyle=":",
        alpha=0.95,
        label=f"Aggressive (Top 1) — {currency_symbol}{top1_growth[-1]:,.0f}",
        zorder=2,
    )
    if bench_growth:
        ax_top.plot(
            dates_num,
            bench_growth,
            color="#475569",
            linewidth=2.0,
            linestyle="--",
            label=f"{benchmark_label} — {currency_symbol}{bench_growth[-1]:,.0f}",
            zorder=3,
        )

    all_vals = (
        top1_growth + top3_growth + top3_r6_growth + top5_growth + top10_growth + bench_growth
    )
    max_val = max(all_vals)
    min_val = max(1.0, min(all_vals))
    formatter = _make_currency_formatter(currency_symbol)
    if max_val / min_val >= 8.0:
        ax_top.set_yscale("log")
        ax_top.yaxis.set_major_formatter(formatter)
        ax_top.yaxis.set_minor_formatter(mticker.NullFormatter())
    else:
        ax_top.yaxis.set_major_formatter(formatter)

    ax_top.set_ylabel(
        f"Growth of {currency_symbol}10,000 (TWR)",
        fontsize=10,
        color="#1e293b",
        fontweight="bold",
    )
    ax_top.legend(
        loc="upper left",
        frameon=True,
        facecolor="#ffffff",
        edgecolor="#e2e8f0",
        fontsize=8.6,
    )
    plt.setp(ax_top.get_xticklabels(), visible=False)

    # Bottom panel: Drawdowns from peak (%).
    ax_bot.fill_between(dates_num, top3_dd, 0.0, color="#2563eb", alpha=0.14)
    ax_bot.plot(dates_num, top3_dd, color="#2563eb", linewidth=1.7, label="Standard (Top 3)")
    ax_bot.plot(
        dates_num,
        top1_dd,
        color="#d97706",
        linewidth=1.2,
        linestyle=":",
        label="Aggressive (Top 1)",
    )
    if bench_dd:
        ax_bot.plot(
            dates_num,
            bench_dd,
            color="#475569",
            linewidth=1.5,
            linestyle="--",
            label=benchmark_short_label,
        )
    ax_bot.axhline(
        -60.0,
        color="#dc2626",
        linewidth=0.9,
        linestyle="--",
        alpha=0.65,
    )
    ax_bot.text(
        float(dates_num[0]),
        -62.5,
        "Rule 8 expectation (−60% to −75%)",
        fontsize=8.2,
        color="#b91c1c",
        va="top",
    )

    min_dd = min(min(top1_dd), min(top3_dd), min(bench_dd) if bench_dd else 0.0, -75.0)
    ax_bot.set_ylim(max(-100.0, min_dd - 6.0), 3.0)
    ax_bot.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_bot.set_ylabel("Drawdown (%)", fontsize=10, color="#1e293b", fontweight="bold")
    ax_bot.legend(
        loc="lower left",
        ncol=3,
        frameon=True,
        facecolor="#ffffff",
        edgecolor="#e2e8f0",
        fontsize=8.3,
    )

    ax_bot.xaxis_date()
    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    ax_bot.xaxis.set_major_locator(locator)
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    start_win = summary.get("backtest_start_window", summary.get("start_window", ""))
    end_win = summary.get("latest_window", "")
    signal_m = summary.get("latest_signal_month", "")
    fee_pct = summary.get("fee_pct", 0.15)
    survivorship_aware = not bool(summary.get("survivorship_warning", True))

    fig.suptitle(
        title,
        fontsize=14,
        fontweight="bold",
        color="#0f172a",
        y=0.97,
    )
    if subtitle is None:
        scope_tag = "S&P 500 (Historical Membership)" if survivorship_aware else "S&P 500"
        sig_part = f" (signal: {signal_m})" if signal_m else ""
        subtitle = (
            f"{scope_tag} · Windows {start_win} to {end_win}{sig_part} · "
            f"3Y TR ranked, 3M >= 0% · {fee_pct:.2f}% US FX fee"
        )
    ax_top.set_title(subtitle, fontsize=9.6, color="#475569", pad=10)

    if footer_note is None:
        footer_note = (
            "Mechanistic run on public S&P 500 data "
            "(fja05680 membership + weib08 + Yahoo Finance). Not financial advice."
            if survivorship_aware
            else "Mechanistic run on public S&P 500 data "
            "(Wikipedia constituents & date_added + Yahoo Finance). Not financial advice."
        )
    fig.text(0.5, 0.012, footer_note, ha="center", fontsize=8.1, color="#64748b")

    fig.subplots_adjust(left=0.09, right=0.97, top=0.89, bottom=0.085)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def generate_markets_comparison_chart(
    strategy_series: Mapping[str, Sequence[tuple[date, float]]],
    benchmark_series: Mapping[str, Sequence[tuple[date, float]]],
    output_path: Path,
    *,
    title: str = "Cross-Market Monthly Momentum Comparison (Standard Top 3, Rebased)",
    footer_note: str = (
        "All curves rebased to 10,000 at common start month (TWR). "
        "Non-US & ACWI universes reflect current holdings (survivorship-biased). "
        "Not financial advice."
    ),
) -> Path:
    """Render a side-by-side comparison PNG across US, All-World ACWI, and UK FTSE 100."""
    non_empty = {lbl: list(pts) for lbl, pts in strategy_series.items() if pts}
    if not non_empty:
        raise ValueError("Cannot render comparison chart without at least one strategy series.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    common_start = max(pts[0][0] for pts in non_empty.values())

    palette = [
        ("#2563eb", "-"),
        ("#0891b2", "-"),
        ("#7c3aed", "-."),
        ("#059669", "-"),
    ]
    bench_palette = [
        ("#475569", "--"),
        ("#0f766e", ":"),
        ("#94a3b8", "--"),
    ]

    def _rebase(pts: Sequence[tuple[date, float]]) -> tuple[list[date], list[float]]:
        sliced = [(d, v) for d, v in pts if d >= common_start and v > 0.0]
        if not sliced:
            sliced = [(d, v) for d, v in pts if v > 0.0]
        base = sliced[0][1]
        return [d for d, _ in sliced], [(v / base) * 10_000.0 for _, v in sliced]

    fig = plt.figure(figsize=(11.8, 7.4), dpi=180, facecolor="#ffffff")
    gs = fig.add_gridspec(2, 1, height_ratios=[2.15, 1.05], hspace=0.16)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    for ax in (ax_top, ax_bot):
        ax.set_facecolor("#ffffff")
        ax.grid(True, which="major", linestyle="-", linewidth=0.6, color="#e2e8f0", alpha=0.9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.tick_params(colors="#334155", labelsize=9.5)

    all_growth: list[float] = []
    all_dds: list[float] = []
    max_end = common_start

    for idx, (lbl, pts) in enumerate(non_empty.items()):
        color, ls = palette[idx % len(palette)]
        ds, vals = _rebase(pts)
        dds = _compute_drawdown_pct(vals)
        all_growth.extend(vals)
        all_dds.extend(dds)
        if ds[-1] > max_end:
            max_end = ds[-1]
        dnums: Any = mdates.date2num(ds)
        ax_top.plot(
            dnums,
            vals,
            color=color,
            linewidth=2.2 if idx < 2 else 1.8,
            linestyle=ls,
            label=f"{lbl} — {vals[-1]:,.0f}",
            zorder=5 - idx,
        )
        ax_bot.plot(dnums, dds, color=color, linewidth=1.6, linestyle=ls, label=lbl)

    for idx, (lbl, b_pts) in enumerate(benchmark_series.items()):
        if not b_pts:
            continue
        color, ls = bench_palette[idx % len(bench_palette)]
        ds, vals = _rebase(b_pts)
        dds = _compute_drawdown_pct(vals)
        all_growth.extend(vals)
        all_dds.extend(dds)
        dnums_b: Any = mdates.date2num(ds)
        ax_top.plot(
            dnums_b,
            vals,
            color=color,
            linewidth=1.7,
            linestyle=ls,
            label=f"{lbl} — {vals[-1]:,.0f}",
            zorder=2,
        )
        if idx == 0:
            ax_bot.plot(dnums_b, dds, color=color, linewidth=1.4, linestyle=ls, label=lbl)

    max_v = max(all_growth)
    min_v = max(1.0, min(all_growth))
    idx_fmt = mticker.FuncFormatter(lambda x, _p: f"{x:,.0f}")
    if max_v / min_v >= 8.0:
        ax_top.set_yscale("log")
        ax_top.yaxis.set_major_formatter(idx_fmt)
        ax_top.yaxis.set_minor_formatter(mticker.NullFormatter())
    else:
        ax_top.yaxis.set_major_formatter(idx_fmt)

    ax_top.set_ylabel("Rebased TWR Index (Start = 10,000)", fontsize=10, fontweight="bold")
    ax_top.legend(
        loc="upper left",
        frameon=True,
        facecolor="#ffffff",
        edgecolor="#e2e8f0",
        fontsize=8.4,
    )
    plt.setp(ax_top.get_xticklabels(), visible=False)

    min_dd = min(min(all_dds) if all_dds else 0.0, -55.0)
    ax_bot.set_ylim(max(-100.0, min_dd - 6.0), 3.0)
    ax_bot.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_bot.set_ylabel("Drawdown (%)", fontsize=10, color="#1e293b", fontweight="bold")
    ax_bot.legend(
        loc="lower left",
        ncol=2,
        frameon=True,
        facecolor="#ffffff",
        edgecolor="#e2e8f0",
        fontsize=8.2,
    )

    ax_bot.xaxis_date()
    locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
    ax_bot.xaxis.set_major_locator(locator)
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    fig.suptitle(title, fontsize=13.6, fontweight="bold", color="#0f172a", y=0.97)
    ax_top.set_title(
        f"Common window {common_start.strftime('%Y-%m')} to {max_end.strftime('%Y-%m')} · "
        "US S&P 500 vs All World ACWI (UK-Accessible & Full) vs UK FTSE 100",
        fontsize=9.6,
        color="#475569",
        pad=10,
    )
    fig.text(0.5, 0.012, footer_note, ha="center", fontsize=8.0, color="#64748b")

    fig.subplots_adjust(left=0.09, right=0.97, top=0.89, bottom=0.085)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path
