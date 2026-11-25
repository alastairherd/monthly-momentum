"""Monthly DCA momentum backtesting engine implementing Rules 1-8."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from monthly_momentum.backtest.data import BacktestDataset, CorporateEvent, PricePoint
from monthly_momentum.backtest.metrics import BacktestMetrics, compute_backtest_metrics
from monthly_momentum.models import RankedSecurity, RankingResult, SecurityMetric
from monthly_momentum.normalize import add_months, months_between, ticker_match_key
from monthly_momentum.ranking import rank_securities


@dataclass(slots=True)
class BacktestConfig:
    """Configuration for a monthly momentum simulation run."""

    start_month: str | None = None
    end_month: str | None = None
    monthly_contribution: float = 500.0
    initial_lump_sum: float = 0.0
    top_n: int = 3
    rule6_enabled: bool = False
    fee_pct: float = 0.15
    sell_fee_pct: float = 0.15
    benchmark_fee_pct: float = 0.0
    risk_free_rate: float = 0.0
    signal_mode: str = "same_month"  # "same_month" or "next_month"
    exclude_tickers: tuple[str, ...] = ()
    market_fee_map: dict[str, float] | None = None


@dataclass(slots=True)
class _Position:
    ticker: str
    name: str
    index: str
    market: str
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
    holdings_weights: dict[str, float] = field(default_factory=dict)


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


@dataclass(slots=True)
class SubperiodRow:
    """Comparison metrics for a single historical sub-period or crisis window."""

    period_label: str
    start_month: str
    end_month: str
    top1_xirr_pct: float | None
    top3_xirr_pct: float | None
    top5_xirr_pct: float | None
    top10_xirr_pct: float | None
    benchmark_xirr_pct: float | None


def _find_lookback_month(
    ticker_prices: Mapping[str, PricePoint],
    signal_month: str,
    offset_months: int,
) -> str | None:
    target_month = add_months(signal_month, -offset_months)
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
    excluded_keys: frozenset[str] = frozenset(),
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
        if tkey in excluded_keys:
            continue
        if signal_month not in tprices:
            continue
        if not dataset.is_member(tkey, membership_month, membership_dt):
            continue

        cur_pt = tprices[signal_month]
        m_3y = _find_lookback_month(tprices, signal_month, 36)
        m_3m = _find_lookback_month(tprices, signal_month, 3)

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
        index=metrics[0].index if metrics else "S&P 500",
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
    """Apply takeover/delist events in ``(prev_dt, cur_dt]`` to held positions."""
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
            takeover_now += proceeds
            notes.append(f"Delist {ev.ticker} ({proceeds:,.2f})")
        count += 1

    return takeover_now, takeover_next, notes, count


def _compute_portfolio_weights(
    dataset: BacktestDataset,
    positions: Mapping[str, _Position],
    total_value: float,
    signal_month: str,
) -> dict[str, float]:
    if total_value <= 0.0:
        return {}
    raw_vals: dict[str, float] = {}
    eq_total = 0.0
    for pos in positions.values():
        val = pos.units * _mark_price(dataset, pos, signal_month)
        if val > 0.0:
            raw_vals[pos.ticker] = val
            eq_total += val
    weights: dict[str, float] = {
        t: round((v / total_value) * 100.0, 4) for t, v in raw_vals.items()
    }
    rem_cash = total_value - eq_total
    if rem_cash > 0.0 and (rem_cash / total_value) >= 0.0005:
        weights["CASH"] = round((rem_cash / total_value) * 100.0, 4)
    return weights


def _mark_price(dataset: BacktestDataset, pos: _Position, month: str) -> float:
    pt = dataset.prices.get(pos.ticker, {}).get(month)
    if pt is not None:
        pos.last_price = pt.adj_close
        return pt.adj_close
    return pos.last_price


def _resolve_buy_fee(config: BacktestConfig, market: str) -> float:
    if config.market_fee_map and market in config.market_fee_map:
        return config.market_fee_map[market]
    return config.fee_pct


def _resolve_sell_fee(config: BacktestConfig, market: str) -> float:
    if config.market_fee_map:
        # UK stamp duty applies to buys only (0% on sells); FX markets charge FX fee on both.
        if market == "uk":
            return 0.0
        if market in config.market_fee_map:
            return config.market_fee_map[market]
    return config.sell_fee_pct


def run_backtest(
    dataset: BacktestDataset,
    config: BacktestConfig,
    label: str | None = None,
) -> BacktestResult:
    """Run monthly DCA momentum simulation over ``dataset``."""
    if config.monthly_contribution < 0.0:
        raise ValueError("monthly_contribution must be >= 0.")
    if config.initial_lump_sum < 0.0:
        raise ValueError("initial_lump_sum must be >= 0.")
    if config.monthly_contribution == 0.0 and config.initial_lump_sum == 0.0:
        raise ValueError("Either initial_lump_sum or monthly_contribution must be > 0.")
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

    excluded_keys = frozenset(ticker_match_key(t) for t in config.exclude_tickers if t.strip())
    last_price_month: dict[str, str] = {
        tkey: max(tprices.keys()) for tkey, tprices in dataset.prices.items() if tprices
    }

    positions: dict[str, _Position] = {}
    closed_records: list[dict[str, str]] = []
    uninvested_cash = 0.0
    pending_takeover_cash = 0.0
    total_contributed = 0.0
    total_fees_paid = 0.0
    rule6_exits_count = 0
    takeover_events_count = 0
    delistings_liquidated_count = 0
    max_single_weight_pct = 0.0

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

        # 1. Process explicit corporate events (Rule 7) since previous bar.
        tk_now, tk_next, tk_notes, tk_cnt = _process_corporate_events(
            dataset.events, prev_dt, signal_dt, positions, dataset, signal_month
        )
        takeover_events_count += tk_cnt

        # Auto-liquidate positions whose price series permanently ended before signal_month.
        delist_cash_now = 0.0
        for tkey in list(positions.keys()):
            t_last = last_price_month.get(tkey)
            if t_last is not None and signal_month > t_last:
                pos = positions.pop(tkey)
                proceeds = pos.units * pos.last_price
                delist_cash_now += proceeds
                delistings_liquidated_count += 1
                is_distressed = pos.last_price <= 1.0
                closed_records.append(
                    {
                        "ticker": pos.ticker,
                        "name": pos.name,
                        "index": pos.index,
                        "first_bought_date": pos.first_bought_date,
                        "last_top10_month": pos.last_top10_month,
                        "status": "sold" if is_distressed else "taken_over",
                        "notes": (
                            f"Delisted/final bar {t_last} at {pos.last_price:.4f} "
                            f"(proceeds={proceeds:,.2f})"
                        ),
                    }
                )
                tk_notes.append(f"Delisted {tkey} ({proceeds:,.2f})")

        available_takeover = pending_takeover_cash + tk_now + delist_cash_now
        pending_takeover_cash = tk_next

        # 2. Rank eligible point-in-time constituents.
        ranking = _rank_for_month(
            dataset,
            idx,
            top_n=config.top_n,
            window_month=window_month,
            signal_mode=config.signal_mode,
            excluded_keys=excluded_keys,
        )
        rankings_by_window.append(ranking)
        top10_keys = ranking.top10_tickers

        # 3. Mark portfolio before Rule 6 sells & deposit, then execute Rule 6 exits.
        rule6_proceeds_net = 0.0
        rule6_sells: list[str] = []
        fees_this_month = 0.0

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
                sell_fee_rate = _resolve_sell_fee(config, pos.market)
                sell_fee = gross_sale * (sell_fee_rate / 100.0)
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

        if is_final_signal_only:
            weights_final = _compute_portfolio_weights(
                dataset, positions, pre_deposit_value, signal_month
            )
            if pre_deposit_value > 0.0 and positions:
                top_pos_w = max(
                    (pos.units * _mark_price(dataset, pos, signal_month) / pre_deposit_value)
                    * 100.0
                    for pos in positions.values()
                )
                max_single_weight_pct = max(max_single_weight_pct, top_pos_w)
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
                    holdings_weights=weights_final,
                )
            )
            nav_dates.append(signal_dt)
            nav_values.append(twr_nav)
            if bench_nav_val is not None:
                bench_nav_values.append(bench_nav_val)
            break

        # 5. Deposit optional initial lump sum (Month 1) + monthly DCA contribution.
        is_first_buy = idx == first_signal_idx
        deposit = (config.initial_lump_sum if is_first_buy else 0.0) + config.monthly_contribution
        if deposit > 0.0:
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
                fee_rate = _resolve_buy_fee(config, pt.market)
                fee = gross_each * (fee_rate / 100.0)
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
                        market=pt.market,
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
        if post_buy_value > 0.0 and positions:
            top_pos_w = max(
                (pos.units * _mark_price(dataset, pos, signal_month) / post_buy_value) * 100.0
                for pos in positions.values()
            )
            max_single_weight_pct = max(max_single_weight_pct, top_pos_w)

        denom = pre_deposit_value + deposit
        if denom > 0.0 and buy_fees > 0.0:
            twr_nav *= post_buy_value / denom

        if bench_pt is not None:
            b_cash = benchmark_cash + deposit
            if b_cash > 0.0:
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

        weights_month = _compute_portfolio_weights(dataset, positions, post_buy_value, signal_month)
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
                holdings_weights=weights_month,
            )
        )

    final_dt = nav_dates[-1]
    ending_value = points[-1].portfolio_value
    cash_flows_closed = list(cash_flows) + [(final_dt, ending_value)]

    bench_ending = points[-1].benchmark_value
    bench_cf_closed: list[tuple[date, float]] | None = None
    if bench_ending is not None and benchmark_cash_flows:
        bench_cf_closed = list(benchmark_cash_flows) + [(final_dt, bench_ending)]

    # End-of-backtest holding concentration stats.
    final_weights: list[tuple[str, float]] = []
    if ending_value > 0.0:
        for pos in positions.values():
            w = (pos.units * pos.last_price / ending_value) * 100.0
            final_weights.append((pos.ticker, w))
        final_weights.sort(key=lambda item: item[1], reverse=True)

    top_holding_ticker = final_weights[0][0] if final_weights else None
    top_holding_weight_pct = final_weights[0][1] if final_weights else 0.0
    top5_holdings_weight_pct = sum(w for _, w in final_weights[:5])

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
        top_holding_ticker=top_holding_ticker,
        top_holding_weight_pct=top_holding_weight_pct,
        max_single_holding_weight_pct=max_single_weight_pct,
        top5_holdings_weight_pct=top5_holdings_weight_pct,
        active_holdings_count=len(positions),
        delistings_liquidated_count=delistings_liquidated_count,
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
    """Run all strategy variants (Top 1, Top 3, Top 5, Top 10 +/- Rule 6)."""
    specs: list[tuple[str, int, bool]] = [
        ("Aggressive (Top 1)", 1, False),
        ("Standard (Top 3)", 3, False),
        ("Standard (Top 3 + Rule 6)", 3, True),
        ("Balanced (Top 5)", 5, False),
        ("Balanced (Top 5 + Rule 6)", 5, True),
        ("Cautious (Top 10)", 10, False),
        ("Cautious (Top 10 + Rule 6)", 10, True),
    ]
    results: list[VariantSummary] = []
    for label, top_n, rule6 in specs:
        cfg = BacktestConfig(
            start_month=base_config.start_month,
            end_month=base_config.end_month,
            monthly_contribution=base_config.monthly_contribution,
            initial_lump_sum=base_config.initial_lump_sum,
            top_n=top_n,
            rule6_enabled=rule6,
            fee_pct=base_config.fee_pct,
            sell_fee_pct=base_config.sell_fee_pct,
            benchmark_fee_pct=base_config.benchmark_fee_pct,
            risk_free_rate=base_config.risk_free_rate,
            signal_mode=base_config.signal_mode,
            exclude_tickers=base_config.exclude_tickers,
            market_fee_map=base_config.market_fee_map,
        )
        res = run_backtest(dataset, cfg, label=label)
        results.append(VariantSummary(label=label, top_n=top_n, rule6_enabled=rule6, result=res))
    return results


def run_subperiod_summary(
    dataset: BacktestDataset,
    base_config: BacktestConfig,
    periods: Sequence[tuple[str, str | None, str | None]],
) -> list[SubperiodRow]:
    """Evaluate Top 1 / Top 3 / Top 5 / Top 10 vs benchmark across specified sub-periods."""
    rows: list[SubperiodRow] = []
    for label, start_m, end_m in periods:
        xirrs: dict[int, float | None] = {}
        bench_xirr: float | None = None
        eff_start = start_m or ""
        eff_end = end_m or ""
        for top_n in (1, 3, 5, 10):
            cfg = BacktestConfig(
                start_month=start_m,
                end_month=end_m,
                monthly_contribution=base_config.monthly_contribution,
                initial_lump_sum=base_config.initial_lump_sum,
                top_n=top_n,
                rule6_enabled=False,
                fee_pct=base_config.fee_pct,
                sell_fee_pct=base_config.sell_fee_pct,
                benchmark_fee_pct=base_config.benchmark_fee_pct,
                risk_free_rate=base_config.risk_free_rate,
                signal_mode=base_config.signal_mode,
                exclude_tickers=base_config.exclude_tickers,
                market_fee_map=base_config.market_fee_map,
            )
            res = run_backtest(dataset, cfg)
            xirrs[top_n] = res.metrics.xirr_pct
            eff_start = res.metrics.start_month
            eff_end = res.metrics.end_month
            if top_n == 3:
                bench_xirr = res.metrics.benchmark_xirr_pct
        rows.append(
            SubperiodRow(
                period_label=label,
                start_month=eff_start,
                end_month=eff_end,
                top1_xirr_pct=xirrs[1],
                top3_xirr_pct=xirrs[3],
                top5_xirr_pct=xirrs[5],
                top10_xirr_pct=xirrs[10],
                benchmark_xirr_pct=bench_xirr,
            )
        )
    return rows


def summarize_portfolio_allocations(result: BacktestResult, top_k: int = 8) -> dict[str, Any]:
    """Summarize monthly stock weight composition and concentration stats for a backtest run."""
    if not result.points:
        raise ValueError("Cannot summarize allocations for an empty backtest result.")

    names: dict[str, str] = {}
    first_bought: dict[str, str] = {}
    for rec in result.final_holdings:
        tk = rec.get("ticker", "")
        if tk:
            if rec.get("name"):
                names[tk] = rec["name"]
            if rec.get("first_bought_date"):
                first_bought[tk] = rec["first_bought_date"]
    for r_res in result.rankings_by_window:
        for item in r_res.ranked:
            if item.ticker not in names and item.name:
                names[item.ticker] = item.name

    cumulative_w: dict[str, float] = {}
    for pt in result.points:
        for tk, w in pt.holdings_weights.items():
            if tk != "CASH" and w > 0.0:
                cumulative_w[tk] = cumulative_w.get(tk, 0.0) + w

    final_raw = {
        tk: w for tk, w in result.points[-1].holdings_weights.items() if tk != "CASH" and w > 0.0
    }
    by_final = sorted(
        final_raw,
        key=lambda t: (final_raw[t], cumulative_w.get(t, 0.0)),
        reverse=True,
    )
    selected: list[str] = list(by_final[: min(5, top_k)])
    if len(selected) < top_k:
        by_cum = sorted(
            [t for t in cumulative_w if t not in selected],
            key=lambda t: cumulative_w[t],
            reverse=True,
        )
        selected.extend(by_cum[: top_k - len(selected)])

    selected.sort(
        key=lambda t: (final_raw.get(t, 0.0), cumulative_w.get(t, 0.0), t),
        reverse=True,
    )

    series_points: list[dict[str, Any]] = []
    peak_top1 = 0.0
    for pt in result.points:
        active_vals = sorted(
            [w for tk, w in pt.holdings_weights.items() if tk != "CASH" and w > 0.0],
            reverse=True,
        )
        top1_pct = active_vals[0] if active_vals else 0.0
        top5_pct = sum(active_vals[:5])
        top10_pct = sum(active_vals[:10])
        peak_top1 = max(peak_top1, top1_pct)
        hhi = sum((w / 100.0) ** 2 for w in active_vals)
        effective_n = (1.0 / hhi) if hhi > 0.0 else 0.0

        sel_weights: dict[str, float] = {}
        sel_sum = 0.0
        for tk in selected:
            val = round(pt.holdings_weights.get(tk, 0.0), 2)
            sel_weights[tk] = val
            sel_sum += val
        sel_weights["OTHER"] = round(max(0.0, 100.0 - sel_sum), 2)

        series_points.append(
            {
                "w": pt.window_month,
                "d": pt.dt.isoformat(),
                "n_holdings": len(active_vals),
                "top1_pct": round(top1_pct, 2),
                "top5_pct": round(top5_pct, 2),
                "top10_pct": round(top10_pct, 2),
                "effective_n": round(effective_n, 2),
                "weights": sel_weights,
            }
        )

    final_top10 = [
        {
            "ticker": tk,
            "name": names.get(tk, tk),
            "weight_pct": round(final_raw[tk], 2),
            "first_bought_date": first_bought.get(tk, ""),
        }
        for tk in by_final[:10]
    ]
    last_sp = series_points[-1]
    return {
        "variant_label": result.label,
        "start_window": result.points[0].window_month,
        "latest_window": result.points[-1].window_month,
        "selected_tickers": selected,
        "names": {tk: names.get(tk, tk) for tk in selected},
        "final_holdings_count": last_sp["n_holdings"],
        "final_top1_ticker": final_top10[0]["ticker"] if final_top10 else "",
        "final_top1_pct": last_sp["top1_pct"],
        "final_top5_pct": last_sp["top5_pct"],
        "final_top10_pct": last_sp["top10_pct"],
        "peak_top1_pct": round(peak_top1, 2),
        "final_effective_n": last_sp["effective_n"],
        "final_top10": final_top10,
        "points": series_points,
    }


ALLOCATION_VARIANT_LABELS: tuple[str, ...] = (
    "Aggressive (Top 1)",
    "Standard (Top 3)",
    "Standard (Top 3 + Rule 6)",
    "Balanced (Top 5)",
    "Cautious (Top 10)",
)


def build_variants_allocation_payload(
    variants: Mapping[str, BacktestResult],
    top_k: int = 8,
) -> dict[str, Any]:
    """Build compact JSON-serializable allocation histories across key strategy variants."""
    return {
        label: summarize_portfolio_allocations(variants[label], top_k=top_k)
        for label in ALLOCATION_VARIANT_LABELS
        if label in variants
    }


FUNDING_SCHEDULE_KEYS: tuple[str, ...] = (
    "dca_100",
    "dca_100_r6",
    "lump_10k_dca_100",
    "lump_10k_dca_100_r6",
    "lump_10k_only",
    "lump_10k_only_r6",
)


def build_funding_schedule_comparison(
    dataset: BacktestDataset,
    base_config: BacktestConfig,
    *,
    lump_sum: float = 10_000.0,
    monthly_dca: float = 100.0,
    top_n: int = 3,
    top_k: int = 8,
) -> dict[str, Any]:
    """Compare pure monthly DCA, Day-1 lump-sum + DCA, and pure lump-sum funding schedules."""
    lump_str = "10k" if lump_sum == 10_000.0 else f"{lump_sum:,.0f}"
    mo_str = f"{monthly_dca:,.0f}"
    specs: tuple[tuple[str, float, float, bool, str], ...] = (
        ("dca_100", 0.0, monthly_dca, False, f"Pure Monthly DCA ({mo_str}/mo)"),
        ("dca_100_r6", 0.0, monthly_dca, True, f"Pure Monthly DCA ({mo_str}/mo + Rule 6)"),
        ("lump_10k_dca_100", lump_sum, monthly_dca, False, f"Lump {lump_str} + {mo_str}/mo"),
        (
            "lump_10k_dca_100_r6",
            lump_sum,
            monthly_dca,
            True,
            f"Lump {lump_str} + {mo_str}/mo + Rule 6",
        ),
        ("lump_10k_only", lump_sum, 0.0, False, f"Pure Lump Sum ({lump_str}, 0/mo)"),
        ("lump_10k_only_r6", lump_sum, 0.0, True, f"Pure Lump Sum ({lump_str} + Rule 6)"),
    )
    out: dict[str, Any] = {}
    for key, lump, mo, r6, label in specs:
        cfg = BacktestConfig(
            start_month=base_config.start_month,
            end_month=base_config.end_month,
            monthly_contribution=mo,
            initial_lump_sum=lump,
            top_n=top_n,
            rule6_enabled=r6,
            fee_pct=base_config.fee_pct,
            sell_fee_pct=base_config.sell_fee_pct,
            benchmark_fee_pct=base_config.benchmark_fee_pct,
            risk_free_rate=base_config.risk_free_rate,
            signal_mode=base_config.signal_mode,
            exclude_tickers=base_config.exclude_tickers,
            market_fee_map=base_config.market_fee_map,
        )
        res = run_backtest(dataset, cfg, label=label)
        m = res.metrics
        out[key] = {
            "key": key,
            "label": label,
            "initial_lump_sum": lump,
            "monthly_contribution": mo,
            "rule6_enabled": r6,
            "total_contributed": round(m.total_contributed, 2),
            "ending_value": round(m.ending_value, 2),
            "benchmark_ending_value": (
                round(m.benchmark_ending_value, 2) if m.benchmark_ending_value is not None else None
            ),
            "xirr_pct": round(m.xirr_pct, 2) if m.xirr_pct is not None else None,
            "benchmark_xirr_pct": (
                round(m.benchmark_xirr_pct, 2) if m.benchmark_xirr_pct is not None else None
            ),
            "twr_cagr_pct": round(m.twr_cagr_pct, 2) if m.twr_cagr_pct is not None else None,
            "max_drawdown_pct": round(m.max_drawdown_pct, 2),
            "allocation": summarize_portfolio_allocations(res, top_k=top_k),
        }
    return out
