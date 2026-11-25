"""Tests for holdings CSV persistence and Rule 6 staged-exit logic."""

from __future__ import annotations

import csv
from pathlib import Path

from monthly_momentum.holdings import (
    apply_monthly_run_to_holdings,
    evaluate_rule6,
    read_holdings_csv,
    record_manual_exit,
    record_takeover,
    write_holdings_csv,
)
from monthly_momentum.models import (
    Holding,
    HoldingStatus,
    Rule6ActionType,
    SecurityMetric,
)
from monthly_momentum.ranking import rank_securities


def _holding(
    ticker: str,
    last_top10: str,
    status: HoldingStatus = HoldingStatus.HOLDING,
    extra: dict[str, str] | None = None,
) -> Holding:
    return Holding(
        ticker=ticker,
        name=f"{ticker} Corp",
        index="S&P 500",
        first_bought_date=f"{last_top10}-01",
        last_top10_month=last_top10,
        status=status,
        notes="",
        extra=extra or {},
    )


def test_rule6_thresholds_and_resets() -> None:
    holdings = [
        _holding("H71", "2020-12"),  # 71m in 2026-11 -> HOLD
        _holding("H72", "2020-11"),  # 72m -> SELL_THIRD
        _holding("S1_73", "2020-10", HoldingStatus.RULE6_STAGE1_SOLD),  # 73m -> HOLD
        _holding("S1_84", "2019-11", HoldingStatus.RULE6_STAGE1_SOLD),  # 84m -> SELL_HALF
        _holding("S0_85", "2019-10", HoldingStatus.HOLDING),  # 85m missed stage 1 -> SELL_HALF
        _holding("S2_95", "2018-12", HoldingStatus.RULE6_STAGE2_SOLD),  # 95m -> HOLD
        _holding("S2_96", "2018-11", HoldingStatus.RULE6_STAGE2_SOLD),  # 96m -> SELL_REMAINING
        _holding("BACK", "2019-01", HoldingStatus.RULE6_STAGE1_SOLD),  # returns to top10 -> RESET
    ]

    recs = evaluate_rule6(holdings, run_month="2026-11", top10_tickers={"BACK"}, enabled=True)
    by_t = {r.holding.ticker: r for r in recs}

    assert by_t["H71"].action == Rule6ActionType.HOLD
    assert by_t["H72"].action == Rule6ActionType.SELL_THIRD
    assert by_t["H72"].next_status == HoldingStatus.RULE6_STAGE1_SOLD
    assert by_t["S1_73"].action == Rule6ActionType.HOLD
    assert by_t["S1_84"].action == Rule6ActionType.SELL_HALF
    assert by_t["S1_84"].next_status == HoldingStatus.RULE6_STAGE2_SOLD
    assert by_t["S0_85"].action == Rule6ActionType.SELL_HALF
    assert by_t["S2_95"].action == Rule6ActionType.HOLD
    assert by_t["S2_96"].action == Rule6ActionType.SELL_REMAINING
    assert by_t["S2_96"].next_status == HoldingStatus.SOLD
    assert by_t["BACK"].action == Rule6ActionType.RESET_TOP10
    assert by_t["BACK"].next_status == HoldingStatus.HOLDING


def test_apply_run_rebuy_after_exit_and_template_parity(tmp_path: Path) -> None:
    holdings = [
        _holding("NVDA", "2018-01", HoldingStatus.SOLD, extra={"broker": "Freetrade"}),
        _holding("MSFT", "2020-11", HoldingStatus.HOLDING, extra={"broker": "Freetrade"}),
    ]
    ranking = rank_securities(
        [
            SecurityMetric("NVDA", "NVIDIA", "S&P 500", 500.0, 12.0, "total_return", "test"),
            SecurityMetric("AVGO", "Broadcom", "S&P 500", 300.0, 5.0, "total_return", "test"),
            SecurityMetric("LLY", "Eli Lilly", "S&P 500", 200.0, 3.0, "total_return", "test"),
        ],
        month="2026-11",
        top_n=3,
    )

    updated, _ = apply_monthly_run_to_holdings(
        holdings,
        ranking=ranking,
        run_month="2026-11",
        buy_date="2026-11-02",
        apply_rule6_sells=True,
    )
    # Closed NVDA row preserved + new active NVDA row added.
    nvda_rows = [h for h in updated if h.ticker == "NVDA"]
    assert len(nvda_rows) == 2
    assert nvda_rows[0].status == HoldingStatus.SOLD
    assert nvda_rows[1].status == HoldingStatus.HOLDING
    assert [h for h in updated if h.ticker == "MSFT"][0].status == HoldingStatus.RULE6_STAGE1_SOLD

    record_manual_exit(updated, "AVGO", stage=1, date_str="2026-11-10")
    record_takeover(updated, "LLY", date_str="2026-11-15", cash_amount=400.0, currency="GBP")

    out_path = tmp_path / "holdings.csv"
    write_holdings_csv(updated, out_path)
    reread = read_holdings_csv(out_path)
    assert len(reread) == len(updated)
    assert reread[0].extra["broker"] == "Freetrade"

    # When no extra cols are present, header matches templates/holdings.example.csv verbatim.
    clean_path = tmp_path / "clean_holdings.csv"
    write_holdings_csv([_holding("AAPL", "2026-10")], clean_path)
    template_path = Path(__file__).resolve().parent.parent / "templates" / "holdings.example.csv"
    with (
        template_path.open("r", encoding="utf-8") as tf,
        clean_path.open("r", encoding="utf-8") as cf,
    ):
        assert next(csv.reader(tf)) == next(csv.reader(cf))
