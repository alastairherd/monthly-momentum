"""Typer CLI entry point for Monthly Momentum."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from monthly_momentum.backtest.data import load_backtest_dataset
from monthly_momentum.backtest.engine import BacktestConfig, compare_variants, run_backtest
from monthly_momentum.holdings import (
    HOLDINGS_COLUMNS,
    apply_monthly_run_to_holdings,
    evaluate_rule6,
    read_holdings_csv,
    record_manual_exit,
    record_takeover,
    write_holdings_csv,
)
from monthly_momentum.live import (
    fetch_live_metrics,
    fetch_sp500_constituents,
    load_constituents_csv,
    write_raw_metrics_csv,
)
from monthly_momentum.models import (
    ACTIVE_STATUSES,
    Holding,
    HoldingStatus,
    RankingResult,
    Rule6ActionType,
    StrategyVariant,
)
from monthly_momentum.normalize import add_months, normalize_month, normalize_ticker
from monthly_momentum.parsers import ColumnOverrides, load_screener_csv
from monthly_momentum.planner import build_monthly_plan
from monthly_momentum.ranking import rank_securities, read_ranking_csv, write_ranking_csv
from monthly_momentum.refresh import run_public_refresh
from monthly_momentum.report import rebuild_public_reports

app = typer.Typer(
    name="monthly-momentum",
    help="Monthly index-constituent momentum strategy CLI, tracker, and backtester.",
    no_args_is_help=True,
)
holdings_app = typer.Typer(
    name="holdings",
    help="Manage portfolio holdings and check Rule 6 staged exits.",
    no_args_is_help=True,
)
app.add_typer(holdings_app, name="holdings")

console = Console()


def _current_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _current_date() -> str:
    return datetime.now(UTC).date().isoformat()


def _resolve_top_n(variant: StrategyVariant, top_n: int | None) -> int:
    if top_n is not None:
        if top_n < 1:
            raise typer.BadParameter("--top-n must be >= 1.")
        return top_n
    return variant.top_n


def _print_ranking_table(result: RankingResult, limit: int = 10) -> None:
    table = Table(
        title=(
            f"{result.index} Momentum Ranking ({result.month}) · "
            f"source={result.source} ({result.return_type})"
        )
    )
    table.add_column("Rank", justify="right", style="cyan")
    table.add_column("Ticker", style="bold")
    table.add_column("Company")
    table.add_column("3Y Return", justify="right")
    table.add_column("3M Return", justify="right")
    table.add_column("Buy?", justify="center")

    for item in result.ranked[:limit]:
        buy_badge = "[green]YES[/green]" if item.selected_for_buy else "—"
        table.add_row(
            f"#{item.rank}",
            item.ticker,
            item.name,
            f"{item.return_3y_pct:+.2f}%",
            f"{item.return_3m_pct:+.2f}%",
            buy_badge,
        )
    console.print(table)
    console.print(
        f"Eligible: [bold]{len(result.ranked)}[/bold] | "
        f"Excluded: [bold]{len(result.excluded)}[/bold]"
    )


@app.command()
def init(
    holdings_path: Annotated[
        Path,
        typer.Option("--holdings", help="Path to initialize personal holdings CSV."),
    ] = Path("data/private/holdings.csv"),
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing holdings file.")
    ] = False,
) -> None:
    """Initialize local gitignored personal folders and empty holdings CSV."""
    Path("data/private").mkdir(parents=True, exist_ok=True)
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    if holdings_path.exists() and not force:
        console.print(f"[yellow]Already exists:[/yellow] {holdings_path}")
        return
    holdings_path.parent.mkdir(parents=True, exist_ok=True)
    with holdings_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HOLDINGS_COLUMNS)
        writer.writeheader()
    console.print(f"[green]Initialized holdings sheet:[/green] {holdings_path}")


@app.command()
def refresh(
    root: Annotated[Path, typer.Option("--root", help="Repository root directory.")] = Path("."),
    years: Annotated[int, typer.Option("--years", help="Years of monthly prices to fetch.")] = 12,
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="Override as-of date (YYYY-MM-DD).")
    ] = None,
    include_mtd: Annotated[
        bool, typer.Option("--include-mtd", help="Include current in-progress calendar month.")
    ] = False,
    contribution: Annotated[
        float, typer.Option("--contribution", help="Monthly DCA amount for performance stats.")
    ] = 500.0,
    fee_pct: Annotated[
        float, typer.Option("--fee-pct", help="Transaction fee % (Rule 8 default 0.15%).")
    ] = 0.15,
    batch_size: Annotated[
        int, typer.Option("--batch-size", help="Yahoo Finance ticker download batch size.")
    ] = 100,
) -> None:
    """Fetch public S&P 500 data and regenerate committed rankings, chart, and README."""
    as_of_dt = date.fromisoformat(as_of) if as_of else None
    result = run_public_refresh(
        root_dir=root,
        years=years,
        as_of=as_of_dt,
        include_mtd=include_mtd,
        contribution=contribution,
        fee_pct=fee_pct,
        batch_size=batch_size,
    )
    console.print(
        f"[green]Refreshed public dataset:[/green] {result.constituents_count} constituents, "
        f"{result.price_rows_count} monthly price rows."
    )
    console.print(
        f"Latest window [bold]{result.report.latest_window}[/bold] "
        f"(signal {result.report.latest_signal_month}): "
        f"Top 3 = [bold cyan]{', '.join(result.report.top3_tickers)}[/bold cyan]"
    )
    console.print(f"Chart written to [bold]{result.report.chart_path}[/bold]")


@app.command()
def report(
    root: Annotated[Path, typer.Option("--root", help="Repository root directory.")] = Path("."),
    contribution: Annotated[
        float, typer.Option("--contribution", help="Monthly DCA amount for performance stats.")
    ] = 500.0,
    fee_pct: Annotated[
        float, typer.Option("--fee-pct", help="Transaction fee % (Rule 8 default 0.15%).")
    ] = 0.15,
) -> None:
    """Rebuild committed rankings, model holdings, performance chart, and README offline."""
    summary = rebuild_public_reports(
        root_dir=root,
        contribution=contribution,
        fee_pct=fee_pct,
    )
    console.print(
        f"[green]Rebuilt public reports offline[/green] for window "
        f"[bold]{summary.latest_window}[/bold] ({summary.windows_count} windows total)."
    )
    console.print(f"Top 3: [bold cyan]{', '.join(summary.top3_tickers)}[/bold cyan]")
    console.print(f"Updated {summary.chart_path} and {summary.readme_path}")


@app.command()
def rank(
    csv_path: Annotated[Path, typer.Argument(help="Finviz, Market Chameleon, or canonical CSV.")],
    month: Annotated[str | None, typer.Option("--month", help="Target month (YYYY-MM).")] = None,
    source: Annotated[
        str, typer.Option("--source", help="auto, finviz, market_chameleon, or canonical.")
    ] = "auto",
    index: Annotated[str, typer.Option("--index", help="Index label.")] = "S&P 500",
    index_filter: Annotated[
        str | None, typer.Option("--index-filter", help="Filter rows matching this index column.")
    ] = None,
    variant: Annotated[
        StrategyVariant, typer.Option("--variant", help="aggressive | standard | cautious.")
    ] = StrategyVariant.STANDARD,
    top_n: Annotated[
        int | None, typer.Option("--top-n", help="Override number of stocks to select.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write ranking CSV snapshot.")
    ] = None,
    save_all: Annotated[
        bool, typer.Option("--save-all", help="Write all ranked rows instead of top 10.")
    ] = False,
    col_ticker: Annotated[str | None, typer.Option("--col-ticker")] = None,
    col_name: Annotated[str | None, typer.Option("--col-name")] = None,
    col_3y: Annotated[str | None, typer.Option("--col-3y")] = None,
    col_3m: Annotated[str | None, typer.Option("--col-3m")] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    """Rank an exported screener CSV using Rules 1-4."""
    eff_month = normalize_month(month or _current_month())
    eff_top_n = _resolve_top_n(variant, top_n)
    metrics = load_screener_csv(
        csv_path,
        source=source,
        default_index=index,
        index_filter=index_filter,
        col_overrides=ColumnOverrides(
            ticker=col_ticker,
            name=col_name,
            return_3y=col_3y,
            return_3m=col_3m,
        ),
    )
    result = rank_securities(metrics, month=eff_month, top_n=eff_top_n, index=index)
    if output is not None:
        write_ranking_csv(result, output, limit=None if save_all else max(10, eff_top_n))

    if json_out:
        typer.echo(
            json.dumps(
                {
                    "month": result.month,
                    "index": result.index,
                    "top_n": result.top_n,
                    "eligible_count": len(result.ranked),
                    "excluded_count": len(result.excluded),
                    "top_picks": [asdict(r) for r in result.top_picks],
                    "top10": [asdict(r) for r in result.top10],
                },
                indent=2,
            )
        )
        return

    _print_ranking_table(result, limit=max(10, eff_top_n))
    if output is not None:
        console.print(f"[green]Saved ranking CSV:[/green] {output}")


@app.command()
def fetch(
    as_of: Annotated[str | None, typer.Option("--as-of", help="As-of date (YYYY-MM-DD).")] = None,
    index: Annotated[str, typer.Option("--index", help="Index label.")] = "S&P 500",
    constituents_file: Annotated[
        Path | None, typer.Option("--constituents-file", help="Custom constituents CSV.")
    ] = None,
    raw_output: Annotated[
        Path | None, typer.Option("--raw-output", help="Save raw metrics CSV.")
    ] = None,
    rank_results: Annotated[
        bool, typer.Option("--rank/--no-rank", help="Rank immediately after fetch.")
    ] = True,
    month: Annotated[str | None, typer.Option("--month", help="Target month (YYYY-MM).")] = None,
    variant: Annotated[StrategyVariant, typer.Option("--variant")] = StrategyVariant.STANDARD,
    top_n: Annotated[int | None, typer.Option("--top-n")] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write ranked snapshot CSV.")
    ] = None,
    batch_size: Annotated[int, typer.Option("--batch-size")] = 100,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Fetch live S&P 500 returns (Wikipedia + Yahoo Finance) and optionally rank."""
    as_of_dt = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    eff_month = normalize_month(month or as_of_dt.strftime("%Y-%m"))
    constituents = (
        load_constituents_csv(constituents_file, default_index=index)
        if constituents_file
        else fetch_sp500_constituents()
    )
    metrics = fetch_live_metrics(constituents, index=index, as_of=as_of_dt, batch_size=batch_size)
    if raw_output is not None:
        write_raw_metrics_csv(metrics, raw_output, month=eff_month)

    if not rank_results:
        if json_out:
            typer.echo(json.dumps([asdict(m) for m in metrics], indent=2))
        else:
            console.print(f"[green]Fetched {len(metrics)} metrics.[/green]")
        return

    eff_top_n = _resolve_top_n(variant, top_n)
    result = rank_securities(metrics, month=eff_month, top_n=eff_top_n, index=index)
    if output is not None:
        write_ranking_csv(result, output, limit=max(10, eff_top_n))

    if json_out:
        typer.echo(
            json.dumps(
                {
                    "month": result.month,
                    "top_picks": [asdict(r) for r in result.top_picks],
                    "top10": [asdict(r) for r in result.top10],
                },
                indent=2,
            )
        )
        return

    _print_ranking_table(result, limit=max(10, eff_top_n))


@app.command()
def run(
    input_csv: Annotated[
        Path | None, typer.Option("--input", "-i", help="Screener or ranking CSV.")
    ] = None,
    live: Annotated[
        bool, typer.Option("--live", help="Fetch live S&P 500 returns instead of CSV.")
    ] = False,
    use_public: Annotated[
        bool,
        typer.Option(
            "--use-public", help="Use committed data/rankings/latest.csv if no --input given."
        ),
    ] = False,
    holdings_path: Annotated[
        Path, typer.Option("--holdings", help="Holdings tracking CSV.")
    ] = Path("data/private/holdings.csv"),
    month: Annotated[str | None, typer.Option("--month", help="Target YYYY-MM.")] = None,
    source: Annotated[str, typer.Option("--source")] = "auto",
    index: Annotated[str, typer.Option("--index")] = "S&P 500",
    variant: Annotated[StrategyVariant, typer.Option("--variant")] = StrategyVariant.STANDARD,
    top_n: Annotated[int | None, typer.Option("--top-n")] = None,
    contribution: Annotated[
        float, typer.Option("--contribution", help="New monthly investment amount.")
    ] = 500.0,
    rule6_cash: Annotated[
        float, typer.Option("--rule6-cash", help="Cash proceeds from Rule 6 sells.")
    ] = 0.0,
    takeover_cash: Annotated[
        float, typer.Option("--takeover-cash", help="Cash proceeds from Rule 7 takeovers.")
    ] = 0.0,
    currency: Annotated[str, typer.Option("--currency")] = "GBP",
    market: Annotated[
        str, typer.Option("--market", help="us (0.15% FX), uk (0.5% stamp), or other.")
    ] = "us",
    fee_pct: Annotated[float | None, typer.Option("--fee-pct")] = None,
    rule6: Annotated[
        bool, typer.Option("--rule6/--no-rule6", help="Evaluate Rule 6 staged exits.")
    ] = True,
    apply_changes: Annotated[
        bool, typer.Option("--apply", help="Persist top-10 & buy updates to --holdings.")
    ] = False,
    apply_rule6: Annotated[
        bool, typer.Option("--apply-rule6", help="Also apply Rule 6 status transitions.")
    ] = False,
    ranking_output: Annotated[
        Path | None, typer.Option("--ranking-output", help="Optional ranking snapshot path.")
    ] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Execute the full monthly ISA workflow: rank, Rule 6 check, and buy allocation."""
    eff_top_n = _resolve_top_n(variant, top_n)
    eff_month = normalize_month(month or _current_month())

    if live:
        constituents = fetch_sp500_constituents()
        metrics = fetch_live_metrics(constituents, index=index)
        ranking = rank_securities(metrics, month=eff_month, top_n=eff_top_n, index=index)
    else:
        resolved_input = input_csv
        if resolved_input is None and use_public:
            resolved_input = Path("data/rankings/latest.csv")
        if resolved_input is None:
            raise typer.BadParameter("Provide --input <csv>, --use-public, or --live.")
        metrics = load_screener_csv(resolved_input, source=source, default_index=index)
        ranking = rank_securities(metrics, month=eff_month, top_n=eff_top_n, index=index)

    if ranking_output is not None:
        write_ranking_csv(ranking, ranking_output, limit=max(10, eff_top_n))

    holdings = read_holdings_csv(holdings_path) if holdings_path.exists() else []
    plan = build_monthly_plan(
        ranking=ranking,
        holdings=holdings,
        contribution=contribution,
        rule6_cash=rule6_cash,
        takeover_cash=takeover_cash,
        currency=currency,
        market=market,
        fee_pct=fee_pct,
        rule6_enabled=rule6,
    )

    if apply_changes:
        updated_holdings, _ = apply_monthly_run_to_holdings(
            holdings=holdings,
            ranking=ranking,
            run_month=eff_month,
            buy_date=_current_date(),
            apply_rule6_sells=apply_rule6,
            rule6_enabled=rule6,
        )
        write_holdings_csv(updated_holdings, holdings_path)

    if json_out:
        typer.echo(
            json.dumps(
                {
                    "month": plan.month,
                    "currency": plan.currency,
                    "total_investable": plan.total_investable,
                    "fee_pct": plan.fee_pct,
                    "allocations": [asdict(a) for a in plan.allocations],
                    "rule6": [
                        {
                            "ticker": r.holding.ticker,
                            "action": r.action.value,
                            "sell_fraction": r.sell_fraction,
                            "months_out_of_top10": r.months_out_of_top10,
                            "message": r.message,
                        }
                        for r in plan.rule6_recommendations
                    ],
                    "warnings": plan.warnings,
                    "applied": apply_changes,
                },
                indent=2,
            )
        )
        return

    _print_ranking_table(plan.ranking, limit=max(10, eff_top_n))

    buy_table = Table(
        title=(
            f"Monthly Buy Plan ({plan.month}) · Total {plan.currency} {plan.total_investable:,.2f} "
            f"(fee {plan.fee_pct:.2f}%)"
        )
    )
    buy_table.add_column("Rank", justify="right")
    buy_table.add_column("Ticker", style="bold")
    buy_table.add_column("Company")
    buy_table.add_column("Gross", justify="right")
    buy_table.add_column("Est. Fee", justify="right")
    buy_table.add_column("Net", justify="right")
    buy_table.add_column("Already Held?", justify="center")
    for a in plan.allocations:
        buy_table.add_row(
            f"#{a.rank}",
            a.ticker,
            a.name,
            f"{plan.currency} {a.gross_amount:,.2f}",
            f"{plan.currency} {a.estimated_fee:,.2f}",
            f"{plan.currency} {a.net_amount:,.2f}",
            "Yes (add)" if a.already_held else "New",
        )
    console.print(buy_table)

    actionable = [r for r in plan.rule6_recommendations if r.action != Rule6ActionType.HOLD]
    if actionable:
        r6_table = Table(title="Rule 6 Exit / Reset Recommendations")
        r6_table.add_column("Ticker", style="bold")
        r6_table.add_column("Months Out", justify="right")
        r6_table.add_column("Action")
        r6_table.add_column("Detail")
        for r in actionable:
            r6_table.add_row(
                r.holding.ticker,
                str(r.months_out_of_top10),
                r.action.value,
                r.message,
            )
        console.print(r6_table)
    else:
        console.print("[dim]Rule 6 check: no exits triggered.[/dim]")

    for warn in plan.warnings:
        console.print(f"[yellow]Note:[/yellow] {warn}")
    if apply_changes:
        console.print(f"[green]Updated holdings saved to {holdings_path}[/green]")
    else:
        console.print("[dim]Dry run — pass --apply to persist changes to holdings.[/dim]")


@holdings_app.command("list")
def holdings_list(
    holdings_path: Annotated[Path, typer.Option("--holdings")] = Path("data/private/holdings.csv"),
    as_of_month: Annotated[str | None, typer.Option("--as-of-month")] = None,
    show_all: Annotated[
        bool, typer.Option("--all", help="Include sold and taken-over rows.")
    ] = False,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List portfolio holdings and time elapsed outside Top 10."""
    holdings = read_holdings_csv(holdings_path)
    eff_month = normalize_month(as_of_month or _current_month())
    recs = evaluate_rule6(holdings, run_month=eff_month, top10_tickers=set(), enabled=True)
    rec_by_id = {id(r.holding): r for r in recs}

    visible = holdings if show_all else [h for h in holdings if h.status in ACTIVE_STATUSES]
    if json_out:
        typer.echo(
            json.dumps(
                [
                    {
                        "ticker": h.ticker,
                        "name": h.name,
                        "index": h.index,
                        "first_bought_date": h.first_bought_date,
                        "last_top10_month": h.last_top10_month,
                        "status": h.status.value,
                        "months_out_of_top10": (
                            rec_by_id[id(h)].months_out_of_top10 if id(h) in rec_by_id else None
                        ),
                        "notes": h.notes,
                    }
                    for h in visible
                ],
                indent=2,
            )
        )
        return

    table = Table(title=f"Holdings ({holdings_path}) as of {eff_month}")
    table.add_column("Ticker", style="bold")
    table.add_column("Name")
    table.add_column("First Bought")
    table.add_column("Last Top 10")
    table.add_column("Months Out", justify="right")
    table.add_column("Status")
    table.add_column("Notes")
    for h in visible:
        rec = rec_by_id.get(id(h))
        m_out = str(rec.months_out_of_top10) if rec else "—"
        table.add_row(
            h.ticker,
            h.name,
            h.first_bought_date,
            h.last_top10_month,
            m_out,
            h.status.value,
            h.notes,
        )
    console.print(table)


@holdings_app.command("check")
def holdings_check(
    holdings_path: Annotated[Path, typer.Option("--holdings")] = Path("data/private/holdings.csv"),
    ranking_path: Annotated[
        Path | None, typer.Option("--ranking", help="Ranking CSV for top-10 lookup.")
    ] = None,
    month: Annotated[str | None, typer.Option("--month")] = None,
    rule6: Annotated[bool, typer.Option("--rule6/--no-rule6")] = True,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Evaluate Rule 6 staged exits for active holdings."""
    holdings = read_holdings_csv(holdings_path)
    eff_month = normalize_month(month or _current_month())
    top10: set[str] = set()
    if ranking_path is not None:
        rows = read_ranking_csv(ranking_path)
        top10 = {r.ticker for r in rows if r.in_top10}
    recs = evaluate_rule6(holdings, run_month=eff_month, top10_tickers=top10, enabled=rule6)

    if json_out:
        typer.echo(
            json.dumps(
                [
                    {
                        "ticker": r.holding.ticker,
                        "action": r.action.value,
                        "sell_fraction": r.sell_fraction,
                        "months_out_of_top10": r.months_out_of_top10,
                        "next_status": r.next_status.value,
                        "next_milestone_month": r.next_milestone_month,
                        "message": r.message,
                    }
                    for r in recs
                ],
                indent=2,
            )
        )
        return

    table = Table(title=f"Rule 6 Check ({eff_month})")
    table.add_column("Ticker", style="bold")
    table.add_column("Status")
    table.add_column("Months Out", justify="right")
    table.add_column("Action")
    table.add_column("Next Check")
    table.add_column("Message")
    for r in recs:
        table.add_row(
            r.holding.ticker,
            r.holding.status.value,
            str(r.months_out_of_top10),
            r.action.value,
            r.next_milestone_month or "—",
            r.message,
        )
    console.print(table)


@holdings_app.command("add")
def holdings_add(
    ticker: Annotated[str, typer.Option("--ticker")],
    name: Annotated[str, typer.Option("--name")] = "",
    index: Annotated[str, typer.Option("--index")] = "S&P 500",
    first_bought: Annotated[str | None, typer.Option("--first-bought")] = None,
    last_top10: Annotated[str | None, typer.Option("--last-top10")] = None,
    notes: Annotated[str, typer.Option("--notes")] = "",
    holdings_path: Annotated[Path, typer.Option("--holdings")] = Path("data/private/holdings.csv"),
) -> None:
    """Add a new active holding row."""
    holdings = read_holdings_csv(holdings_path)
    norm_t = normalize_ticker(ticker)
    bought_dt = first_bought or _current_date()
    top10_m = normalize_month(last_top10 or bought_dt)
    holdings.append(
        Holding(
            ticker=norm_t,
            name=name or norm_t,
            index=index,
            first_bought_date=bought_dt,
            last_top10_month=top10_m,
            status=HoldingStatus.HOLDING,
            notes=notes,
        )
    )
    write_holdings_csv(holdings, holdings_path)
    console.print(f"[green]Added {norm_t} to {holdings_path}[/green]")


@holdings_app.command("record-exit")
def holdings_record_exit(
    ticker: Annotated[str, typer.Option("--ticker")],
    stage: Annotated[int | None, typer.Option("--stage", help="Rule 6 stage: 1, 2, or 3.")] = None,
    sold: Annotated[bool, typer.Option("--sold", help="Mark full position sold.")] = False,
    exit_date: Annotated[str | None, typer.Option("--date")] = None,
    notes: Annotated[str, typer.Option("--notes")] = "",
    holdings_path: Annotated[Path, typer.Option("--holdings")] = Path("data/private/holdings.csv"),
) -> None:
    """Record a manual Rule 6 stage sale or full exit."""
    holdings = read_holdings_csv(holdings_path)
    updated = record_manual_exit(
        holdings,
        ticker=ticker,
        stage=stage,
        full_sale=sold,
        date_str=exit_date or _current_date(),
        note=notes,
    )
    write_holdings_csv(holdings, holdings_path)
    console.print(f"[green]Updated {updated.ticker}[/green] -> status={updated.status.value}")


@holdings_app.command("record-takeover")
def holdings_record_takeover(
    ticker: Annotated[str, typer.Option("--ticker")],
    takeover_date: Annotated[str | None, typer.Option("--date")] = None,
    cash: Annotated[float | None, typer.Option("--cash")] = None,
    currency: Annotated[str, typer.Option("--currency")] = "GBP",
    notes: Annotated[str, typer.Option("--notes")] = "",
    holdings_path: Annotated[Path, typer.Option("--holdings")] = Path("data/private/holdings.csv"),
) -> None:
    """Record a corporate takeover on an active holding (Rule 7)."""
    holdings = read_holdings_csv(holdings_path)
    dt_str = takeover_date or _current_date()
    updated = record_takeover(
        holdings,
        ticker=ticker,
        date_str=dt_str,
        cash_amount=cash,
        currency=currency,
        note=notes,
    )
    write_holdings_csv(holdings, holdings_path)
    next_m = add_months(normalize_month(dt_str), 1)
    console.print(
        f"[green]Recorded takeover for {updated.ticker}.[/green] "
        f"Reinvest proceeds in {next_m} via --takeover-cash."
    )


@app.command()
def backtest(
    prices: Annotated[Path, typer.Option("--prices", help="Historical prices CSV.")] = Path(
        "data/monthly_prices.csv"
    ),
    constituents: Annotated[
        Path, typer.Option("--constituents", help="Constituent intervals CSV.")
    ] = Path("data/constituents.csv"),
    events: Annotated[
        Path | None, typer.Option("--events", help="Optional takeovers/delistings CSV.")
    ] = None,
    snapshots: Annotated[
        Path | None, typer.Option("--snapshots", help="Optional point-in-time snapshots CSV.")
    ] = None,
    benchmark_csv: Annotated[Path | None, typer.Option("--benchmark-csv")] = None,
    benchmark_ticker: Annotated[str, typer.Option("--benchmark-ticker")] = "^SP500TR",
    start: Annotated[str | None, typer.Option("--start", help="Start YYYY-MM.")] = None,
    end: Annotated[str | None, typer.Option("--end", help="End YYYY-MM.")] = None,
    contribution: Annotated[float, typer.Option("--contribution")] = 500.0,
    variant: Annotated[StrategyVariant, typer.Option("--variant")] = StrategyVariant.STANDARD,
    top_n: Annotated[int | None, typer.Option("--top-n")] = None,
    rule6: Annotated[bool, typer.Option("--rule6/--no-rule6")] = False,
    fee_pct: Annotated[float, typer.Option("--fee-pct")] = 0.15,
    sell_fee_pct: Annotated[float, typer.Option("--sell-fee-pct")] = 0.15,
    signal_mode: Annotated[
        str, typer.Option("--signal-mode", help="same_month or next_month.")
    ] = "same_month",
    equity_out: Annotated[Path | None, typer.Option("--equity-out")] = None,
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run a survivorship-bias-free monthly DCA backtest."""
    eff_top_n = _resolve_top_n(variant, top_n)
    dataset = load_backtest_dataset(
        prices_path=prices,
        constituents_path=constituents,
        events_path=events,
        benchmark_path=benchmark_csv,
        benchmark_ticker=benchmark_ticker,
        snapshots_path=snapshots,
    )
    res = run_backtest(
        dataset,
        BacktestConfig(
            start_month=start,
            end_month=end,
            monthly_contribution=contribution,
            top_n=eff_top_n,
            rule6_enabled=rule6,
            fee_pct=fee_pct,
            sell_fee_pct=sell_fee_pct,
            signal_mode=signal_mode,
        ),
    )

    if equity_out is not None:
        equity_out.parent.mkdir(parents=True, exist_ok=True)
        with equity_out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "window_month",
                    "signal_month",
                    "date",
                    "contributed_cum",
                    "portfolio_value",
                    "twr_nav",
                    "benchmark_value",
                    "benchmark_nav",
                    "top_picks",
                ],
            )
            writer.writeheader()
            for pt in res.points:
                writer.writerow(
                    {
                        "window_month": pt.window_month,
                        "signal_month": pt.signal_month,
                        "date": pt.dt.isoformat(),
                        "contributed_cum": f"{pt.contributed_cum:.2f}",
                        "portfolio_value": f"{pt.portfolio_value:.2f}",
                        "twr_nav": f"{pt.twr_nav:.6f}",
                        "benchmark_value": (
                            f"{pt.benchmark_value:.2f}" if pt.benchmark_value is not None else ""
                        ),
                        "benchmark_nav": (
                            f"{pt.benchmark_nav:.6f}" if pt.benchmark_nav is not None else ""
                        ),
                        "top_picks": ";".join(pt.top_picks),
                    }
                )

    m = res.metrics
    if json_out:
        typer.echo(
            json.dumps(
                {
                    "label": res.label,
                    "start_month": m.start_month,
                    "end_month": m.end_month,
                    "months_invested": m.months_invested,
                    "total_contributed": round(m.total_contributed, 2),
                    "ending_value": round(m.ending_value, 2),
                    "xirr_pct": round(m.xirr_pct, 2) if m.xirr_pct is not None else None,
                    "twr_cagr_pct": (
                        round(m.twr_cagr_pct, 2) if m.twr_cagr_pct is not None else None
                    ),
                    "max_drawdown_pct": round(m.max_drawdown_pct, 2),
                    "total_fees_paid": round(m.total_fees_paid, 2),
                    "rule6_exits_count": m.rule6_exits_count,
                    "takeover_events_count": m.takeover_events_count,
                    "warnings": res.warnings,
                },
                indent=2,
            )
        )
        return

    table = Table(title=f"Backtest Results — {res.label} ({m.start_month} .. {m.end_month})")
    table.add_column("Metric", style="bold")
    table.add_column("Strategy", justify="right")
    table.add_column("Benchmark", justify="right")
    table.add_row("Total Contributed", f"{m.total_contributed:,.2f}", f"{m.total_contributed:,.2f}")
    table.add_row(
        "Ending Value",
        f"{m.ending_value:,.2f}",
        f"{m.benchmark_ending_value:,.2f}" if m.benchmark_ending_value is not None else "—",
    )
    table.add_row(
        "XIRR (Annualized)",
        f"{m.xirr_pct:.2f}%" if m.xirr_pct is not None else "—",
        f"{m.benchmark_xirr_pct:.2f}%" if m.benchmark_xirr_pct is not None else "—",
    )
    table.add_row(
        "TWR CAGR",
        f"{m.twr_cagr_pct:.2f}%" if m.twr_cagr_pct is not None else "—",
        f"{m.benchmark_twr_cagr_pct:.2f}%" if m.benchmark_twr_cagr_pct is not None else "—",
    )
    table.add_row(
        "Max Drawdown (TWR)",
        f"{m.max_drawdown_pct:.2f}%",
        f"{m.benchmark_max_drawdown_pct:.2f}%" if m.benchmark_max_drawdown_pct is not None else "—",
    )
    table.add_row("Fees Paid", f"{m.total_fees_paid:,.2f}", "0.00")
    table.add_row(
        "Rule 6 Exits / Takeovers",
        f"{m.rule6_exits_count} / {m.takeover_events_count}",
        "—",
    )
    console.print(table)
    for w in res.warnings:
        console.print(f"[yellow]Warning:[/yellow] {w}")


@app.command()
def compare(
    prices: Annotated[Path, typer.Option("--prices")] = Path("data/monthly_prices.csv"),
    constituents: Annotated[Path, typer.Option("--constituents")] = Path("data/constituents.csv"),
    events: Annotated[Path | None, typer.Option("--events")] = None,
    snapshots: Annotated[Path | None, typer.Option("--snapshots")] = None,
    benchmark_csv: Annotated[Path | None, typer.Option("--benchmark-csv")] = None,
    benchmark_ticker: Annotated[str, typer.Option("--benchmark-ticker")] = "^SP500TR",
    start: Annotated[str | None, typer.Option("--start")] = None,
    end: Annotated[str | None, typer.Option("--end")] = None,
    contribution: Annotated[float, typer.Option("--contribution")] = 500.0,
    fee_pct: Annotated[float, typer.Option("--fee-pct")] = 0.15,
    signal_mode: Annotated[str, typer.Option("--signal-mode")] = "same_month",
    json_out: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare Top 1, Top 3, Top 3 + Rule 6, Top 10, Top 10 + Rule 6, and Benchmark."""
    dataset = load_backtest_dataset(
        prices_path=prices,
        constituents_path=constituents,
        events_path=events,
        benchmark_path=benchmark_csv,
        benchmark_ticker=benchmark_ticker,
        snapshots_path=snapshots,
    )
    rows = compare_variants(
        dataset,
        BacktestConfig(
            start_month=start,
            end_month=end,
            monthly_contribution=contribution,
            fee_pct=fee_pct,
            sell_fee_pct=fee_pct,
            signal_mode=signal_mode,
        ),
    )

    if json_out:
        typer.echo(
            json.dumps(
                [
                    {
                        "label": row.label,
                        "ending_value": round(row.result.metrics.ending_value, 2),
                        "xirr_pct": (
                            round(row.result.metrics.xirr_pct, 2)
                            if row.result.metrics.xirr_pct is not None
                            else None
                        ),
                        "twr_cagr_pct": (
                            round(row.result.metrics.twr_cagr_pct, 2)
                            if row.result.metrics.twr_cagr_pct is not None
                            else None
                        ),
                        "max_drawdown_pct": round(row.result.metrics.max_drawdown_pct, 2),
                    }
                    for row in rows
                ],
                indent=2,
            )
        )
        return

    table = Table(title="Strategy Variant Comparison")
    table.add_column("Variant", style="bold")
    table.add_column("Ending Value", justify="right")
    table.add_column("XIRR", justify="right")
    table.add_column("TWR CAGR", justify="right")
    table.add_column("Max Drawdown", justify="right")
    table.add_column("5Y Win Rate", justify="right")
    for row in rows:
        m = row.result.metrics
        win_s = f"{m.rolling_5y.win_rate_pct:.1f}%" if m.rolling_5y else "—"
        table.add_row(
            row.label,
            f"{m.ending_value:,.2f}",
            f"{m.xirr_pct:.2f}%" if m.xirr_pct is not None else "—",
            f"{m.twr_cagr_pct:.2f}%" if m.twr_cagr_pct is not None else "—",
            f"{m.max_drawdown_pct:.2f}%",
            win_s,
        )
    console.print(table)
