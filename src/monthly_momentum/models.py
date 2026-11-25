"""Core domain models for Monthly Momentum."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from monthly_momentum.normalize import ticker_match_key


class StrategyVariant(StrEnum):
    """Supported position-count strategy variants from docs/rules.md and docs/research.md."""

    AGGRESSIVE = "aggressive"
    STANDARD = "standard"
    BALANCED = "balanced"
    CAUTIOUS = "cautious"

    @property
    def top_n(self) -> int:
        if self is StrategyVariant.AGGRESSIVE:
            return 1
        if self is StrategyVariant.STANDARD:
            return 3
        if self is StrategyVariant.BALANCED:
            return 5
        return 10

    @property
    def label(self) -> str:
        if self is StrategyVariant.AGGRESSIVE:
            return "Aggressive (Top 1)"
        if self is StrategyVariant.STANDARD:
            return "Standard (Top 3)"
        if self is StrategyVariant.BALANCED:
            return "Balanced (Top 5)"
        return "Cautious (Top 10)"


class HoldingStatus(StrEnum):
    """Lifecycle status of a portfolio holding."""

    HOLDING = "holding"
    RULE6_STAGE1_SOLD = "rule6_stage1_sold"
    RULE6_STAGE2_SOLD = "rule6_stage2_sold"
    SOLD = "sold"
    TAKEN_OVER = "taken_over"


ACTIVE_STATUSES: frozenset[HoldingStatus] = frozenset(
    {
        HoldingStatus.HOLDING,
        HoldingStatus.RULE6_STAGE1_SOLD,
        HoldingStatus.RULE6_STAGE2_SOLD,
    }
)


class Rule6ActionType(StrEnum):
    """Mechanistic Rule 6 exit/hold recommendation."""

    HOLD = "hold"
    RESET_TOP10 = "reset_top10"
    SELL_THIRD = "sell_third"
    SELL_HALF = "sell_half"
    SELL_REMAINING = "sell_remaining"


@dataclass(slots=True)
class SecurityMetric:
    """Raw return metrics for a single index constituent."""

    ticker: str
    name: str
    index: str
    return_3y_pct: float | None
    return_3m_pct: float | None
    return_type: str
    source: str
    sector: str = ""


@dataclass(slots=True)
class ExcludedSecurity:
    """Security excluded from monthly ranking with reason."""

    ticker: str
    name: str
    reason: str
    return_3y_pct: float | None
    return_3m_pct: float | None


@dataclass(slots=True)
class RankedSecurity:
    """Ranked eligible security for a monthly investment window."""

    month: str
    rank: int
    ticker: str
    name: str
    index: str
    return_3y_pct: float
    return_3m_pct: float
    return_type: str
    source: str
    selected_for_buy: bool
    in_top10: bool
    sector: str = ""


@dataclass(slots=True)
class RankingResult:
    """Complete monthly ranking outcome."""

    month: str
    index: str
    top_n: int
    ranked: list[RankedSecurity]
    excluded: list[ExcludedSecurity]
    source: str
    return_type: str

    @property
    def top_picks(self) -> list[RankedSecurity]:
        return self.ranked[: self.top_n]

    @property
    def top10(self) -> list[RankedSecurity]:
        return self.ranked[:10]

    @property
    def top10_tickers(self) -> set[str]:
        return {ticker_match_key(item.ticker) for item in self.top10}


@dataclass(slots=True)
class Holding:
    """Tracked holding row matching templates/holdings.example.csv."""

    ticker: str
    name: str
    index: str
    first_bought_date: str
    last_top10_month: str
    status: HoldingStatus
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Rule6Recommendation:
    """Rule 6 evaluation for a single active holding."""

    holding: Holding
    action: Rule6ActionType
    sell_fraction: float
    months_out_of_top10: int
    years_out_of_top10: float
    next_status: HoldingStatus
    message: str
    next_milestone_month: str | None


@dataclass(slots=True)
class BuyAllocation:
    """Monthly equal-split purchase allocation for one selected stock."""

    rank: int
    ticker: str
    name: str
    gross_amount: float
    fee_pct: float
    estimated_fee: float
    net_amount: float
    already_held: bool


@dataclass(slots=True)
class MonthlyPlan:
    """Complete monthly execution plan combining ranking, Rule 6, and buys."""

    month: str
    currency: str
    contribution: float
    rule6_cash: float
    takeover_cash: float
    total_investable: float
    market: str
    fee_pct: float
    ranking: RankingResult
    rule6_recommendations: list[Rule6Recommendation]
    allocations: list[BuyAllocation]
    warnings: list[str]
