"""iShares MSCI ACWI ETF All-World universe ingestion, UK ISA tagging, and Yahoo v8 fetcher."""

from __future__ import annotations

import csv
import io
import math
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from monthly_momentum.hero import DEFAULT_DAILY_WINDOWS
from monthly_momentum.live import DEFAULT_USER_AGENT
from monthly_momentum.normalize import (
    add_months,
    ftse_to_yahoo,
    normalize_month,
    normalize_ticker,
    subtract_calendar_years,
    to_yahoo_ticker,
    tsx_to_yahoo,
)
from monthly_momentum.refresh import merge_monthly_price_rows, write_monthly_prices_csv

_THREAD_LOCAL = threading.local()
_YAHOO_CHART_HOSTS: tuple[str, str] = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")

ISHARES_ACWI_CSV_URL = (
    "https://www.ishares.com/us/products/239600/ishares-msci-acwi-etf/latest-holdings.csv"
)
YAHOO_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

ACWI_CONSTITUENT_COLUMNS: list[str] = [
    "ticker",
    "raw_ticker",
    "name",
    "sector",
    "location",
    "exchange",
    "market_currency",
    "quote_currency",
    "weight_pct",
    "market",
    "uk_accessible",
    "uk_access_note",
    "index",
]

ACWI_SNAPSHOT_COLUMNS: list[str] = [
    "snapshot_month",
    "ticker",
    "name",
    "sector",
    "location",
    "exchange",
    "market_currency",
    "uk_accessible",
]

ACWI_EXCHANGE_SUFFIX_MAP: dict[str, str] = {
    "NYSE": "",
    "NASDAQ": "",
    "Cboe BZX": "",
    "London Stock Exchange": ".L",
    "Toronto Stock Exchange": ".TO",
    "Nyse Euronext - Euronext Paris": ".PA",
    "Xetra": ".DE",
    "Deutsche Boerse Xetra": ".DE",
    "SIX Swiss Exchange": ".SW",
    "Euronext Amsterdam": ".AS",
    "Borsa Italiana": ".MI",
    "Bolsa De Madrid": ".MC",
    "Nasdaq Omx Nordic": ".ST",
    "Omx Nordic Exchange Copenhagen A/S": ".CO",
    "Nasdaq Omx Helsinki Ltd.": ".HE",
    "Nyse Euronext - Euronext Brussels": ".BR",
    "Oslo Bors Asa": ".OL",
    "Nyse Euronext - Euronext Lisbon": ".LS",
    "Wiener Boerse Ag": ".VI",
    "Irish Stock Exchange - All Market": ".IR",
    "Hong Kong Exchanges And Clearing Ltd": ".HK",
    "Tokyo Stock Exchange": ".T",
    "National Stock Exchange Of India": ".NS",
    "Bse Ltd": ".BO",
    "Shanghai Stock Exchange": ".SS",
    "Shenzhen Stock Exchange": ".SZ",
    "Korea Exchange (Stock Market)": ".KS",
    "Korea Exchange (Kosdaq)": ".KQ",
    "Taiwan Stock Exchange": ".TW",
    "Gretai Securities Market": ".TWO",
    "Asx - All Markets": ".AX",
    "XBSP": ".SA",
    "Saudi Stock Exchange": ".SR",
    "Johannesburg Stock Exchange": ".JO",
    "Bolsa Mexicana De Valores": ".MX",
    "Bursa Malaysia": ".KL",
    "Warsaw Stock Exchange/Equities/Main Market": ".WA",
    "Singapore Exchange": ".SI",
    "Tel Aviv Stock Exchange": ".TA",
    "Stock Exchange Of Thailand": ".BK",
    "Istanbul Stock Exchange": ".IS",
    "Athens Exchange S.A. Cash Market": ".AT",
    "Abu Dhabi Securities Exchange": ".AE",
    "Dubai Financial Market": ".AE",
    "Qatar Exchange": ".QA",
    "Indonesia Stock Exchange": ".JK",
    "Santiago Stock Exchange": ".SN",
    "Philippine Stock Exchange Inc.": ".PS",
    "Kuwait Stock Exchange": ".KW",
    "New Zealand Exchange Ltd": ".NZ",
    "Budapest Stock Exchange": ".BD",
    "Bolsa De Valores De Colombia": ".CL",
    "Prague Stock Exchange": ".PR",
    "Egyptian Exchange": ".CA",
}

ACWI_TICKER_OVERRIDES: dict[tuple[str, str], str] = {
    ("Prague Stock Exchange", "BAAKOMB"): "KOMB.PR",
    ("Bse Ltd", "532483"): "CANBK.NS",
    ("Bse Ltd", "534091"): "MCX.NS",
    ("Bursa Malaysia", "MAYBANK"): "1155.KL",
    ("Bursa Malaysia", "PBBANK"): "1295.KL",
}

_US_EXCHANGES: frozenset[str] = frozenset({"NYSE", "NASDAQ", "Cboe BZX"})
_UK_EXCHANGES: frozenset[str] = frozenset({"London Stock Exchange"})
_CA_EXCHANGES: frozenset[str] = frozenset({"Toronto Stock Exchange"})
_EU_UK_ACCESSIBLE_EXCHANGES: frozenset[str] = frozenset(
    {
        "Nyse Euronext - Euronext Paris",
        "Xetra",
        "Deutsche Boerse Xetra",
        "SIX Swiss Exchange",
        "Euronext Amsterdam",
        "Borsa Italiana",
        "Bolsa De Madrid",
        "Nasdaq Omx Nordic",
        "Omx Nordic Exchange Copenhagen A/S",
        "Nasdaq Omx Helsinki Ltd.",
        "Nyse Euronext - Euronext Brussels",
        "Oslo Bors Asa",
        "Nyse Euronext - Euronext Lisbon",
        "Wiener Boerse Ag",
        "Irish Stock Exchange - All Market",
    }
)
UK_ACCESSIBLE_EXCHANGES: frozenset[str] = (
    _US_EXCHANGES | _UK_EXCHANGES | _CA_EXCHANGES | _EU_UK_ACCESSIBLE_EXCHANGES
)

SUBUNIT_CURRENCIES: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 100.0),
    "GBX": ("GBP", 100.0),
    "ZAc": ("ZAR", 100.0),
    "ZAC": ("ZAR", 100.0),
    "ILA": ("ILS", 100.0),
    "ILX": ("ILS", 100.0),
    "KWF": ("KWD", 1000.0),
}

LEGACY_USD_CROSS_PAIRS: tuple[str, ...] = ("GBPUSD=X", "CADUSD=X", "EURUSD=X")


@dataclass(slots=True)
class AcwiConstituent:
    """Single iShares MSCI ACWI equity constituent with UK ISA accessibility metadata."""

    ticker: str
    raw_ticker: str
    name: str
    sector: str
    location: str
    exchange: str
    market_currency: str
    quote_currency: str
    weight_pct: float
    market: str
    uk_accessible: bool
    uk_access_note: str
    index: str = "MSCI ACWI"


@dataclass(slots=True)
class AcwiRefreshResult:
    """Counts and metadata from refreshing the iShares MSCI ACWI dataset."""

    as_of_label: str
    total_csv_equities: int
    mapped_constituents: int
    priced_tickers: int
    uk_accessible_count: int
    price_rows_count: int
    fx_rows_count: int
    hero_daily_path: str | None = None
    hero_daily_missing: tuple[str, ...] = ()


def classify_uk_accessibility(exchange: str, location: str) -> tuple[bool, str]:
    """Classify whether a stock on ``exchange`` is typically UK retail ISA accessible."""
    ex = exchange.strip()
    loc = location.strip()
    if loc.lower() == "russian federation" or ex == "Standard-Classica-Forts":
        return False, "Sanctioned / suspended market (Russia)"
    if ex == "NO MARKET (E.G. UNLISTED)":
        return False, "Unlisted security"
    if ex in _UK_EXCHANGES:
        return True, "UK ISA (UK LSE)"
    if ex in _US_EXCHANGES:
        return True, "UK ISA (US)"
    if ex in _CA_EXCHANGES:
        return True, "UK ISA (Canada)"
    if ex in _EU_UK_ACCESSIBLE_EXCHANGES:
        return True, "UK ISA (Europe)"
    return False, f"Non-UK ISA exchange ({ex})"


def market_code_for_acwi_exchange(exchange: str) -> str:
    """Return short fee/market key (``us``, ``uk``, ``ca``, ``eu``, or ``intl``)."""
    ex = exchange.strip()
    if ex in _UK_EXCHANGES:
        return "uk"
    if ex in _US_EXCHANGES:
        return "us"
    if ex in _CA_EXCHANGES:
        return "ca"
    if ex in _EU_UK_ACCESSIBLE_EXCHANGES:
        return "eu"
    return "intl"


def map_acwi_ticker(raw_ticker: str, exchange: str) -> str | None:
    """Map an iShares ACWI ``(raw_ticker, exchange)`` pair to canonical Yahoo-compatible ticker."""
    raw = raw_ticker.strip().upper()
    ex = exchange.strip()
    if not raw or raw in {"-", "--", "N/A"}:
        return None
    if (ex, raw) in ACWI_TICKER_OVERRIDES:
        return ACWI_TICKER_OVERRIDES[(ex, raw)]
    suffix = ACWI_EXCHANGE_SUFFIX_MAP.get(ex)
    if suffix is None:
        return None

    if suffix == "":
        cleaned = raw.replace(" ", ".")
        norm = normalize_ticker(cleaned)
        return norm or None
    if suffix == ".L":
        return ftse_to_yahoo(raw)
    if suffix == ".TO":
        return tsx_to_yahoo(raw)
    if suffix == ".HK":
        if raw.isdigit():
            return f"{raw.zfill(4)}.HK"
        body = raw.replace(" ", "-").replace(".", "-")
        return f"{body}.HK"
    if (suffix == ".BK" and raw.endswith(".R")) or (suffix == ".IS" and raw.endswith(".E")):
        raw = raw[:-2]
    elif suffix == ".MX":
        raw = raw.replace("*", "")
    elif suffix == ".AE" and raw == "ETISALAT":
        raw = "EAND"

    body = raw.replace(" ", "-").replace(".", "-")
    return f"{body}{suffix}" if body else None


def fetch_ishares_acwi_csv(timeout: float = 30.0) -> str:
    """Download the latest official iShares MSCI ACWI ETF holdings CSV."""
    req = urllib.request.Request(ISHARES_ACWI_CSV_URL, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def parse_ishares_acwi_csv(csv_text: str) -> tuple[str, list[AcwiConstituent], int]:
    """Parse iShares ACWI holdings CSV into mapped equity constituents.

    Returns ``(as_of_label, constituents, total_csv_equities)``.
    """
    lines = csv_text.splitlines()
    as_of_label = ""
    for line in lines[:12]:
        if line.lower().startswith("fund holdings as of"):
            parsed_row = next(csv.reader([line]), [])
            if len(parsed_row) >= 2:
                as_of_label = parsed_row[1].strip()
            break

    hdr_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("Ticker,Name,")),
        None,
    )
    if hdr_idx is None:
        raise ValueError("Could not find 'Ticker,Name,...' header in iShares ACWI CSV.")

    reader = csv.DictReader(io.StringIO("\n".join(lines[hdr_idx:])))
    by_ticker: dict[str, AcwiConstituent] = {}
    total_csv_equities = 0

    for row in reader:
        asset_class = (row.get("Asset Class") or "").strip()
        if asset_class != "Equity":
            continue
        total_csv_equities += 1

        raw_ticker = (row.get("Ticker") or "").strip()
        exchange = (row.get("Exchange") or "").strip()
        location = (row.get("Location") or "").strip()
        mapped = map_acwi_ticker(raw_ticker, exchange)
        if mapped is None:
            continue

        raw_weight = (row.get("Weight (%)") or "0").replace(",", "").strip()
        try:
            weight_pct = float(raw_weight) if raw_weight else 0.0
        except ValueError:
            weight_pct = 0.0

        market_curr = (row.get("Market Currency") or row.get("Currency") or "USD").strip().upper()
        accessible, note = classify_uk_accessibility(exchange, location)
        mcode = market_code_for_acwi_exchange(exchange)

        item = AcwiConstituent(
            ticker=mapped,
            raw_ticker=raw_ticker,
            name=(row.get("Name") or mapped).strip() or mapped,
            sector=(row.get("Sector") or "").strip(),
            location=location,
            exchange=exchange,
            market_currency=market_curr,
            quote_currency=market_curr,
            weight_pct=weight_pct,
            market=mcode,
            uk_accessible=accessible,
            uk_access_note=note,
        )
        prev = by_ticker.get(mapped)
        if prev is None or item.weight_pct > prev.weight_pct:
            by_ticker[mapped] = item

    constituents = sorted(by_ticker.values(), key=lambda c: c.ticker)
    return as_of_label, constituents, total_csv_equities


def write_acwi_constituents_csv(records: Sequence[AcwiConstituent], path: Path) -> None:
    """Persist ACWI constituents with UK accessibility metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda c: c.ticker)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ACWI_CONSTITUENT_COLUMNS)
        writer.writeheader()
        for c in ordered:
            writer.writerow(
                {
                    "ticker": c.ticker,
                    "raw_ticker": c.raw_ticker,
                    "name": c.name,
                    "sector": c.sector,
                    "location": c.location,
                    "exchange": c.exchange,
                    "market_currency": c.market_currency,
                    "quote_currency": c.quote_currency,
                    "weight_pct": f"{c.weight_pct:.4f}",
                    "market": c.market,
                    "uk_accessible": "true" if c.uk_accessible else "false",
                    "uk_access_note": c.uk_access_note,
                    "index": c.index,
                }
            )


def load_acwi_constituents_csv(path: Path) -> list[AcwiConstituent]:
    """Load persisted ACWI constituent metadata CSV."""
    out: list[AcwiConstituent] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            try:
                weight = float(row.get("weight_pct") or 0.0)
            except ValueError:
                weight = 0.0
            acc_raw = (row.get("uk_accessible") or "").strip().lower()
            out.append(
                AcwiConstituent(
                    ticker=ticker,
                    raw_ticker=(row.get("raw_ticker") or ticker).strip(),
                    name=(row.get("name") or ticker).strip(),
                    sector=(row.get("sector") or "").strip(),
                    location=(row.get("location") or "").strip(),
                    exchange=(row.get("exchange") or "").strip(),
                    market_currency=(row.get("market_currency") or "USD").strip().upper(),
                    quote_currency=(row.get("quote_currency") or "USD").strip().upper(),
                    weight_pct=weight,
                    market=(row.get("market") or "intl").strip().lower(),
                    uk_accessible=acc_raw in {"true", "1", "yes"},
                    uk_access_note=(row.get("uk_access_note") or "").strip(),
                    index=(row.get("index") or "MSCI ACWI").strip(),
                )
            )
    return out


def update_acwi_snapshots_csv(
    snapshots_path: Path,
    snapshot_month: str,
    constituents: Sequence[AcwiConstituent],
) -> None:
    """Append/update monthly point-in-time MSCI ACWI constituent snapshots."""
    norm_month = normalize_month(snapshot_month)
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    if snapshots_path.exists():
        with snapshots_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                m_raw = (row.get("snapshot_month") or "").strip()
                t_raw = (row.get("ticker") or "").strip().upper()
                if not m_raw or not t_raw:
                    continue
                m = normalize_month(m_raw)
                if m == norm_month:
                    continue
                by_key[(m, t_raw)] = {
                    "snapshot_month": m,
                    "ticker": t_raw,
                    "name": (row.get("name") or t_raw).strip(),
                    "sector": (row.get("sector") or "").strip(),
                    "location": (row.get("location") or "").strip(),
                    "exchange": (row.get("exchange") or "").strip(),
                    "market_currency": (row.get("market_currency") or "").strip(),
                    "uk_accessible": (row.get("uk_accessible") or "false").strip().lower(),
                }

    for c in constituents:
        by_key[(norm_month, c.ticker)] = {
            "snapshot_month": norm_month,
            "ticker": c.ticker,
            "name": c.name,
            "sector": c.sector,
            "location": c.location,
            "exchange": c.exchange,
            "market_currency": c.market_currency,
            "uk_accessible": "true" if c.uk_accessible else "false",
        }

    snapshots_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [by_key[k] for k in sorted(by_key)]
    with snapshots_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ACWI_SNAPSHOT_COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)


def sanitize_monthly_bars(
    bars: Sequence[tuple[str, float, float]],
) -> list[tuple[str, float, float]]:
    """Remove Yahoo Finance 1-bar glitches and truncate step-function split/unit corruptions.

    Expects chronologically sorted ``(date_str, close, adj_close)`` bars with positive prices.
    """
    cleaned = [(d, float(c), float(a)) for d, c, a in bars if c > 0.0 and a > 0.0]
    cleaned.sort(key=lambda b: b[0])
    if len(cleaned) < 3:
        return cleaned

    # Pass 1: drop isolated 1-bar spike/crash glitches that immediately revert on the next bar.
    filtered: list[tuple[str, float, float]] = [cleaned[0]]
    for i in range(1, len(cleaned) - 1):
        _, prev_c, prev_a = filtered[-1]
        cur_d, cur_c, cur_a = cleaned[i]
        _, next_c, next_a = cleaned[i + 1]

        adj_jump = cur_a / prev_a
        adj_revert = next_a / prev_a
        cls_jump = cur_c / prev_c
        cls_revert = next_c / prev_c

        bad_adj = (adj_jump > 8.0 or adj_jump < 0.125) and (0.25 <= adj_revert <= 4.0)
        bad_cls = (cls_jump > 8.0 or cls_jump < 0.125) and (0.25 <= cls_revert <= 4.0)
        if bad_adj or bad_cls:
            continue
        filtered.append((cur_d, cur_c, cur_a))
    filtered.append(cleaned[-1])

    if len(filtered) >= 2:
        last_ratio = filtered[-1][2] / filtered[-2][2]
        last_c_ratio = filtered[-1][1] / filtered[-2][1]
        if last_ratio > 10.0 or last_ratio < 0.08 or last_c_ratio > 10.0 or last_c_ratio < 0.08:
            filtered.pop()

    # Pass 2: if a permanent step-function unit/split glitch (>10x or <0.08x) occurred,
    # discard all corrupted history prior to the regime break.
    cut_idx = 0
    for i in range(1, len(filtered)):
        a_ratio = filtered[i][2] / filtered[i - 1][2]
        c_ratio = filtered[i][1] / filtered[i - 1][1]
        if a_ratio > 10.0 or a_ratio < 0.08 or c_ratio > 10.0 or c_ratio < 0.08:
            cut_idx = i
    if cut_idx > 0:
        filtered = filtered[cut_idx:]

    return filtered


def _tz_for_meta(meta: dict[str, Any]) -> ZoneInfo | timezone:
    tz_name = meta.get("exchangeTimezoneName")
    if isinstance(tz_name, str) and tz_name.strip():
        try:
            return ZoneInfo(tz_name.strip())
        except Exception:
            pass
    gmtoffset = meta.get("gmtoffset", 0)
    try:
        offset_sec = int(gmtoffset)
    except (TypeError, ValueError):
        offset_sec = 0
    return timezone(timedelta(seconds=offset_sec))


def _get_yahoo_session() -> Any:
    sess = getattr(_THREAD_LOCAL, "session", None)
    if sess is None:
        from curl_cffi import requests as cffi_requests

        sess = cffi_requests.Session(impersonate="chrome")
        _THREAD_LOCAL.session = sess
    return sess


def _fetch_single_v8_monthly(
    canonical_ticker: str,
    period1: int,
    period2: int,
    cutoff_month: str,
    timeout: float = 12.0,
) -> tuple[str, str | None, list[tuple[str, float, float]]]:
    yahoo_sym = to_yahoo_ticker(canonical_ticker)
    encoded = urllib.parse.quote(yahoo_sym, safe="")
    session = _get_yahoo_session()
    backoffs = (1.5, 3.5, 7.0)
    payload: dict[str, Any] | None = None
    start_host_idx = sum(ord(ch) for ch in yahoo_sym) & 1

    for attempt in range(4):
        host = _YAHOO_CHART_HOSTS[(start_host_idx + attempt) & 1]
        url = (
            f"https://{host}/v8/finance/chart/{encoded}"
            f"?period1={period1}&period2={period2}&interval=1mo&events=div%2Csplit"
        )
        try:
            resp = session.get(url, timeout=timeout)
            status = int(resp.status_code)
            if status in {400, 404, 422}:
                return canonical_ticker, None, []
            if status == 429 or status >= 500:
                if attempt < 3:
                    time.sleep(backoffs[attempt])
                    continue
                return canonical_ticker, None, []
            if status != 200:
                return canonical_ticker, None, []
            payload = resp.json()
            break
        except Exception:
            if attempt < 3:
                time.sleep(backoffs[attempt])

    if not payload:
        return canonical_ticker, None, []

    results = payload.get("chart", {}).get("result") or []
    if not results:
        return canonical_ticker, None, []

    res = results[0]
    meta = res.get("meta") or {}
    timestamps = res.get("timestamp") or []
    indicators = res.get("indicators") or {}
    quote_list = indicators.get("quote") or []
    adj_list = indicators.get("adjclose") or []
    if not timestamps or not quote_list:
        return canonical_ticker, None, []

    closes = quote_list[0].get("close") or []
    adjs = adj_list[0].get("adjclose") if adj_list else closes
    if not closes or not adjs:
        return canonical_ticker, None, []

    raw_curr = str(meta.get("currency") or "").strip()
    scale = 1.0
    iso_curr: str | None = raw_curr.upper() if raw_curr else None
    if raw_curr in SUBUNIT_CURRENCIES:
        iso_curr, scale = SUBUNIT_CURRENCIES[raw_curr]

    tz = _tz_for_meta(meta)
    by_month: dict[str, tuple[str, float, float]] = {}
    for ts, c_raw, a_raw in zip(timestamps, closes, adjs, strict=False):
        if ts is None or c_raw is None:
            continue
        a_eff = c_raw if a_raw is None else a_raw
        try:
            c_val = float(c_raw) / scale
            a_val = float(a_eff) / scale
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(c_val) and math.isfinite(a_val)) or c_val <= 0.0 or a_val <= 0.0:
            continue

        local_dt = datetime.fromtimestamp(int(ts), tz=tz).date()
        month_key = local_dt.strftime("%Y-%m")
        if month_key >= cutoff_month:
            continue
        if month_key not in by_month:
            by_month[month_key] = (f"{month_key}-01", c_val, a_val)

    raw_bars = [by_month[m] for m in sorted(by_month)]
    sanitized = sanitize_monthly_bars(raw_bars)
    return canonical_ticker, iso_curr, sanitized


def fetch_yahoo_v8_monthly_bars(
    canonical_tickers: Sequence[str],
    start: date,
    end: date,
    as_of: date,
    max_workers: int = 6,
    market_by_ticker: dict[str, str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Fetch completed, sanitized monthly bars for ``canonical_tickers`` via Yahoo v8 API."""
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    period2 = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp())
    cutoff_month = as_of.strftime("%Y-%m")
    unique_tickers = list(dict.fromkeys(canonical_tickers))

    rows: list[dict[str, str]] = []
    currencies: dict[str, str] = {}

    def _run_one(t: str) -> tuple[str, str | None, list[tuple[str, float, float]]]:
        return _fetch_single_v8_monthly(
            t, period1=period1, period2=period2, cutoff_month=cutoff_month
        )

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        for ticker, iso_curr, bars in pool.map(_run_one, unique_tickers):
            if iso_curr:
                currencies[ticker] = iso_curr
            mkt = market_by_ticker.get(ticker, "intl") if market_by_ticker else "intl"
            for dt_s, c_val, a_val in bars:
                rows.append(
                    {
                        "date": dt_s,
                        "ticker": ticker,
                        "close": f"{c_val:.4f}",
                        "adj_close": f"{a_val:.4f}",
                        "market": mkt,
                    }
                )

    rows.sort(key=lambda r: (r["date"], r["ticker"]))
    return rows, currencies


def _fetch_single_v8_daily(
    canonical_ticker: str,
    period1: int,
    period2: int,
    timeout: float = 12.0,
) -> list[tuple[str, float]]:
    """Fetch split/dividend-adjusted daily closes for one ticker via the Yahoo v8 API."""
    yahoo_sym = to_yahoo_ticker(canonical_ticker)
    encoded = urllib.parse.quote(yahoo_sym, safe="")
    session = _get_yahoo_session()
    backoffs = (1.5, 3.5, 7.0)
    payload: dict[str, Any] | None = None
    start_host_idx = sum(ord(ch) for ch in yahoo_sym) & 1

    for attempt in range(4):
        host = _YAHOO_CHART_HOSTS[(start_host_idx + attempt) & 1]
        url = (
            f"https://{host}/v8/finance/chart/{encoded}"
            f"?period1={period1}&period2={period2}&interval=1d&events=div%2Csplit"
        )
        try:
            resp = session.get(url, timeout=timeout)
            status = int(resp.status_code)
            if status in {400, 404, 422}:
                return []
            if status == 429 or status >= 500:
                if attempt < 3:
                    time.sleep(backoffs[attempt])
                    continue
                return []
            if status != 200:
                return []
            payload = resp.json()
            break
        except Exception:
            if attempt < 3:
                time.sleep(backoffs[attempt])

    if not payload:
        return []

    results = payload.get("chart", {}).get("result") or []
    if not results:
        return []

    res = results[0]
    meta = res.get("meta") or {}
    timestamps = res.get("timestamp") or []
    indicators = res.get("indicators") or {}
    quote_list = indicators.get("quote") or []
    adj_list = indicators.get("adjclose") or []
    if not timestamps or not quote_list:
        return []

    closes = quote_list[0].get("close") or []
    adjs = adj_list[0].get("adjclose") if adj_list else closes
    if not closes or not adjs:
        return []

    raw_curr = str(meta.get("currency") or "").strip()
    scale = SUBUNIT_CURRENCIES[raw_curr][1] if raw_curr in SUBUNIT_CURRENCIES else 1.0
    tz = _tz_for_meta(meta)

    out: list[tuple[str, float]] = []
    for ts, c_raw, a_raw in zip(timestamps, closes, adjs, strict=False):
        if ts is None or c_raw is None:
            continue
        a_eff = c_raw if a_raw is None else a_raw
        try:
            a_val = float(a_eff) / scale
        except (TypeError, ValueError):
            continue
        if not math.isfinite(a_val) or a_val <= 0.0:
            continue
        local_dt = datetime.fromtimestamp(int(ts), tz=tz).date()
        out.append((local_dt.isoformat(), a_val))
    return out


def fetch_yahoo_v8_daily_bars(
    canonical_tickers: Sequence[str],
    start: date,
    end: date,
    max_workers: int = 6,
) -> list[dict[str, str]]:
    """Fetch daily adjusted closes for ``canonical_tickers`` within ``[start, end]``."""
    period1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    period2 = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp())
    unique_tickers = list(dict.fromkeys(t for t in canonical_tickers if t.strip()))
    rows: list[dict[str, str]] = []

    def _run_one(t: str) -> list[tuple[str, float]]:
        return _fetch_single_v8_daily(t, period1=period1, period2=period2)

    bars_by_ticker: dict[str, list[tuple[str, float]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        mapped = pool.map(_run_one, unique_tickers)
        for ticker, bars in zip(unique_tickers, mapped, strict=True):
            bars_by_ticker[ticker] = bars
    for ticker in unique_tickers:
        for dt_s, a_val in bars_by_ticker.get(ticker, []):
            rows.append({"date": dt_s, "ticker": ticker, "adj_close": f"{a_val:.4f}"})

    rows.sort(key=lambda r: (r["date"], r["ticker"]))
    return rows


def refresh_hero_daily_prices_csv(
    root_dir: Path = Path("."),
    *,
    daily_windows: int = DEFAULT_DAILY_WINDOWS,
    as_of: date | None = None,
    max_workers: int = 6,
) -> tuple[Path | None, list[str]]:
    """Refresh the committed daily-bars CSV behind the cumulative hero chart.

    Reads the UK-accessible rankings history to find the first windows' picks, fetches
    daily Yahoo bars for those holdings plus the ACWI benchmark, and rewrites
    ``data/global/daily_prices_first_months.csv``. Returns the CSV path (or ``None``
    when no rankings history exists yet) and the tickers that returned no data.
    """
    from monthly_momentum.hero import HERO_DAILY_CSV

    history_path = root_dir / "data" / "global" / "rankings" / "history_acwi_uk_accessible.csv"
    if not history_path.exists():
        return None, []

    picks_by_window: dict[str, list[str]] = {}
    with history_path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            window = (row.get("month") or "").strip()
            try:
                rank = int(float(row.get("rank") or 0))
            except ValueError:
                rank = 0
            if (
                window
                and rank <= 3
                and (row.get("selected_for_buy") or "").strip().lower() == "true"
            ):
                picks_by_window.setdefault(window, []).append((row.get("ticker") or "").strip())

    windows = sorted(picks_by_window)
    if not windows:
        return None, []

    hero_tickers: set[str] = {"ACWI"}
    for window in windows[: max(1, daily_windows) + 1]:
        hero_tickers.update(t for t in picks_by_window[window] if t)

    first_window = windows[0]
    first_signal = add_months(first_window, -1)
    # The last daily session needed is the month-end close of the K-th daily interval's
    # window month; keep a small buffer of sessions after it.
    last_signal = add_months(windows[min(daily_windows, len(windows) - 1)], -1)
    after_last = add_months(last_signal, 1)
    last_month_end = date(int(after_last[:4]), int(after_last[5:7]), 1) - timedelta(days=1)
    start = date(int(first_signal[:4]), int(first_signal[5:7]), 1) - timedelta(days=10)
    end = last_month_end + timedelta(days=10)

    rows = fetch_yahoo_v8_daily_bars(
        sorted(hero_tickers), start=start, end=end, max_workers=max_workers
    )
    fetched: dict[str, set[str]] = {}
    for row in rows:
        fetched.setdefault(row["ticker"], set()).add(row["date"])
    failed = sorted(t for t in sorted(hero_tickers) if not fetched.get(t))

    out_path = root_dir / "data" / "global" / HERO_DAILY_CSV
    # Keep any previously committed CSV when the fetch is incomplete so a Yahoo hiccup
    # never degrades the chart until the next complete refresh.
    if failed or not rows:
        return (out_path if out_path.exists() else None), failed

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["date", "ticker", "adj_close"])
        writer.writeheader()
        writer.writerows(rows)
    return out_path, failed


def fetch_all_fx_rates_v8(
    currencies: Sequence[str],
    years: int = 12,
    as_of: date | None = None,
    max_workers: int = 6,
) -> list[dict[str, str]]:
    """Fetch monthly ``USD{CCY}=X`` + legacy USD cross FX pairs via Yahoo v8 API."""
    eff_as_of = as_of or datetime.now(UTC).date()
    start = subtract_calendar_years(eff_as_of, years) - timedelta(days=35)
    end = eff_as_of + timedelta(days=2)

    iso_set = sorted(
        {
            SUBUNIT_CURRENCIES[c][0] if c in SUBUNIT_CURRENCIES else c.strip().upper()
            for c in currencies
            if c and c.strip().upper() != "USD"
        }
    )
    pairs = [f"USD{c}=X" for c in iso_set]
    for legacy in LEGACY_USD_CROSS_PAIRS:
        if legacy not in pairs:
            pairs.append(legacy)

    raw_rows, _ = fetch_yahoo_v8_monthly_bars(
        pairs,
        start=start,
        end=end,
        as_of=eff_as_of,
        max_workers=max_workers,
    )
    return [{"date": r["date"], "pair": r["ticker"], "rate": r["close"]} for r in raw_rows]


def _load_us_completed_coverage(us_prices_path: Path) -> dict[str, set[str]]:
    coverage: dict[str, set[str]] = {}
    if not us_prices_path.exists():
        return coverage
    with us_prices_path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            dt_s = (row.get("date") or "").strip()
            ticker = normalize_ticker(row.get("ticker") or "")
            if len(dt_s) >= 7 and ticker:
                coverage.setdefault(ticker, set()).add(dt_s[:7])
    return coverage


def refresh_acwi_market(
    root_dir: Path = Path("."),
    years: int = 12,
    as_of: date | None = None,
    max_workers: int = 6,
) -> AcwiRefreshResult:
    """Fetch iShares MSCI ACWI universe, monthly prices, FX rates, and snapshots."""
    from monthly_momentum.markets import merge_fx_csv

    eff_as_of = as_of or datetime.now(UTC).date()
    latest_completed_month = add_months(eff_as_of.strftime("%Y-%m"), -1)
    data_dir = root_dir / "data"
    global_dir = data_dir / "global"

    csv_text = fetch_ishares_acwi_csv()
    as_of_label, constituents, total_csv_equities = parse_ishares_acwi_csv(csv_text)

    # Skip re-downloading ACWI US constituents already fully covered in data/monthly_prices.csv.
    us_coverage = _load_us_completed_coverage(data_dir / "monthly_prices.csv")
    download_tickers: list[str] = []
    market_map: dict[str, str] = {"ACWI": "benchmark_acwi"}
    for c in constituents:
        market_map[c.ticker] = c.market
        if c.market == "us":
            us_months = us_coverage.get(c.ticker, set())
            if latest_completed_month in us_months and len(us_months) >= 48:
                continue
        download_tickers.append(c.ticker)
    download_tickers.append("ACWI")

    start = subtract_calendar_years(eff_as_of, years) - timedelta(days=35)
    end = eff_as_of + timedelta(days=2)
    fresh_rows, yahoo_currencies = fetch_yahoo_v8_monthly_bars(
        download_tickers,
        start=start,
        end=end,
        as_of=eff_as_of,
        max_workers=max_workers,
        market_by_ticker=market_map,
    )
    if not fresh_rows:
        raise RuntimeError("Yahoo Finance returned zero ACWI monthly price rows.")

    for c in constituents:
        if c.ticker in yahoo_currencies:
            c.quote_currency = yahoo_currencies[c.ticker]

    acwi_const_path = global_dir / "acwi_constituents.csv"
    write_acwi_constituents_csv(constituents, acwi_const_path)

    acwi_prices_path = global_dir / "acwi_monthly_prices.csv"
    merged_prices = merge_monthly_price_rows(acwi_prices_path, fresh_rows)
    write_monthly_prices_csv(merged_prices, acwi_prices_path)

    all_currs = sorted(
        {c.market_currency for c in constituents} | {c.quote_currency for c in constituents}
    )
    fx_fresh = fetch_all_fx_rates_v8(
        all_currs, years=years, as_of=eff_as_of, max_workers=max_workers
    )
    merged_fx = merge_fx_csv(global_dir / "fx_rates.csv", fx_fresh)

    snapshot_month = add_months(latest_completed_month, 1)
    update_acwi_snapshots_csv(global_dir / "acwi_snapshots.csv", snapshot_month, constituents)

    priced_set = {r["ticker"] for r in merged_prices} | set(us_coverage.keys())
    priced_constituents = sum(1 for c in constituents if c.ticker in priced_set)

    hero_daily_path: Path | None = None
    hero_daily_missing: tuple[str, ...] = ()
    try:
        hero_daily_path, hero_missing = refresh_hero_daily_prices_csv(
            root_dir=root_dir, as_of=eff_as_of, max_workers=max_workers
        )
        hero_daily_missing = tuple(hero_missing)
    except Exception:  # noqa: BLE001 - the hero chart degrades gracefully without daily bars
        hero_daily_missing = ()

    return AcwiRefreshResult(
        as_of_label=as_of_label,
        total_csv_equities=total_csv_equities,
        mapped_constituents=len(constituents),
        priced_tickers=priced_constituents,
        uk_accessible_count=sum(1 for c in constituents if c.uk_accessible),
        price_rows_count=len(merged_prices),
        fx_rows_count=len(merged_fx),
        hero_daily_path=str(hero_daily_path) if hero_daily_path is not None else None,
        hero_daily_missing=hero_daily_missing,
    )
