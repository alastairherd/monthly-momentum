# Monthly Momentum

Workspace, rulebook, and CSV templates for running a monthly index-constituent momentum strategy inside a Stocks and Shares ISA.

> **Note:** This repository is for personal research, record-keeping, and tooling. Nothing here is financial advice.

## Monthly Workflow Summary

1. **When:** On the first trading day of each month, invest that month's contribution (plus any Rule 6/7 cash).
2. **Universe & Ranking:** Start from current constituents of a major index (S&P 500 is the most thoroughly tested), rank by 3-year total return including dividends, and exclude any share below its price 3 months ago.
3. **Selection:** Split that month's money equally across the top 3 (even if you already hold them). Record the top 10 if tracking the optional Rule 6 exit.
4. **Hold Discipline:** Never sell because a share has fallen — every tested stop-loss hurt performance.
5. **Optional Staged Exit (Rule 6):** If a holding stays outside the top 10 for 6 years, sell 1/3; at 7 years, sell 1/2 of the remainder; at 8 years, sell the rest (stop selling if it returns to the top 10).

See [docs/rules.md](docs/rules.md) for the complete rules, tested variants, rejected rules, free screener options, simplifications, and backtesting data requirements.

## Repository Layout

| Path | Purpose | Tracked in Git |
| :--- | :--- | :--- |
| [docs/rules.md](docs/rules.md) | Full strategy specification, rejected rules, and data sources | Yes |
| [templates/monthly-ranking.example.csv](templates/monthly-ranking.example.csv) | Header template for monthly screener snapshots | Yes |
| [templates/holdings.example.csv](templates/holdings.example.csv) | Header template for personal holdings and Rule 6 top-10 tracking | Yes |
| [data/README.md](data/README.md) | Guide to gitignored local data folders | Yes |
| `data/private/`, `data/raw/`, `records/`, `portfolio/` | Personal ISA records, holdings logs, and screener CSV dumps | No (gitignored) |

## Privacy & Git Hygiene

Keep all personal financial data out of version control. Personal holdings, ISA transactions, broker exports, and downloaded screener dumps belong in gitignored locations (`data/private/`, `data/raw/`, `records/`, `portfolio/`) or files matching `*.local.*`, `*.private.*`, `*.sqlite3`, or `*.db`.

Only strategy documentation, code, and header-only `.example.csv` templates should be committed to GitHub.

## Planned Next Steps

- Build or script a monthly ranking tracker from screener exports (Finviz / Market Chameleon).
- Maintain a holdings & top-10 appearance log to automate Rule 6 (6/7/8-year faded-winner checks).
- Optionally add survivorship-bias-free backtesting using historical datasets that include delisted companies (e.g., Norgate or EODHD).
