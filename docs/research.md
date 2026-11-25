# Monthly Index Momentum Research Notes

Evidence summary supporting [rules.md](rules.md), compiled across 20-year survivorship-aware US testing, UK FTSE 100 analysis, 16 international equity markets, global currency-converted pools, and professional fund comparisons.

> **Note:** Research notes and backtests are historical evidence summaries, not financial advice.

## 1. 20-Year Survivorship-Aware US Study (2006–2025)

Using daily stock histories including delisted companies combined with historical S&P 500 membership intervals (covering 98–100% of index constituents per year, including collapsed or failed firms such as **Lehman Brothers**, **Bear Stearns**, **Wachovia**, **Fannie Mae**, **CIT**, **SVB**, and **First Republic**):

- **Remaining gaps:** Washington Mutual and pre-bankruptcy General Motors (2008–09) are absent from the free dataset, slightly flattering every strategy that could have held them, including the S&P 500 benchmark.
- **Settings:** £100/month invested on the first trading day of each month, dividends reinvested, no commission, fractional shares, `0.2%` transaction cost.

### Sub-Period & Crisis Performance (Annualized Money-Weighted Return)

| Period | S&P 500 Tracker | 10 Random Shares | Top 10 Winners (Hold) | Top 1 Winner (Hold) |
| :--- | :---: | :---: | :---: | :---: |
| 2006–2025 (20 yrs) | 13.3% | 13.3% | 17.7% | 23.4% |
| 2006–2015 (First decade) | 10.1% | 11.0% | 11.1% | 13.4% |
| 2016–2025 (Second decade) | 15.6% | 12.5% | 28.0% | 47.5% |
| 2007–2012 Financial Crisis | 7.7% | 9.1% | 7.9% | 11.3% |
| Worst Drawdown (20 yrs) | −55% | — | −66% | −76% |

Key observations:
- **Regime dependence:** Momentum barely matched equal-weighted random stocks during `2006–2015` (and trailed random picks during `2007–2012`), then outperformed sharply in `2016–2025`.
- **Concentration & tail winners:** In `2016–2025`, **Nvidia (`NVDA`)** alone grew to **46%** of the Top 10 portfolio (and up to **55–70%** in Top 1). Even after **removing Nvidia** (`15.0%`/yr) or **removing Nvidia, AMD, and Broadcom** (`14.2%`/yr), Top 10 still beat the S&P 500 tracker (`13.3%`/yr, which retained those three stocks).
- **Rare catastrophic failures:** Across `344` stocks bought by the Top 10 strategy over 20 years, only `7` fell more than 80% within a year of appearing in the Top 10, and `11` went near zero (e.g., SVB, Signature Bank, SunEdison, Circuit City). Small equal monthly purchases kept single failures immaterial relative to multi-bagger winners.

## 2. Position Count: Top 1 vs Top 3 vs Top 5 vs Top 10

| Rule (2006–2025, £100/mo) | Top 1 | Top 3 | Top 5 | Top 10 |
| :--- | :---: | :---: | :---: | :---: |
| Hold forever (% a year) | 23.4% | 21.6% | 19.5% | 17.7% |
| Hold forever, Nvidia removed | 19.5% | 18.0% | 16.9% | 15.0% |
| Worst drawdown (hold forever) | −76% | −65% | −66% | −66% |

Across all `11` rolling 10-year windows starting each year from `2006` to `2016`:
- **Top 1** beat the S&P 500 tracker in `11 of 11` windows (median `18.2%`, worst window `12.7%`, worst fall `−78%`).
- **Top 3** beat the tracker in `11 of 11` windows (median `17.5%`, worst window `10.7%`, worst fall `−65%`).
- **Top 10** beat the tracker in `8 of 11` windows (median `13.9%`, worst window `7.8%`, worst fall `−67%`).

Top 3–5 delivers most of the concentration upside with materially less single-stock concentration risk than Top 1 (which put up to 55–70% into a single winner and trailed in weaker international markets).

## 3. Exit Rules & "Sleeping Giants"

### Rejected Stop-Losses
- **Way II's 8% / 10% stop-losses** (even with a 5-day pause): `4.1%`–`10.4%`/yr, far below buy-and-hold.
- **50% trailing fall exit (full or half at 50% / rest at 75%):** Hurts returns severely because eventual multi-baggers suffer huge drawdowns along the way (**Nvidia** fell `−85%` after its 2008 purchase, **AMD** `−96%`, **Netflix** `−82%`). Market-wide crashes still drive portfolio drawdowns regardless.

### Laggard Exits: Why 4 Years Hurts vs Staged 6/7/8 Years

| Exit Rule (2006–2025, %/yr) | Top 1 | Top 3 | Top 5 | Top 10 |
| :--- | :---: | :---: | :---: | :---: |
| Hold forever (with / without NVDA) | 23.4 / 19.5 | 21.6 / 18.0 | 19.5 / 16.9 | 17.7 / 15.0 |
| Sell all at 4 yrs out of Top 10 | 31.8 / 14.8 | 26.8 / 13.9 | 23.1 / 13.1 | 19.2 / 12.7 |
| Staged 4 / 5 / 6 yrs | 28.0 / 20.0 | 24.7 / 17.0 | 21.3 / 15.1 | 18.4 / 13.7 |
| **Staged 6 / 7 / 8 yrs (Rule 6)** | **26.4 / 22.0** | **22.6 / 18.4** | **19.9 / 16.6** | **17.9 / 14.9** |

- **Why 4-year exits fail without Nvidia:** Although ~70% of individual 4-year sales moved cash into higher-returning replacements, the remaining ~30% sold "sleeping giants" during multi-year plateaus (**Apple** Oct 2016 went on to `10.8×`, **Amazon** Nov 2015 `7.5×`, **Alphabet** Jan 2012 `19×`, **Broadcom** Jan 2022 `6.5×`). Without Nvidia (`77` replacement buys), the 4-year rule trailed plain holding (`$173k` vs `$198k` in Top 10).
- **Why 6 / 7 / 8-year staging works:** Giants like Apple stayed outside the Top 10 for six years (`2012–2018`) before compounding `5.7×`. Delaying trims to years **6** (`1/3`), **7** (`1/2` remaining), and **8** (remainder) spared Amazon and Broadcom, improving returns slightly for Top 1–3 even without Nvidia (`18.4%` vs `18.0%` in Top 3), while stopping sales if the holding returns to the Top 10.

## 4. UK FTSE 100 & 16 International Markets

Testing `£100`/month across international equity sets (including `0.5%` UK stamp duty on FTSE purchases; note non-US datasets lack delisted failures, so equal-split within the same dataset serves as the survivorship-matched baseline):

- **UK FTSE 100:** Winners beat the equal-split baseline in all three tested windows (`2010–2018`: Top 3 `23.1%` vs `11.5%`; `2015–Mar 2020`: Top 3 `1.7%` vs `0.7%`; `2022–2026`: Top 3 `26.6%` vs `15.7%` FTSE tracker). Rule 6 / 4-year exits barely triggered in the UK due to a smaller index.
- **2022–2026 Europe (with dividends):** Top 10 beat the equal-split baseline in all `6` tested markets (Germany, Italy, Spain, France, Sweden, Switzerland). Dividends added `~4%`/yr to the baseline and `~5%`/yr to winners (energy, banks, utilities).
- **2009–2018 Global Bear-Rebound Decade:** Top 10 won in Canada and Norway, roughly matched in China, and **lost** in Japan, South Korea (`8.2%` vs `12.2%`), Australia, Turkey, Vietnam, and both US NYSE/Nasdaq samples (`9.8%` vs `15.0%`). Momentum systematically struggled after the 2009 crash and in Japan/Korea.
- **Payoff Asymmetry Across 16 Markets:** Buying and holding builds 100–200 positions so losses are bounded (`−9%` average money shortfall when trailing), while big winning runs add `+16%` average surplus (overall median `+1%`, mean `+2%` across all 16 markets when including 2009–2018).
- **Global USD-Converted Pool:** Combining markets in USD (`2010–2018` and `2022–2026`) gave Top 3 `24.0%`–`32.8%`/yr, though non-US survivorship bias flatters foreign selections until survivorship-free global data (e.g., Norgate / EODHD) is connected.

## 5. Hedge Funds, Active Managers & Live Momentum ETFs

On a **time-weighted return (TWR)** basis (`2006–2025` US large caps):

| Strategy | TWR CAGR | Volatility | Max Drawdown | Sharpe Ratio |
| :--- | :---: | :---: | :---: | :---: |
| S&P 500 Tracker | 10.9% | 19% | −55% | 0.48 |
| Top 10 Winners (Hold) | 13.6% | 24% | −66% | 0.50 |
| Top 3 Winners (Hold) | 17.5% | 26% | −65% | 0.62 |
| Top 1 Winner (Hold) | 19.2% | 30% | −76% | 0.58 |
| Top 1 + Staged 6/7/8y | 21.6% | 33% | −76% | 0.60 |

- **Live ETF validation:** iShares MSCI USA Momentum Factor ETF (`MTUM`, `0.15%` ER) returned `17.58%`/yr over 10 years to June 2026, confirming real-money momentum persistence.
- **Why institutions cannot replicate Top 3:** Concentration limits, benchmark tracking-error caps, and career risk during `−65%` to `−76%` drawdowns prevent institutional funds from holding 40–70% weights in a single winner.

## 6. Practical Verdict & Execution Notes

- **As an S&P 500 replacement:** **3/10** — excessive single-stock concentration, regional failures (Japan/Korea), and `−65%` to `−76%` drawdowns.
- **As a satellite slice (e.g., ~20% of equity portfolio inside a UK Stocks & Shares ISA):** **6/10** — captures individual-investor concentration advantage tax-free with low costs (`0.15%` US FX / `0.50%` UK stamp duty) alongside a core global/S&P tracker, evaluated over 5+ years.
- **Broker API note:** Trading 212's API (`Invest` and `Stocks ISA`, beta) supports orders, positions, and account state, but provides **no historical price or candle endpoints** — historical price feeds must come from public datasets (`yfinance`, Hugging Face/Norgate/EODHD) or screeners (Finviz, Market Chameleon).
