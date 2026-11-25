# Public & Local Data Directory

## Public Committed Data (Tracked in Git)

All public market data, performance trajectories, charts, and mechanistic strategy outputs live directly in `data/` and `assets/`, and are refreshed automatically by the monthly GitHub Action (`.github/workflows/monthly-refresh.yml`) or manually via `uv run monthly-momentum refresh --with-global`:

- `data/constituents_history.csv` — Historical S&P 500 membership intervals (`fja05680/sp500` back to 1996 + live Wikipedia updates).
- `data/constituents.csv` — Current S&P 500 index constituents fetched from Wikipedia (`Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Date added`).
- `data/constituent_snapshots.csv` — Monthly point-in-time S&P 500 constituent roster snapshots accumulated across refreshes.
- `data/monthly_prices.csv` — Completed monthly `close` and dividend/split-adjusted `adj_close` bars (20-year HF + Yahoo ratio-spliced series + `^SP500TR`).
- `data/rankings/latest.csv` & `data/rankings/history.csv` — Latest Top 10 and full US S&P 500 window history.
- `data/model_holdings.csv` — Mechanistic Rule 6 tracking log for the US Top 3 model portfolio (matches `templates/holdings.example.csv`).
- `data/performance.csv` & `data/summary.json` — US S&P 500 variant equity & TWR NAV series (`assets/performance.png`).
- `data/global/` — International & All-World datasets and reports:
  - `acwi_constituents.csv`, `acwi_snapshots.csv`, `acwi_monthly_prices.csv` — Official iShares MSCI ACWI (`ACWI`) holdings with UK retail Stocks & Shares ISA accessibility flags (`uk_accessible`, `uk_access_note`) and subunit-normalized Yahoo v8 monthly prices.
  - `constituents.csv`, `monthly_prices.csv` — Wikipedia `FTSE 100`, `S&P/TSX 60`, `EURO STOXX 50` constituents and monthly bars.
  - `fx_rates.csv` — Monthly `USD{CCY}=X` and USD cross FX pairs across all ACWI currencies.
  - `rankings/latest_acwi_all.csv`, `history_acwi_all.csv` — Unfiltered Full ACWI rankings with UK ISA accessibility columns.
  - `rankings/latest_acwi_uk_accessible.csv`, `history_acwi_uk_accessible.csv`, `model_holdings_acwi_uk_accessible.csv` — Filtered UK-ISA-accessible All-World winners & Rule 6 log.
  - `rankings/latest_ftse100.csv`, `history_ftse100.csv`, `model_holdings_ftse100.csv` — UK FTSE 100 picks & Rule 6 log (`0.50%` UK stamp duty).
  - `performance_acwi.csv`, `performance_acwi_uk_accessible.csv`, `performance_ftse100.csv`, `summary.json` — Variant TWR & DCA series powering `assets/performance_acwi.png`, `assets/performance_acwi_uk_accessible.png`, `assets/performance_ftse100.png`, and `assets/performance_markets_comparison.png`.

## Private / Personal Folders (Gitignored)

Personal ISA records and one-off broker/screener exports stay out of version control in gitignored paths:

- `data/private/` — Personal holdings logs, ISA transaction records, broker exports, and Rule 6 top-10 tracking sheets (gitignored).
- `data/raw/` — Downloaded screener exports (e.g. Finviz or Market Chameleon CSVs) and raw ad-hoc market data dumps (gitignored).

Copy the header-only templates from [../templates/](../templates/) into `data/private/` or run `uv run monthly-momentum init` before recording personal portfolio data.
