"""Monthly DCA momentum backtesting engine implementing Rules 1-8."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from monthly_momentum.backtest.data import BacktestDataset, CorporateEvent, PricePoint
from monthly_momentum.backtest.metrics import BacktestMetrics, compute_backtest_metrics
from monthly_momentum.models import RankedSecurity, RankingResult, SecurityMetric
from monthly_momentum.normalize import add_months, months_between
from monthly_momentum.ranking import rank_securities


@dataclass(slots=True)
class BacktestConfig:
    """Configuration for a monthly momentum simulation run."""

    start_month: str | None = None
    end_month: str | None = None
    monthly_contribution: float = 500.0
    top_n: int = 3
    rule6_enabled: bool = False
    fee_pct: float = 0.15
    sell_fee_pct: float = 0.15
    benchmark_fee_pct: float = 0.0
    risk_free_rate: float = 0.0
    signal_mode: str = "same_month"  # "same_month" or "next_month"


@dataclass(slots=True)
class _Position:
    ticker: str
    name: str
    index: str
    units: float
    first_bought_date: str
    last_top10_month: str
    rule6_stage: int = 0  # 0=holding, 1=stage1 sold, 2=stage2 sold
    last_price: float = 0.0


@dataclass(slots=True)
class MonthlyBacktestPoint:
    """Single monthly snapshot along the backtest equity & TWR curve."""

    signal_month: str
    window_month: str
    dt: date
    contributed_cum: float
    portfolio_value: float
    twr_nav: float
    benchmark_value: float | None
    benchmark_nav: float | None
    top_picks: list[str]
    top10: list[str]
    eligible_count: int
    excluded_count: int
    rule6_sells: list[str]
    takeovers: list[str]
    fees_paid_month: float


@dataclass(slots=True)
class BacktestResult:
    """Full output of a backtest run including monthly snapshots and final holdings."""

    label: str
    config: BacktestConfig
    metrics: BacktestMetrics
    points: list[MonthlyBacktestPoint]
    rankings_by_window: list[RankingResult]
    final_holdings: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VariantSummary:
    """Comparison row for compare_variants."""

    label: str
    top_n: int
    rule6_enabled: bool
    result: BacktestResult


def _find_lookback_month(
    ticker_prices: Mapping[str, PricePoint],
    all_months: list[str],
    signal_idx: int,
    offset_months: int,
) -> str | None:
    target_month = add_months(all_months[signal_idx], -offset_months)
    if target_month in ticker_prices:
        return target_month
    # Fall back at most 1 calendar month if a bar was missed near target date.
    prev_month = add_months(target_month, -1)
    if prev_month in ticker_prices:
        return prev_month
    return None


def _rank_for_month(
    dataset: BacktestDataset,
    signal_idx: int,
    top_n: int,
    window_month: str,
    signal_mode: str = "same_month",
) -> RankingResult:
    signal_month = dataset.months[signal_idx]
    signal_dt = dataset.month_dates[signal_month]
    if signal_mode == "next_month":
        membership_dt = date(int(window_month[:4]), int(window_month[5:7]), 1)
        membership_month = window_month
    else:
        membership_dt = signal_dt
        membership_month = signal_month

    metrics: list[SecurityMetric] = []
    for tkey, tprices in dataset.prices.items():
        if signal_month not in tprices:
            continue
        if not dataset.is_member(tkey, membership_month, membership_dt):
            continue

        cur_pt = tprices[signal_month]
        m_3y = _find_lookback_month(tprices, dataset.months, signal_idx, 36)
        m_3m = _find_lookback_month(tprices, dataset.months, signal_idx, 3)

        ret_3y: float | None = None
        if m_3y is not None and tprices[m_3y].adj_close > 0.0:
            ret_3y = (cur_pt.adj_close / tprices[m_3y].adj_close - 1.0) * 100.0

        ret_3m: float | None = None
        if m_3m is not None and tprices[m_3m].close > 0.0:
            ret_3m = (cur_pt.close / tprices[m_3m].close - 1.0) * 100.0

        meta = dataset.constituent_meta.get(tkey)
        metrics.append(
            SecurityMetric(
                ticker=tkey,
                name=meta.name if meta else tkey,
                index=meta.index if meta else "S&P 500",
                return_3y_pct=ret_3y,
                return_3m_pct=ret_3m,
                return_type="total_return",
                source="backtest",
                sector=meta.sector if meta else "",
            )
        )

    return rank_securities(
        metrics,
        month=window_month,
        top_n=top_n,
        index="S&P 500",
        source_override="backtest",
    )


def _process_corporate_events(
    events: list[CorporateEvent],
    prev_dt: date | None,
    cur_dt: date,
    positions: dict[str, _Position],
    dataset: BacktestDataset,
    signal_month: str,
) -> tuple[float, float, list[str], int]:
    """Apply takeover/delist events in ``(prev_dt, cur_dt]`` to held positions.

    Returns ``(takeover_cash_now, takeover_cash_next_month, event_notes, count)``.
    Rule 7: cash from takeovers goes into the *next* month's buys. An event
    strictly before ``cur_dt`` (since the previous rebalance) is ready for this
    rebalance; an event occurring on ``cur_dt`` itself settles for next month.
    """
    takeover_now = 0.0
    takeover_next = 0.0
    notes: list[str] = []
    count = 0

    for ev in events:
        if prev_dt is not None and ev.dt <= prev_dt:
            continue
        if ev.dt > cur_dt:
            continue
        if ev.ticker not in positions:
            continue

        pos = positions.pop(ev.ticker)
        ev_month = ev.dt.strftime("%Y-%m")
        tprices = dataset.prices.get(ev.ticker, {})
        ref_pt = tprices.get(ev_month) or tprices.get(signal_month)
        ref_price = ref_pt.adj_close if ref_pt is not None else pos.last_price

        if ev.cash_per_share is not None:
            proceeds = pos.units * max(0.0, ev.cash_per_share)
        elif ev.delist_return_pct is not None:
            proceeds = pos.units * ref_price * max(0.0, 1.0 + ev.delist_return_pct / 100.0)
        else:
            proceeds = pos.units * ref_price

        if ev.event_type in {"takeover", "merger", "cash_acquisition"}:
            if ev.dt < cur_dt:
                takeover_now += proceeds
            else:
                takeover_next += proceeds
            notes.append(f"Takeover {ev.ticker} ({proceeds:,.2f})")
        else:
            # Delisting / bankruptcy proceeds (often 0.0) stay as cash if any recovery exists.
            takeover_now += proceeds
            notes.append(f"Delist {ev.ticker} ({proceeds:,.2f})")
        count += 1

    return takeover_now, takeover_next, notes, count


def _mark_price(dataset: BacktestDataset, pos: _Position, month: str) -> float:
    pt = dataset.prices.get(pos.ticker, {}).get(month)
    if pt is not None:
        pos.last_price = pt.adj_close
        return pt.adj_close
    return pos.last_price


def run_backtest(
    dataset: BacktestDataset,
    config: BacktestConfig,
    label: str | None = None,
) -> BacktestResult:
    """Run monthly DCA momentum simulation over ``dataset``."""
    if not dataset.months:
        raise ValueError("Backtest dataset contains no price months.")

    all_months = dataset.months
    if len(all_months) <= 36:
        raise ValueError(
            f"Need more than 36 monthly bars for 3-year lookback; found {len(all_months)}."
        )

    first_signal_idx = 36
    if config.start_month:
        start_signal = (
            add_months(config.start_month, -1)
            if config.signal_mode == "next_month"
            else config.start_month
        )
        candidates = [i for i in range(36, len(all_months)) if all_months[i] >= start_signal]
        if not candidates:
            raise ValueError(f"No months >= {config.start_month} after 3-year warmup.")
        first_signal_idx = candidates[0]

    last_signal_idx = len(all_months) - 1
    if config.end_month:
        end_signal = (
            add_months(config.end_month, -1)
            if config.signal_mode == "next_month"
            else config.end_month
        )
        candidates = [
            i for i in range(first_signal_idx, len(all_months)) if all_months[i] <= end_signal
        ]
        if not candidates:
            raise ValueError(f"No months <= {config.end_month} in backtest range.")
        last_signal_idx = candidates[-1]

    positions: dict[str, _Position] = {}
    closed_records: list[dict[str, str]] = []
    uninvested_cash = 0.0
    pending_takeover_cash = 0.0
    total_contributed = 0.0
    total_fees_paid = 0.0
    rule6_exits_count = 0
    takeover_events_count = 0

    benchmark_units = 0.0
    benchmark_cash = 0.0
    benchmark_cash_flows: list[tuple[date, float]] = []

    points: list[MonthlyBacktestPoint] = []
    rankings_by_window: list[RankingResult] = []
    cash_flows: list[tuple[date, float]] = []
    nav_dates: list[date] = []
    nav_values: list[float] = []
    bench_nav_values: list[float] = []

    twr_nav = 1.0
    prev_post_buy_value = 0.0
    prev_dt: date | None = None
    bench_base_price: float | None = None
    months_invested = 0

    for idx in range(first_signal_idx, last_signal_idx + 1):
        signal_month = all_months[idx]
        signal_dt = dataset.month_dates[signal_month]
        window_month = (
            add_months(signal_month, 1) if config.signal_mode == "next_month" else signal_month
        )
        is_final_signal_only = (
            config.signal_mode == "next_month" and idx == last_signal_idx and idx > first_signal_idx
        )

        # 1. Process corporate events (Rule 7) since previous bar.
        tk_now, tk_next, tk_notes, tk_cnt = _process_corporate_events(
            dataset.events, prev_dt, signal_dt, positions, dataset, signal_month
        )
        takeover_events_count += tk_cnt
        available_takeover = pending_takeover_cash + tk_now
        pending_takeover_cash = tk_next

        # 2. Rank eligible point-in-time constituents.
        ranking = _rank_for_month(
            dataset,
            idx,
            top_n=config.top_n,
            window_month=window_month,
            signal_mode=config.signal_mode,
        )
        rankings_by_window.append(ranking)
        top10_keys = ranking.top10_tickers

        # 3. Mark portfolio before Rule 6 sells & deposit, then execute Rule 6 exits.
        rule6_proceeds_net = 0.0
        rule6_sells: list[str] = []
        fees_this_month = 0.0

        # Refresh position prices on current bar.
        holdings_gross_before_sells = sum(
            pos.units * _mark_price(dataset, pos, signal_month) for pos in positions.values()
        )
        pre_sells_value = holdings_gross_before_sells + uninvested_cash + available_takeover

        membership_dt = (
            date(int(window_month[:4]), int(window_month[5:7]), 1)
            if config.signal_mode == "next_month"
            else signal_dt
        )
        membership_month = window_month if config.signal_mode == "next_month" else signal_month

        for tkey in list(positions.keys()):
            pos = positions[tkey]
            is_member_now = dataset.is_member(tkey, membership_month, membership_dt)
            if is_member_now and tkey in top10_keys:
                # Simplification 2: only index members count as winners.
                pos.last_top10_month = window_month
                pos.rule6_stage = 0
                continue

            if not config.rule6_enabled:
                continue

            months_out = months_between(pos.last_top10_month, window_month)
            sell_fraction = 0.0
            next_stage = pos.rule6_stage
            stage_label = ""
            if months_out >= 96:
                sell_fraction = 1.0
                next_stage = 3
                stage_label = "8y(100%)"
            elif months_out >= 84 and pos.rule6_stage < 2:
                sell_fraction = 0.5
                next_stage = 2
                stage_label = "7y(1/2)"
            elif months_out >= 72 and pos.rule6_stage < 1:
                sell_fraction = 1.0 / 3.0
                next_stage = 1
                stage_label = "6y(1/3)"

            if sell_fraction > 0.0:
                price = _mark_price(dataset, pos, signal_month)
                units_to_sell = pos.units * sell_fraction
                gross_sale = units_to_sell * price
                sell_fee = gross_sale * (config.sell_fee_pct / 100.0)
                net_sale = gross_sale - sell_fee
                fees_this_month += sell_fee
                total_fees_paid += sell_fee
                rule6_proceeds_net += net_sale
                rule6_exits_count += 1
                rule6_sells.append(f"{tkey}:{stage_label}")
                pos.units -= units_to_sell
                pos.rule6_stage = next_stage
                if sell_fraction >= 0.999999 or pos.units <= 1e-12:
                    closed_records.append(
                        {
                            "ticker": pos.ticker,
                            "name": pos.name,
                            "index": pos.index,
                            "first_bought_date": pos.first_bought_date,
                            "last_top10_month": pos.last_top10_month,
                            "status": "sold",
                            "notes": f"Rule 6 full exit in {window_month}",
                        }
                    )
                    del positions[tkey]

        pre_deposit_value = pre_sells_value - fees_this_month
        if prev_post_buy_value > 0.0:
            period_ret = (pre_deposit_value / prev_post_buy_value) - 1.0
            twr_nav *= 1.0 + period_ret

        # Benchmark update before deposit.
        bench_pt = dataset.benchmark_prices.get(signal_month)
        bench_val: float | None = None
        bench_nav_val: float | None = None
        if bench_pt is not None:
            if bench_base_price is None:
                bench_base_price = bench_pt.adj_close
            bench_nav_val = bench_pt.adj_close / bench_base_price
            bench_val = benchmark_units * bench_pt.adj_close + benchmark_cash

        # 4. In next_month mode, the final completed bar values the previous window
        # and generates the upcoming window's picks without booking an un-elapsed month.
        if is_final_signal_only:
            points.append(
                MonthlyBacktestPoint(
                    signal_month=signal_month,
                    window_month=window_month,
                    dt=signal_dt,
                    contributed_cum=round(total_contributed, 2),
                    portfolio_value=round(pre_deposit_value, 2),
                    twr_nav=twr_nav,
                    benchmark_value=round(bench_val, 2) if bench_val is not None else None,
                    benchmark_nav=bench_nav_val,
                    top_picks=[r.ticker for r in ranking.top_picks],
                    top10=[r.ticker for r in ranking.top10],
                    eligible_count=len(ranking.ranked),
                    excluded_count=len(ranking.excluded),
                    rule6_sells=rule6_sells,
                    takeovers=tk_notes,
                    fees_paid_month=round(fees_this_month, 2),
                )
            )
            nav_dates.append(signal_dt)
            nav_values.append(twr_nav)
            if bench_nav_val is not None:
                bench_nav_values.append(bench_nav_val)
            break

        # 5. Deposit monthly contribution and buy equal splits across Top N.
        deposit = config.monthly_contribution
        total_contributed += deposit
        months_invested += 1
        cash_flows.append((signal_dt, -deposit))
        benchmark_cash_flows.append((signal_dt, -deposit))

        buy_pool = deposit + uninvested_cash + available_takeover + rule6_proceeds_net
        uninvested_cash = 0.0

        picks: list[RankedSecurity] = ranking.top_picks
        buy_fees = 0.0
        if picks and buy_pool > 0.0:
            gross_each = buy_pool / len(picks)
            for pick in picks:
                pt = dataset.prices[pick.ticker][signal_month]
                fee = gross_each * (config.fee_pct / 100.0)
                net = gross_each - fee
                buy_fees += fee
                fees_this_month += fee
                total_fees_paid += fee
                units = net / pt.adj_close
                if pick.ticker in positions:
                    positions[pick.ticker].units += units
                    positions[pick.ticker].last_top10_month = window_month
                    positions[pick.ticker].rule6_stage = 0
                    positions[pick.ticker].last_price = pt.adj_close
                else:
                    positions[pick.ticker] = _Position(
                        ticker=pick.ticker,
                        name=pick.name,
                        index=pick.index,
                        units=units,
                        first_bought_date=(
                            f"{window_month}-01"
                            if config.signal_mode == "next_month"
                            else signal_dt.isoformat()
                        ),
                        last_top10_month=window_month,
                        rule6_stage=0,
                        last_price=pt.adj_close,
                    )
        else:
            uninvested_cash = buy_pool

        post_buy_value = (
            sum(pos.units * _mark_price(dataset, pos, signal_month) for pos in positions.values())
            + uninvested_cash
        )

        # Incorporate buy-fee drag into TWR cleanly without counting deposit inflow as return.
        denom = pre_deposit_value + deposit
        if denom > 0.0 and buy_fees > 0.0:
            twr_nav *= post_buy_value / denom

        if bench_pt is not None:
            b_cash = benchmark_cash + deposit
            b_fee = b_cash * (config.benchmark_fee_pct / 100.0)
            b_net = b_cash - b_fee
            benchmark_units += b_net / bench_pt.adj_close
            benchmark_cash = 0.0
            bench_val = benchmark_units * bench_pt.adj_close

        prev_post_buy_value = post_buy_value
        prev_dt = signal_dt

        nav_dates.append(signal_dt)
        nav_values.append(twr_nav)
        if bench_nav_val is not None:
            bench_nav_values.append(bench_nav_val)

        points.append(
            MonthlyBacktestPoint(
                signal_month=signal_month,
                window_month=window_month,
                dt=signal_dt,
                contributed_cum=round(total_contributed, 2),
                portfolio_value=round(post_buy_value, 2),
                twr_nav=twr_nav,
                benchmark_value=round(bench_val, 2) if bench_val is not None else None,
                benchmark_nav=bench_nav_val,
                top_picks=[r.ticker for r in picks],
                top10=[r.ticker for r in ranking.top10],
                eligible_count=len(ranking.ranked),
                excluded_count=len(ranking.excluded),
                rule6_sells=rule6_sells,
                takeovers=tk_notes,
                fees_paid_month=round(fees_this_month, 2),
            )
        )

    final_dt = nav_dates[-1]
    ending_value = points[-1].portfolio_value
    cash_flows_closed = list(cash_flows) + [(final_dt, ending_value)]

    bench_ending = points[-1].benchmark_value
    bench_cf_closed: list[tuple[date, float]] | None = None
    if bench_ending is not None and benchmark_cash_flows:
        bench_cf_closed = list(benchmark_cash_flows) + [(final_dt, bench_ending)]

    metrics = compute_backtest_metrics(
        start_month=points[0].window_month,
        end_month=points[-1].window_month,
        months_invested=months_invested,
        dates=nav_dates,
        nav_series=nav_values,
        cash_flows=cash_flows_closed,
        total_contributed=total_contributed,
        ending_value=ending_value,
        total_fees_paid=total_fees_paid,
        rule6_exits_count=rule6_exits_count,
        takeover_events_count=takeover_events_count,
        benchmark_nav=bench_nav_values if len(bench_nav_values) == len(nav_dates) else None,
        benchmark_cash_flows=bench_cf_closed,
        benchmark_ending_value=bench_ending,
        risk_free_rate=config.risk_free_rate,
    )

    final_holdings: list[dict[str, str]] = []
    for rec in closed_records:
        final_holdings.append(rec)
    for pos in sorted(positions.values(), key=lambda p: p.ticker):
        if pos.rule6_stage == 2:
            status = "rule6_stage2_sold"
        elif pos.rule6_stage == 1:
            status = "rule6_stage1_sold"
        else:
            status = "holding"
        final_holdings.append(
            {
                "ticker": pos.ticker,
                "name": pos.name,
                "index": pos.index,
                "first_bought_date": pos.first_bought_date,
                "last_top10_month": pos.last_top10_month,
                "status": status,
                "notes": f"Model units={pos.units:.4f}",
            }
        )

    eff_label = label or f"Top {config.top_n}" + (" + Rule 6" if config.rule6_enabled else "")
    return BacktestResult(
        label=eff_label,
        config=config,
        metrics=metrics,
        points=points,
        rankings_by_window=rankings_by_window,
        final_holdings=final_holdings,
        warnings=list(dataset.warnings),
    )


def compare_variants(
    dataset: BacktestDataset,
    base_config: BacktestConfig,
) -> list[VariantSummary]:
    """Run all strategy variants from docs/rules.md over the exact same window."""
    specs: list[tuple[str, int, bool]] = [
        ("Aggressive (Top 1)", 1, False),
        ("Standard (Top 3)", 3, False),
        ("Standard (Top 3 + Rule 6)", 3, True),
        ("Cautious (Top 10)", 10, False),
        ("Cautious (Top 10 + Rule 6)", 10, True),
    ]
    results: list[VariantSummary] = []
    for label, top_n, rule6 in specs:
        cfg = BacktestConfig(
            start_month=base_config.start_month,
            end_month=base_config.end_month,
            monthly_contribution=base_config.monthly_contribution,
            top_n=top_n,
            rule6_enabled=rule6,
            fee_pct=base_config.fee_pct,
            sell_fee_pct=base_config.sell_fee_pct,
            benchmark_fee_pct=base_config.benchmark_fee_pct,
            risk_free_rate=base_config.risk_free_rate,
            signal_mode=base_config.signal_mode,
        )
        res = run_backtest(dataset, cfg, label=label)
        results.append(VariantSummary(label=label, top_n=top_n, rule6_enabled=rule6, result=res))
    return results
