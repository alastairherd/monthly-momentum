"""Tests for monthly ranking rules and template CSV roundtripping."""

from __future__ import annotations

import csv
from pathlib import Path

from monthly_momentum.models import SecurityMetric
from monthly_momentum.ranking import rank_securities, read_ranking_csv, write_ranking_csv


def _make_metric(ticker: str, r3y: float | None, r3m: float | None) -> SecurityMetric:
    return SecurityMetric(
        ticker=ticker,
        name=f"{ticker} Inc",
        index="S&P 500",
        return_3y_pct=r3y,
        return_3m_pct=r3m,
        return_type="total_return",
        source="test",
    )


def test_rank_securities_exclusions_ties_and_template_parity(tmp_path: Path) -> None:
    metrics = [
        _make_metric("DROP_NEG", 999.0, -0.01),
        _make_metric("DROP_NEW", None, 10.0),
        _make_metric("DROP_3M", 120.0, None),
        _make_metric("ZERO_3M", 50.0, 0.0),
        _make_metric("TIE_B", 200.0, 5.0),
        _make_metric("TIE_A", 200.0, 10.0),
        _make_metric("TOP1", 350.0, 15.0),
        _make_metric("FOURTH", 150.0, 3.0),
    ]

    result = rank_securities(metrics, month="2026-11", top_n=3)
    assert [r.ticker for r in result.ranked] == ["TOP1", "TIE_A", "TIE_B", "FOURTH", "ZERO_3M"]
    assert [r.ticker for r in result.top_picks] == ["TOP1", "TIE_A", "TIE_B"]
    assert [e.reason for e in result.excluded] == [
        "negative_3m_return",
        "missing_3y_return",
        "missing_3m_return",
    ]

    out_csv = tmp_path / "ranking.csv"
    write_ranking_csv(result, out_csv, limit=10)

    template_path = (
        Path(__file__).resolve().parent.parent / "templates" / "monthly-ranking.example.csv"
    )
    with template_path.open("r", encoding="utf-8") as tf, out_csv.open("r", encoding="utf-8") as of:
        assert next(csv.reader(tf)) == next(csv.reader(of))

    loaded = read_ranking_csv(out_csv)
    assert len(loaded) == 5
    assert loaded[0].selected_for_buy is True
    assert loaded[3].selected_for_buy is False
