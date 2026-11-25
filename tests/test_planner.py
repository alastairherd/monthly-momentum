"""Tests for monthly cash allocation planner and Rule 8 fees."""

from __future__ import annotations

import pytest

from monthly_momentum.models import Holding, HoldingStatus, SecurityMetric
from monthly_momentum.planner import build_monthly_plan
from monthly_momentum.ranking import rank_securities


def test_monthly_plan_equal_split_fees_and_warnings() -> None:
    ranking = rank_securities(
        [
            SecurityMetric("NVDA", "NVIDIA", "S&P 500", 500.0, 12.0, "total_return", "test"),
            SecurityMetric("AVGO", "Broadcom", "S&P 500", 300.0, 5.0, "total_return", "test"),
            SecurityMetric("LLY", "Eli Lilly", "S&P 500", 200.0, 3.0, "total_return", "test"),
        ],
        month="2026-11",
        top_n=3,
    )
    holdings = [
        Holding("NVDA", "NVIDIA", "S&P 500", "2025-01-02", "2026-10", HoldingStatus.HOLDING),
        Holding("OLD", "Old Winner", "S&P 500", "2018-01-02", "2020-11", HoldingStatus.HOLDING),
    ]

    plan = build_monthly_plan(
        ranking=ranking,
        holdings=holdings,
        contribution=500.0,
        rule6_cash=100.0,
        takeover_cash=300.0,
        currency="GBP",
        market="us",
    )

    assert plan.total_investable == 900.0
    assert plan.fee_pct == 0.15
    assert len(plan.allocations) == 3
    assert plan.allocations[0].gross_amount == 300.0
    assert plan.allocations[0].estimated_fee == pytest.approx(0.45, abs=0.01)
    assert plan.allocations[0].already_held is True
    assert plan.allocations[1].already_held is False

    uk_plan = build_monthly_plan(ranking=ranking, holdings=[], contribution=600.0, market="uk")
    assert uk_plan.fee_pct == 0.50
    assert uk_plan.allocations[0].estimated_fee == pytest.approx(1.0, abs=0.01)

    agg_ranking = rank_securities(
        [SecurityMetric("NVDA", "NVIDIA", "S&P 500", 500.0, 12.0, "total_return", "test")],
        month="2026-11",
        top_n=1,
    )
    agg_plan = build_monthly_plan(agg_ranking, holdings=[], contribution=500.0)
    assert any("-76%" in w for w in agg_plan.warnings)
