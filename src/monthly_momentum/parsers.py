"""Screener CSV parsers for Finviz, Market Chameleon, and canonical snapshots."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from monthly_momentum.models import SecurityMetric
from monthly_momentum.normalize import normalize_ticker, parse_percent, ticker_match_key

_FINVIZ_3Y_ALIASES: tuple[str, ...] = (
    "performance (3 years)",
    "perf 3y",
    "3-year performance",
    "3y performance",
    "perf 3yr",
    "performance 3y",
)
_FINVIZ_3M_ALIASES: tuple[str, ...] = (
    "performance (quarter)",
    "perf quart",
    "perf quarter",
    "performance (3 months)",
    "perf 3m",
    "3-month performance",
)
_MC_3Y_ALIASES: tuple[str, ...] = (
    "3-year total return",
    "3 year total return",
    "3y total return",
    "3-yr total return",
    "total return 3y",
    "3-year return",
)
_MC_3M_ALIASES: tuple[str, ...] = (
    "3 month total return",
    "3-month total return",
    "3m total return",
    "3-mo total return",
    "total return 3m",
    "3-month return",
)
_CANONICAL_3Y_ALIASES: tuple[str, ...] = (
    "return_3y_pct",
    "return_3y",
    "3y_return",
    "3y_total_return",
)
_CANONICAL_3M_ALIASES: tuple[str, ...] = (
    "return_3m_pct",
    "return_3m",
    "3m_return",
    "3m_price_return",
)
_TICKER_ALIASES: tuple[str, ...] = ("ticker", "symbol", "epic")
_NAME_ALIASES: tuple[str, ...] = ("company", "company name", "company_name", "name", "security")
_INDEX_ALIASES: tuple[str, ...] = ("index", "universe")
_SECTOR_ALIASES: tuple[str, ...] = ("sector", "gics sector")


@dataclass(slots=True)
class ColumnOverrides:
    """Explicit header names overriding automatic screener column detection."""

    ticker: str | None = None
    name: str | None = None
    return_3y: str | None = None
    return_3m: str | None = None
    index: str | None = None
    sector: str | None = None


def _norm_header(header: str) -> str:
    return " ".join(header.strip().lower().split())


def detect_screener_source(headers: list[str]) -> str:
    """Auto-detect screener format from CSV column headers."""
    normed = {_norm_header(h) for h in headers}
    if any(alias in normed for alias in _CANONICAL_3Y_ALIASES):
        return "canonical"
    if any(alias in normed for alias in _MC_3Y_ALIASES) or any(
        alias in normed for alias in _MC_3M_ALIASES
    ):
        return "market_chameleon"
    if any(alias in normed for alias in _FINVIZ_3Y_ALIASES) or any(
        alias in normed for alias in _FINVIZ_3M_ALIASES
    ):
        return "finviz"
    raise ValueError(
        "Could not auto-detect CSV screener format from headers "
        f"{headers!r}. Specify --source or --col-* overrides."
    )


def _find_column(
    header_map: dict[str, str],
    aliases: tuple[str, ...],
    override: str | None = None,
    required: bool = True,
) -> str | None:
    if override is not None:
        key = _norm_header(override)
        if key in header_map:
            return header_map[key]
        raise ValueError(f"Column override {override!r} not found in CSV headers.")
    for alias in aliases:
        if alias in header_map:
            return header_map[alias]
    if required:
        raise ValueError(
            f"Missing required column matching any of {aliases!r} in headers "
            f"{list(header_map.values())!r}."
        )
    return None


def _metric_completeness_score(metric: SecurityMetric) -> tuple[int, int]:
    has_3y = 1 if metric.return_3y_pct is not None else 0
    has_3m = 1 if metric.return_3m_pct is not None else 0
    return (has_3y + has_3m, has_3y)


def load_screener_csv(
    path: Path,
    source: str = "auto",
    default_index: str = "S&P 500",
    index_filter: str | None = None,
    col_overrides: ColumnOverrides | None = None,
) -> list[SecurityMetric]:
    """Load and normalize security metrics from a Finviz, Market Chameleon, or canonical CSV."""
    overrides = col_overrides or ColumnOverrides()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file {path} has no header row.")
        headers = list(reader.fieldnames)
        header_map = {_norm_header(h): h for h in headers if h is not None}
        detected = detect_screener_source(headers) if source == "auto" else source.lower()

        if detected == "finviz":
            y3_aliases = _FINVIZ_3Y_ALIASES + _CANONICAL_3Y_ALIASES
            m3_aliases = _FINVIZ_3M_ALIASES + _CANONICAL_3M_ALIASES
            default_return_type = "price_only"
        elif detected == "market_chameleon":
            y3_aliases = _MC_3Y_ALIASES + _CANONICAL_3Y_ALIASES
            m3_aliases = _MC_3M_ALIASES + _CANONICAL_3M_ALIASES
            default_return_type = "total_return"
        elif detected == "canonical":
            y3_aliases = _CANONICAL_3Y_ALIASES + _MC_3Y_ALIASES + _FINVIZ_3Y_ALIASES
            m3_aliases = _CANONICAL_3M_ALIASES + _MC_3M_ALIASES + _FINVIZ_3M_ALIASES
            default_return_type = "total_return"
        else:
            raise ValueError(
                f"Unsupported source {source!r}; expected auto, finviz, market_chameleon, "
                "or canonical."
            )

        ticker_col = _find_column(header_map, _TICKER_ALIASES, overrides.ticker, required=True)
        name_col = _find_column(header_map, _NAME_ALIASES, overrides.name, required=False)
        y3_col = _find_column(header_map, y3_aliases, overrides.return_3y, required=True)
        m3_col = _find_column(header_map, m3_aliases, overrides.return_3m, required=True)
        index_col = _find_column(header_map, _INDEX_ALIASES, overrides.index, required=False)
        sector_col = _find_column(header_map, _SECTOR_ALIASES, overrides.sector, required=False)
        return_type_col = header_map.get("return_type")
        row_source_col = header_map.get("source")

        assert ticker_col is not None and y3_col is not None and m3_col is not None

        deduped: dict[str, SecurityMetric] = {}
        order: list[str] = []
        filter_norm = index_filter.strip().lower() if index_filter else None

        for row in reader:
            raw_ticker = (row.get(ticker_col) or "").strip()
            ticker = normalize_ticker(raw_ticker)
            if not ticker:
                continue

            row_index = (row.get(index_col) or "").strip() if index_col else ""
            effective_index = row_index or default_index
            if filter_norm and effective_index.strip().lower() != filter_norm:
                continue

            name = (row.get(name_col) or "").strip() if name_col else ""
            sector = (row.get(sector_col) or "").strip() if sector_col else ""
            row_return_type = (
                (row.get(return_type_col) or "").strip() if return_type_col else ""
            ) or default_return_type
            row_source = (
                (row.get(row_source_col) or "").strip() if row_source_col else ""
            ) or detected

            metric = SecurityMetric(
                ticker=ticker,
                name=name or ticker,
                index=effective_index,
                return_3y_pct=parse_percent(row.get(y3_col)),
                return_3m_pct=parse_percent(row.get(m3_col)),
                return_type=row_return_type,
                source=row_source,
                sector=sector,
            )

            key = ticker_match_key(ticker)
            if key not in deduped:
                deduped[key] = metric
                order.append(key)
            elif _metric_completeness_score(metric) > _metric_completeness_score(deduped[key]):
                deduped[key] = metric

    return [deduped[k] for k in order]
