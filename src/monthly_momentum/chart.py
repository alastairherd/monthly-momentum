"""FT-inspired broadsheet editorial performance charts using headless Matplotlib."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from datetime import date, timedelta
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


def _squarify(values: Sequence[float], x: float, y: float, w: float, h: float) -> list[tuple]:
    """Squarified treemap layout: returns (x, y, w, h) per value, in input order."""
    total = float(sum(values))
    if total <= 0.0 or not values:
        return [(x, y, 0.0, 0.0) for _ in values]
    order = sorted(range(len(values)), key=lambda i: -values[i])
    scaled = {i: values[i] / total * w * h for i in order}
    rects: dict[int, tuple] = {}

    def _worst(row: list[int], side: float) -> float:
        s = sum(scaled[i] for i in row)
        mx, mn = max(scaled[i] for i in row), min(scaled[i] for i in row)
        if s <= 0 or mn <= 0:
            return math.inf
        return max(side * side * mx / (s * s), (s * s) / (side * side * mn))

    remaining = list(order)
    cx, cy, cw, ch = x, y, w, h
    while remaining:
        side = min(cw, ch)
        row = [remaining.pop(0)]
        while remaining and _worst([*row, remaining[0]], side) <= _worst(row, side):
            row.append(remaining.pop(0))
        row_area = sum(scaled[i] for i in row)
        if cw >= ch:  # lay the row as a column on the left
            col_w = row_area / ch if ch > 0 else 0.0
            yy = cy
            for i in row:
                hh = scaled[i] / col_w if col_w > 0 else 0.0
                rects[i] = (cx, yy, col_w, hh)
                yy += hh
            cx, cw = cx + col_w, cw - col_w
        else:  # lay the row along the top
            row_h = row_area / cw if cw > 0 else 0.0
            xx = cx
            for i in row:
                ww = scaled[i] / row_h if row_h > 0 else 0.0
                rects[i] = (xx, cy + ch - row_h, ww, row_h)
                xx += ww
            ch -= row_h
    return [rects[i] for i in range(len(values))]


def generate_live_tracker_chart(tracker: Any, series: Any, output_path: Path) -> Path:
    """Render the live tracker: treemap of what the portfolio holds + race vs the benchmark.

    ``tracker``/``series`` are ``monthly_momentum.tracker.LiveTracker``/``LiveSeries``.
    """
    pts = series.points
    if not pts:
        raise ValueError("Cannot render the live tracker chart from an empty series.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    latest = pts[-1]
    sym = "$"
    amount = tracker.monthly_amount
    color_for = {
        tk: HERO_BAND_COLORS[i % len(HERO_BAND_COLORS)] for i, tk in enumerate(tracker.tickers)
    }

    fig = plt.figure(figsize=(12.0, 6.4), facecolor=PAPER_BG)
    port_ret = round((latest.total / latest.cash - 1.0) * 100.0, 1) + 0.0
    bench_ret = round((latest.benchmark / latest.cash - 1.0) * 100.0, 1) + 0.0
    start_s = f"{tracker.inception:%-d %b %Y}"
    title = f"Live: {sym}{amount:.0f}/month in the All World Top 3, since {start_s}"
    n_sessions = len(pts)
    subtitle = (
        f"{tracker.universe} · equal thirds into each month's Top 3 · "
        f"{sym}{latest.cash:,.0f} put in so far · marked at the {latest.date:%-d %b %Y} close "
        f"({n_sessions} session{'s' if n_sessions != 1 else ''})"
    )
    granularity = (
        f"daily closes to {series.daily_through:%b %Y}, month-end after"
        if series.daily_through
        else "daily closes"
    )
    _draw_top_rule_and_headers(
        fig,
        title,
        subtitle,
        footer_left=(
            f"Source: Yahoo Finance dividend-adjusted {granularity}. "
            "Real forward record, not a backtest. Not financial advice."
        ),
        footer_right="Monthly Momentum · Live tracker",
        left=0.05,
    )

    # ---- Left: treemap of current holdings (area = value today) ----
    notes = [n for n in getattr(tracker, "notes", []) if n.get("text")]
    lift = 0.035 * len(notes)
    ax_t = fig.add_axes((0.05, 0.10 + lift, 0.44, 0.70 - lift))
    ax_t.set_xlim(0, 1)
    ax_t.set_ylim(0, 1)
    ax_t.axis("off")
    ax_t.text(
        0.0,
        1.035,
        "What it holds now — area is today's value",
        transform=ax_t.transAxes,
        ha="left",
        va="bottom",
        fontsize=10.5,
        fontweight="bold",
        color=INK_DARK,
    )
    holdings = list(series.holdings)
    rects = _squarify([max(h.value, 1e-9) for h in holdings], 0.0, 0.0, 1.0, 1.0)
    gap = 0.006
    for h, (rx, ry, rw, rh) in zip(holdings, rects, strict=True):
        color = color_for.get(h.ticker, OTHER_BAND_COLOR)
        ax_t.add_patch(
            plt.Rectangle(
                (rx + gap, ry + gap),
                max(rw - 2 * gap, 0),
                max(rh - 2 * gap, 0),
                facecolor=color,
                edgecolor=PAPER_BG,
                linewidth=0,
            )
        )
        ink = _text_color_for(color)
        if rw * rh < 0.012:
            continue
        big = rw > 0.22 and rh > 0.22
        weight = h.value / latest.total * 100.0 if latest.total > 0 else 0.0
        lx, ly = rx + 0.025, ry + rh - 0.03
        ax_t.text(
            lx,
            ly,
            h.ticker,
            ha="left",
            va="top",
            color=ink,
            fontsize=20 if big else 11,
            fontweight="bold",
        )
        if big:
            ax_t.text(
                lx,
                ly - 0.085,
                h.name.title()[:28],
                ha="left",
                va="top",
                color=ink,
                fontsize=9.5,
                alpha=0.9,
            )
        ax_t.text(
            lx,
            ry + 0.03,
            f"{sym}{h.value:,.2f} · {weight:.0f}% of portfolio\n"
            f"{round(h.return_pct, 1) + 0.0:+.1f}% on {sym}{h.invested:,.2f} in",
            ha="left",
            va="bottom",
            color=ink,
            fontsize=10 if big else 8,
            linespacing=1.4,
        )

    # ---- Right: portfolio vs benchmark, same cash ----
    ax = fig.add_axes((0.565, 0.13 + lift, 0.30, 0.67 - lift))
    _style_editorial_axis(ax)
    dates = [p.date for p in pts]
    totals = [p.total for p in pts]
    benches = [p.benchmark for p in pts]
    cash = [p.cash for p in pts]
    port_c = SERIES_COLORS["top3"]
    bench_c = SERIES_COLORS["bench"]
    single = len(pts) == 1
    mk = 7 if single else (4 if len(pts) <= 40 else 0)
    ax.plot(
        dates, cash, color=INK_MUTED, linestyle=":", linewidth=1.2, drawstyle="steps-post", zorder=2
    )
    ax.plot(
        dates,
        benches,
        color=bench_c,
        linestyle="--",
        linewidth=1.6,
        marker="o",
        markersize=mk,
        zorder=3,
    )
    ax.plot(
        dates,
        totals,
        color=port_c,
        linestyle="-",
        linewidth=2.4,
        marker="o",
        markersize=mk + 1 if mk else 0,
        zorder=4,
    )
    ax.yaxis.set_major_formatter(_make_currency_formatter(sym))

    lo = min([*totals, *benches, *cash])
    hi = max([*totals, *benches, *cash])
    pad = max((hi - lo) * 0.15, hi * 0.04)
    ax.set_ylim(lo - pad, hi + pad)
    span = (dates[-1] - dates[0]).days
    if single:
        ax.set_xlim(dates[0] - timedelta(days=3), dates[0] + timedelta(days=3))
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d %b"))
        if not notes:
            ax.text(
                0.5,
                0.18,
                "Day one: both start from the same cash.\n"
                "A new point lands after every market close.",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=8.8,
                color=INK_SUB,
            )
    elif span <= 92:
        ax.set_xlim(dates[0] - timedelta(days=1), dates[-1] + timedelta(days=1))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=7))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d %b"))
    else:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=7))
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.text(
        0.0,
        1.035,
        f"Portfolio vs the same cash in the {tracker.benchmark_label}",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10.5,
        fontweight="bold",
        color=INK_DARK,
    )

    labels = [
        (latest.total, f"Top 3 portfolio\n{sym}{latest.total:,.2f} ({port_ret:+.1f}%)", port_c),
        (
            latest.benchmark,
            f"{tracker.benchmark_label}\n{sym}{latest.benchmark:,.2f} ({bench_ret:+.1f}%)",
            bench_c,
        ),
        (latest.cash, f"Cash in\n{sym}{latest.cash:,.0f}", INK_MUTED),
    ]
    y0, y1 = ax.get_ylim()
    frac = sorted(((v - y0) / (y1 - y0), txt, c) for v, txt, c in labels)
    placed: list[float] = []
    min_gap = 0.14
    for f, _txt, _c in frac:
        f = max(f, placed[-1] + min_gap) if placed else f
        placed.append(f)
    if placed and placed[-1] > 1.0:
        shift = placed[-1] - 1.0
        placed = [p - shift for p in placed]
    for (_f, txt, c), fy in zip(frac, placed, strict=True):
        ax.text(
            1.03,
            fy,
            txt,
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=8.8,
            color=c,
            fontweight="bold" if c != INK_MUTED else "normal",
            linespacing=1.25,
        )

    for k, note in enumerate(notes):
        try:
            note_day = date.fromisoformat(note["date"])
        except (KeyError, ValueError):
            continue
        marker = str(k + 1)
        if dates[0] <= note_day <= dates[-1]:
            note_x = float(mdates.date2num(note_day))
            ax.axvline(note_x, color=EVENT_COLOR, linestyle="--", linewidth=0.9, zorder=1)
            ax.text(
                note_x,
                0.97,
                f" {marker} {note.get('label', '')}".rstrip(),
                transform=ax.get_xaxis_transform(),
                ha="left",
                va="top",
                fontsize=8.4,
                fontweight="bold",
                color=EVENT_COLOR,
            )
        fig.text(
            0.05,
            0.05 + 0.035 * (len(notes) - 1 - k),
            f"{marker}  {note_day:%-d %b %Y}: {note['text']}",
            ha="left",
            va="bottom",
            fontsize=8.6,
            color=INK_SUB,
        )

    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path


def generate_stock_contribution_chart(
    panels: Sequence[Mapping[str, Any]],
    output_path: Path,
    *,
    title: str,
    subtitle: str,
    footer_note: str,
    currency_symbol: str = "$",
) -> Path:
    """Stacked value-by-stock areas, one panel per backtest, showing which shares drove gains.

    Each panel mapping holds ``label``, ``dates``, ``cash`` (cumulative contributions),
    ``bands`` (ordered ``(ticker, values)`` pairs, largest final value first), ``other``
    (value of every remaining holding), and ``names`` (ticker → company name).
    """
    if not panels:
        raise ValueError("Cannot render the stock contribution chart without panels.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sym = currency_symbol

    fig = plt.figure(figsize=(14.5, 6.6), facecolor=PAPER_BG)
    _draw_top_rule_and_headers(fig, title, subtitle, footer_left=footer_note, left=0.055)
    slot = 0.95 / len(panels)
    for idx, panel in enumerate(panels):
        ax = fig.add_axes((0.055 + idx * slot, 0.12, slot - 0.235, 0.66))
        _style_editorial_axis(ax)
        dates = list(panel["dates"])
        bands: list[tuple[str, list[float]]] = list(panel["bands"])
        other = [max(0.0, v) for v in panel["other"]]
        cash = list(panel["cash"])
        names: Mapping[str, str] = panel.get("names", {})

        # Bottom → top: other holdings, then named bands smallest-first so the biggest
        # winner sits on top where the curve ends.
        stack_keys = ["Other", *[tk for tk, _ in reversed(bands)]]
        stack_vals = [other, *[[max(0.0, v) for v in vals] for _, vals in reversed(bands)]]
        colors = [OTHER_BAND_COLOR] + [
            HERO_BAND_COLORS[(len(bands) - 1 - i) % len(HERO_BAND_COLORS)]
            for i in range(len(bands))
        ]
        ax.stackplot(dates, stack_vals, colors=colors, linewidth=0.0, alpha=0.95, zorder=2)
        ax.plot(dates, cash, color=INK_DARK, linestyle=":", linewidth=1.3, zorder=4)
        ax.yaxis.set_major_formatter(_make_currency_formatter(sym))
        ax.set_xlim(dates[0], dates[-1])
        ax.set_ylim(0, None)
        ax.xaxis.set_major_locator(mdates.YearLocator(base=4 if len(dates) > 150 else 2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.text(
            0.0,
            1.035,
            str(panel["label"]),
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=10.5,
            fontweight="bold",
            color=INK_DARK,
        )

        total_final = sum(vals[-1] for vals in stack_vals)
        y_top = ax.get_ylim()[1]
        # Label each band at its final-value midpoint, nudged apart to avoid overlaps.
        mids: list[tuple[float, str, str]] = []
        base = 0.0
        invested: Mapping[str, float] = panel.get("invested", {})
        for key, vals, color in zip(stack_keys, stack_vals, colors, strict=True):
            v = vals[-1]
            share = v / total_final * 100.0 if total_final > 0 else 0.0
            paid = invested.get(key)
            growth = (
                f"  {_format_compact_value(sym, paid)} → {_format_compact_value(sym, v)}"
                + (f" ({v / paid:.0f}×)" if v / paid >= 10 else f" ({v / paid:.1f}×)")
                if paid
                else f"  {_format_compact_value(sym, v)}"
            )
            if key == "Other":
                txt = f"Everything else{growth} · {share:.0f}%"
                ink = INK_SUB
            else:
                txt = f"{key}{growth} · {share:.0f}%"
                ink = color
            mids.append(((base + v / 2.0) / y_top, txt, ink))
            base += v
        mids.sort(key=lambda m: m[0])
        placed: list[float] = []
        for f, _t, _c in mids:
            placed.append(max(f, placed[-1] + 0.058) if placed else max(f, 0.03))
        if placed and placed[-1] > 0.98:
            shift = placed[-1] - 0.98
            placed = [max(0.0, p - shift) for p in placed]
            for i in range(1, len(placed)):
                placed[i] = max(placed[i], placed[i - 1] + 0.058)
        for (f, txt, ink), fy in zip(mids, placed, strict=True):
            ax.annotate(
                txt,
                xy=(1.0, f),
                xycoords="axes fraction",
                xytext=(1.03, fy),
                textcoords="axes fraction",
                ha="left",
                va="center",
                fontsize=8.4,
                color=ink,
                fontweight="bold",
                arrowprops={"arrowstyle": "-", "color": LEADER_COLOR, "linewidth": 0.6},
            )
        cash_final = cash[-1]
        ax.text(
            0.02,
            0.96,
            f"{_format_compact_value(sym, cash_final)} put in (dotted) became "
            f"{_format_compact_value(sym, total_final)}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9.0,
            color=INK_SUB,
        )
        top_names = ", ".join(names.get(tk, tk).title() for tk, _ in bands[:2])
        if top_names:
            ax.text(
                0.02,
                0.90,
                f"Biggest: {top_names}",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8.4,
                color=INK_MUTED,
            )

    fig.savefig(output_path, dpi=180, facecolor=PAPER_BG)
    plt.close(fig)
    return output_path
