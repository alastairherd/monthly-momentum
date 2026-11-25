"""Survivorship-bias-free backtesting package for Monthly Momentum."""

from monthly_momentum.backtest.data import (
    BacktestDataset,
    ConstituentInterval,
    CorporateEvent,
    PricePoint,
    load_backtest_dataset,
)
from monthly_momentum.backtest.engine import (
    BacktestConfig,
    BacktestResult,
    MonthlyBacktestPoint,
    VariantSummary,
    compare_variants,
    run_backtest,
)
from monthly_momentum.backtest.metrics import (
    BacktestMetrics,
    DrawdownStats,
    RollingComparison,
    compute_backtest_metrics,
    compute_max_drawdown,
    compute_rolling_outperformance,
    compute_xirr,
)

__all__ = [
    "BacktestConfig",
    "BacktestDataset",
    "BacktestMetrics",
    "BacktestResult",
    "ConstituentInterval",
    "CorporateEvent",
    "DrawdownStats",
    "MonthlyBacktestPoint",
    "PricePoint",
    "RollingComparison",
    "VariantSummary",
    "compare_variants",
    "compute_backtest_metrics",
    "compute_max_drawdown",
    "compute_rolling_outperformance",
    "compute_xirr",
    "load_backtest_dataset",
    "run_backtest",
]
