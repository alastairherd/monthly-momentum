"""Holdings persistence and Rule 6 staged-exit tracking."""

from __future__ import annotations

import csv
from pathlib import Path

from monthly_momentum.models import (
    ACTIVE_STATUSES,
    Holding,
    HoldingStatus,
    RankingResult,
    Rule6ActionType,
    Rule6Recommendation,
)
from monthly_momentum.normalize import (
    add_months,
    months_between,
    normalize_month,
    normalize_ticker,
    ticker_match_key,
)

HOLDINGS_COLUMNS: list[str] = [
    "ticker",
    "name",
    "index",
    "first_bought_date",
    "last_top10_month",
    "status",
    "notes",
]

_STATUS_ALIASES: dict[str, HoldingStatus] = {
    "": HoldingStatus.HOLDING,
    "active": HoldingStatus.HOLDING,
    "open": HoldingStatus.HOLDING,
    "holding": HoldingStatus.HOLDING,
    "rule6_stage1_sold": HoldingStatus.RULE6_STAGE1_SOLD,
    "stage1": HoldingStatus.RULE6_STAGE1_SOLD,
    "rule6_stage2_sold": HoldingStatus.RULE6_STAGE2_SOLD,
    "stage2": HoldingStatus.RULE6_STAGE2_SOLD,
    "sold": HoldingStatus.SOLD,
    "closed": HoldingStatus.SOLD,
    "exited": HoldingStatus.SOLD,
    "taken_over": HoldingStatus.TAKEN_OVER,
    "takeover": HoldingStatus.TAKEN_OVER,
    "acquired": HoldingStatus.TAKEN_OVER,
}


def _parse_status(raw: str) -> HoldingStatus:
    key = raw.strip().lower()
    if key in _STATUS_ALIASES:
        return _STATUS_ALIASES[key]
    raise ValueError(
        f"Unrecognized holding status {raw!r}; expected one of {[s.value for s in HoldingStatus]}."
    )


def read_holdings_csv(path: Path) -> list[Holding]:
    """Read personal or model holdings CSV matching templates/holdings.example.csv."""
    if not path.exists():
        return []
    holdings: list[Holding] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        extra_cols = [c for c in reader.fieldnames if c not in HOLDINGS_COLUMNS]
        for row in reader:
            ticker = normalize_ticker(row.get("ticker") or "")
            if not ticker:
                continue
            first_bought = (row.get("first_bought_date") or "").strip()
            last_top10_raw = (row.get("last_top10_month") or "").strip()
            if last_top10_raw:
                last_top10 = normalize_month(last_top10_raw)
            elif first_bought:
                last_top10 = normalize_month(first_bought)
            else:
                raise ValueError(
                    f"Holding {ticker} is missing both first_bought_date and last_top10_month."
                )
            extra = {col: (row.get(col) or "").strip() for col in extra_cols}
            holdings.append(
                Holding(
                    ticker=ticker,
                    name=(row.get("name") or ticker).strip(),
                    index=(row.get("index") or "S&P 500").strip(),
                    first_bought_date=first_bought or f"{last_top10}-01",
                    last_top10_month=last_top10,
                    status=_parse_status(row.get("status") or ""),
                    notes=(row.get("notes") or "").strip(),
                    extra=extra,
                )
            )
    return holdings


def write_holdings_csv(holdings: list[Holding], path: Path) -> None:
    """Write holdings CSV preserving schema parity with templates/holdings.example.csv."""
    path.parent.mkdir(parents=True, exist_ok=True)
    extra_cols: list[str] = []
    seen_extra: set[str] = set()
    for h in holdings:
        for key in h.extra:
            if key not in HOLDINGS_COLUMNS and key not in seen_extra:
                seen_extra.add(key)
                extra_cols.append(key)

    fieldnames = HOLDINGS_COLUMNS + extra_cols
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for h in holdings:
            row: dict[str, str] = {
                "ticker": h.ticker,
                "name": h.name,
                "index": h.index,
                "first_bought_date": h.first_bought_date,
                "last_top10_month": h.last_top10_month,
                "status": h.status.value,
                "notes": h.notes,
            }
            for col in extra_cols:
                row[col] = h.extra.get(col, "")
            writer.writerow(row)


def _append_note(existing: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return existing
    if not existing.strip():
        return addition
    return f"{existing.strip()}; {addition}"


def evaluate_rule6(
    holdings: list[Holding],
    run_month: str,
    top10_tickers: set[str],
    enabled: bool = True,
) -> list[Rule6Recommendation]:
    """Evaluate Rule 6 staged-exit status for every active holding."""
    norm_month = normalize_month(run_month)
    top10_keys = {ticker_match_key(t) for t in top10_tickers}
    recommendations: list[Rule6Recommendation] = []

    for h in holdings:
        if h.status not in ACTIVE_STATUSES:
            continue

        key = ticker_match_key(h.ticker)
        if key in top10_keys:
            if h.status in {HoldingStatus.RULE6_STAGE1_SOLD, HoldingStatus.RULE6_STAGE2_SOLD}:
                recommendations.append(
                    Rule6Recommendation(
                        holding=h,
                        action=Rule6ActionType.RESET_TOP10,
                        sell_fraction=0.0,
                        months_out_of_top10=0,
                        years_out_of_top10=0.0,
                        next_status=HoldingStatus.HOLDING,
                        message="Returned to top 10 — stop Rule 6 selling and reset clock.",
                        next_milestone_month=add_months(norm_month, 72),
                    )
                )
            else:
                recommendations.append(
                    Rule6Recommendation(
                        holding=h,
                        action=Rule6ActionType.HOLD,
                        sell_fraction=0.0,
                        months_out_of_top10=0,
                        years_out_of_top10=0.0,
                        next_status=HoldingStatus.HOLDING,
                        message="In top 10 — Rule 6 clock reset.",
                        next_milestone_month=add_months(norm_month, 72),
                    )
                )
            continue

        ref_month = h.last_top10_month or normalize_month(h.first_bought_date)
        months_out = months_between(ref_month, norm_month)
        if months_out < 0:
            raise ValueError(
                f"Holding {h.ticker} has last_top10_month={ref_month} after run_month={norm_month}."
            )
        years_out = round(months_out / 12.0, 2)

        if not enabled:
            recommendations.append(
                Rule6Recommendation(
                    holding=h,
                    action=Rule6ActionType.HOLD,
                    sell_fraction=0.0,
                    months_out_of_top10=months_out,
                    years_out_of_top10=years_out,
                    next_status=h.status,
                    message=f"Rule 6 disabled ({months_out}m outside top 10).",
                    next_milestone_month=None,
                )
            )
            continue

        if months_out >= 96:
            recommendations.append(
                Rule6Recommendation(
                    holding=h,
                    action=Rule6ActionType.SELL_REMAINING,
                    sell_fraction=1.0,
                    months_out_of_top10=months_out,
                    years_out_of_top10=years_out,
                    next_status=HoldingStatus.SOLD,
                    message=(
                        f"Outside top 10 for {months_out}m (>= 8y) — sell 100% of remaining shares."
                    ),
                    next_milestone_month=None,
                )
            )
        elif months_out >= 84:
            if h.status in {HoldingStatus.HOLDING, HoldingStatus.RULE6_STAGE1_SOLD}:
                warn = (
                    " (Year 6 trim was not marked as sold; staging to Year 7 exit.)"
                    if h.status == HoldingStatus.HOLDING
                    else ""
                )
                recommendations.append(
                    Rule6Recommendation(
                        holding=h,
                        action=Rule6ActionType.SELL_HALF,
                        sell_fraction=0.5,
                        months_out_of_top10=months_out,
                        years_out_of_top10=years_out,
                        next_status=HoldingStatus.RULE6_STAGE2_SOLD,
                        message=(
                            f"Outside top 10 for {months_out}m (>= 7y) — sell 1/2 of remaining"
                            f" shares.{warn}"
                        ),
                        next_milestone_month=add_months(ref_month, 96),
                    )
                )
            else:
                recommendations.append(
                    Rule6Recommendation(
                        holding=h,
                        action=Rule6ActionType.HOLD,
                        sell_fraction=0.0,
                        months_out_of_top10=months_out,
                        years_out_of_top10=years_out,
                        next_status=h.status,
                        message=(
                            f"Stage 2 already sold ({months_out}m out of top 10); "
                            f"final exit at {add_months(ref_month, 96)}."
                        ),
                        next_milestone_month=add_months(ref_month, 96),
                    )
                )
        elif months_out >= 72:
            if h.status == HoldingStatus.HOLDING:
                recommendations.append(
                    Rule6Recommendation(
                        holding=h,
                        action=Rule6ActionType.SELL_THIRD,
                        sell_fraction=1.0 / 3.0,
                        months_out_of_top10=months_out,
                        years_out_of_top10=years_out,
                        next_status=HoldingStatus.RULE6_STAGE1_SOLD,
                        message=f"Outside top 10 for {months_out}m (>= 6y) — sell 1/3.",
                        next_milestone_month=add_months(ref_month, 84),
                    )
                )
            else:
                recommendations.append(
                    Rule6Recommendation(
                        holding=h,
                        action=Rule6ActionType.HOLD,
                        sell_fraction=0.0,
                        months_out_of_top10=months_out,
                        years_out_of_top10=years_out,
                        next_status=h.status,
                        message=(
                            f"Stage 1 already sold ({months_out}m out of top 10); "
                            f"next check at {add_months(ref_month, 84)}."
                        ),
                        next_milestone_month=add_months(ref_month, 84),
                    )
                )
        else:
            recommendations.append(
                Rule6Recommendation(
                    holding=h,
                    action=Rule6ActionType.HOLD,
                    sell_fraction=0.0,
                    months_out_of_top10=months_out,
                    years_out_of_top10=years_out,
                    next_status=h.status,
                    message=(
                        f"Hold ({months_out}m out of top 10; Year 6 check at "
                        f"{add_months(ref_month, 72)})."
                    ),
                    next_milestone_month=add_months(ref_month, 72),
                )
            )

    return recommendations


def apply_monthly_run_to_holdings(
    holdings: list[Holding],
    ranking: RankingResult,
    run_month: str,
    buy_date: str,
    apply_rule6_sells: bool = False,
    rule6_enabled: bool = True,
) -> tuple[list[Holding], list[Rule6Recommendation]]:
    """Update holdings with top-10 appearances, new top-N buys, and optional Rule 6 sells."""
    norm_month = normalize_month(run_month)
    updated = [
        Holding(
            ticker=h.ticker,
            name=h.name,
            index=h.index,
            first_bought_date=h.first_bought_date,
            last_top10_month=h.last_top10_month,
            status=h.status,
            notes=h.notes,
            extra=dict(h.extra),
        )
        for h in holdings
    ]

    recommendations = evaluate_rule6(
        updated,
        run_month=norm_month,
        top10_tickers=ranking.top10_tickers,
        enabled=rule6_enabled,
    )

    rec_by_id = {id(rec.holding): rec for rec in recommendations}
    top10_keys = ranking.top10_tickers

    for h in updated:
        if h.status not in ACTIVE_STATUSES:
            continue
        rec = rec_by_id.get(id(h))
        key = ticker_match_key(h.ticker)
        if key in top10_keys:
            h.last_top10_month = norm_month
            if rec is not None and rec.action == Rule6ActionType.RESET_TOP10:
                h.status = HoldingStatus.HOLDING
                h.notes = _append_note(h.notes, f"Returned to top 10 ({norm_month})")
        elif (
            apply_rule6_sells
            and rec is not None
            and rec.action
            in {
                Rule6ActionType.SELL_THIRD,
                Rule6ActionType.SELL_HALF,
                Rule6ActionType.SELL_REMAINING,
            }
        ):
            h.status = rec.next_status
            h.notes = _append_note(h.notes, f"Rule 6 {rec.action.value} ({norm_month})")

    active_by_key = {ticker_match_key(h.ticker): h for h in updated if h.status in ACTIVE_STATUSES}
    for pick in ranking.top_picks:
        key = ticker_match_key(pick.ticker)
        if key in active_by_key:
            existing = active_by_key[key]
            existing.last_top10_month = norm_month
            if not existing.name or existing.name == existing.ticker:
                existing.name = pick.name
        else:
            new_holding = Holding(
                ticker=pick.ticker,
                name=pick.name,
                index=pick.index,
                first_bought_date=buy_date,
                last_top10_month=norm_month,
                status=HoldingStatus.HOLDING,
                notes=f"Bought in {norm_month} rank #{pick.rank}",
            )
            updated.append(new_holding)
            active_by_key[key] = new_holding

    return updated, recommendations


def _find_active_holding(holdings: list[Holding], ticker: str) -> Holding:
    key = ticker_match_key(ticker)
    for h in holdings:
        if h.status in ACTIVE_STATUSES and ticker_match_key(h.ticker) == key:
            return h
    raise ValueError(f"No active holding found for ticker {ticker!r}.")


def record_manual_exit(
    holdings: list[Holding],
    ticker: str,
    stage: int | None = None,
    full_sale: bool = False,
    date_str: str = "",
    note: str = "",
) -> Holding:
    """Record a manual Rule 6 stage sale or full exit on an active holding."""
    target = _find_active_holding(holdings, ticker)
    if full_sale or stage == 3:
        target.status = HoldingStatus.SOLD
        default_note = f"Sold remaining position ({date_str})" if date_str else "Sold position"
    elif stage == 1:
        target.status = HoldingStatus.RULE6_STAGE1_SOLD
        default_note = f"Rule 6 stage 1 sold 1/3 ({date_str})" if date_str else "Rule 6 stage 1"
    elif stage == 2:
        target.status = HoldingStatus.RULE6_STAGE2_SOLD
        default_note = f"Rule 6 stage 2 sold 1/2 ({date_str})" if date_str else "Rule 6 stage 2"
    else:
        raise ValueError("Specify stage in {1, 2, 3} or full_sale=True.")
    target.notes = _append_note(target.notes, note or default_note)
    return target


def record_takeover(
    holdings: list[Holding],
    ticker: str,
    date_str: str,
    cash_amount: float | None = None,
    currency: str = "GBP",
    note: str = "",
) -> Holding:
    """Record a corporate takeover on an active holding (Rule 7)."""
    target = _find_active_holding(holdings, ticker)
    target.status = HoldingStatus.TAKEN_OVER
    cash_part = f" — cash {currency} {cash_amount:,.2f}" if cash_amount is not None else ""
    default_note = f"Takeover on {date_str}{cash_part} (reinvest next month per Rule 7)"
    target.notes = _append_note(target.notes, note or default_note)
    return target
