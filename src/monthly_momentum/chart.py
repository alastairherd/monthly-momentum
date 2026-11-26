"""FT-inspired broadsheet editorial performance charts using headless Matplotlib."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Liberation Sans", "DejaVu Sans", "Arial", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["text.parse_math"] = False

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

ALLOCATION_PALETTE: tuple[str, ...] = (
    "#0F5C6E",  # Deep petrol teal
    "#2B4590",  # Editorial cobalt
    "#C45D18",  # Burnt amber
    "#2E6F40",  # Forest sage
    "#7A3E65",  # Muted plum
    "#C28B22",  # Ochre gold
    "#3C8C9E",  # Slate cyan
    "#8F3A32",  # Terracotta rust
)
OTHER_BAND_COLOR = "#D6D3C9"

MACRO_EVENTS: tuple[tuple[date, str], ...] = (
    (date(2008, 9, 1), "2008\nGFC"),
    (date(2020, 3, 1), "Covid\n2020"),
    (date(2022, 1, 1), "2022 rate\nshock"),
)

# Band colors for the cumulative hero chart (chronological holding order).
HERO_BAND_COLORS: tuple[str, ...] = (
    "#0F5C6E",  # Deep petrol teal
    "#C45D18",  # Burnt amber
    "#2B4590",  # Editorial cobalt
    "#7A3E65",  # Muted plum
    "#2E6F40",  # Forest sage
    "#C28B22",  # Ochre gold
    "#3C8C9E",  # Slate cyan
    "#8F3A32",  # Terracotta rust
    "#5B4A8A",  # Muted violet
    "#6B7F3A",  # Olive green
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
    left_aligned_years: Collection[int] = (),
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
        is_left = ev_dt.year in left_aligned_years
        ax.annotate(
            ev_label,
            xy=(x_ev, y_text),
            xytext=(-4 if is_left else 4, 0),
            textcoords="offset points",
            ha="right" if is_left else "left",
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
            linespacing=1.12,
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
    del benchmark_label, currency_symbol

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
                f"{short_name}  {_format_compact_value('', vals[-1])}",
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
        top3_r6_growth, SERIES_COLORS["top3_r6"], "Top 3 + staged exits", lw=1.6, ls="-.", zorder=5
    )
    _plot_curve(
        top3_growth, SERIES_COLORS["top3"], "Top 3 (Standard)", lw=2.5, ls="-", zorder=6, bold=1
    )

    all_vals = (
        top1_growth + top3_growth + top3_r6_growth + top5_growth + top10_growth + bench_growth
    )
    max_val = max(all_vals)
    min_val = max(1.0, min(all_vals))
    formatter = mticker.FuncFormatter(lambda x, _p: f"{x:,.0f}")
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
        f"Rebased TWR index of monthly DCA portfolio (start = 10,000, {scale_desc})",
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
        x_threshold = float(dates_num[min(len(dates_num) - 1, max(0, len(dates_num) // 3))])
        ax_bot.text(
            x_threshold,
            -62.5,
            "Drawdown tolerance (-60% to -75%)",
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


def benchmark_relative_series(
    strategy_series: Mapping[str, Sequence[tuple[date, float]]],
    benchmarks_by_market: Mapping[str, Sequence[tuple[date, float]]],
) -> dict[str, list[tuple[date, float]]]:
    """Compare strategy and benchmark growth over the same dates for every market."""
    ratios_by_market: dict[str, dict[date, float]] = {}
    for market, points in strategy_series.items():
        benchmark = {
            day: nav
            for day, nav in benchmarks_by_market.get(market, ())
            if math.isfinite(nav) and nav > 0.0
        }
        ratios = {
            day: nav / benchmark[day]
            for day, nav in points
            if day in benchmark and math.isfinite(nav) and nav >= 0.0
        }
        if len(ratios) >= 2 and any(ratios.values()):
            ratios_by_market[market] = ratios

    if not ratios_by_market:
        return {}

    dates = sorted(set.intersection(*(set(ratios) for ratios in ratios_by_market.values())))
    start = next((d for d in dates if all(r[d] > 0.0 for r in ratios_by_market.values())), None)
    if start is None or start == dates[-1]:
        return {}

    return {
        market: [(d, (ratios[d] / ratios[start] - 1.0) * 100.0) for d in dates if d >= start]
        for market, ratios in ratios_by_market.items()
    }


def generate_benchmark_relative_chart(
    market_series: Mapping[str, Sequence[tuple[date, float]]],
    output_path: Path,
) -> Path:
    """Render the cumulative percentage lead or lag against each market's benchmark."""
    first_series = next(iter(market_series.values()))
    start, end = first_series[0][0], first_series[-1][0]
    fig, ax = plt.subplots(figsize=(11.8, 5.2), dpi=180, facecolor=PAPER_BG)
    _style_editorial_axis(ax)
    ax.axhline(0.0, color=INK_DARK, linewidth=1.15, linestyle="--", zorder=2)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=0))
    ax.xaxis_date()
    locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.tick_params(labelsize=11)
    ax.margins(x=0.015, y=0.12)

    labels: list[tuple[float, str, str, int]] = []
    for idx, (market, points) in enumerate(market_series.items()):
        color, linestyle, width = COMPARISON_STYLES[idx % len(COMPARISON_STYLES)]
        dates, values = zip(*points, strict=True)
        date_numbers: Any = mdates.date2num(dates)
        ax.plot(date_numbers, values, color=color, linestyle=linestyle, linewidth=width, zorder=3)
        ax.plot(date_numbers[-1], values[-1], marker="o", markersize=4, color=color, zorder=4)
        label = f"{_shorten_small_multiple_title(market)}  {values[-1]:+.1f}%"
        labels.append((values[-1], label, color, 1))

    ax.set_ylabel("Growth relative to benchmark", color=INK_SUB, fontsize=11, labelpad=9)
    _place_direct_labels(ax, labels, min_gap=0.09, font_size=11.5)
    _draw_top_rule_and_headers(
        fig,
        "How each momentum strategy performed against its own benchmark",
        f"Top 3 portfolios · {start:%b %Y} to {end:%b %Y} · 0% means matching the benchmark",
        "Compared with S&P 500 Total Return (^SP500TR), MSCI ACWI ETF (ACWI) "
        "and FTSE 100 ETF (ISF.L). Dividends reinvested.",
        left=0.085,
    )
    fig.subplots_adjust(left=0.085, right=0.77, top=0.805, bottom=0.11)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path


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


def generate_allocation_chart(
    allocation_summary: dict[str, Any],
    output_path: Path,
    *,
    title: str,
    subtitle: str,
    footer_note: str,
) -> Path:
    """Render a broadsheet 100% stacked-area portfolio composition + concentration PNG."""
    series_pts = allocation_summary.get("points") or []
    if not series_pts:
        raise ValueError("Cannot render allocation chart from empty points.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected: list[str] = list(allocation_summary.get("selected_tickers") or [])
    stack_keys = [*selected, "OTHER"]

    dates = [date.fromisoformat(str(pt["d"])) for pt in series_pts]
    dates_num: Any = mdates.date2num(dates)
    stacks: list[list[float]] = [
        [float(pt["weights"].get(k, 0.0)) for pt in series_pts] for k in stack_keys
    ]
    colors: list[str] = [
        ALLOCATION_PALETTE[idx % len(ALLOCATION_PALETTE)] for idx in range(len(selected))
    ] + [OTHER_BAND_COLOR]

    fig = plt.figure(figsize=(11.8, 7.5), dpi=180, facecolor=PAPER_BG)
    gs = fig.add_gridspec(2, 1, height_ratios=[2.1, 1.0], hspace=0.28)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    _style_editorial_axis(ax_top, show_bottom=False)
    _style_editorial_axis(ax_bot, show_bottom=True)

    ax_top.stackplot(
        dates_num,
        *stacks,
        colors=colors,
        alpha=0.90,
        edgecolor=PAPER_BG,
        linewidth=0.6,
        zorder=2,
    )
    ax_top.set_ylim(0.0, 100.0)
    ax_top.yaxis.set_major_locator(mticker.MultipleLocator(25))
    ax_top.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_top.set_xlim(float(dates_num[0]), float(dates_num[-1]))

    ax_top.text(
        0.0,
        1.03,
        "Portfolio weight by holding (% of market value, sums to 100%)",
        transform=ax_top.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )
    _draw_event_markers(ax_top, dates, label_y_frac=0.96)

    # Direct labels anchored at each band's final vertical midpoint
    last_w = series_pts[-1]["weights"]
    end_holdings = int(allocation_summary.get("final_holdings_count", series_pts[-1]["n_holdings"]))
    cum = 0.0
    area_labels: list[tuple[float, str, str, int]] = []
    labeled_nonzero = 0
    for idx, key in enumerate(stack_keys):
        val = float(last_w.get(key, 0.0))
        mid = cum + val / 2.0
        cum += val
        if key == "OTHER":
            other_cnt = max(0, end_holdings - labeled_nonzero)
            lbl_txt = (
                f"Other ({other_cnt} stocks)  {val:.1f}%" if other_cnt > 0 else f"Other  {val:.1f}%"
            )
            if val >= 0.3:
                area_labels.append((mid, lbl_txt, INK_SUB, 0))
        else:
            if val > 0.0:
                labeled_nonzero += 1
            peak_val = max(stacks[idx])
            if val >= 1.2 or peak_val >= 8.0:
                val_txt = f"{val:.1f}%" if val >= 1.0 else "<1%"
                area_labels.append(
                    (
                        mid,
                        f"{key}  {val_txt}",
                        ALLOCATION_PALETTE[idx % len(ALLOCATION_PALETTE)],
                        1 if val >= 5.0 else 0,
                    )
                )

    _place_direct_labels(ax_top, area_labels, min_gap=0.095, x_text_axes=1.018, font_size=8.4)

    # Bottom panel: Top 1, Top 5, Top 10 concentration lines over time
    top1_s = [float(pt["top1_pct"]) for pt in series_pts]
    top5_s = [float(pt["top5_pct"]) for pt in series_pts]
    top10_s = [float(pt["top10_pct"]) for pt in series_pts]

    last_x = float(dates_num[-1])
    ax_bot.axhline(0.0, color=INK_DARK, linewidth=1.1, zorder=2)
    ax_bot.fill_between(dates_num, top1_s, 0.0, color=SERIES_COLORS["top3"], alpha=0.11, zorder=1)
    ax_bot.plot(dates_num, top10_s, color=SERIES_COLORS["bench"], linewidth=1.4, ls="--", zorder=2)
    ax_bot.plot(dates_num, top5_s, color=SERIES_COLORS["top5"], linewidth=1.9, zorder=3)
    ax_bot.plot(dates_num, top1_s, color=SERIES_COLORS["top3"], linewidth=2.2, zorder=4)

    for vals, col, ms in (
        (top10_s, SERIES_COLORS["bench"], 3.2),
        (top5_s, SERIES_COLORS["top5"], 3.6),
        (top1_s, SERIES_COLORS["top3"], 4.0),
    ):
        ax_bot.plot([last_x], [vals[-1]], marker="o", markersize=ms, color=col, zorder=5)

    ax_bot.set_ylim(0.0, 105.0)
    ax_bot.yaxis.set_major_locator(mticker.MultipleLocator(25))
    ax_bot.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))

    start_n = int(series_pts[0]["n_holdings"])
    eff_n = float(allocation_summary.get("final_effective_n", series_pts[-1]["effective_n"]))
    top1_tk = str(allocation_summary.get("final_top1_ticker") or "")
    top1_lbl = f"Top 1 ({top1_tk})  {top1_s[-1]:.1f}%" if top1_tk else f"Top 1  {top1_s[-1]:.1f}%"

    ax_bot.text(
        0.0,
        1.04,
        f"Concentration over time (%) · Holdings grew {start_n} → {end_holdings} "
        f"(Effective N = {eff_n:.1f})",
        transform=ax_bot.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )

    conc_labels: list[tuple[float, str, str, int]] = [
        (top10_s[-1], f"Top 10 combined  {top10_s[-1]:.1f}%", SERIES_COLORS["bench"], 0),
        (top5_s[-1], f"Top 5 combined  {top5_s[-1]:.1f}%", SERIES_COLORS["top5"], 1),
        (top1_s[-1], top1_lbl, SERIES_COLORS["top3"], 1),
    ]
    _place_direct_labels(ax_bot, conc_labels, min_gap=0.18, x_text_axes=1.018, font_size=8.3)

    ax_bot.xaxis_date()
    ax_bot.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=11))
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.075)
    fig.subplots_adjust(left=0.075, right=0.77, top=0.825, bottom=0.085)
    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path


def generate_funding_comparison_chart(
    funding_schedules: Mapping[str, dict[str, Any]],
    output_path: Path,
    *,
    title: str,
    subtitle: str,
    currency_symbol: str = "$",
    footer_note: str,
) -> Path:
    """Render a broadsheet 1x3 comparison of Pure DCA vs Hybrid Lump+DCA vs Pure Lump Sum."""
    from matplotlib.patches import Patch

    panel_specs: tuple[tuple[str, str], ...] = (
        ("dca_100", f"Pure DCA ({currency_symbol}100/mo)"),
        ("lump_10k_dca_100", f"Lump {currency_symbol}10k + {currency_symbol}100/mo"),
        ("lump_10k_only", f"Pure Lump {currency_symbol}10k ({currency_symbol}0/mo)"),
    )
    panels: list[tuple[str, dict[str, Any]]] = []
    for key, hdr in panel_specs:
        if key not in funding_schedules:
            raise ValueError(f"Missing funding schedule '{key}' for comparison chart.")
        panels.append((hdr, funding_schedules[key]))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Deterministic union of top tickers across all 3 schedules so stocks keep consistent colors.
    score_map: dict[str, float] = {}
    for _, sched in panels:
        alloc = sched["allocation"]
        pts = alloc.get("points") or []
        if not pts:
            continue
        last_w = pts[-1]["weights"]
        for tk in alloc.get("selected_tickers") or []:
            max_w = max(float(pt["weights"].get(tk, 0.0)) for pt in pts)
            final_w = float(last_w.get(tk, 0.0))
            score_map[tk] = max(score_map.get(tk, 0.0), final_w * 2.0 + max_w * 0.25)

    union_tickers = sorted(score_map, key=lambda t: (-score_map[t], t))[: len(ALLOCATION_PALETTE)]
    ticker_colors = {
        tk: ALLOCATION_PALETTE[idx % len(ALLOCATION_PALETTE)]
        for idx, tk in enumerate(union_tickers)
    }
    stack_keys = [*union_tickers, "OTHER"]
    colors = [ticker_colors[tk] for tk in union_tickers] + [OTHER_BAND_COLOR]

    fig = plt.figure(figsize=(12.4, 5.9), dpi=180, facecolor=PAPER_BG)
    gs = fig.add_gridspec(1, 3, wspace=0.14)

    first_ax: Any = None
    for idx, (hdr, sched) in enumerate(panels):
        ax = fig.add_subplot(gs[0, idx], sharey=first_ax)
        if first_ax is None:
            first_ax = ax
        _style_editorial_axis(ax, show_bottom=True)

        alloc = sched["allocation"]
        pts = alloc["points"]
        dates = [date.fromisoformat(str(pt["d"])) for pt in pts]
        dates_num: Any = mdates.date2num(dates)

        stacks: list[list[float]] = []
        for tk in union_tickers:
            stacks.append([float(pt["weights"].get(tk, 0.0)) for pt in pts])
        other_vals: list[float] = []
        for pt in pts:
            named = sum(float(pt["weights"].get(tk, 0.0)) for tk in union_tickers)
            other_vals.append(max(0.0, 100.0 - named))
        stacks.append(other_vals)

        ax.stackplot(
            dates_num,
            *stacks,
            colors=colors,
            alpha=0.92,
            edgecolor=PAPER_BG,
            linewidth=0.55,
            zorder=2,
        )
        ax.set_ylim(0.0, 100.0)
        ax.yaxis.set_major_locator(mticker.MultipleLocator(25))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
        if idx > 0:
            plt.setp(ax.get_yticklabels(), visible=False)
        ax.set_xlim(float(dates_num[0]), float(dates_num[-1]))
        ax.xaxis_date()
        ax.xaxis.set_major_locator(mdates.YearLocator(base=4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("'%y"))

        end_val = float(sched.get("ending_value") or 0.0)
        xirr_val = sched.get("xirr_pct")
        eff_n = float(alloc.get("final_effective_n") or 0.0)
        n_hold = int(alloc.get("final_holdings_count") or 0)
        xirr_txt = f"{float(xirr_val):.1f}%" if xirr_val is not None else "—"

        ax.text(
            0.0,
            1.11,
            hdr,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=10.5,
            fontweight="bold",
            color=INK_DARK,
        )
        ax.text(
            0.0,
            1.035,
            f"End {_format_compact_value(currency_symbol, end_val)} · XIRR {xirr_txt} · "
            f"Eff N {eff_n:.1f} (N={n_hold})",
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.3,
            color=INK_SUB,
        )

        # Clean in-band callouts at the right edge for major holdings (>= 12% vertical span)
        x_text = float(dates_num[-1]) - (float(dates_num[-1]) - float(dates_num[0])) * 0.025
        cum = 0.0
        for s_idx, key in enumerate(stack_keys):
            val = stacks[s_idx][-1]
            mid_y = cum + val / 2.0
            cum += val
            if val < 12.0:
                continue
            band_col = colors[s_idx]
            txt_col = INK_DARK if band_col in {OTHER_BAND_COLOR, "#C28B22"} else "#FFFFFF"
            lbl = f"Other {val:.0f}%" if key == "OTHER" else f"{key} {val:.0f}%"
            ax.text(
                x_text,
                mid_y,
                lbl,
                ha="right",
                va="center",
                fontsize=8.3,
                fontweight="bold",
                color=txt_col,
                zorder=5,
            )

    legend_handles = [
        Patch(facecolor=ticker_colors[tk], edgecolor=PAPER_BG, linewidth=0.5, label=tk)
        for tk in union_tickers
    ] + [Patch(facecolor=OTHER_BAND_COLOR, edgecolor=PAPER_BG, linewidth=0.5, label="Other")]
    fig.legend(
        handles=legend_handles,
        loc="lower left",
        bbox_to_anchor=(0.055, 0.052),
        ncol=min(len(legend_handles), 9),
        frameon=False,
        fontsize=8.4,
        handlelength=1.2,
        handletextpad=0.5,
        columnspacing=1.2,
    )

    _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.06)
    fig.subplots_adjust(left=0.06, right=0.975, top=0.76, bottom=0.165, wspace=0.12)
    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path


def _plot_dca_hero_panel(
    ax: Any,
    series_list: Sequence[
        tuple[Sequence[date], Sequence[float], str, float | None, str, float, str, int]
    ],
    cash_dates: Sequence[date],
    cash_vals: Sequence[float],
    *,
    panel_title: str,
    panel_subtitle: str,
    currency_symbol: str,
    show_events: bool = False,
) -> None:
    """Render one linear dollar-value DCA panel with shaded principal floor and direct labels."""
    _style_editorial_axis(ax, show_bottom=True)

    def _fmt_compact_tick(val: float, _pos: Any) -> str:
        if val >= 1_000_000:
            return f"{currency_symbol}{val / 1_000_000:.1f}M"
        if val >= 1_000:
            return f"{currency_symbol}{val / 1_000:.0f}k"
        return f"{currency_symbol}{val:.0f}"

    formatter = mticker.FuncFormatter(_fmt_compact_tick)

    c_nums: Any = mdates.date2num(cash_dates)
    ax.fill_between(c_nums, cash_vals, 0.0, color="#E4E1D6", alpha=0.68, zorder=1)
    ax.plot(c_nums, cash_vals, color="#9E9B92", linewidth=1.0, zorder=1)

    all_y: list[float] = list(cash_vals)
    cash_txt = _format_compact_value(currency_symbol, float(cash_vals[-1]))
    labels: list[tuple[float, str, str, int]] = [
        (
            float(cash_vals[-1]),
            f"Cash put in\n{cash_txt}",
            INK_MUTED,
            0,
        )
    ]

    for ds, vals, label_name, xirr_pct, color, lw, ls, bold in series_list:
        if not ds or not vals:
            continue
        d_nums: Any = mdates.date2num(ds)
        all_y.extend(float(v) for v in vals)
        ax.plot(d_nums, vals, color=color, linewidth=lw, linestyle=ls, zorder=4 if bold else 3)
        ax.plot(
            [float(d_nums[-1])],
            [float(vals[-1])],
            marker="o",
            markersize=4.4 if bold else 3.6,
            color=color,
            zorder=5 if bold else 4,
        )
        val_txt = _format_compact_value(currency_symbol, float(vals[-1]))
        line2 = f"{val_txt} ({xirr_pct:.1f}%/yr)" if xirr_pct is not None else val_txt
        labels.append((float(vals[-1]), f"{label_name}\n{line2}", color, bold))

    max_y = max(all_y) if all_y else 1.0
    ax.set_ylim(0.0, max_y * 1.13)
    ax.yaxis.set_major_formatter(formatter)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5, prune="upper"))

    span_days = max(30.0, float(c_nums[-1]) - float(c_nums[0]))
    ax.set_xlim(float(c_nums[0]) - span_days * 0.015, float(c_nums[-1]) + span_days * 0.015)
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("'%y"))

    if show_events:
        _draw_event_markers(ax, cash_dates, label_y_frac=0.95, left_aligned_years={2020})

    ax.text(
        0.0,
        1.105,
        panel_title,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10.5,
        fontweight="bold",
        color=INK_DARK,
    )
    ax.text(
        0.0,
        1.032,
        panel_subtitle,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8.5,
        color=INK_SUB,
    )
    _place_direct_labels(ax, labels, min_gap=0.165, x_text_axes=1.022, font_size=8.0)


def _text_color_for(background: str) -> str:
    """Pick ink or white text for legibility on a colored band."""
    r, g, b = (int(background[i : i + 2], 16) for i in (1, 3, 5))
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return INK_DARK if luminance > 0.55 else "#FFFFFF"


def _draw_hero_first_year_inset(
    ax_top: Any,
    pts: Sequence[dict[str, Any]],
    *,
    benchmark_label: str,
    start: date,
) -> None:
    """Zoom the daily-granularity opening year inside the hero chart's top panel."""
    cutoff_d = date(start.year + 1, start.month, start.day)
    window_pts = [pt for pt in pts if pt["date"] <= cutoff_d]
    if len(window_pts) < 20:
        return

    inset = ax_top.inset_axes([0.04, 0.56, 0.19, 0.36])
    inset.set_facecolor(PAPER_BG)
    _style_editorial_axis(inset, show_bottom=True)

    i_dates = [pt["date"] for pt in window_pts]
    i_nums: Any = mdates.date2num(i_dates)
    i_totals = [float(pt["total"]) for pt in window_pts]
    i_cash = [float(pt["cash"]) for pt in window_pts]
    i_bench = [pt["benchmark"] for pt in window_pts]
    has_i_bench = all(b is not None for b in i_bench)
    i_bench_f = [float(b) for b in i_bench] if has_i_bench else []

    if has_i_bench:
        inset.plot(
            i_nums, i_bench_f, color=SERIES_COLORS["bench"], linewidth=1.2, linestyle="--", zorder=3
        )
    inset.plot(i_nums, i_cash, color="#9E9B92", linewidth=1.0, linestyle=":", zorder=2)
    inset.plot(i_nums, i_totals, color=SERIES_COLORS["top3"], linewidth=1.6, zorder=4)
    inset.plot(
        [i_nums[-1]],
        [i_totals[-1]],
        marker="o",
        markersize=3.0,
        color=SERIES_COLORS["top3"],
        zorder=5,
    )

    series_vals = i_totals + i_cash + i_bench_f
    inset.set_ylim(min(series_vals) * 0.94, max(series_vals) * 1.06)
    inset.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
    inset.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _p: _format_compact_value("", v))
    )
    inset.set_xlim(i_nums[0] - 6, i_nums[-1] + 6)
    inset.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    inset.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    inset.tick_params(axis="both", labelsize=6.2, pad=2)
    inset.tick_params(axis="x", length=2)

    inset.text(
        0.0,
        1.12,
        "First year in detail",
        transform=inset.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.2,
        fontweight="bold",
        color=INK_SUB,
    )
    inset.text(
        0.0,
        1.03,
        f"vs {benchmark_label} and cash deposited",
        transform=inset.transAxes,
        ha="left",
        va="bottom",
        fontsize=6.2,
        color=INK_MUTED,
    )


def generate_hero_cumulative_chart(
    series: Any,
    output_path: Path,
    *,
    title: str,
    subtitle: str,
    footer_note: str,
    benchmark_label: str = "ACWI ETF",
    currency_symbol: str = "$",
) -> Path:
    """Render the cumulative hero chart: stacked holdings + benchmark line + race panel.

    ``series`` is a ``monthly_momentum.hero.HeroCumulativeSeries``: mixed-granularity
    points (daily early, monthly after) with per-holding values, a benchmark DCA series,
    and cash contributed. Works with monthly-only series too (no daily segment).
    """
    pts = series.points
    if not pts:
        raise ValueError("Cannot render the hero cumulative chart from an empty series.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dates = [pt["date"] for pt in pts]
    dates_num: Any = mdates.date2num(dates)
    totals = [float(pt["total"]) for pt in pts]
    bench_vals = [pt["benchmark"] for pt in pts]
    cash_vals = [float(pt["cash"]) for pt in pts]
    has_bench = all(b is not None for b in bench_vals)

    band_keys = list(series.band_tickers)
    band_vals = [[max(0.02, float(pt["stocks"].get(tk, 0.0))) for pt in pts] for tk in band_keys]
    colors = [HERO_BAND_COLORS[i % len(HERO_BAND_COLORS)] for i in range(len(band_keys))] + [
        OTHER_BAND_COLOR
    ]

    fig = plt.figure(figsize=(11.8, 7.4), dpi=180, facecolor=PAPER_BG)
    gs = fig.add_gridspec(2, 1, height_ratios=[2.0, 1.0], hspace=0.30)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1], sharex=ax_top)

    _style_editorial_axis(ax_top, show_bottom=False)
    _style_editorial_axis(ax_bot, show_bottom=True)

    stack_handles = [
        *band_vals,
        [max(0.02, totals[j] - sum(v[j] for v in band_vals)) for j in range(len(pts))],
    ]
    other_vals = stack_handles[-1]
    ax_top.stackplot(
        dates_num,
        *stack_handles,
        colors=colors,
        alpha=0.92,
        edgecolor=PAPER_BG,
        linewidth=0.5,
        zorder=2,
    )

    def _plot_over_line(vals: list[float], color: str, ls: str, lw: float) -> None:
        # Paper-colored casing keeps the line legible over the filled bands.
        ax_top.plot(dates_num, vals, color=PAPER_BG, linewidth=lw + 1.6, linestyle=ls, zorder=5)
        ax_top.plot(dates_num, vals, color=color, linewidth=lw, linestyle=ls, zorder=6)

    _plot_over_line(cash_vals, "#9E9B92", ":", 1.1)
    if has_bench:
        _plot_over_line([float(b) for b in bench_vals], SERIES_COLORS["bench"], "--", 1.7)

    last_x = float(dates_num[-1])
    ax_top.plot([last_x], [totals[-1]], marker="o", markersize=4.6, color=INK_DARK, zorder=8)
    if has_bench:
        ax_top.plot(
            [last_x],
            [float(bench_vals[-1])],
            marker="o",
            markersize=3.8,
            color=SERIES_COLORS["bench"],
            zorder=8,
        )
    ax_top.plot([last_x], [cash_vals[-1]], marker="o", markersize=3.4, color="#9E9B92", zorder=8)

    all_vals = totals + cash_vals + ([float(b) for b in bench_vals] if has_bench else [])
    max_val = max(all_vals)
    # Keep the axis floor low enough that the first months' equal-thirds bands
    # (roughly a third of the opening value each) stay visible on the log scale.
    min_val = max(1.0, min(totals) * 0.3)
    ax_top.set_yscale("log")
    ax_top.set_ylim(min_val * 0.9, max_val * 1.2)
    compact_fmt = mticker.FuncFormatter(lambda x, _p: _format_compact_value("", x))
    ax_top.yaxis.set_major_formatter(compact_fmt)
    ax_top.yaxis.set_minor_formatter(mticker.NullFormatter())

    x_span = max(30.0, last_x - float(dates_num[0]))
    ax_top.set_xlim(float(dates_num[0]) - x_span * 0.012, last_x + x_span * 0.012)

    ax_top.text(
        0.0,
        1.03,
        "Portfolio value by holding (stacked bands, log scale)",
        transform=ax_top.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )
    _draw_event_markers(ax_top, dates, label_y_frac=0.96)
    ax_top.tick_params(labelbottom=False)

    # In-band labels at each band's peak share (named holdings, then the Other band).
    # Greedy collision avoidance keeps the largest labels readable when several bands
    # peak in the same early months.
    n_pts = len(pts)
    x_min, x_max = float(dates_num[0]), last_x
    y_lo, y_hi = ax_top.get_ylim()
    log_lo, log_hi = math.log(y_lo), math.log(y_hi)

    def _y_frac(value: float) -> float:
        return (math.log(max(value, 1e-9)) - log_lo) / (log_hi - log_lo)

    labeled_bands: list[tuple[str, list[float], str, int]] = [
        (tk, band_vals[idx], colors[idx], idx) for idx, tk in enumerate(band_keys)
    ] + [("Other", other_vals, OTHER_BAND_COLOR, len(band_keys))]
    candidates: list[tuple[float, str, list[float], str, int]] = []
    for tk, vals, band_color, stack_idx in labeled_bands:
        shares = [vals[j] / totals[j] for j in range(n_pts)]
        peak_share = max(shares)
        if peak_share >= 0.10:
            candidates.append((peak_share, tk, vals, band_color, stack_idx))
    candidates.sort(reverse=True)

    placed: list[tuple[float, float]] = []
    for peak_share, tk, vals, band_color, stack_idx in candidates:
        shares = [vals[j] / totals[j] for j in range(n_pts)]
        peak_j = shares.index(peak_share)
        label_x = min(max(float(dates_num[peak_j]), x_min + x_span * 0.05), x_max - x_span * 0.05)
        near_j = min(range(n_pts), key=lambda j: abs(float(dates_num[j]) - label_x))
        lower = sum(band_vals[i][near_j] for i in range(stack_idx))
        upper = lower + vals[near_j]
        # Visual midpoint of the band on the log axis (clamp below-axis fill to the floor).
        lower_eff = max(lower, y_lo)
        mid_y = math.sqrt(lower_eff * upper) if lower_eff > 0.0 else (lower + upper) / 2.0
        mid_y = min(max(mid_y, y_lo * 1.03), y_hi * 0.97)
        x_frac = (float(dates_num[near_j]) - x_min) / x_span
        y_frac = _y_frac(mid_y)
        if any(abs(x_frac - px) < 0.10 and abs(y_frac - py) < 0.06 for px, py in placed):
            continue
        placed.append((x_frac, y_frac))
        ax_top.text(
            float(dates_num[near_j]),
            mid_y,
            f"{tk} · {peak_share * 100.0:.0f}%",
            ha="center",
            va="center",
            fontsize=8.2,
            fontweight="bold",
            color=_text_color_for(band_color),
            path_effects=[patheffects.withStroke(linewidth=1.8, foreground=band_color)],
            zorder=9,
        )

    line_labels: list[tuple[float, str, str, int]] = [
        (
            totals[-1],
            f"Portfolio  {_format_compact_value(currency_symbol, totals[-1])}",
            INK_DARK,
            1,
        )
    ]
    if has_bench:
        line_labels.append(
            (
                float(bench_vals[-1]),
                (
                    f"{benchmark_label}  "
                    f"{_format_compact_value(currency_symbol, float(bench_vals[-1]))}"
                ),
                SERIES_COLORS["bench"],
                0,
            )
        )
    line_labels.append(
        (
            cash_vals[-1],
            f"Cash put in  {_format_compact_value(currency_symbol, cash_vals[-1])}",
            INK_MUTED,
            0,
        )
    )
    _place_direct_labels(ax_top, line_labels, min_gap=0.092, x_text_axes=1.018, font_size=8.6)

    # Inset: the daily-granularity first year at a readable linear scale.
    if series.daily_through is not None:
        _draw_hero_first_year_inset(
            ax_top,
            pts,
            benchmark_label=benchmark_label,
            start=pts[0]["date"],
        )

    # Bottom panel: cumulative growth vs the benchmark, in percent.
    ax_bot.axhline(0.0, color=INK_DARK, linewidth=1.15, zorder=2)
    if has_bench:
        rel = [(t / float(b) - 1.0) * 100.0 for t, b in zip(totals, bench_vals, strict=True)]
        ax_bot.fill_between(dates_num, rel, 0.0, color=SERIES_COLORS["top3"], alpha=0.12, zorder=1)
        ax_bot.plot(dates_num, rel, color=SERIES_COLORS["top3"], linewidth=1.9, zorder=3)
        ax_bot.plot(
            [last_x], [rel[-1]], marker="o", markersize=4.2, color=SERIES_COLORS["top3"], zorder=4
        )
        pad = max(6.0, (max(rel) - min(min(rel), 0.0)) * 0.08)
        ax_bot.set_ylim(min(min(rel), 0.0) - pad, max(rel) + pad)
        rel_labels = [(rel[-1], f"{rel[-1]:+.0f}% vs {benchmark_label}", SERIES_COLORS["top3"], 1)]
        _place_direct_labels(ax_bot, rel_labels, min_gap=0.2, x_text_axes=1.018, font_size=9.0)
    else:
        ax_bot.text(
            0.5,
            0.5,
            "Benchmark series unavailable",
            transform=ax_bot.transAxes,
            ha="center",
            va="center",
            fontsize=9.0,
            color=INK_MUTED,
        )
    ax_bot.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_bot.text(
        0.0,
        1.06,
        f"Growth of the same deposits in the portfolio vs {benchmark_label} (%)",
        transform=ax_bot.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.3,
        fontweight="bold",
        color=INK_SUB,
    )

    ax_bot.xaxis_date()
    ax_bot.xaxis.set_major_locator(mdates.YearLocator())
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.075)
    fig.subplots_adjust(left=0.075, right=0.775, top=0.83, bottom=0.085)
    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path


def generate_hero_vs_sp500_chart(
    us_full_points: Sequence[dict[str, Any]],
    output_path: Path,
    *,
    us_full_xirr_pct: float | None,
    sp500_full_xirr_pct: float | None,
    common_9y: Mapping[str, Any] | None = None,
    monthly_amount: float = 100.0,
    currency_symbol: str = "$",
) -> Path:
    """Render a simple FT-broadsheet hero comparison for $100/mo DCA vs index trackers."""
    if not us_full_points:
        raise ValueError("Cannot render hero chart from empty points.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    us_dates = [pt["d"] for pt in us_full_points]
    us_cash = [float(pt["cash"]) for pt in us_full_points]
    us_vals = [float(pt["strategy"]) for pt in us_full_points]
    sp_pts = [(pt["d"], float(pt["sp500"])) for pt in us_full_points if pt.get("sp500") is not None]

    us_20y_end = us_vals[-1]
    sp_20y_end = sp_pts[-1][1] if sp_pts else None
    yrs_20y = max(1, len(us_full_points) // 12)
    right_series: list[
        tuple[Sequence[date], Sequence[float], str, float | None, str, float, str, int]
    ] = []
    if sp_pts:
        right_series.append(
            (
                [d for d, _ in sp_pts],
                [v for _, v in sp_pts],
                "S&P 500",
                sp500_full_xirr_pct,
                SERIES_COLORS["bench"],
                1.7,
                "--",
                0,
            )
        )
    right_series.append(
        (us_dates, us_vals, "US Top 3", us_full_xirr_pct, SERIES_COLORS["top5"], 2.5, "-", 1)
    )

    w0 = str(us_full_points[0].get("window_month") or "")
    w1 = str(us_full_points[-1].get("window_month") or "")
    start_20y = w0[:4] if len(w0) >= 4 else str(us_dates[0].year)
    end_20y = w1[:4] if len(w1) >= 4 else str(us_dates[-1].year)
    mo_lbl = f"{currency_symbol}{monthly_amount:,.0f}"
    subtitle = (
        f"Actual portfolio value from {mo_lbl} invested on the 1st of every month "
        "(after 0.15% FX fees, reinvested dividends) vs index trackers"
    )
    footer_note = (
        "Source: fja05680 S&P 500 membership, weib08, iShares ACWI & Yahoo Finance. "
        "Non-US ACWI pool reflects current constituents. Not financial advice."
    )

    if common_9y and common_9y.get("acwi_uk"):
        acwi_uk = common_9y["acwi_uk"]
        uk_dates = list(acwi_uk["dates"])
        uk_vals = [float(v) for v in acwi_uk["values"]]
        uk_cash = [float(v) for v in acwi_uk["cash"]]
        uk_xirr = acwi_uk.get("xirr_pct")

        left_series: list[
            tuple[Sequence[date], Sequence[float], str, float | None, str, float, str, int]
        ] = []
        acwi_b = common_9y.get("acwi_bench")
        if acwi_b and acwi_b.get("values"):
            left_series.append(
                (
                    acwi_b["dates"],
                    acwi_b["values"],
                    "ACWI ETF",
                    acwi_b.get("xirr_pct"),
                    "#8D939E",
                    1.4,
                    ":",
                    0,
                )
            )
        sp9 = common_9y.get("sp500")
        sp_9y_end: float | None = None
        if sp9 and sp9.get("values"):
            sp9_vals = [float(v) for v in sp9["values"]]
            sp_9y_end = sp9_vals[-1]
            left_series.append(
                (
                    sp9["dates"],
                    sp9_vals,
                    "S&P 500",
                    sp9.get("xirr_pct"),
                    SERIES_COLORS["bench"],
                    1.7,
                    "--",
                    0,
                )
            )
        us9 = common_9y.get("us_top3")
        if us9 and us9.get("values"):
            left_series.append(
                (
                    us9["dates"],
                    us9["values"],
                    "US Top 3",
                    us9.get("xirr_pct"),
                    SERIES_COLORS["top5"],
                    1.85,
                    "-",
                    0,
                )
            )
        left_series.append(
            (uk_dates, uk_vals, "All World UK ISA", uk_xirr, SERIES_COLORS["top3"], 2.5, "-", 1)
        )

        yrs_9y = max(1, len(uk_dates) // 12)
        denom_9y = (
            sp_9y_end
            if sp_9y_end and sp_9y_end > 0.0
            else (
                float(acwi_b["values"][-1])
                if acwi_b and acwi_b.get("values") and float(acwi_b["values"][-1]) > 0.0
                else None
            )
        )
        ratio_9y = (uk_vals[-1] / denom_9y) if denom_9y else None
        ratio_20y = (us_20y_end / sp_20y_end) if sp_20y_end and sp_20y_end > 0.0 else None

        if ratio_9y is not None and ratio_20y is not None:
            title = (
                f"Investing {mo_lbl}/month in Top 3 winners beat the S&P 500 by "
                f"{ratio_9y:.1f}x over {yrs_9y}y and {ratio_20y:.1f}x over {yrs_20y}y"
            )
        elif ratio_9y is not None:
            title = (
                f"All World (UK ISA) Top 3 returned {ratio_9y:.1f}x an index tracker "
                f"at {mo_lbl}/month"
            )
        else:
            title = f"Investing {mo_lbl}/month in Top 3 winners vs index trackers"

        fig = plt.figure(figsize=(14.0, 6.0), dpi=180, facecolor=PAPER_BG)
        gs = fig.add_gridspec(1, 2, wspace=0.58)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])

        c9_win = f"{common_9y['start_window']}..{common_9y['end_window']}"
        c9_cash_txt = _format_compact_value(currency_symbol, uk_cash[-1])
        c20_cash_txt = _format_compact_value(currency_symbol, us_cash[-1])
        _plot_dca_hero_panel(
            ax1,
            left_series,
            uk_dates,
            uk_cash,
            panel_title=f"Same {yrs_9y}-year window ({c9_win})",
            panel_subtitle=f"Apples-to-apples · {c9_cash_txt} cash put in ({mo_lbl}/mo)",
            currency_symbol=currency_symbol,
            show_events=False,
        )
        _plot_dca_hero_panel(
            ax2,
            right_series,
            us_dates,
            us_cash,
            panel_title=f"Full {yrs_20y}-year US test ({start_20y}–{end_20y})",
            panel_subtitle=f"Includes 2008 crash & delistings · {c20_cash_txt} put in",
            currency_symbol=currency_symbol,
            show_events=True,
        )
        _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.052)
        fig.subplots_adjust(left=0.052, right=0.865, top=0.765, bottom=0.115, wspace=0.58)
    else:
        ratio_20y = (us_20y_end / sp_20y_end) if sp_20y_end and sp_20y_end > 0.0 else None
        if ratio_20y is not None:
            title = (
                f"Investing {mo_lbl}/month in US Top 3 winners beat the S&P 500 by {ratio_20y:.1f}x"
            )
        else:
            title = f"Investing {mo_lbl}/month in US Top 3 winners vs index tracker"

        fig = plt.figure(figsize=(11.4, 5.4), dpi=180, facecolor=PAPER_BG)
        ax = fig.add_subplot(1, 1, 1)
        _plot_dca_hero_panel(
            ax,
            right_series,
            us_dates,
            us_cash,
            panel_title=f"US S&P 500 Top 3 ({start_20y}–{end_20y})",
            panel_subtitle=(
                f"{_format_compact_value(currency_symbol, us_cash[-1])} cash put in ({mo_lbl}/mo)"
            ),
            currency_symbol=currency_symbol,
            show_events=True,
        )
        _draw_top_rule_and_headers(fig, title, subtitle, footer_note, left=0.075)
        fig.subplots_adjust(left=0.075, right=0.835, top=0.77, bottom=0.12)

    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path
