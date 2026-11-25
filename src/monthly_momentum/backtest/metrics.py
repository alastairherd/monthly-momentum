"""Performance metrics: XIRR, TWR CAGR, max drawdown, Sharpe, and 5y rolling win rate."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class DrawdownStats:
    """Maximum drawdown details on a time-weighted NAV series."""

    max_drawdown_pct: float
    peak_date: date | None
    trough_date: date | None
    recovery_date: date | None


@dataclass(slots=True)
class RollingComparison:
    """Rule 8 5-year rolling outperformance comparison against benchmark."""

    window_months: int
    windows_count: int
    win_count: int
    win_rate_pct: float
    avg_excess_cagr_pct: float


@dataclass(slots=True)
class BacktestMetrics:
    """Consolidated strategy vs benchmark summary metrics."""

    start_month: str
    end_month: str
    months_invested: int
    total_contributed: float
    ending_value: float
    total_profit: float
    total_return_pct: float
    xirr_pct: float | None
    twr_cagr_pct: float | None
    max_drawdown_pct: float
    drawdown_peak_date: date | None
    drawdown_trough_date: date | None
    drawdown_recovery_date: date | None
    annualized_volatility_pct: float | None
    sharpe_ratio: float | None
    total_fees_paid: float
    rule6_exits_count: int
    takeover_events_count: int
    benchmark_ending_value: float | None
    benchmark_xirr_pct: float | None
    benchmark_twr_cagr_pct: float | None
    benchmark_max_drawdown_pct: float | None
    rolling_5y: RollingComparison | None


def _xnpv(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    base_date = cash_flows[0][0]
    total = 0.0
    for dt, amount in cash_flows:
        years = (dt - base_date).days / 365.25
        total += amount / ((1.0 + rate) ** years)
    return total


def compute_xirr(cash_flows: list[tuple[date, float]]) -> float | None:
    """Compute annualized money-weighted XIRR (%) via bracketed bisection."""
    if len(cash_flows) < 2:
        return None
    ordered = sorted(cash_flows, key=lambda item: item[0])
    has_neg = any(amt < 0 for _, amt in ordered)
    has_pos = any(amt > 0 for _, amt in ordered)
    if not (has_neg and has_pos):
        return None
    if (ordered[-1][0] - ordered[0][0]).days <= 0:
        return None

    low = -0.99
    high = 10.0
    f_low = _xnpv(low, ordered)
    f_high = _xnpv(high, ordered)

    attempts = 0
    while f_low * f_high > 0 and high < 1000.0 and attempts < 10:
        high *= 2.0
        f_high = _xnpv(high, ordered)
        attempts += 1

    if f_low * f_high > 0:
        return None

    for _ in range(120):
        mid = 0.5 * (low + high)
        f_mid = _xnpv(mid, ordered)
        if abs(f_mid) < 1e-8 or (high - low) < 1e-9:
            return mid * 100.0
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return 0.5 * (low + high) * 100.0


def compute_max_drawdown(dates: list[date], nav_series: list[float]) -> DrawdownStats:
    """Compute maximum percentage drawdown on a time-weighted NAV curve."""
    if not dates or len(dates) != len(nav_series):
        return DrawdownStats(0.0, None, None, None)

    peak_val = nav_series[0]
    peak_dt = dates[0]
    max_dd = 0.0
    best_peak_dt: date | None = dates[0]
    best_trough_dt: date | None = dates[0]
    best_peak_val = peak_val
    trough_idx = 0

    for i, (dt, val) in enumerate(zip(dates, nav_series, strict=True)):
        if val > peak_val:
            peak_val = val
            peak_dt = dt
        if peak_val > 0.0:
            dd = (val / peak_val - 1.0) * 100.0
            if dd < max_dd:
                max_dd = dd
                best_peak_dt = peak_dt
                best_trough_dt = dt
                best_peak_val = peak_val
                trough_idx = i

    recovery_dt: date | None = None
    if max_dd < 0.0:
        for dt, val in zip(dates[trough_idx + 1 :], nav_series[trough_idx + 1 :], strict=True):
            if val >= best_peak_val:
                recovery_dt = dt
                break
    else:
        best_peak_dt = None
        best_trough_dt = None

    return DrawdownStats(
        max_drawdown_pct=max_dd,
        peak_date=best_peak_dt,
        trough_date=best_trough_dt,
        recovery_date=recovery_dt,
    )


def compute_twr_cagr_pct(dates: list[date], nav_series: list[float]) -> float | None:
    """Compute annualized time-weighted CAGR (%) from a NAV curve."""
    if len(dates) < 2 or len(dates) != len(nav_series):
        return None
    start_val = nav_series[0]
    end_val = nav_series[-1]
    days = (dates[-1] - dates[0]).days
    if start_val <= 0.0 or end_val <= 0.0 or days <= 0:
        return None
    years = days / 365.25
    return ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0


def compute_rolling_outperformance(
    dates: list[date],
    strategy_nav: list[float],
    benchmark_nav: list[float],
    window_months: int = 60,
) -> RollingComparison | None:
    """Compare rolling ``window_months`` annualized returns against benchmark."""
    n = len(dates)
    if (
        n <= window_months
        or len(strategy_nav) != n
        or len(benchmark_nav) != n
        or window_months <= 0
    ):
        return None

    wins = 0
    excess_rates: list[float] = []
    years = window_months / 12.0
    for i in range(window_months, n):
        s0, s1 = strategy_nav[i - window_months], strategy_nav[i]
        b0, b1 = benchmark_nav[i - window_months], benchmark_nav[i]
        if s0 <= 0.0 or b0 <= 0.0 or s1 <= 0.0 or b1 <= 0.0:
            continue
        s_cagr = ((s1 / s0) ** (1.0 / years) - 1.0) * 100.0
        b_cagr = ((b1 / b0) ** (1.0 / years) - 1.0) * 100.0
        diff = s_cagr - b_cagr
        excess_rates.append(diff)
        if s_cagr > b_cagr:
            wins += 1

    if not excess_rates:
        return None
    count = len(excess_rates)
    return RollingComparison(
        window_months=window_months,
        windows_count=count,
        win_count=wins,
        win_rate_pct=(wins / count) * 100.0,
        avg_excess_cagr_pct=sum(excess_rates) / count,
    )


def compute_backtest_metrics(
    start_month: str,
    end_month: str,
    months_invested: int,
    dates: list[date],
    nav_series: list[float],
    cash_flows: list[tuple[date, float]],
    total_contributed: float,
    ending_value: float,
    total_fees_paid: float,
    rule6_exits_count: int,
    takeover_events_count: int,
    benchmark_nav: list[float] | None = None,
    benchmark_cash_flows: list[tuple[date, float]] | None = None,
    benchmark_ending_value: float | None = None,
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """Compute full strategy and benchmark comparison metrics."""
    profit = ending_value - total_contributed
    total_return_pct = (profit / total_contributed * 100.0) if total_contributed > 0.0 else 0.0
    xirr_pct = compute_xirr(cash_flows)
    twr_cagr_pct = compute_twr_cagr_pct(dates, nav_series)
    dd = compute_max_drawdown(dates, nav_series)

    monthly_returns = [
        nav_series[i] / nav_series[i - 1] - 1.0
        for i in range(1, len(nav_series))
        if nav_series[i - 1] > 0.0
    ]
    ann_vol_pct: float | None = None
    sharpe: float | None = None
    if len(monthly_returns) >= 2:
        mean_r = sum(monthly_returns) / len(monthly_returns)
        var = sum((r - mean_r) ** 2 for r in monthly_returns) / (len(monthly_returns) - 1)
        std_m = math.sqrt(var)
        ann_vol = std_m * math.sqrt(12.0)
        ann_vol_pct = ann_vol * 100.0
        if ann_vol > 0.0 and twr_cagr_pct is not None:
            sharpe = ((twr_cagr_pct / 100.0) - risk_free_rate) / ann_vol

    bench_xirr = compute_xirr(benchmark_cash_flows) if benchmark_cash_flows else None
    bench_cagr = (
        compute_twr_cagr_pct(dates, benchmark_nav)
        if benchmark_nav is not None and len(benchmark_nav) == len(dates)
        else None
    )
    bench_dd = (
        compute_max_drawdown(dates, benchmark_nav).max_drawdown_pct
        if benchmark_nav is not None and len(benchmark_nav) == len(dates)
        else None
    )
    rolling_5y = (
        compute_rolling_outperformance(dates, nav_series, benchmark_nav, window_months=60)
        if benchmark_nav is not None and len(benchmark_nav) == len(dates)
        else None
    )

    return BacktestMetrics(
        start_month=start_month,
        end_month=end_month,
        months_invested=months_invested,
        total_contributed=total_contributed,
        ending_value=ending_value,
        total_profit=profit,
        total_return_pct=total_return_pct,
        xirr_pct=xirr_pct,
        twr_cagr_pct=twr_cagr_pct,
        max_drawdown_pct=dd.max_drawdown_pct,
        drawdown_peak_date=dd.peak_date,
        drawdown_trough_date=dd.trough_date,
        drawdown_recovery_date=dd.recovery_date,
        annualized_volatility_pct=ann_vol_pct,
        sharpe_ratio=sharpe,
        total_fees_paid=total_fees_paid,
        rule6_exits_count=rule6_exits_count,
        takeover_events_count=takeover_events_count,
        benchmark_ending_value=benchmark_ending_value,
        benchmark_xirr_pct=bench_xirr,
        benchmark_twr_cagr_pct=bench_cagr,
        benchmark_max_drawdown_pct=bench_dd,
        rolling_5y=rolling_5y,
    )
