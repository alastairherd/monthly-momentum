"""Tests for FTSE 100, TSX 60, EURO STOXX 50 parsers, FX conversion, and fees."""

from __future__ import annotations

from datetime import date

import pytest

from monthly_momentum.backtest.data import PricePoint
from monthly_momentum.markets import (
    convert_prices_to_currency,
    parse_eurostoxx50_wikipedia_html,
    parse_ftse100_wikipedia_html,
    parse_tsx60_wikipedia_html,
)
from monthly_momentum.normalize import ftse_to_yahoo, tsx_to_yahoo


def test_ftse_and_tsx_symbol_mapping() -> None:
    assert ftse_to_yahoo("RR.") == "RR.L"
    assert ftse_to_yahoo("BT.A") == "BT-A.L"
    assert ftse_to_yahoo("AZN") == "AZN.L"
    assert ftse_to_yahoo("III.L") == "III.L"

    assert tsx_to_yahoo("CTC.A") == "CTC-A.TO"
    assert tsx_to_yahoo("BIP.UN") == "BIP-UN.TO"
    assert tsx_to_yahoo("RY") == "RY.TO"


def test_international_wikipedia_parsers() -> None:
    ftse_html = """
    <table class="wikitable" id="constituents">
      <tr><th>Company</th><th>Ticker</th><th>FTSE industry sector</th></tr>
      <tr><td>Rolls-Royce Holdings</td><td>RR.</td><td>Aerospace & Defense</td></tr>
      <tr><td>BT Group</td><td>BT.A</td><td>Telecommunications</td></tr>
    </table>
    """
    ftse = parse_ftse100_wikipedia_html(ftse_html)
    assert [r.ticker for r in ftse] == ["BT-A.L", "RR.L"]
    assert ftse[0].index == "FTSE 100"

    tsx_rows = "\n".join(
        f"<tr><td>SYM{i}</td><td>Company {i}</td><td>Financials</td></tr>" for i in range(29)
    )
    tsx_html = f"""
    <table class="wikitable">
      <tr><th>Symbol</th><th>Company</th><th>Sector</th></tr>
      <tr><td>CTC.A</td><td>Canadian Tire</td><td>Consumer Cyclical</td></tr>
      {tsx_rows}
    </table>
    """
    tsx = parse_tsx60_wikipedia_html(tsx_html)
    assert any(r.ticker == "CTC-A.TO" for r in tsx)

    stoxx_rows = "\n".join(
        f"<tr><td>STX{i}.PA</td><td>EX: STX{i}</td>"
        f"<td>Name {i}</td><td>SE</td><td>FR</td><td>Tech</td></tr>"
        for i in range(29)
    )
    stoxx_html = f"""
    <table class="wikitable" id="constituents">
      <tr><th>Ticker</th><th>Main listing</th><th>Name</th>
      <th>Corporate form</th><th>Registered office</th><th>Sector</th></tr>
      <tr><td>ADS.DE</td><td>FWB: ADS</td><td>Adidas</td>
      <td>AG</td><td>Germany</td><td>Consumer Discretionary</td></tr>
      {stoxx_rows}
    </table>
    """
    stoxx = parse_eurostoxx50_wikipedia_html(stoxx_html)
    assert any(r.ticker == "ADS.DE" and r.index == "EURO STOXX 50" for r in stoxx)


def test_convert_prices_to_currency_usd_and_gbp() -> None:
    prices = {
        "RR.L": {
            "2026-10": PricePoint(
                dt=date(2026, 10, 1),
                month="2026-10",
                ticker="RR.L",
                close=5.0,
                adj_close=5.5,
                market="uk",
            )
        },
        "NVDA": {
            "2026-10": PricePoint(
                dt=date(2026, 10, 1),
                month="2026-10",
                ticker="NVDA",
                close=125.0,
                adj_close=125.0,
                market="us",
            )
        },
    }
    fx = {"GBPUSD=X": {"2026-10": 1.25}}

    usd_map = convert_prices_to_currency(prices, fx, target_currency="USD")
    assert usd_map["RR.L"]["2026-10"].close == pytest.approx(6.25)
    assert usd_map["RR.L"]["2026-10"].adj_close == pytest.approx(6.875)
    assert usd_map["NVDA"]["2026-10"].close == pytest.approx(125.0)

    gbp_map = convert_prices_to_currency(prices, fx, target_currency="GBP")
    assert gbp_map["RR.L"]["2026-10"].close == pytest.approx(5.0)
    assert gbp_map["NVDA"]["2026-10"].close == pytest.approx(100.0)
