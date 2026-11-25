"""FT-inspired broadsheet editorial performance charts using headless Matplotlib."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Liberation Sans", "DejaVu Sans", "Arial", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# Original stone-ivory broadsheet palette (distinct from FT salmon/claret branding)
PAPER_BG = "#F6F5F0"
INK_DARK = "#181A1F"
INK_SUB = "#525866"
INK_MUTED = "#6E737D"
GRID_COLOR = "#DAD7CE"
SPINE_COLOR = "#9E9B92"
LEADER_COLOR = "#B8B5AC"
EVENT_COLOR = "#7D7A72"

SERIES_COLORS: dict[str, str] = {
    "top3": "#0F5C6E",  # Deep petrol teal (hero)
    "top3_r6": "#7A3E65",  # Muted plum
    "top5": "#2B4590",  # Editorial cobalt
    "top10": "#2E6F40",  # Forest sage
    "top1": "#C45D18",  # Burnt amber
    "bench": "#5E6572",  # Slate graphite
}

COMPARISON_STYLES: list[tuple[str, str, float]] = [
    ("#0F5C6E", "-", 2.4),  # UK-Accessible ACWI / hero
    ("#2B4590", "-", 2.3),  # US S&P 500
    ("#C45D18", "-.", 2.0),  # Full ACWI
    ("#2E6F40", "-", 2.1),  # UK FTSE 100
]

BENCH_COMP_STYLES: list[tuple[str, str, float]] = [
    ("#5E6572", "--", 1.5),
    ("#8B4D2B", ":", 1.5),
    ("#8D939E", "--", 1.3),
]

MACRO_EVENTS: tuple[tuple[date, str], ...] = (
    (date(2008, 9, 1), "2008\nGFC"),
    (date(2020, 3, 1), "Covid\n2020"),
    (date(2022, 1, 1), "2022 rate\nshock"),
)


def _compute_drawdown_pct(navs: Sequence[float]) -> list[float]:
    peak = 0.0
    out: list[float] = []
    for v in navs:
        if v > peak:
            peak = v
        out.append(((v / peak) - 1.0) * 100.0 if peak > 0.0 else 0.0)
    return out


def _format_compact_value(symbol: str, val: float) -> str:
    if val >= 1_000_000:
        return f"{symbol}{val / 1_000_000:.2f}M"
    if val >= 100_000:
        return f"{symbol}{val / 1_000:.1f}k"
    if val >= 10_000:
        return f"{symbol}{val / 1_000:.1f}k"
    return f"{symbol}{val:,.0f}"


def _make_currency_formatter(symbol: str) -> mticker.FuncFormatter:
    def _fmt(val: float, _pos: Any) -> str:
        if val >= 1_000_000:
            return f"{symbol}{val / 1_000_000:.1f}M"
        if val >= 1_000:
            return f"{symbol}{val:,.0f}"
        return f"{symbol}{val:.0f}"

    return mticker.FuncFormatter(_fmt)


def _style_editorial_axis(ax: Any, *, show_bottom: bool = True) -> None:
    ax.set_facecolor(PAPER_BG)
    ax.grid(False)
    ax.yaxis.grid(True, which="major", linestyle="-", linewidth=0.75, color=GRID_COLOR, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    if show_bottom:
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color(SPINE_COLOR)
        ax.spines["bottom"].set_linewidth(0.85)
    else:
        ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", length=0, colors=INK_SUB, labelsize=9.0, pad=5)
    ax.tick_params(
        axis="x",
        length=4 if show_bottom else 0,
        width=0.75,
        color=SPINE_COLOR,
        colors=INK_SUB,
        labelsize=9.0,
        pad=4,
    )


def _draw_top_rule_and_headers(
    fig: Any,
    title: str,
    subtitle: str,
    footer_left: str,
    footer_right: str = "Monthly Momentum · Mechanistic Simulation",
    *,
    left: float = 0.085,
) -> None:
    # Editorial thick black accent rule at top-left
    rule = fig.add_artist(
        plt.Line2D(
            [left, left + 0.055],
            [0.968, 0.968],
            transform=fig.transFigure,
            color=INK_DARK,
            linewidth=4.2,
            solid_capstyle="butt",
        )
    )
    rule.set_zorder(10)
    fig.text(
        left,
        0.946,
        title,
        ha="left",
        va="top",
        fontsize=15.0,
        fontweight="bold",
        color=INK_DARK,
    )
    fig.text(
        left,
        0.903,
        subtitle,
        ha="left",
        va="top",
        fontsize=9.8,
        color=INK_SUB,
    )
    fig.text(
        left,
        0.015,
        footer_left,
        ha="left",
        va="bottom",
        fontsize=8.0,
        color=INK_MUTED,
    )
    fig.text(
        0.985,
        0.015,
        footer_right,
        ha="right",
        va="bottom",
        fontsize=8.0,
        color=INK_MUTED,
    )


def _draw_event_markers(
    ax: Any,
    dates: Sequence[date],
    *,
    label_y_frac: float = 0.96,
) -> None:
    if len(dates) < 6:
        return
    d_min, d_max = dates[0], dates[-1]
    ylim = ax.get_ylim()
    y0, y1 = float(ylim[0]), float(ylim[1])
    use_log = ax.get_yscale() == "log"

    if use_log and y0 > 0.0 and y1 > y0:
        y_text = y0 * ((y1 / y0) ** label_y_frac)
    else:
        y_text = y0 + (y1 - y0) * label_y_frac

    for ev_dt, ev_label in MACRO_EVENTS:
        if (ev_dt - d_min).days < 120 or (d_max - ev_dt).days < 120:
            continue
        x_ev = float(mdates.date2num(ev_dt))
        ax.axvline(
            x_ev,
            color=EVENT_COLOR,
            linewidth=0.85,
            linestyle=(0, (1.5, 2.2)),
            alpha=0.85,
            zorder=1,
        )
        ax.annotate(
            ev_label,
            xy=(x_ev, y_text),
            xytext=(4, 0),
            textcoords="offset points",
            ha="left",
            va="top",
            fontsize=7.7,
            color=INK_MUTED,
            linespacing=1.15,
        )


def _place_direct_labels(
    ax: Any,
    items: Sequence[tuple[float, str, str, int]],
    *,
    min_gap: float = 0.088,
    x_text_axes: float = 1.022,
    font_size: float = 8.6,
) -> None:
    """Place color-matched direct labels on the right margin with collision avoidance.

    Each item is ``(raw_y_value, label_text, color, font_weight_flag)``.
    """
    if not items:
        return

    y0, y1 = float(ax.get_ylim()[0]), float(ax.get_ylim()[1])
    use_log = ax.get_yscale() == "log"

    def _to_frac(v: float) -> float:
        if use_log and y0 > 0.0 and y1 > y0 and v > 0.0:
            return (math.log(v) - math.log(y0)) / (math.log(y1) - math.log(y0))
        if y1 == y0:
            return 0.5
        return (v - y0) / (y1 - y0)

    def _from_frac(f: float) -> float:
        if use_log and y0 > 0.0 and y1 > y0:
            return y0 * ((y1 / y0) ** f)
        return y0 + (y1 - y0) * f

    indexed = sorted(
        [(idx, _to_frac(v), lbl, col, bold) for idx, (v, lbl, col, bold) in enumerate(items)],
        key=lambda x: x[1],
    )
    eff_gap = min(min_gap, 0.90 / max(1, len(indexed)))
    placed = [item[1] for item in indexed]

    # Forward pass upward
    placed[0] = max(0.03, placed[0])
    for i in range(1, len(placed)):
        placed[i] = max(placed[i], placed[i - 1] + eff_gap)

    # Pull downward from top ceiling if needed
    if placed[-1] > 0.97:
        placed[-1] = 0.97
        for i in range(len(placed) - 2, -1, -1):
            placed[i] = min(placed[i], placed[i + 1] - eff_gap)
        if placed[0] < 0.02:
            shift = 0.02 - placed[0]
            for i in range(len(placed)):
                placed[i] = min(0.97, placed[i] + shift)

    trans = ax.get_yaxis_transform()
    x_data_max = float(ax.get_xlim()[1])

    for (orig_f, lbl, col, bold), adj_f in zip(
        [(it[1], it[2], it[3], it[4]) for it in indexed], placed, strict=True
    ):
        y_orig = _from_frac(orig_f)
        y_adj = _from_frac(adj_f)
        if abs(adj_f - orig_f) >= 0.018:
            ax.annotate(
                "",
                xy=(1.016, y_adj),
                xycoords=trans,
                xytext=(x_data_max, y_orig),
                textcoords="data",
                arrowprops={
                    "arrowstyle": "-",
                    "color": LEADER_COLOR,
                    "linewidth": 0.75,
                    "shrinkA": 2,
                    "shrinkB": 2,
                },
                clip_on=False,
            )
        ax.text(
            x_text_axes,
            y_adj,
            lbl,
            transform=trans,
            ha="left",
            va="center",
            fontsize=font_size,
            fontweight="bold" if bold else "normal",
            color=col,
            clip_on=False,
        )


def generate_performance_chart(
    performance_rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    output_path: Path,
    *,
    title: str = "US momentum has outperformed the S&P 500 over 20 years",
    subtitle: str | None = None,
    benchmark_label: str = "S&P 500 Total Return (^SP500TR)",
    benchmark_short_label: str = "S&P 500 TR",
    currency_symbol: str = "£",
    footer_note: str | None = None,
) -> Path:
    """Render a broadsheet-styled dual-panel TWR growth and drawdown PNG chart."""
    if not performance_rows:
        raise ValueError("Cannot generate performance chart from empty performance rows.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    del benchmark_label

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

    fig = plt.figure(figsize=(11.8, 7.3), dpi=180, facecolor=PAPER_BG)
    gs = fig.add_gridspec(2, 1, height_ratios=[2.15, 1.0], hspace=0.28)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    _style_editorial_axis(ax_top, show_bottom=False)
    _style_editorial_axis(ax_bot, show_bottom=True)

    last_x = float(dates_num[-1])
    growth_labels: list[tuple[float, str, str, int]] = []

    def _plot_curve(
        vals: list[float],
        color: str,
        short_name: str,
        *,
        lw: float = 1.9,
        ls: str = "-",
        zorder: int = 3,
        bold: int = 0,
        alpha: float = 1.0,
    ) -> None:
        if not vals:
            return
        ax_top.plot(
            dates_num, vals, color=color, linewidth=lw, linestyle=ls, alpha=alpha, zorder=zorder
        )
        ax_top.plot(
            [last_x],
            [vals[-1]],
            marker="o",
            markersize=4.4 if bold else 3.6,
            color=color,
            zorder=zorder + 1,
        )
        growth_labels.append(
            (
                vals[-1],
                f"{short_name}  {_format_compact_value(currency_symbol, vals[-1])}",
                color,
                bold,
            )
        )

    _plot_curve(
        bench_growth, SERIES_COLORS["bench"], benchmark_short_label, lw=1.7, ls="--", zorder=2
    )
    _plot_curve(top1_growth, SERIES_COLORS["top1"], "Top 1", lw=1.4, ls=":", zorder=2, alpha=0.9)
    _plot_curve(top10_growth, SERIES_COLORS["top10"], "Top 10", lw=1.7, ls="-", zorder=3)
    if top5_growth:
        _plot_curve(top5_growth, SERIES_COLORS["top5"], "Top 5", lw=1.9, ls="-", zorder=4)
    _plot_curve(
        top3_r6_growth, SERIES_COLORS["top3_r6"], "Top 3 + Rule 6", lw=1.6, ls="-.", zorder=5
    )
    _plot_curve(
        top3_growth, SERIES_COLORS["top3"], "Top 3 (Standard)", lw=2.5, ls="-", zorder=6, bold=1
    )

    all_vals = (
        top1_growth + top3_growth + top3_r6_growth + top5_growth + top10_growth + bench_growth
    )
    max_val = max(all_vals)
    min_val = max(1.0, min(all_vals))
    formatter = _make_currency_formatter(currency_symbol)
    if max_val / min_val >= 8.0:
        ax_top.set_yscale("log")
        ax_top.set_ylim(min_val * 0.86, max_val * 1.18)
        ax_top.yaxis.set_major_formatter(formatter)
        ax_top.yaxis.set_minor_formatter(mticker.NullFormatter())
    else:
        pad = (max_val - min_val) * 0.08
        ax_top.set_ylim(max(0.0, min_val - pad), max_val + pad * 1.4)
        ax_top.yaxis.set_major_formatter(formatter)

    x_span = max(30.0, last_x - float(dates_num[0]))
    ax_top.set_xlim(float(dates_num[0]) - x_span * 0.012, last_x + x_span * 0.012)

    scale_desc = "log scale" if ax_top.get_yscale() == "log" else "linear scale"
    ax_top.text(
        0.0,
        1.03,
        f"Growth of {currency_symbol}10,000 invested (TWR, {scale_desc})",
        transform=ax_top.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )
    _draw_event_markers(ax_top, dates, label_y_frac=0.96)
    _place_direct_labels(ax_top, growth_labels, min_gap=0.092, x_text_axes=1.018, font_size=8.6)

    # Bottom panel: Drawdowns from peak with bold 0% baseline and direct labels
    ax_bot.axhline(0.0, color=INK_DARK, linewidth=1.25, zorder=2)
    ax_bot.fill_between(dates_num, top3_dd, 0.0, color=SERIES_COLORS["top3"], alpha=0.11, zorder=1)
    ax_bot.plot(dates_num, top3_dd, color=SERIES_COLORS["top3"], linewidth=1.8, zorder=4)
    ax_bot.plot(dates_num, top1_dd, color=SERIES_COLORS["top1"], linewidth=1.25, ls=":", zorder=3)
    if bench_dd:
        ax_bot.plot(
            dates_num, bench_dd, color=SERIES_COLORS["bench"], linewidth=1.4, ls="--", zorder=2
        )

    ax_bot.plot(
        [last_x], [top3_dd[-1]], marker="o", markersize=4.0, color=SERIES_COLORS["top3"], zorder=5
    )
    ax_bot.plot(
        [last_x], [top1_dd[-1]], marker="o", markersize=3.2, color=SERIES_COLORS["top1"], zorder=4
    )
    if bench_dd:
        ax_bot.plot(
            [last_x],
            [bench_dd[-1]],
            marker="o",
            markersize=3.2,
            color=SERIES_COLORS["bench"],
            zorder=3,
        )

    min_dd_obs = min(min(top1_dd), min(top3_dd), min(bench_dd) if bench_dd else 0.0)
    y_bot_min = max(-100.0, min(min_dd_obs - 8.0, -45.0))
    ax_bot.set_ylim(y_bot_min, 5.0)
    ax_bot.yaxis.set_major_locator(mticker.MultipleLocator(20))
    ax_bot.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))

    if y_bot_min <= -62.0:
        ax_bot.axhline(-60.0, color="#9F3A26", linewidth=0.85, linestyle="--", alpha=0.55, zorder=1)
        x_rule8 = float(dates_num[min(len(dates_num) - 1, max(0, len(dates_num) // 3))])
        ax_bot.text(
            x_rule8,
            -62.5,
            "Rule 8 pain threshold (-60% to -75%)",
            fontsize=7.8,
            color="#9F3A26",
            va="top",
        )

    ax_bot.text(
        0.0,
        1.04,
        "Drawdown from peak (%)",
        transform=ax_bot.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )

    dd_labels: list[tuple[float, str, str, int]] = [
        (
            top3_dd[-1],
            f"Top 3  ({top3_dd[-1]:.0f}%, max {min(top3_dd):.0f}%)",
            SERIES_COLORS["top3"],
            1,
        ),
        (
            top1_dd[-1],
            f"Top 1  ({top1_dd[-1]:.0f}%, max {min(top1_dd):.0f}%)",
            SERIES_COLORS["top1"],
            0,
        ),
    ]
    if bench_dd:
        dd_labels.append(
            (
                bench_dd[-1],
                f"{benchmark_short_label}  ({bench_dd[-1]:.0f}%, max {min(bench_dd):.0f}%)",
                SERIES_COLORS["bench"],
                0,
            )
        )
    _place_direct_labels(ax_bot, dd_labels, min_gap=0.17, x_text_axes=1.018, font_size=8.3)

    ax_bot.xaxis_date()
    locator = mdates.AutoDateLocator(minticks=6, maxticks=11)
    ax_bot.xaxis.set_major_locator(locator)
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    start_win = summary.get("backtest_start_window", summary.get("start_window", ""))
    end_win = summary.get("latest_window", "")
    signal_m = summary.get("latest_signal_month", "")
    fee_pct = summary.get("fee_pct", 0.15)
    survivorship_aware = not bool(summary.get("survivorship_warning", True))

    if subtitle is None:
        scope_tag = "S&P 500 historical membership" if survivorship_aware else "S&P 500"
        sig_part = f" (signal {signal_m})" if signal_m else ""
        subtitle = (
            f"{scope_tag} · {start_win} to {end_win}{sig_part} · "
            f"Top 3Y total return with non-negative 3M filter · {fee_pct:.2f}% fee"
        )
    if footer_note is None:
        footer_note = (
            "Source: fja05680 S&P 500 membership, weib08 & Yahoo Finance (reinvested dividends). "
            "Not financial advice."
            if survivorship_aware
            else (
                "Source: Wikipedia S&P 500 & Yahoo Finance (reinvested dividends). "
                "Not financial advice."
            )
        )

    _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.075)
    fig.subplots_adjust(left=0.075, right=0.775, top=0.825, bottom=0.085)
    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path


def _shorten_small_multiple_title(label: str) -> str:
    return (
        label.replace("All World — ", "")
        .replace(" (Top 3)", "")
        .replace("UK-Accessible ACWI", "ACWI (UK ISA)")
    )


def generate_markets_comparison_chart(
    strategy_series: Mapping[str, Sequence[tuple[date, float]]],
    benchmark_series: Mapping[str, Sequence[tuple[date, float]]],
    output_path: Path,
    *,
    title: str = "UK-accessible All World and US momentum lead since 2017",
    footer_note: str = (
        "Source: Yahoo Finance, iShares ACWI, Wikipedia (reinvested dividends, USD/GBP FX). "
        "Non-US universes reflect current constituents. Not financial advice."
    ),
) -> Path:
    """Render an FT-inspired comparison chart with Burn-Murdoch small-multiples drawdowns."""
    non_empty = {lbl: list(pts) for lbl, pts in strategy_series.items() if pts}
    if not non_empty:
        raise ValueError("Cannot render comparison chart without at least one strategy series.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    common_start = max(pts[0][0] for pts in non_empty.values())

    def _rebase(pts: Sequence[tuple[date, float]]) -> tuple[list[date], list[float]]:
        sliced = [(d, v) for d, v in pts if d >= common_start and v > 0.0]
        if not sliced:
            sliced = [(d, v) for d, v in pts if v > 0.0]
        base = sliced[0][1]
        return [d for d, _ in sliced], [(v / base) * 10_000.0 for _, v in sliced]

    n_cols = len(non_empty)
    fig = plt.figure(figsize=(11.8, 7.6), dpi=180, facecolor=PAPER_BG)
    outer_gs = fig.add_gridspec(2, 1, height_ratios=[1.85, 1.05], hspace=0.34)
    ax_top = fig.add_subplot(outer_gs[0])
    bot_gs = outer_gs[1].subgridspec(1, n_cols, wspace=0.14)

    _style_editorial_axis(ax_top, show_bottom=True)

    all_growth: list[float] = []
    growth_labels: list[tuple[float, str, str, int]] = []
    panel_data: list[tuple[str, list[date], list[float], str]] = []
    max_end = common_start
    ref_dates: list[date] = []

    for idx, (lbl, pts) in enumerate(non_empty.items()):
        color, ls, lw = COMPARISON_STYLES[idx % len(COMPARISON_STYLES)]
        ds, vals = _rebase(pts)
        dds = _compute_drawdown_pct(vals)
        all_growth.extend(vals)
        panel_data.append((lbl, ds, dds, color))
        if ds[-1] > max_end:
            max_end = ds[-1]
        if not ref_dates or len(ds) > len(ref_dates):
            ref_dates = ds

        dnums: Any = mdates.date2num(ds)
        ax_top.plot(dnums, vals, color=color, linewidth=lw, linestyle=ls, zorder=6 - idx)
        ax_top.plot([dnums[-1]], [vals[-1]], marker="o", markersize=4.2, color=color, zorder=7)
        growth_labels.append(
            (
                vals[-1],
                f"{_shorten_small_multiple_title(lbl)}  {_format_compact_value('', vals[-1])}",
                color,
                1,
            )
        )

    for idx, (lbl, b_pts) in enumerate(benchmark_series.items()):
        if not b_pts:
            continue
        color, ls, lw = BENCH_COMP_STYLES[idx % len(BENCH_COMP_STYLES)]
        ds, vals = _rebase(b_pts)
        all_growth.extend(vals)
        dnums_b: Any = mdates.date2num(ds)
        ax_top.plot(dnums_b, vals, color=color, linewidth=lw, linestyle=ls, zorder=2, alpha=0.9)
        ax_top.plot([dnums_b[-1]], [vals[-1]], marker="o", markersize=3.2, color=color, zorder=3)
        short_b = lbl.split(" (")[0]
        growth_labels.append(
            (vals[-1], f"{short_b}  {_format_compact_value('', vals[-1])}", color, 0)
        )

    max_v = max(all_growth)
    min_v = max(1.0, min(all_growth))
    idx_fmt = mticker.FuncFormatter(lambda x, _p: f"{x:,.0f}")
    if max_v / min_v >= 6.0:
        ax_top.set_yscale("log")
        ax_top.set_ylim(min_v * 0.85, max_v * 1.18)
        ax_top.yaxis.set_major_formatter(idx_fmt)
        ax_top.yaxis.set_minor_formatter(mticker.NullFormatter())
    else:
        ax_top.yaxis.set_major_formatter(idx_fmt)

    dnums_ref: Any = mdates.date2num(ref_dates)
    x_span = max(30.0, float(dnums_ref[-1]) - float(dnums_ref[0]))
    ax_top.set_xlim(float(dnums_ref[0]) - x_span * 0.012, float(dnums_ref[-1]) + x_span * 0.012)
    ax_top.xaxis_date()
    ax_top.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=10))
    ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    ax_top.text(
        0.0,
        1.03,
        "Rebased TWR index (Common start = 10,000, log scale)"
        if ax_top.get_yscale() == "log"
        else "Rebased TWR index (Common start = 10,000)",
        transform=ax_top.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )
    _draw_event_markers(ax_top, ref_dates, label_y_frac=0.96)
    _place_direct_labels(ax_top, growth_labels, min_gap=0.098, x_text_axes=1.015, font_size=8.5)

    # Bottom row: Burn-Murdoch 1xN small-multiples drawdown strip
    global_min_dd = min(min(dds) for _, _, dds, _ in panel_data)
    y_bot_min = max(-100.0, math.floor((global_min_dd - 6.0) / 10.0) * 10.0)

    first_sub_ax: Any = None
    for idx, (lbl, ds, dds, color) in enumerate(panel_data):
        ax_m = fig.add_subplot(bot_gs[0, idx], sharey=first_sub_ax)
        if first_sub_ax is None:
            first_sub_ax = ax_m
        _style_editorial_axis(ax_m, show_bottom=True)
        ax_m.axhline(0.0, color=INK_DARK, linewidth=1.25, zorder=2)

        dnums_m: Any = mdates.date2num(ds)
        ax_m.fill_between(dnums_m, dds, 0.0, color=color, alpha=0.14, zorder=1)
        ax_m.plot(dnums_m, dds, color=color, linewidth=1.8, zorder=3)
        ax_m.plot([dnums_m[-1]], [dds[-1]], marker="o", markersize=4.2, color=color, zorder=4)

        ax_m.set_ylim(y_bot_min, 4.0)
        ax_m.yaxis.set_major_locator(mticker.MultipleLocator(20))
        ax_m.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
        if idx > 0:
            plt.setp(ax_m.get_yticklabels(), visible=False)

        ax_m.xaxis_date()
        yr_start = date(ds[0].year + 1 if ds[0].month > 6 else ds[0].year, 1, 1)
        yr_mid = date(2022, 1, 1)
        yr_end = date(ds[-1].year, 1, 1)
        ax_m.set_xticks(mdates.date2num([yr_start, yr_mid, yr_end]))
        ax_m.xaxis.set_major_formatter(mdates.DateFormatter("'%y"))

        short_hdr = _shorten_small_multiple_title(lbl)
        ax_m.text(
            0.0,
            1.05,
            short_hdr,
            transform=ax_m.transAxes,
            ha="left",
            va="bottom",
            fontsize=9.1,
            fontweight="bold",
            color=color,
        )
        max_dd_val = min(dds)
        ax_m.text(
            0.03,
            0.06,
            f"Max {max_dd_val:.0f}% · Now {dds[-1]:.0f}%",
            transform=ax_m.transAxes,
            ha="left",
            va="bottom",
            fontsize=7.9,
            color=INK_SUB,
        )
        if idx == 0:
            ax_m.text(
                0.0,
                1.21,
                "Drawdown from peak by universe (%)",
                transform=ax_m.transAxes,
                ha="left",
                va="bottom",
                fontsize=9.3,
                fontweight="bold",
                color=INK_SUB,
            )

    subtitle = (
        f"Standard (Top 3) portfolios rebased over {common_start.strftime('%Y-%m')} to "
        f"{max_end.strftime('%Y-%m')} · Growth above, peak-to-trough drawdowns below"
    )
    _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.07)
    fig.subplots_adjust(left=0.07, right=0.78, top=0.825, bottom=0.08)
    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path
