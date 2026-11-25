"""Monthly execution planner combining ranking, Rule 6 exits, and Rule 8 fees."""

from __future__ import annotations

from monthly_momentum.holdings import evaluate_rule6
from monthly_momentum.models import (
    ACTIVE_STATUSES,
    BuyAllocation,
    Holding,
    MonthlyPlan,
    RankingResult,
    Rule6ActionType,
)
from monthly_momentum.normalize import ticker_match_key

DEFAULT_MARKET_FEES: dict[str, float] = {
    "us": 0.15,
    "uk": 0.50,
    "other": 0.0,
    "none": 0.0,
}


def resolve_fee_pct(market: str, fee_pct: float | None) -> float:
    """Resolve fee percentage from explicit override or Rule 8 market defaults."""
    if fee_pct is not None:
        if fee_pct < 0.0 or fee_pct >= 100.0:
            raise ValueError(f"fee_pct must be between 0 and 100, got {fee_pct}.")
        return float(fee_pct)
    key = market.strip().lower()
    if key not in DEFAULT_MARKET_FEES:
        raise ValueError(
            f"Unknown market {market!r}; expected one of {sorted(DEFAULT_MARKET_FEES)}."
        )
    return DEFAULT_MARKET_FEES[key]


def build_monthly_plan(
    ranking: RankingResult,
    holdings: list[Holding],
    contribution: float,
    rule6_cash: float = 0.0,
    takeover_cash: float = 0.0,
    currency: str = "GBP",
    market: str = "us",
    fee_pct: float | None = None,
    rule6_enabled: bool = True,
) -> MonthlyPlan:
    """Create a complete monthly buy & Rule 6 exit plan."""
    if contribution < 0.0 or rule6_cash < 0.0 or takeover_cash < 0.0:
        raise ValueError("Cash amounts must be non-negative.")

    eff_fee_pct = resolve_fee_pct(market, fee_pct)
    rule6_recs = evaluate_rule6(
        holdings,
        run_month=ranking.month,
        top10_tickers=ranking.top10_tickers,
        enabled=rule6_enabled,
    )

    total_investable = round(contribution + rule6_cash + takeover_cash, 2)
    picks = ranking.top_picks
    active_keys = {ticker_match_key(h.ticker) for h in holdings if h.status in ACTIVE_STATUSES}

    allocations: list[BuyAllocation] = []
    warnings: list[str] = []

    if ranking.top_n == 1:
        warnings.append(
            "Aggressive Top 1 variant selected: historical backtests showed drawdowns up to -76%."
        )

    if len(picks) < ranking.top_n:
        warnings.append(
            f"Only {len(picks)} eligible securities passed the 3-month filter "
            f"(requested top {ranking.top_n})."
        )

    pending_sells = [
        rec
        for rec in rule6_recs
        if rec.action
        in {
            Rule6ActionType.SELL_THIRD,
            Rule6ActionType.SELL_HALF,
            Rule6ActionType.SELL_REMAINING,
        }
    ]
    if pending_sells and rule6_cash == 0.0:
        tickers = ", ".join(rec.holding.ticker for rec in pending_sells)
        warnings.append(
            f"Rule 6 recommends selling {tickers}. Once executed, include proceeds via "
            "--rule6-cash so they reinvest into this month's buys."
        )

    if picks and total_investable > 0.0:
        gross_each = total_investable / len(picks)
        for pick in picks:
            est_fee = round(gross_each * (eff_fee_pct / 100.0), 4)
            net = round(gross_each - est_fee, 4)
            allocations.append(
                BuyAllocation(
                    rank=pick.rank,
                    ticker=pick.ticker,
                    name=pick.name,
                    gross_amount=round(gross_each, 2),
                    fee_pct=eff_fee_pct,
                    estimated_fee=round(est_fee, 2),
                    net_amount=round(net, 2),
                    already_held=ticker_match_key(pick.ticker) in active_keys,
                )
            )
    elif not picks and total_investable > 0.0:
        warnings.append(
            "No eligible securities passed the 3-month momentum filter; hold cash until next month."
        )

    return MonthlyPlan(
        month=ranking.month,
        currency=currency.upper(),
        contribution=round(contribution, 2),
        rule6_cash=round(rule6_cash, 2),
        takeover_cash=round(takeover_cash, 2),
        total_investable=total_investable,
        market=market.lower(),
        fee_pct=eff_fee_pct,
        ranking=ranking,
        rule6_recommendations=rule6_recs,
        allocations=allocations,
        warnings=warnings,
    )
