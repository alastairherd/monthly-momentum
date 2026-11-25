# Monthly Momentum

Mechanistic monthly index-constituent momentum strategy, public S&P 500 ranking & performance tracker, Rule 6 faded-winner monitor, and survivorship-bias-free backtester (`uv` Python).

> **Note:** This repository is for personal research, record-keeping, and tooling. Nothing here is financial advice.

<!-- AUTO-GENERATED:START -->

## Latest Mechanistic Picks — 2026-11 Window

Generated deterministically from completed monthly data through **2026-10** (`503` active constituents · `261` eligible after the 3-year history & non-negative 3-month return filter). Next trading day action: split this month's contribution equally across **Top 3** (or **Top 5** for Balanced).

### Standard Strategy Picks (Top 3 — Equal 1/3 Split)

| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return |
| :---: | :--- | :--- | :--- | :---: | :---: |
| #1 | **LITE** | Lumentum | Information Technology | +2044.10% | +17.75% |
| #2 | **MU** | Micron Technology | Information Technology | +1235.84% | +7.50% |
| #3 | **CVNA** | Carvana | Consumer Discretionary | +1164.63% | +9.51% |

- **Aggressive (Top 1):** **LITE** (Lumentum) — `+2044.10%` 3Y TR, `+17.75%` 3M *(note: Top 1 historically saw drawdowns up to −76%)*.
- **Balanced (Top 5):** **LITE**, **MU**, **CVNA**, **PLTR**, **ECHO** (equal 1/5 split).

<details>
<summary>Full Top 10 for 2026-11 (Cautious Variant & Rule 6 Watchlist)</summary>

| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return | Top 3 Buy |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: |
| #1 | LITE | Lumentum | Information Technology | +2044.10% | +17.75% | Yes |
| #2 | MU | Micron Technology | Information Technology | +1235.84% | +7.50% | Yes |
| #3 | CVNA | Carvana | Consumer Discretionary | +1164.63% | +9.51% | Yes |
| #4 | PLTR | Palantir Technologies | Information Technology | +1143.99% | +49.61% | No |
| #5 | ECHO | EchoStar | Communication Services | +599.42% | +15.28% | No |
| #6 | DELL | Dell Technologies | Information Technology | +562.57% | +4.67% | No |
| #7 | CRWD | CrowdStrike | Information Technology | +466.68% | +31.21% | No |
| #8 | AMD | Advanced Micro Devices | Information Technology | +412.49% | +6.02% | No |
| #9 | NVDA | Nvidia | Information Technology | +403.31% | +1.94% | No |
| #10 | MRVL | Marvell Technology | Information Technology | +319.42% | +4.71% | No |

</details>

## Performance Chart (Mechanistic Simulation)

![Monthly Momentum Performance](assets/performance.png)

Monthly £500 DCA simulation across **251** windows (**2006-01** to **2026-11**, `£125,000` invested, `0.15%` US FX fee on buys/sells vs `0.00%` `^SP500TR` benchmark):

| Variant | Ending Value | XIRR | TWR CAGR | Max Drawdown | Top Holding (%) | 5Y Rolling Win vs S&P 500 TR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Aggressive (Top 1) | £2,230,104 | 23.27% | 20.47% | -66.9% | NVDA (40.1%) | 99.0% (189/191) |
| Standard (Top 3) | £1,869,372 | 21.94% | 19.77% | -66.0% | NVDA (33.7%) | 100.0% (191/191) |
| Standard (Top 3 + Rule 6) | £2,036,495 | 22.58% | 20.22% | -66.0% | NVDA (42.2%) | 100.0% (191/191) |
| Balanced (Top 5) | £1,553,120 | 20.54% | 17.13% | -64.8% | NVDA (34.4%) | 94.2% (180/191) |
| Balanced (Top 5 + Rule 6) | £1,498,362 | 20.27% | 16.87% | -64.8% | NVDA (37.9%) | 94.2% (180/191) |
| Cautious (Top 10) | £1,236,131 | 18.81% | 15.76% | -63.9% | NVDA (36.3%) | 86.4% (165/191) |
| Cautious (Top 10 + Rule 6) | £1,194,711 | 18.55% | 15.53% | -63.9% | NVDA (35.0%) | 84.3% (161/191) |
| *Standard (Top 3) — excl. NVDA* | £1,263,288 | 18.97% | 17.51% | -65.3% | AAPL (39.9%) | 97.9% (187/191) |
| *Cautious (Top 10) — excl. NVDA* | £806,439 | 15.55% | 13.31% | -62.6% | AAPL (24.1%) | 79.1% (151/191) |
| *Standard (Top 3) — excl. NVDA/AMD/AVGO* | £1,083,922 | 17.81% | 16.63% | -65.3% | AAPL (46.6%) | 94.2% (180/191) |
| S&P 500 Total Return (`^SP500TR`) | £609,852 | 13.39% | 11.13% | -50.9% | Cap-weighted | Baseline |

> **Historical Dataset Coverage:** Built from point-in-time S&P 500 membership (`fja05680/sp500` back to 1996 + live Wikipedia updates) and US stock price histories (`weib08/Stocks-Daily-Price` spliced onto Yahoo Finance, covering `663` active and acquired/delisted S&P 500 tickers; note that OTC bankruptcy tickers such as `LEHMQ`, `BSC`, `SIVB`, and `FRC` are absent from the free Hugging Face dataset). See [docs/research.md](docs/research.md) for the full survivorship-free study.

### Historical Sub-Period Breakdown (XIRR % / Year)

| Period | Top 1 | Top 3 | Top 5 | Top 10 | S&P 500 TR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| First Decade (2006–2015) (2006-01..2015-12) | 18.59% | 16.96% | 14.64% | 12.27% | 10.67% |
| Financial Crisis Era (2007–2012) (2007-01..2012-12) | 19.41% | 16.33% | 12.85% | 9.02% | 7.71% |
| Recent Decade (2016–Latest) (2016-01..2026-11) | 44.82% | 37.76% | 33.33% | 28.24% | 15.37% |

## Multi-Market & Global Developed Pool (2026-11)

Mechanistic international rankings refreshed alongside S&P 500 from Wikipedia + Yahoo Finance (note: non-US pools use current index constituents and therefore carry survivorship bias; see [docs/research.md](docs/research.md)).

### Global Developed Pool Top 3 (US + UK + Canada + Eurozone, USD FX-converted · `841` tickers)

| Rank | Ticker | Company | Index | Currency | 3Y Return (USD) | 3M Return (USD) |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: |
| #1 | **LITE** | Lumentum | S&P 500 | USD | +2044.10% | +17.75% |
| #2 | **MU** | Micron Technology | S&P 500 | USD | +1235.84% | +7.50% |
| #3 | **CVNA** | Carvana | S&P 500 | USD | +1164.63% | +9.51% |

### FTSE 100 Picks (2026-11 · GBP, 0.50% UK Stamp Duty)

| Rank | Ticker | Company | Sector | 3Y Total Return | 3M Price Return |
| :---: | :--- | :--- | :--- | :---: | :---: |
| #1 | **BGEO.L** | Lion Finance Group | Banks | +261.72% | +3.62% |
| #2 | **PCT.L** | Polar Capital Technology Trust | Closed End Investments | +202.85% | +3.69% |
| #3 | **SMT.L** | Scottish Mortgage Investment Trust | Closed End Investments | +147.85% | +19.62% |

- FTSE 100 Top 3 DCA (2017-12..2026-11): XIRR `11.71%` vs `ISF.L` TR ETF `7.39%`, TWR CAGR `11.41%`, Max Drawdown `-38.4%`.

## Model Portfolio & Rule 6 Faded-Winner Status

- **Active model positions (Standard Top 3 + Rule 6):** `71` (tracked in [`data/model_holdings.csv`](data/model_holdings.csv)).
- **Rule 6 Exit Signals this month:** None triggered.

| Ticker | Company | Months Out of Top 10 | Status | Next Rule 6 Check |
| :--- | :--- | :---: | :--- | :---: |
| CME | CME Group | 94m | `rule6_stage2_sold` | 2027-01 |
| NKTR | NKTR | 92m | `rule6_stage2_sold` | 2027-03 |
| CSX | CSX Corporation | 88m | `rule6_stage2_sold` | 2027-07 |
| TTWO | Take-Two Interactive | 85m | `rule6_stage2_sold` | 2027-10 |
| BA | Boeing | 85m | `rule6_stage2_sold` | 2027-10 |

## Mechanistic Stock Picks by Month / Window

Every monthly window below is computed mechanistically from `data/monthly_prices.csv` using the completed prior month's data (`data/rankings/history.csv`).

### Latest 12 Monthly Windows

| Window | Signal Data | Top 3 (Standard Equal Split) | Top 1 (Aggressive) | Ranks 4–10 (Rule 6 Watchlist) | Eligible |
| :--- | :--- | :--- | :--- | :--- | :---: |
| 2026-11 | 2026-10 | **LITE** (+2044%), **MU** (+1236%), **CVNA** (+1165%) | LITE | PLTR, ECHO, DELL, CRWD, AMD, NVDA, MRVL | 261 |
| 2026-10 | 2026-09 | **LITE** (+2050%), **PLTR** (+1069%), **HOOD** (+1047%) | LITE | DELL, CRWD, AMD, NVDA, ANET, HPE, P | 186 |
| 2026-09 | 2026-08 | **LITE** (+1590%), **PLTR** (+1144%), **HOOD** (+862%) | LITE | DELL, CVNA, CRWD, NVDA, IBKR, ANET, BNY | 303 |
| 2026-08 | 2026-07 | **WDC** (+1601%), **STX** (+1345%), **MU** (+1066%) | WDC | DELL, HOOD, HWM, FLEX, CRWD, ANET, NVDA | 299 |
| 2026-07 | 2026-06 | **WDC** (+2138%), **APP** (+1902%), **MU** (+1753%) | WDC | STX, LITE, VRT, CVNA, FIX, CIEN, HOOD | 319 |
| 2026-06 | 2026-05 | **CVNA** (+2725%), **APP** (+2351%), **WDC** (+1722%) | CVNA | VRT, LITE, STX, MU, FIX, CIEN, PLTR | 194 |
| 2026-05 | 2026-04 | **VRT** (+2109%), **LITE** (+1770%), **WDC** (+1576%) | VRT | FIX, STX, CIEN, COHR, MU, NVDA, AVGO | 244 |
| 2026-04 | 2026-03 | **VRT** (+1657%), **LITE** (+1201%), **FIX** (+855%) | VRT | WDC, CIEN, STX, COHR, MU, HWM, EME | 223 |
| 2026-03 | 2026-02 | **FIX** (+895%), **WDC** (+865%), **NVDA** (+664%) | FIX | MU, CIEN, STX, HWM, NRG, GE, LRCX | 321 |
| 2026-02 | 2026-01 | **CVNA** (+3844%), **FIX** (+855%), **WDC** (+656%) | CVNA | MU, STX, HWM, RCL, EME, META, LRCX | 320 |
| 2026-01 | 2025-12 | **CVNA** (+8803%), **FIX** (+721%), **WDC** (+625%) | CVNA | AVGO, GE, MU, STX, HWM, LRCX, CEG | 233 |
| 2025-12 | 2025-11 | **APP** (+4060%), **PLTR** (+2146%), **HOOD** (+1240%) | APP | NVDA, AVGO, WDC, STX, GE, HWM, CRWD | 247 |

<details>
<summary>Full Monthly Pick History (251 windows: 2006-01 to 2026-11)</summary>

| Window | Signal Data | Top 3 (Standard) | Top 1 | Ranks 4–10 | Eligible |
| :--- | :--- | :--- | :--- | :--- | :---: |
| 2026-11 | 2026-10 | LITE, MU, CVNA | LITE | PLTR, ECHO, DELL, CRWD, AMD, NVDA, MRVL | 261 |
| 2026-10 | 2026-09 | LITE, PLTR, HOOD | LITE | DELL, CRWD, AMD, NVDA, ANET, HPE, P | 186 |
| 2026-09 | 2026-08 | LITE, PLTR, HOOD | LITE | DELL, CVNA, CRWD, NVDA, IBKR, ANET, BNY | 303 |
| 2026-08 | 2026-07 | WDC, STX, MU | WDC | DELL, HOOD, HWM, FLEX, CRWD, ANET, NVDA | 299 |
| 2026-07 | 2026-06 | WDC, APP, MU | WDC | STX, LITE, VRT, CVNA, FIX, CIEN, HOOD | 319 |
| 2026-06 | 2026-05 | CVNA, APP, WDC | CVNA | VRT, LITE, STX, MU, FIX, CIEN, PLTR | 194 |
| 2026-05 | 2026-04 | VRT, LITE, WDC | VRT | FIX, STX, CIEN, COHR, MU, NVDA, AVGO | 244 |
| 2026-04 | 2026-03 | VRT, LITE, FIX | VRT | WDC, CIEN, STX, COHR, MU, HWM, EME | 223 |
| 2026-03 | 2026-02 | FIX, WDC, NVDA | FIX | MU, CIEN, STX, HWM, NRG, GE, LRCX | 321 |
| 2026-02 | 2026-01 | CVNA, FIX, WDC | CVNA | MU, STX, HWM, RCL, EME, META, LRCX | 320 |
| 2026-01 | 2025-12 | CVNA, FIX, WDC | CVNA | AVGO, GE, MU, STX, HWM, LRCX, CEG | 233 |
| 2025-12 | 2025-11 | APP, PLTR, HOOD | APP | NVDA, AVGO, WDC, STX, GE, HWM, CRWD | 247 |
| 2025-11 | 2025-10 | APP, PLTR, NVDA | APP | HOOD, AVGO, GE, HWM, DASH, WDC, STX | 260 |
| 2025-10 | 2025-09 | APP, PLTR, NVDA | APP | HOOD, VST, RCL, GE, AVGO, HWM, EME | 309 |
| 2025-09 | 2025-08 | PLTR, NVDA, RCL | PLTR | VST, SMCI, AVGO, GE, NFLX, HWM, COIN | 335 |
| 2025-08 | 2025-07 | PLTR, SMCI, NVDA | PLTR | VST, RCL, AXON, COIN, GE, AVGO, CEG | 330 |
| 2025-07 | 2025-06 | PLTR, SMCI, NVDA | PLTR | RCL, VST, AXON, NFLX, COIN, GE, AVGO | 284 |
| 2025-06 | 2025-05 | PLTR, AXON, NVDA | PLTR | VST, NFLX, GE, CEG, HWM, RCL, AVGO | 199 |
| 2025-05 | 2025-04 | PLTR, SMCI, NFLX | PLTR | FICO, HWM, NRG, LLY, TKO, TT, PGR | 166 |
| 2025-04 | 2025-03 | SMCI, PLTR, HWM | SMCI | GE, TPL, LLY, TRGP, NRG, CAH, TKO | 227 |
| 2025-03 | 2025-02 | SMCI, PLTR, HWM | SMCI | LLY, AVGO, GE, META, NRG, RCL, PGR | 175 |
| 2025-02 | 2025-01 | VST, CEG, PLTR | VST | AXON, HWM, AVGO, TPL, ANET, TRGP, GE | 274 |
| 2025-01 | 2024-12 | VST, FICO, NVDA | VST | PLTR, AXON, AVGO, TRGP, HWM, DECK, ANET | 205 |
| 2024-12 | 2024-11 | VST, FICO, HWM | VST | NVDA, TRGP, TPL, AXON, RCL, ANET, PLTR | 340 |
| 2024-11 | 2024-10 | VST, NVDA, FICO | VST | ANET, AVGO, HWM, LLY, TRGP, IRM, BLDR | 295 |
| 2024-10 | 2024-09 | VST, FICO, ANET | VST | AVGO, BLDR, HWM, PHM, TRGP, ERIE, IRM | 388 |
| 2024-09 | 2024-08 | NVDA, LLY, ANET | NVDA | FICO, TRGP, AVGO, BLDR, MPC, HWM, ACGL | 366 |
| 2024-08 | 2024-07 | NVDA, VST, ANET | NVDA | AVGO, TRGP, LLY, MCK, FANG, FICO, HWM | 362 |
| 2024-07 | 2024-06 | NVDA, VST, LLY | NVDA | ANET, AVGO, MCK, TRGP, FICO, PANW, KLAC | 196 |
| 2024-06 | 2024-05 | NVDA, VST, LLY | NVDA | FSLR, ANET, DECK, TRGP, MPC, AVGO, MCK | 282 |
| 2024-05 | 2024-04 | SMCI, NVDA, LLY | SMCI | BLDR, MPC, TRGP, AVGO, MCK, FANG, COP | 297 |
| 2024-04 | 2024-03 | SMCI, NVDA, BLDR | SMCI | LLY, MPC, ANET, TRGP, FANG, AVGO, STLD | 362 |
| 2024-03 | 2024-02 | NVDA, BLDR, ANET | NVDA | LLY, STLD, JBL, NUE, TRGP, MPC, MCK | 388 |
| 2024-02 | 2024-01 | NVDA, BLDR, MPC | NVDA | NUE, STLD, ANET, TRGP, LLY, JBL, IT | 437 |
| 2024-01 | 2023-12 | BLDR, NVDA, FANG | BLDR | LLY, TRGP, NUE, STLD, ANET, JBL, PWR | 416 |
| 2023-12 | 2023-11 | FANG, LLY, MPC | FANG | TRGP, STLD, ANET, PANW, IT, IRM, MCK | 238 |
| 2023-11 | 2023-10 | FANG, MPC, TRGP | FANG | COP, LLY, ANET, HAL, MCK, EQT, ACGL | 69 |
| 2023-10 | 2023-09 | OXY, TRGP, FANG | OXY | MPC, APA, EOG, COP, XOM, SLB, HES | 139 |
| 2023-09 | 2023-08 | DVN, TRGP, OXY | DVN | ON, MPC, FANG, PWR, NUE, LLY, STLD | 356 |
| 2023-08 | 2023-07 | DVN, ON, PWR | DVN | TRGP, NVDA, NUE, FANG, STLD, OXY, MPC | 334 |
| 2023-07 | 2023-06 | PWR, ON, NVDA | PWR | NUE, TRGP, TSLA, EQT, PANW, BBWI, HCA | 300 |
| 2023-06 | 2023-05 | ON, PWR, FSLR | ON | NVDA, HWM, AVGO, LLY, ANET, IT, EQT | 168 |
| 2023-05 | 2023-04 | TRGP, PWR, FSLR | TRGP | NVDA, HWM, ACGL, XOM, FTNT, ANET, AJG | 182 |
| 2023-04 | 2023-03 | ON, MPC, FCX | ON | FSLR, TSLA, STLD, PWR, NUE, MOS, NVDA | 269 |
| 2023-03 | 2023-02 | STLD, TSLA, NUE | STLD | PWR, FCX, ON, URI, NVDA, MOS, MPWR | 179 |
| 2023-02 | 2023-01 | MRNA, STLD, FCX | MRNA | PWR, NUE, ALB, FSLR, NVDA, SEDG, URI | 370 |
| 2023-01 | 2022-12 | MRNA, PWR, STLD | MRNA | BBWI, SEDG, FCX, LLY, DVN, MCK, ETSY | 391 |
| 2022-12 | 2022-11 | ENPH, MRNA, ALB | ENPH | SEDG, PWR, FCX, ON, LLY, NVDA, ETSY | 336 |
| 2022-11 | 2022-10 | ENPH, ALB, DVN | ENPH | PWR, LLY, FCX, DXCM, MOH, MCK, MOS | 181 |
| 2022-10 | 2022-09 | TSLA, ENPH, ALB | TSLA | PWR, ON, MOH, DVN, MCK, AAPL, REGN | 141 |
| 2022-09 | 2022-08 | TSLA, ENPH, ALB | TSLA | PWR, ON, SEDG, AAPL, MPWR, NUE, MCK | 130 |
| 2022-08 | 2022-07 | TSLA, MRNA, ENPH | TSLA | SEDG, PWR, FTNT, GNRC, ALB, MPWR, LLY | 229 |
| 2022-07 | 2022-06 | LLY, MCK, UNH | LLY | AZO, BMY, LKQ, DG, TMUS, HUM, CI | 48 |
| 2022-06 | 2022-05 | ENPH, ALB, KLAC | ENPH | PWR, DVN, MOS, NUE, LLY, MCK, SNPS | 185 |
| 2022-05 | 2022-04 | ENPH, SEDG, FCX | ENPH | TGT, NUE, PWR, MCK, LLY, NEM, MOS | 158 |
| 2022-04 | 2022-03 | ENPH, TSLA, SEDG | ENPH | FCX, PWR, URI, NUE, CF, DE, MCK | 177 |
| 2022-03 | 2022-02 | FTNT, FCX, HWM | FTNT | STX, AMP, AVGO, NUE, BRO, DVN, DE | 226 |
| 2022-02 | 2022-01 | AAPL, KLAC, QCOM | AAPL | AMAT, LRCX, STX, TSCO, LOW, AMP, BRO | 213 |
| 2022-01 | 2021-12 | ENPH, TSLA, NVDA | ENPH | SEDG, AMD, EPAM, LRCX, TER, FTNT, KLAC | 366 |
| 2021-12 | 2021-11 | ENPH, TSLA, NVDA | ENPH | AMD, ETSY, LRCX, FTNT, KLAC, TER, DXCM | 197 |
| 2021-11 | 2021-10 | ENPH, TSLA, GNRC | ENPH | AMD, ETSY, NVDA, DXCM, MPWR, MSCI, PAYC | 276 |
| 2021-10 | 2021-09 | TSLA, ETSY, CMG | TSLA | MPWR, DXCM, MSCI, KLAC, WST, PWR, CDNS | 210 |
| 2021-09 | 2021-08 | ENPH, TSLA, GNRC | ENPH | ETSY, AMD, CMG, WST, FTNT, DXCM, MSCI | 269 |
| 2021-08 | 2021-07 | ENPH, GNRC, AMD | ENPH | DXCM, FTNT, CMG, ZBRA, WST, PAYC, MSCI | 270 |
| 2021-07 | 2021-06 | ENPH, TSLA, GNRC | ENPH | AMD, ETSY, DXCM, LRCX, FTNT, ZBRA, WST | 343 |
| 2021-06 | 2021-05 | WST, FTNT, TER | WST | LRCX, TGT, PYPL, POOL, CRL, KLAC, MSCI | 416 |
| 2021-05 | 2021-04 | GNRC, DXCM, TER | GNRC | WST, FTNT, ZBRA, LRCX, CMG, PYPL, PAYC | 410 |
| 2021-04 | 2021-03 | ETSY, GNRC, CMG | ETSY | PENN, CDNS, ZBRA, FTNT, KLAC, PYPL, LRCX | 362 |
| 2021-03 | 2021-02 | ENPH, TSLA, ETSY | ENPH | DXCM, CMG, CDNS, ZBRA, FTNT, MPWR, PYPL | 309 |
| 2021-02 | 2021-01 | ENPH, TSLA, ETSY | ENPH | DXCM, AMD, CMG, PAYC, NOW, AAPL, ZBRA | 397 |
| 2021-01 | 2020-12 | TSLA, AMD, ETSY | TSLA | PAYC, CMG, NOW, ZBRA, MSCI, FTNT, CDNS | 391 |
| 2020-12 | 2020-11 | ETSY, AMD, PAYC | ETSY | NOW, ZBRA, MSCI, TGT, IDXX, POOL, PYPL | 345 |
| 2020-11 | 2020-10 | ETSY, PAYC, CMG | ETSY | NOW, MKTX, CPRT, POOL, TGT, WST, QCOM | 235 |
| 2020-10 | 2020-09 | DXCM, ETSY, AMD | DXCM | PAYC, NOW, CMG, ADBE, AMZN, MSCI, AAPL | 323 |
| 2020-09 | 2020-08 | AMD, DXCM, NOW | AMD | CMG, PAYC, AMZN, MSCI, WST, PYPL, ADBE | 346 |
| 2020-08 | 2020-07 | DXCM, AMD, PAYC | DXCM | NOW, FTNT, MSCI, CMG, PYPL, AMZN, WST | 349 |
| 2020-07 | 2020-06 | DXCM, PAYC, AMD | DXCM | NOW, FTNT, MSCI, PYPL, MSFT, ADBE, NFLX | 409 |
| 2020-06 | 2020-05 | DXCM, AMD, PAYC | DXCM | NOW, FTNT, MSCI, PYPL, ODFL, CPRT, KEYS | 204 |
| 2020-05 | 2020-04 | AMD, NOW, MSCI | AMD | NVDA, NFLX, MSFT, AMZN, ADBE, KEYS, PYPL | 63 |
| 2020-04 | 2020-03 | NOW, MSCI, NFLX | NOW | MSFT, NVDA, ODFL, SBAC, AMZN, VRTX, PGR | 27 |
| 2020-03 | 2020-02 | PAYC, NOW, MSCI | PAYC | AMD, ADBE, NVDA, MSFT, LRCX, NFLX, ZTS | 80 |
| 2020-02 | 2020-01 | PAYC, AMD, NOW | PAYC | TDG, MSCI, CPRT, FTNT, ADBE, MA, ANSS | 291 |
| 2020-01 | 2019-12 | AMD, NOW, FTNT | AMD | MSCI, NRG, CPRT, ADBE, ZBRA, VRTX, MA | 324 |
| 2019-12 | 2019-11 | AMD, NRG, FTNT | AMD | MSCI, NOW, CPRT, ADBE, ALGN, EW, MA | 328 |
| 2019-11 | 2019-10 | AMD, NRG, CPRT | AMD | KEYS, MSCI, LRCX, CDW, ALGN, NVDA, MU | 249 |
| 2019-10 | 2019-09 | NRG, BA, KEYS | NRG | CPRT, CDW, TTWO, MA, LRCX, NVDA, MSFT | 256 |
| 2019-09 | 2019-08 | AMD, KEYS, NRG | AMD | TTWO, BA, MA, CPRT, ADBE, NVDA, MU | 311 |
| 2019-08 | 2019-07 | AMD, MU, CPRT | AMD | CDNS, KEYS, ADBE, TTWO, IDXX, MA, MSCI | 253 |
| 2019-07 | 2019-06 | AMD, NFLX, MSCI | AMD | PYPL, CSX, KEYS, ADBE, MA, CPRT, ADSK | 284 |
| 2019-06 | 2019-05 | AMD, ALGN, CSX | AMD | PYPL, CPRT, MSCI, IDXX, DHR, TTWO, ADBE | 184 |
| 2019-05 | 2019-04 | AMD, NVDA, ANET | AMD | ALGN, NFLX, MU, KEYS, NTAP, CPRT, MSCI | 347 |
| 2019-04 | 2019-03 | AMD, NVDA, ANET | AMD | MU, ALGN, NFLX, NRG, BA, KEYS, CSX | 400 |
| 2019-03 | 2019-02 | AMD, ANET, BA | AMD | NRG, ALGN, MU, NFLX, NKTR, KEYS, CSX | 281 |
| 2019-02 | 2019-01 | AMD, NRG, ALGN | AMD | NFLX, BA, MU, KEYS, ADSK, NKTR, IDXX | 256 |
| 2019-01 | 2018-12 | NRG, CME, NEM | NRG | AVGO, YUM, NEE, EXC, CNP, AMT, MKC | 56 |
| 2018-12 | 2018-11 | NRG, UNH, BA | NRG | ROL, DHR, CME, HCA, DE, BSX, ZTS | 150 |
| 2018-11 | 2018-10 | TTWO, ISRG, NRG | TTWO | ADBE, NTAP, FTNT, ADSK, PYPL, UNH, ROL | 140 |
| 2018-10 | 2018-09 | AMD, NVDA, ALGN | AMD | NKTR, TTWO, ANET, DXC, AMZN, ISRG, ADSK | 296 |
| 2018-09 | 2018-08 | AMD, NVDA, ALGN | AMD | TTWO, DXC, ANET, AMZN, CPRT, IDXX, ADBE | 305 |
| 2018-08 | 2018-07 | NVDA, AMD, ALGN | NVDA | TTWO, IDXX, AMZN, CPRT, ADBE, NFLX, ISRG | 306 |
| 2018-07 | 2018-06 | NVDA, AMD, ALGN | NVDA | TTWO, NFLX, AMZN, IDXX, ADBE, ISRG, MSCI | 241 |
| 2018-06 | 2018-05 | NVDA, AMD, ALGN | NVDA | TTWO, NFLX, AMZN, ADBE, IDXX, ISRG, MSCI | 212 |
| 2018-05 | 2018-04 | NKTR, NFLX, DXC | NKTR | AMZN, IDXX, ADBE, ISRG, MSCI, BBY, PGR | 122 |
| 2018-04 | 2018-03 | NVDA, NKTR, NFLX | NVDA | ALGN, AMZN, DXC, LRCX, ADBE, AMAT, IPGP | 172 |
| 2018-03 | 2018-02 | NVDA, ALGN, NFLX | NVDA | AMZN, AMD, DXC, ADBE, BA, ISRG, GPN | 221 |
| 2018-02 | 2018-01 | NVDA, AMD, ALGN | NVDA | NFLX, AMZN, DXC, ADBE, BA, ISRG, DHR | 341 |
| 2018-01 | 2017-12 | NVDA, ALGN, NFLX | NVDA | AMZN, DXC, AVGO, GPN, BA, ADBE, STZ | 318 |
| 2017-12 | 2017-11 | NVDA, ALGN, NFLX | NVDA | DXC, AMZN, AVGO, AVY, ADBE, UNH, AOS | 337 |
| 2017-11 | 2017-10 | NVDA, ALGN, DXC | NVDA | AMZN, NFLX, AVGO, EA, LRCX, AMAT, MTD | 278 |
| 2017-10 | 2017-09 | NVDA, AMD, ALGN | NVDA | DXC, EA, AVGO, NFLX, GPN, AOS, LRCX | 275 |
| 2017-09 | 2017-08 | NVDA, DXC, ALGN | NVDA | EA, AVGO, AMD, GPN, NFLX, CHTR, INCY | 250 |
| 2017-08 | 2017-07 | NVDA, AVGO, AMD | NVDA | EA, AMZN, DXC, ALGN, NFLX, INCY, GPN | 288 |
| 2017-07 | 2017-06 | NVDA, AVGO, ULTA | NVDA | DXC, AMZN, EA, EW, ALGN, GPN, DRI | 263 |
| 2017-06 | 2017-05 | NVDA, ULTA, AVGO | NVDA | EA, AMZN, DXC, EW, NFLX, GPN, IDXX | 228 |
| 2017-05 | 2017-04 | AVGO, EA, NFLX | AVGO | AMD, ULTA, DXC, AMZN, EW, IDXX, LRCX | 277 |
| 2017-04 | 2017-03 | NVDA, AMD, AVGO | NVDA | EA, NFLX, ULTA, SWKS, CHTR, AMZN, IDXX | 290 |
| 2017-03 | 2017-02 | NVDA, AVGO, ULTA | NVDA | EA, SWKS, EW, LUV, CHTR, LRCX, ALK | 327 |
| 2017-02 | 2017-01 | NVDA, AVGO, ULTA | NVDA | EA, SWKS, EW, LUV, ALK, DLR, NFLX | 309 |
| 2017-01 | 2016-12 | NVDA, AVGO, LUV | NVDA | ULTA, ALK, NFLX, DLR, MLM, UNH, NOC | 223 |
| 2016-12 | 2016-11 | NVDA, SWKS, LUV | NVDA | MLM, NOC, VMC, UNH, NFLX, ALK, LRCX | 200 |
| 2016-11 | 2016-10 | NVDA, AVGO, SWKS | NVDA | EA, NFLX, STZ, LUV, NOC, EXPE, AMZN | 140 |
| 2016-10 | 2016-09 | NVDA, AVGO, EW | NVDA | EA, SWKS, GPN, STZ, AYI, TSN, AMZN | 232 |
| 2016-09 | 2016-08 | AVGO, NVDA, EW | AVGO | AYI, STZ, EA, SWKS, AMZN, TSN, MNST | 285 |
| 2016-08 | 2016-07 | AVGO, NVDA, GPN | AVGO | EW, STZ, AYI, EA, TSN, VMC, MNST | 282 |
| 2016-07 | 2016-06 | AVGO, NVDA, AYI | AVGO | EA, STZ, GPN, EW, NOC, CNC, TSN | 242 |
| 2016-06 | 2016-05 | AVGO, AYI, NVDA | AVGO | EA, GPN, NFLX, LUV, EW, STZ, SWKS | 340 |
| 2016-05 | 2016-04 | AVGO, LUV, EW | AVGO | STZ, GPN, UAA, BSX, NOC, TSN, NVDA | 322 |
| 2016-04 | 2016-03 | AVGO, SWKS, LUV | AVGO | UAA, STZ, NOC, NVDA, TSN, HUM, GT | 242 |
| 2016-03 | 2016-02 | AVGO, DAL, STZ | AVGO | NOC, TSN, KR, FSLR, HUM, CI, HRL | 119 |
| 2016-02 | 2016-01 | STZ, AVGO, ILMN | STZ | KR, NVDA, EXR, TSN, HRL, FSLR, ADBE | 91 |
| 2016-01 | 2015-12 | NFLX, AVGO, EA | NFLX | DAL, LUV, STZ, ILMN, HBI, KR, BSX | 270 |
| 2015-12 | 2015-11 | NFLX, LUV, DAL | NFLX | EA, STZ, AVGO, HBI, BSX, VRTX, AAL | 265 |
| 2015-11 | 2015-10 | EA, DAL, LUV | EA | HBI, REGN, AAL, STZ, BSX, ORLY, UAL | 171 |
| 2015-10 | 2015-09 | NFLX, EA, DAL | NFLX | LUV, STZ, UAA, RCL, ORLY, SIG, AAP | 111 |
| 2015-09 | 2015-08 | NFLX, DAL, EA | NFLX | STZ, SEE, HCA, UHS, REGN, RCL, UAA | 96 |
| 2015-08 | 2015-07 | NFLX, EA, GILD | NFLX | STZ, REGN, HCA, RCL, UHS, KR, UAA | 217 |
| 2015-07 | 2015-06 | NFLX, EA, GILD | NFLX | REGN, AVGO, SWKS, CI, UAA, SEE, APTV | 151 |
| 2015-06 | 2015-05 | NFLX, STZ, AVGO | NFLX | EA, GILD, SWKS, REGN, HCA, KR, UHS | 172 |
| 2015-05 | 2015-04 | NFLX, STZ, HBI | NFLX | EA, AVGO, SWKS, REGN, FSLR, VRTX, HCA | 259 |
| 2015-04 | 2015-03 | LUV, STZ, HBI | LUV | GILD, REGN, NFLX, SWKS, EA, HCA, AVGO | 210 |
| 2015-03 | 2015-02 | STZ, LUV, GILD | STZ | NFLX, AVGO, BIIB, EA, UAA, KR, HCA | 231 |
| 2015-02 | 2015-01 | STZ, LUV, REGN | STZ | DAL, WHR, NFLX, UAA, HCA, BIIB, AVGO | 195 |
| 2015-01 | 2014-12 | REGN, DAL, MU | REGN | LUV, STZ, STX, WHR, WDC, AVGO, VRTX | 288 |
| 2014-12 | 2014-11 | REGN, MU, DAL | REGN | LUV, STZ, STX, VRTX, WHR, WDC, APTV | 268 |
| 2014-11 | 2014-10 | REGN, MU, GILD | REGN | DAL, URI, STZ, STX, LUV, PHM, WHR | 275 |
| 2014-10 | 2014-09 | MU, URI, STX | MU | REGN, LYB, GILD, LUV, UAA, NFLX, WDC | 167 |
| 2014-09 | 2014-08 | STX, REGN, MU | STX | GILD, STZ, LYB, UAA, LUV, BIIB, WDC | 259 |
| 2014-08 | 2014-07 | REGN, DAL, STX | REGN | GILD, MU, STZ, UAA, LYB, BIIB, WDC | 221 |
| 2014-07 | 2014-06 | MU, DAL, STZ | MU | GILD, STX, LYB, UAA, BIIB, PHM, WMB | 274 |
| 2014-06 | 2014-05 | DAL, STZ, STX | DAL | LYB, MU, VFC, DFS, WDC, SHW, PPG | 240 |
| 2014-05 | 2014-04 | REGN, DAL, STZ | REGN | LYB, VFC, M, SHW, ORLY, LMT, VLO | 280 |
| 2014-04 | 2014-03 | REGN, STX, STZ | REGN | BIIB, DAL, LYB, M, ORLY, WDC, DFS | 215 |
| 2014-03 | 2014-02 | REGN, BIIB, STX | REGN | GILD, STZ, MA, V, LYB, PHM, DAL | 250 |
| 2014-02 | 2014-01 | REGN, BIIB, STX | REGN | GILD, STZ, MA, V, VFC, LYB, HRB | 197 |
| 2014-01 | 2013-12 | STX, BIIB, GILD | STX | MA, V, STZ, DFS, MCO, VFC, LYB | 312 |
| 2013-12 | 2013-11 | REGN, BIIB, STX | REGN | GILD, LYB, STZ, MA, BKNG, VFC, DFS | 317 |
| 2013-11 | 2013-10 | REGN, BIIB, STX | REGN | LYB, GILD, STZ, DFS, MA, GME, SBUX | 250 |
| 2013-10 | 2013-09 | REGN, BIIB, LYB | REGN | GILD, STZ, SBUX, DFS, MA, MCO, BKNG | 260 |
| 2013-09 | 2013-08 | REGN, LYB, GILD | REGN | STZ, BKNG, SBUX, MA, GME, VFC, PVH | 190 |
| 2013-08 | 2013-07 | REGN, LYB, BKNG | REGN | GILD, STX, DFS, STZ, MCO, SBUX, HD | 259 |
| 2013-07 | 2013-06 | REGN, LYB, BKNG | REGN | BIIB, STX, DFS, STZ, MCO, MNST, GILD | 213 |
| 2013-06 | 2013-05 | REGN, BIIB, LYB | REGN | BKNG, DFS, MCO, STZ, STX, GILD, MA | 306 |
| 2013-05 | 2013-04 | REGN, BIIB, DFS | REGN | STZ, CMG, BKNG, MCO, MNST, GILD, SHW | 286 |
| 2013-04 | 2013-03 | BIIB, DFS, STZ | BIIB | CMG, BKNG, SHW, NFLX, FOSL, LEN, SBUX | 314 |
| 2013-03 | 2013-02 | BKNG, CMG, BIIB | BKNG | STZ, NFLX, FOSL, PVH, VLO, SHW, ORLY | 312 |
| 2013-02 | 2013-01 | BKNG, FOSL, CMG | BKNG | BIIB, LEN, CRM, EMN, AN, SHW, SBUX | 303 |
| 2013-01 | 2012-12 | LEN, BKNG, FOSL | LEN | SHW, PPG, CMI, M, SBUX, EMN, FAST | 206 |
| 2012-12 | 2012-11 | BIIB, BKNG, LEN | BIIB | FOSL, DFS, CMCSA, SHW, HD, AZO, CF | 227 |
| 2012-11 | 2012-10 | FOSL, PRGO, LEN | FOSL | EL, DFS, OKE, FAST, WYNN, CMCSA, HD | 224 |
| 2012-10 | 2012-09 | AAPL, EL, EW | AAPL | FOSL, BIIB, OKE, ROST, TDC, AMZN, CRM | 258 |
| 2012-09 | 2012-08 | AAPL, PRGO, EL | AAPL | FOSL, EW, ROST, AMZN, BIIB, OKE, DFS | 278 |
| 2012-08 | 2012-07 | MNST, PRGO, AAPL | MNST | SPG, AIV, ROST, DFS, EW, BIIB, OKE | 147 |
| 2012-07 | 2012-06 | MNST, PRGO, DLTR | MNST | DFS, ISRG, ROST, SPG, LEN, AIV, BIIB | 126 |
| 2012-06 | 2012-05 | CMG, AAPL, SBUX | CMG | PRGO, DFS, ISRG, DLTR, M, ROST, OKE | 126 |
| 2012-05 | 2012-04 | BKNG, FOSL, CMG | BKNG | FFIV, AAPL, EL, DFS, TDC, WYNN, PRGO | 255 |
| 2012-04 | 2012-03 | BKNG, WYNN, TGNA | BKNG | FFIV, CMG, AAPL, ISRG, DFS, IP, SBUX | 298 |
| 2012-03 | 2012-02 | GNW, BKNG, CMG | GNW | FITB, JBL, IP, CBRE, FFIV, F, AAPL | 292 |
| 2012-02 | 2012-01 | BKNG, CMG, F | BKNG | FITB, FFIV, CBRE, SBUX, AAPL, TPR, THC | 256 |
| 2012-01 | 2011-12 | BKNG, CMG, SBUX | BKNG | AAPL, F, FFIV, THC, FTI, KMX, EL | 315 |
| 2011-12 | 2011-11 | CMG, SBUX, M | CMG | FFIV, EL, TDC, CMI, FTI, KMX, CBRE | 213 |
| 2011-11 | 2011-10 | CMG, AN, FFIV | CMG | TDC, CTSH, AAPL, RL, SBUX, TPR, HUM | 138 |
| 2011-10 | 2011-09 | AAPL, AMZN, AZO | AAPL | ORLY, TJX, MA, CMS, BMY, NI, VFC | 38 |
| 2011-09 | 2011-08 | BKNG, CMG, AN | BKNG | AMZN, SBUX, AAPL, AZO, ORLY, WYNN, RL | 54 |
| 2011-08 | 2011-07 | NFLX, CMG, AN | NFLX | AMZN, SBUX, TPR, EL, AAPL, ORLY, RL | 92 |
| 2011-07 | 2011-06 | NFLX, BKNG, FFIV | NFLX | CMG, AN, ORLY, EW, AMZN, TDC, SBUX | 175 |
| 2011-06 | 2011-05 | NFLX, BKNG, CMG | NFLX | EW, AMZN, AZO, ROST, ORLY, NTAP, EL | 211 |
| 2011-05 | 2011-04 | NFLX, BKNG, EW | NFLX | CMG, TDC, CTSH, AMZN, AZO, ROST, SBUX | 270 |
| 2011-04 | 2011-03 | NFLX, BKNG, EW | NFLX | CTSH, AMZN, ROST, AAPL, AZO, AN, JBL | 251 |
| 2011-03 | 2011-02 | NFLX, BKNG, AAPL | NFLX | ROST, CTSH, NTAP, EL, AN, CMI, RL | 297 |
| 2011-02 | 2011-01 | NFLX, BKNG, CTSH | NFLX | AAPL, CRM, F, NTAP, ROST, CMI, AMZN | 272 |
| 2011-01 | 2010-12 | NFLX, FFIV, BKNG | NFLX | ROST, F, AZO, NTAP, CTSH, CRM, HAS | 289 |
| 2010-12 | 2010-11 | BKNG, ROST, CRM | BKNG | AZO, F, CTSH, NTAP, AMZN, HAS, ORLY | 297 |
| 2010-11 | 2010-10 | BKNG, ROST, CRM | BKNG | AZO, AMZN, ORLY, EL, NTAP, HAS, TJX | 262 |
| 2010-10 | 2010-09 | BKNG, ROST, CRM | BKNG | EP, AZO, NTAP, AAPL, AKAM, HAS, AMZN | 280 |
| 2010-09 | 2010-08 | BKNG, CRM, EP | BKNG | AZO, MCD, CLF, CTSH, INTU, VTR, HAS | 124 |
| 2010-08 | 2010-07 | CRM, VTR, AZO | CRM | HAS, PSA, WELL, NTAP, ORLY, CHRW, CMI | 68 |
| 2010-07 | 2010-06 | AAPL, CRM, NEM | AAPL | HAS, AZO, EOG, CMI, GIS, ORLY, NTAP | 47 |
| 2010-06 | 2010-05 | AAPL, CRM, AMZN | AAPL | TJX, FSLR, ROST, FTI, OXY, CMI, FMC | 184 |
| 2010-05 | 2010-04 | BKNG, ISRG, AAPL | BKNG | FSLR, WDC, AMZN, CRM, FTI, FLS, ATGE | 298 |
| 2010-04 | 2010-03 | BKNG, AMZN, ISRG | BKNG | AAPL, CF, CLF, ATGE, FLS, FTI, OXY | 240 |
| 2010-03 | 2010-02 | BKNG, ISRG, CF | BKNG | AAPL, ATGE, CLF, WDC, FLS, FTI, CMI | 215 |
| 2010-02 | 2010-01 | BKNG, ISRG, AMZN | BKNG | CF, MA, AAPL, ATGE, WDC, FTI, OXY | 244 |
| 2010-01 | 2009-12 | BKNG, CF, AMZN | BKNG | ISRG, MA, AAPL, WDC, ATGE, CRM, FTI | 238 |
| 2009-12 | 2009-11 | BKNG, CF, AMZN | BKNG | ISRG, MA, AAPL, ATGE, FTI, FLS, WDC | 244 |
| 2009-11 | 2009-10 | CF, AMZN, MA | CF | ISRG, AAPL, ATGE, FLS, RRC, WDC, FTI | 232 |
| 2009-10 | 2009-09 | CF, AMZN, MA | CF | ATGE, ISRG, AAPL, OI, FTI, WDC, FLS | 294 |
| 2009-09 | 2009-08 | CF, MA, AMZN | CF | AAPL, ISRG, ATGE, OI, WDC, RRC, FLS | 281 |
| 2009-08 | 2009-07 | CF, MA, AMZN | CF | AAPL, ISRG, ATGE, OI, JNPR, WDC, MCD | 277 |
| 2009-07 | 2009-06 | CF, AAPL, ATGE | CF | AMZN, ICE, MCD, OI, GILD, RRC, BAX | 285 |
| 2009-06 | 2009-05 | CF, MA, AAPL | CF | AMZN, MCD, ICE, RRC, OI, AZO, NEE | 301 |
| 2009-05 | 2009-04 | CF, AMZN, AAPL | CF | AZO, RRC, NEE, HAS, YUM, CMI, OI | 219 |
| 2009-04 | 2009-03 | CF, AMZN, AAPL | CF | AZO, RRC, NEE, ORCL, IBM, NTRS, GME | 85 |
| 2009-03 | 2009-02 | CF, AMZN, AZO | CF | GILD, GME, HES, IBM, PCG, NTRS, TMO | 48 |
| 2009-02 | 2009-01 | MCD, GILD, ABT | MCD | AZO, TAP, NEE, AMZN, XOM, CL, SJM | 57 |
| 2009-01 | 2008-12 | ICE, MCD, GILD | ICE | CHRW, NUE, TAP, AZO, XOM, SHW, T | 23 |
| 2008-12 | 2008-11 | KR, XOM, SHW | KR | ADM, CLX, BBT, ZION, HBAN, RF | 9 |
| 2008-11 | 2008-10 | CHRW, GIS, SHW | CHRW | CPB, WFC, JPM, CLX, KMB, CB, DVA | 22 |
| 2008-10 | 2008-09 | MCD, SCHW, LMT | MCD | BAX, NSC, NKE, FAST, HPQ, BXP, PSA | 117 |
| 2008-09 | 2008-08 | CF, ISRG, UNP | CF | NSC, TMO, MCD, TROW, LMT, HAS, SCHW | 80 |
| 2008-08 | 2008-07 | ISRG, CMI, CSX | ISRG | NOV, FLR, SLB, UNP, GILD, MCD, NSC | 76 |
| 2008-07 | 2008-06 | AAPL, CNX, NOV | AAPL | RRC, NUE, HES, CMI, FCX, FLR, CSX | 116 |
| 2008-06 | 2008-05 | AAPL, RRC, CMI | AAPL | CNX, HES, FCX, NOV, TEX, CSX, GME | 228 |
| 2008-05 | 2008-04 | AAPL, GME, RRC | AAPL | CNX, CMI, FCX, TEX, HES, NOV, NUE | 178 |
| 2008-04 | 2008-03 | RRC, GILD, CSX | RRC | NUE, EOG, DVN, CHRW, GLW, APA, BXP | 73 |
| 2008-03 | 2008-02 | RRC, CNX, TEX | RRC | HES, FCX, GILD, EOG, RIG, CSX, OXY | 55 |
| 2008-02 | 2008-01 | RRC, CNX, HES | RRC | DE, CSX, HUM, CHRW, AIZ, PEG, FE | 41 |
| 2008-01 | 2007-12 | AAPL, GME, MTW | AAPL | NOV, RRC, HES, GOOGL, CNX, VLO, CME | 109 |
| 2007-12 | 2007-11 | AAPL, MTW, GOOGL | AAPL | NOV, CME, HUM, FCX, AKAM, FLR, CNX | 146 |
| 2007-11 | 2007-10 | NVDA, AAPL, NOV | NVDA | HUM, CME, FCX, GOOGL, CMI, FLR, RIG | 202 |
| 2007-10 | 2007-09 | AAPL, NVDA, ATI | AAPL | NOV, GOOGL, TEX, CME, CMI, HUM, FLR | 138 |
| 2007-09 | 2007-08 | NVDA, AAPL, GOOGL | NVDA | NOV, CME, CMI, RIG, HUM, SLB, FLR | 77 |
| 2007-08 | 2007-07 | AAPL, NVDA, CBRE | AAPL | CME, TEX, RIG, NOV, CMI, HUM, FCX | 104 |
| 2007-07 | 2007-06 | AAPL, CBRE, TEX | AAPL | VLO, NVDA, GT, CME, RIG, HUM, CMI | 201 |
| 2007-06 | 2007-05 | ATI, AAPL, TEX | ATI | VLO, NUE, GT, RIG, HUM, NOV, CMI | 229 |
| 2007-05 | 2007-04 | ATI, AAPL, TEX | ATI | VLO, CTSH, HUM, GT, CMI, NVDA, RIG | 187 |
| 2007-04 | 2007-03 | ATI, AAPL, CME | ATI | NUE, VLO, CTSH, TEX, GT, EOG, WMB | 171 |
| 2007-03 | 2007-02 | ATI, CME, NUE | ATI | VLO, CTSH, TEX, AVB, GT, BXP, CMI | 172 |
| 2007-02 | 2007-01 | ATI, AAPL, CME | ATI | NUE, VLO, TEX, ADSK, AVB, CTSH, EOG | 221 |
| 2007-01 | 2006-12 | AAPL, CME, ATI | AAPL | TEX, NUE, CTSH, RIG, ADSK, NVDA, HES | 234 |
| 2006-12 | 2006-11 | ATI, AAPL, CME | ATI | NUE, RIG, CNX, ADSK, CTSH, NVDA, NOV | 243 |
| 2006-11 | 2006-10 | ATI, CME, AAPL | ATI | NUE, NVDA, ADSK, HUM, BXP, CMI, ODP | 240 |
| 2006-10 | 2006-09 | AAPL, ADSK, NVDA | AAPL | HUM, L, ODP, BXP, AES, DVN, CI | 208 |
| 2006-09 | 2006-08 | AAPL, HUM, AES | AAPL | NVDA, OXY, L, BXP, WMB, PSA, VNO | 165 |
| 2006-08 | 2006-07 | VLO, WMB, EOG | VLO | HES, ADM, OXY, HUM, AES, MSI, COP | 116 |
| 2006-07 | 2006-06 | ATI, VLO, NUE | ATI | CNX, RIG, CMI, HUM, HES, ADM, HAL | 134 |
| 2006-06 | 2006-05 | ATI, VLO, NUE | ATI | ADM, RIG, CMI, HAL, HES, OXY, ODP | 131 |
| 2006-05 | 2006-04 | ATI, VLO, NUE | ATI | ADSK, GLW, FCX, CMI, NVDA, OXY, ADM | 178 |
| 2006-04 | 2006-03 | ATI, VLO, NUE | ATI | AMD, AES, GLW, CMI, NVDA, RIG, FCX | 191 |
| 2006-03 | 2006-02 | ATI, EP, AAPL | ATI | AMD, WMB, VLO, HUM, AES, GLW, CMI | 192 |
| 2006-02 | 2006-01 | EP, ATI, AAPL | EP | AMD, WMB, VLO, GLW, HUM, AES, TPR | 213 |
| 2006-01 | 2005-12 | AAPL, ATI, GLW | AAPL | HUM, AMD, TPR, FCX, NUE, CMI, NVDA | 174 |

</details>

<!-- AUTO-GENERATED:END -->

## Monthly Workflow Summary

1. **When:** On the first trading day of each month, invest that month's contribution (plus any Rule 6/7 cash).
2. **Universe & Ranking:** Start from current constituents of a major index (S&P 500 is the most thoroughly tested), rank by 3-year total return including dividends, and exclude any share below its price 3 months ago.
3. **Selection:** Split that month's money equally across the top 3 (even if you already hold them). Record the top 10 if tracking the optional Rule 6 exit.
4. **Hold Discipline:** Never sell because a share has fallen — every tested stop-loss hurt performance.
5. **Optional Staged Exit (Rule 6):** If a holding stays outside the top 10 for 6 years, sell 1/3; at 7 years, sell 1/2 of the remainder; at 8 years, sell the rest (stop selling if it returns to the top 10).

See [docs/rules.md](docs/rules.md) for the complete strategy rules and [docs/research.md](docs/research.md) for the 20-year US, UK FTSE 100, international, exit-rule, and hedge-fund evidence notes.

## Quickstart & CLI Usage

Requires [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync
```

### Public Dataset, Chart & README Refresh

```bash
# Build the 20-year survivorship-aware US dataset (fja05680 + weib08 + Yahoo Finance):
uv run monthly-momentum build-us20

# Incremental monthly refresh (S&P 500 + FTSE 100 / TSX 60 / EURO STOXX 50 + FX rates):
uv run monthly-momentum refresh --with-global

# Rebuild rankings, model holdings, chart, and README deterministically offline from data/:
uv run monthly-momentum report
```

### Monthly ISA Execution & Personal Holdings

```bash
# Optional: initialize gitignored personal ISA tracker (data/private/holdings.csv)
uv run monthly-momentum init

# Plan this month's £500 ISA buys from committed public picks (dry run)
uv run monthly-momentum run --use-public --contribution 500 --currency GBP --market us

# Or rank a manual Finviz / Market Chameleon CSV export
uv run monthly-momentum rank path/to/screener.csv --month 2026-11 --output data/private/rank.csv

# Apply buys & top-10 tracking to your personal holdings sheet
uv run monthly-momentum run --use-public --contribution 500 --apply

# Check Rule 6 status across personal holdings
uv run monthly-momentum holdings check --ranking data/rankings/latest.csv
```

### Backtesting & Variant Comparison

```bash
# Compare Top 1, Top 3, Top 5, Top 10 (+/- Rule 6) on committed 20-year public data:
uv run monthly-momentum compare --signal-mode next_month

# Test sensitivity without Nvidia (or any comma-separated tickers):
uv run monthly-momentum backtest --variant standard --signal-mode next_month --exclude NVDA

# Run an external survivorship-bias-free dataset (e.g. Norgate or EODHD):
uv run monthly-momentum backtest \
  --prices path/to/prices.csv \
  --constituents path/to/constituents.csv \
  --events path/to/events.csv \
  --variant balanced --rule6
```

## Automated Monthly GitHub Action

[`.github/workflows/monthly-refresh.yml`](.github/workflows/monthly-refresh.yml) runs automatically on the **1st of every month at 08:00 UTC** (and on manual `workflow_dispatch`):

1. Runs `uv run monthly-momentum refresh --years 4 --with-global` to fetch the latest Wikipedia S&P 500, FTSE 100, S&P/TSX 60, and EURO STOXX 50 constituents plus completed monthly prices and FX rates from Yahoo Finance.
2. Appends the new month's point-in-time constituent roster to `data/constituent_snapshots.csv`, updates `data/constituents_history.csv`, and ratio-splices new bars onto `data/monthly_prices.csv` (preserving the 20-year history and any exited tickers).
3. Verifies offline reproducibility via `uv run monthly-momentum report` and commits any updated files under `data/`, `assets/`, and `README.md`.

## Repository Layout

| Path | Purpose | Tracked in Git |
| :--- | :--- | :---: |
| [src/monthly_momentum/](src/monthly_momentum/) | Python package (`cli`, `live`, `us20`, `markets`, `ranking`, `holdings`, `planner`, `backtest`, `chart`, `report`, `refresh`) | Yes |
| [tests/](tests/) | Offline pytest unit & integration suite | Yes |
| [docs/rules.md](docs/rules.md) | Full strategy specification, rejected rules, and data sources | Yes |
| [docs/research.md](docs/research.md) | 20-year US, UK FTSE 100, 16-market, global pool, and exit-rule research | Yes |
| [data/constituents_history.csv](data/constituents_history.csv) | Survivorship-aware S&P 500 membership intervals (1996–present) | Yes |
| [data/constituents.csv](data/constituents.csv) | Current S&P 500 constituents and Wikipedia `date_added` | Yes |
| [data/constituent_snapshots.csv](data/constituent_snapshots.csv) | Monthly point-in-time constituent roster archive | Yes |
| [data/monthly_prices.csv](data/monthly_prices.csv) | 20+ year ratio-spliced monthly `close` & `adj_close` bars + `^SP500TR` | Yes |
| [data/global/](data/global/) | FTSE 100, TSX 60, EURO STOXX 50 constituents, prices, FX rates & global rankings | Yes |
| [data/rankings/](data/rankings/) | Mechanistic `latest.csv` and full `history.csv` Top 10 snapshots | Yes |
| [data/model_holdings.csv](data/model_holdings.csv) | Mechanistic Rule 6 tracking sheet for model Top 3 portfolio | Yes |
| [data/performance.csv](data/performance.csv) & [data/summary.json](data/summary.json) | Variant equity series & summary metrics | Yes |
| [assets/performance.png](assets/performance.png) | Generated 20-year performance & drawdown chart | Yes |
| [templates/](templates/) | Header-only CSV templates for rankings, holdings, and backtest inputs | Yes |
| [`.github/workflows/`](.github/workflows/) | Monthly data refresh workflow and CI test/lint workflow | Yes |
| `data/private/`, `data/raw/`, `records/`, `portfolio/` | Optional personal ISA logs, HF parquet cache & local dumps | No (gitignored) |
