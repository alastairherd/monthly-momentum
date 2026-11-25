# Monthly Index Momentum Rules

Complete reference for the evidence-supported strategy rules, rejected alternatives, live execution data, and backtest simplifications.

## The Rules

1. **What you can buy:** Shares in a major index on the day you buy.
   - The **S&P 500** is the most thoroughly tested universe.
   - A wider pool (**US, UK, Canada, Europe**) did better in the tests, but on weaker data.
2. **When:** On the **first trading day of each month**, invest that month's money.
3. **How to rank:** Take each share's **total return, including dividends, over the past 3 years**. Leave out any share that is **below its price of 3 months ago**.
4. **What to buy:** Split the month's money equally across the **top 3**.
   - **Aggressive version (Top 1):** Highest returns, but falls of up to **−76%**.
   - **Cautious version (Top 10):** Broader spread across the top 10.
   - Buy even if you already own the share.
5. **Never sell because a share has fallen.** Every stop-loss tested made things worse.
6. **Optional, staged exit for faded winners:**
   - Once a holding has been out of the **top-10 list for 6 years**, sell a third (**1/3**).
   - At **7 years**, sell half (**1/2**) of what's left.
   - At **8 years**, sell the rest.
   - If it gets back into the top 10, stop selling.
   - Sale money goes into that month's buys.
7. **Takeovers:** Cash from a takeover also goes into the next month's buys.
8. **Setup:**
   - Use a **commission-free broker with fractional shares**, inside a **Stocks and Shares ISA**.
   - Expect about **0.15% currency fee** on US shares, and **0.5% stamp duty** on UK shares.
   - Keep most of your money in a tracker and run this on a **minority slice**.
   - Decide in advance that you'll hold through a **60–75% fall**, and compare it against the tracker after **5 years**.

## Rejected After Testing

The following rules and exits were tested and rejected:

- Way II's **8%/10% stop-losses**, even with the 5-day pause.
- Selling after a **50% fall**, in full or half.
- Selling laggards after **4 years or less**.
- Staged selling that starts at **4 years**.

## Data You Need to Run It Live

Running the strategy live is far easier than backtesting. You only rank today's index members, so historical data on failed or delisted companies is not needed to execute monthly buys.

Each month you need:

- **The current index list**, plus each member's **3-year and 3-month returns**. Free screeners provide this:
  - **Finviz:** Has an index filter for membership in a major stock exchange index (such as Dow Jones Industrial or S&P 500) and provides *Performance: 3-Year, 5-Year, and 10-Year*. That is price-only, which is close enough for ranking.
  - **Market Chameleon:** Screener includes dividends, offering a **3 Month Total Return** (including dividends paid) and a **3-Year Total Return**.
- **Monthly ranking process:** Sort by 3-year return, drop anything with a negative 3-month return, and take the **top 3**. Track the **top 10** if using staged exits. See [../templates/monthly-ranking.example.csv](../templates/monthly-ranking.example.csv).
- **Your own records:** A simple sheet listing each holding and when you first bought it. For staged exits, also record the last month each holding appeared in the top 10. See [../templates/holdings.example.csv](../templates/holdings.example.csv).

## Simplifications vs. the Backtest

- **Shares listed less than 3 years ago:** Screeners will not show a 3-year return for them, so they drop out.
- **Shares that left the index:** If you already own one, keep holding it, but stop counting it as a winner.

Neither simplification should matter much.

## Independent Backtesting Note

Testing the rules yourself requires historical data that includes delisted companies (to avoid survivorship bias), from providers such as **Norgate**, **EODHD**, or the 20-year public US dataset (`fja05680/sp500` + `weib08/Stocks-Daily-Price`) supported by `monthly-momentum build-us20`. You do not need that data to run the rules live.

See [research.md](research.md) for the complete 20-year US, UK FTSE 100, international, and exit-rule evidence behind these rules.
