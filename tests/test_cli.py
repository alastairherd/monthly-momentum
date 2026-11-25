"""End-to-end CLI tests via typer.testing.CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monthly_momentum.cli import app
from monthly_momentum.holdings import read_holdings_csv

runner = CliRunner()


def test_cli_init_rank_run_and_holdings_flow(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    res_init = runner.invoke(app, ["init"])
    assert res_init.exit_code == 0
    holdings_file = tmp_path / "data" / "private" / "holdings.csv"
    assert holdings_file.exists()

    screener = tmp_path / "finviz.csv"
    screener.write_text(
        "Ticker,Company,Performance (3 Years),Performance (Quarter)\n"
        "NVDA,NVIDIA Corp,700%,15%\n"
        "AVGO,Broadcom,300%,8%\n"
        "LLY,Eli Lilly,200%,5%\n"
        "TSLA,Tesla,400%,-4%\n",
        encoding="utf-8",
    )

    res_rank = runner.invoke(app, ["rank", str(screener), "--month", "2026-11", "--json"])
    assert res_rank.exit_code == 0
    payload = json.loads(res_rank.stdout)
    assert [p["ticker"] for p in payload["top_picks"]] == ["NVDA", "AVGO", "LLY"]
    assert payload["excluded_count"] == 1

    # Dry run does not mutate holdings.
    res_dry = runner.invoke(
        app,
        [
            "run",
            "--input",
            str(screener),
            "--month",
            "2026-11",
            "--contribution",
            "600",
            "--json",
        ],
    )
    assert res_dry.exit_code == 0
    assert read_holdings_csv(holdings_file) == []

    # Apply persists Top 3 into holdings.
    res_apply = runner.invoke(
        app,
        [
            "run",
            "--input",
            str(screener),
            "--month",
            "2026-11",
            "--contribution",
            "600",
            "--apply",
            "--json",
        ],
    )
    assert res_apply.exit_code == 0
    saved = read_holdings_csv(holdings_file)
    assert [h.ticker for h in saved] == ["NVDA", "AVGO", "LLY"]

    res_check = runner.invoke(app, ["holdings", "check", "--month", "2026-11", "--json"])
    assert res_check.exit_code == 0
    check_payload = json.loads(res_check.stdout)
    assert len(check_payload) == 3

    res_exit = runner.invoke(
        app,
        ["holdings", "record-exit", "--ticker", "LLY", "--stage", "1", "--date", "2026-11-10"],
    )
    assert res_exit.exit_code == 0
    assert [h.status.value for h in read_holdings_csv(holdings_file) if h.ticker == "LLY"] == [
        "rule6_stage1_sold"
    ]
