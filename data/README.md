# Public & Local Data Directory

## Public Committed Data (Tracked in Git)

All public market data and mechanistic strategy outputs live directly in `data/` and are refreshed automatically by the monthly GitHub Action (`.github/workflows/monthly-refresh.yml`) or manually via `uv run monthly-momentum refresh`:

- `data/constituents.csv` — Current index constituents fetched from Wikipedia (`Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Date added`).
- `data/constituent_snapshots.csv` — Monthly point-in-time constituent roster snapshots accumulated across refreshes.
- `data/monthly_prices.csv` — Completed monthly `close` and dividend/split-adjusted `adj_close` bars for index members and benchmark `^SP500TR`.
- `data/rankings/latest.csv` — Latest investment window's Top 10 ranking snapshot (matches `templates/monthly-ranking.example.csv`).
- `data/rankings/history.csv` — Mechanistic Top 10 ranking history across every monthly window.
- `data/model_holdings.csv` — Mechanistic Rule 6 tracking log for the model Top 3 portfolio (matches `templates/holdings.example.csv`).
- `data/performance.csv` — Monthly time-series equity & TWR NAV values for strategy variants vs `^SP500TR`.
- `data/summary.json` — Summary metrics, latest picks, Rule 6 signals, and metadata powering `README.md` and `assets/performance.png`.

## Private / Personal Folders (Gitignored)

Personal ISA records and one-off broker/screener exports stay out of version control in gitignored paths:

- `data/private/` — Personal holdings logs, ISA transaction records, broker exports, and Rule 6 top-10 tracking sheets (gitignored).
- `data/raw/` — Downloaded screener exports (e.g. Finviz or Market Chameleon CSVs) and raw ad-hoc market data dumps (gitignored).

Copy the header-only templates from [../templates/](../templates/) into `data/private/` or run `uv run monthly-momentum init` before recording personal portfolio data.
