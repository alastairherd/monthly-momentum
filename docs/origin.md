# How this strategy came about

Back to the [README](../README.md).

## The starting point: Way II

The project began as a backtest of **Way II, "Backing winners"**, from Richard Koch and Leo Gough's *The FT Guide to Selecting Shares that Perform* (5th edition). The rules as I coded them:

1. **Average up once.** If a share gains 40% or more in its first year, buy the same amount again, capped at 25% of the portfolio. Fund it from cash or by selling the worst performers.
2. **Superstars** (30%+ annualised): sell half after a 15% fall from peak, and the rest after a further 15% fall.
3. **Mini-stars** (20%+ annualised): the same, with 7% falls.
4. **Everything else:** sell at 8% below purchase or 10% below peak.
5. **Takeovers:** sell.
6. **Each anniversary:** sell any share that lagged the index over the year.
7. **Top up** to 10 shares with the current best performers.
8. **Meltdown:** if the index falls 10% below its starting level or 15% below its peak, sell everything. Buy back once it is 10% above its low.

The book leaves some points open, so I made these calls:

- A share can't become a star until it has been held for 182 days.
- Winners are ranked by best annualised return over up to three years. Shares that fell over the last three months, or were sold in the last 60 days, are excluded.
- Signals are read at one close and trades execute at the next.
- Prices are total return, with dividends reinvested.

## Why it didn't work

The UK backtest looked good, but the dataset only held companies still listed today, and the rules added little beyond holding the first ten picks. Re-tested on US shares, it fell apart:

- **Underperformance.** From March 2022 to March 2026 it returned about 0.2% a year. An S&P 500 tracker returned about 11.8%.
- **Random starts.** Across 500 simulations from random ten-share portfolios, the rules beat simply holding those shares in about 1% of runs and never beat the tracker.
- **Too many small losses.** The 8% and 10% stop-losses kept firing on volatile US shares: 537 trades, mostly selling small losses and replacing them with new "winners".
- **Winners faded.** Its early picks were the previous year's winners, which stopped leading once large US tech took over.
- **The crash rule backfired.** It sold everything three times, including at the bottom of the April 2025 sell-off, and each time bought back about 10% higher.

Adding a pause before acting on a stop-loss didn't rescue it: 4.1–10.4% a year, well behind holding.

## How the rules evolved

1. **A wider test.** Re-running Way II on US data showed the UK result didn't carry over.
2. **Pauses.** Waiting through sharp drops instead of selling immediately helped a little, not enough.
3. **Monthly buying.** Switching to £100 a month, buy and hold each time, moved the question from "when do I sell?" to "where does new money go?".
4. **How many names.** Top 1 kept winning on the headline numbers. Rolling 10-year windows confirmed it often did best, with much bigger swings. Top 3 kept most of the upside with less riding on one company.
5. **Staged selling.** Selling on a crash hurt. Removing laggards gradually did not: selling in thirds once a share has spent 6, 7 and 8 years outside the top 10 is the one exit rule that sometimes helped. It stays optional.
6. **Other countries and a global pool.** To check it wasn't just a US effect, I tested 16 markets and a global pool where each month's winners can come from anywhere, converted to one currency.

The result is the rule in the README: buy the top three winners each month and hold them, optionally tapering out of long-faded names after six to eight years. The numbers behind each step are in [research.md](research.md), and the exact rules are in [rules.md](rules.md).
