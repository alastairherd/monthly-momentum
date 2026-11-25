"""Monthly ranking engine and CSV snapshot persistence."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from monthly_momentum.models import (
    ExcludedSecurity,
    RankedSecurity,
    RankingResult,
    SecurityMetric,
)
from monthly_momentum.normalize import normalize_month, normalize_ticker

RANKING_COLUMNS: list[str] = [
    "month",
    "rank",
    "ticker",
    "name",
    "index",
    "return_3y_pct",
    "return_3m_pct",
    "return_type",
    "source",
    "selected_for_buy",
]


def rank_securities(
    metrics: list[SecurityMetric],
    month: str,
    top_n: int = 3,
    index: str = "S&P 500",
    source_override: str | None = None,
) -> RankingResult:
    """Rank index constituents by 3-year return, excluding missing or negative 3-month returns."""
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}.")
    norm_month = normalize_month(month)

    eligible: list[SecurityMetric] = []
    excluded: list[ExcludedSecurity] = []

    for m in metrics:
        y3 = m.return_3y_pct
        m3 = m.return_3m_pct
        if y3 is None or not math.isfinite(y3):
            excluded.append(
                ExcludedSecurity(
                    ticker=m.ticker,
                    name=m.name,
                    reason="missing_3y_return",
                    return_3y_pct=None,
                    return_3m_pct=m3 if m3 is not None and math.isfinite(m3) else None,
                )
            )
            continue
        if m3 is None or not math.isfinite(m3):
            excluded.append(
                ExcludedSecurity(
                    ticker=m.ticker,
                    name=m.name,
                    reason="missing_3m_return",
                    return_3y_pct=y3,
                    return_3m_pct=None,
                )
            )
            continue
        if m3 < 0.0:
            excluded.append(
                ExcludedSecurity(
                    ticker=m.ticker,
                    name=m.name,
                    reason="negative_3m_return",
                    return_3y_pct=y3,
                    return_3m_pct=m3,
                )
            )
            continue
        eligible.append(m)

    eligible.sort(
        key=lambda item: (
            -(item.return_3y_pct if item.return_3y_pct is not None else 0.0),
            -(item.return_3m_pct if item.return_3m_pct is not None else 0.0),
            item.ticker,
        )
    )

    ranked: list[RankedSecurity] = []
    for pos, item in enumerate(eligible, start=1):
        assert item.return_3y_pct is not None and item.return_3m_pct is not None
        ranked.append(
            RankedSecurity(
                month=norm_month,
                rank=pos,
                ticker=item.ticker,
                name=item.name,
                index=item.index or index,
                return_3y_pct=item.return_3y_pct,
                return_3m_pct=item.return_3m_pct,
                return_type=item.return_type,
                source=source_override or item.source,
                selected_for_buy=pos <= top_n,
                in_top10=pos <= 10,
                sector=item.sector,
            )
        )

    eff_source = source_override or (metrics[0].source if metrics else "unknown")
    eff_return_type = metrics[0].return_type if metrics else "total_return"

    return RankingResult(
        month=norm_month,
        index=index,
        top_n=top_n,
        ranked=ranked,
        excluded=excluded,
        source=eff_source,
        return_type=eff_return_type,
    )


def ranking_rows_to_dicts(rows: list[RankedSecurity]) -> list[dict[str, str]]:
    """Serialize ranked securities into canonical template column dictionaries."""
    return [
        {
            "month": item.month,
            "rank": str(item.rank),
            "ticker": item.ticker,
            "name": item.name,
            "index": item.index,
            "return_3y_pct": f"{item.return_3y_pct:.4f}",
            "return_3m_pct": f"{item.return_3m_pct:.4f}",
            "return_type": item.return_type,
            "source": item.source,
            "selected_for_buy": "true" if item.selected_for_buy else "false",
        }
        for item in rows
    ]


def write_ranking_csv(result: RankingResult, path: Path, limit: int | None = 10) -> None:
    """Write ranking snapshot CSV matching templates/monthly-ranking.example.csv."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = result.ranked if limit is None else result.ranked[:limit]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RANKING_COLUMNS)
        writer.writeheader()
        writer.writerows(ranking_rows_to_dicts(rows))


def write_ranking_history_csv(rows: list[RankedSecurity], path: Path) -> None:
    """Write concatenated multi-month Top 10 ranking history CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RANKING_COLUMNS)
        writer.writeheader()
        writer.writerows(ranking_rows_to_dicts(rows))


def read_ranking_csv(path: Path) -> list[RankedSecurity]:
    """Read canonical ranking snapshot CSV back into RankedSecurity objects."""
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows: list[RankedSecurity] = []
        for raw in reader:
            ticker = normalize_ticker(raw.get("ticker") or "")
            if not ticker:
                continue
            rank = int(raw["rank"])
            selected_raw = (raw.get("selected_for_buy") or "").strip().lower()
            rows.append(
                RankedSecurity(
                    month=normalize_month(raw["month"]),
                    rank=rank,
                    ticker=ticker,
                    name=(raw.get("name") or ticker).strip(),
                    index=(raw.get("index") or "S&P 500").strip(),
                    return_3y_pct=float(raw["return_3y_pct"]),
                    return_3m_pct=float(raw["return_3m_pct"]),
                    return_type=(raw.get("return_type") or "total_return").strip(),
                    source=(raw.get("source") or "csv").strip(),
                    selected_for_buy=selected_raw in {"true", "1", "yes"},
                    in_top10=rank <= 10,
                )
            )
    return rows
