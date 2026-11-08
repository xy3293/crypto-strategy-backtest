# Validation Status

Requested period: 2021-01-01 00:00 UTC to 2026-11-08 00:00 UTC (exclusive).  
Requested markets: Binance BTCUSDT and ETHUSDT USDT-margined perpetual futures (`BTC/USDT` and `ETH/USDT`).  
Requested timeframe: 4h; all twelve default strategies plus 1x perpetual buy-and-hold.

## Verification & Test Results

- **pytest**: **64 passed, 0 failed** in ~3s (see `results/pytest.log`).
- **All unit and integration tests passing**, including:
  - `test_next_open_no_lookahead`
  - `test_funding_sign` (long pays positive funding, short earns)
  - `test_fee_and_slippage` (taker fee 0.05% and adverse slippage 0.05% per side)
  - `test_liquidation` (isolated margin, 0.5% maintenance margin against adverse mark price)
  - `test_stop_gap_and_risk` & `test_stop_risks_one_percent_before_costs` (1% equity risk at ATR stop)
  - `test_strategy_prefix_invariance` across all 12 strategies
  - `test_tight_range_breakout`, `test_no_chase`, `test_target_math`, `test_time_stop_and_no_other_exits` for `jlaw_swing_breakout_4h` (16 new cases)
  - `tests/test_batch5_strategies.py`: long/short entry, long/short exit and prefix invariance for each of `ema_ribbon_4h`, `adx_trend_4h`, `ichimoku_4h`, `rsi_reversion_4h`, `bollinger_mean_reversion_4h` (25 cases)
  - `test_round_trip_pnl_reconciles_equity`
  - `test_real_perpetual_end_to_end` (real Binance data loader & execution)

## Data Layer & Binance Vision Fallback

Binance REST API endpoints (`fapi.binance.com`) return HTTP 451 restricted-location from this environment. The data layer (`backtest/data.py`) was enhanced with an automated fallback to Binance Vision (`https://data.binance.vision`) bulk downloads:
- **First choice**: CCXT Binance public REST API.
- **Fallback on error or 451**: Automated retrieval of Binance Vision monthly and daily bulk archives:
  - Monthly contract klines and mark-price klines (`/data/futures/um/monthly/klines/` & `/data/futures/um/monthly/markPriceKlines/`).
  - Daily archives for incomplete/current months and dates omitted from monthly archives.
  - Raw trade tape aggregation (`/data/futures/um/daily/trades/`) for historical dates omitted by Binance Vision's pre-computed klines (e.g. 2026-10-28), preserving 100% genuine Binance trade execution data.
  - Funding rate history (`/data/futures/um/monthly/fundingRate/`).
- Local raw cache is maintained in `data/vision/` to avoid redundant downloads, and final range datasets are cached as CSV in `data/`.

Both datasets span exactly **12,822 closed 4h bars** and **6,390 funding settlement events** with no artificial bridging or synthetic substitution.

---

## Performance Summary: BTC/USDT Perpetual

Period: 2021-01-01 00:00 UTC to 2026-11-08 00:00 UTC (12,822 bars, 6,390 funding events). Initial capital: $10,000, 2x leverage cap, 1% risk per trade, 0.05% taker fee, 0.05% adverse slippage.

| Strategy | Total Return | CAGR | Sharpe | Max DD | Win Rate | Profit Factor | Trades | Avg Hold (d) | Total Funding (USDT) | Liquidations |
|---|---|---|---|---|---|---|---|---|---|---|
| turtle_donchian_4h | +44.24% | +6.46% | 0.4946 | -21.52% | 30.27% | 1.158 | 370 | 3.67 | -612.26 | 0 |
| supertrend_4h | +31.46% | +4.79% | 0.4741 | -12.77% | 34.13% | 1.167 | 334 | 6.39 | -410.40 | 0 |
| rsi_atr_trend_4h | +24.94% | +3.88% | 0.3155 | -24.39% | 18.29% | 1.323 | 82 | 12.01 | -1125.85 | 0 |
| bollinger_breakout | +60.14% | +8.38% | 0.6352 | -23.95% | 33.12% | 1.182 | 471 | 2.49 | -541.51 | 0 |
| keltner_breakout | +69.31% | +9.42% | 0.7173 | -13.45% | 31.48% | 1.312 | 270 | 4.13 | -772.21 | 0 |
| macd_ema_trend | -19.10% | -3.56% | -0.1747 | -32.24% | 32.15% | 0.958 | 1067 | 1.89 | -367.21 | 0 |
| jlaw_swing_breakout_4h | -3.17% | -0.55% | -0.1822 | -8.06% | 42.86% | 0.834 | 42 | 4.47 | -20.39 | 0 |
| ema_ribbon_4h | +20.70% | +3.27% | 0.2881 | -16.96% | 26.95% | 1.079 | 486 | 3.38 | -706.67 | 0 |
| adx_trend_4h | +22.59% | +3.54% | 0.3299 | -16.41% | 30.54% | 1.096 | 442 | 2.82 | -444.88 | 0 |
| ichimoku_4h | -16.72% | -3.08% | -0.1387 | -32.33% | 24.73% | 0.931 | 655 | 2.21 | -554.99 | 0 |
| rsi_reversion_4h | -59.20% | -14.21% | -1.5624 | -61.94% | 39.39% | 0.667 | 429 | 1.78 | +309.26 | 0 |
| bollinger_mean_reversion_4h | -67.74% | -17.58% | -1.6387 | -70.87% | 48.68% | 0.711 | 797 | 1.34 | +214.95 | 0 |
| buy_and_hold | -100.00% | -100.00% | -0.2249 | -100.00% | 0.00% | 0.000 | 1 | 677.67 | -5657.96 | 1 |

---

## Performance Summary: ETH/USDT Perpetual

Period: 2021-01-01 00:00 UTC to 2026-11-08 00:00 UTC (12,822 bars, 6,390 funding events). Initial capital: $10,000, 2x leverage cap, 1% risk per trade, 0.05% taker fee, 0.05% adverse slippage.

| Strategy | Total Return | CAGR | Sharpe | Max DD | Win Rate | Profit Factor | Trades | Avg Hold (d) | Total Funding (USDT) | Liquidations |
|---|---|---|---|---|---|---|---|---|---|---|
| turtle_donchian_4h | +22.25% | +3.49% | 0.3045 | -21.06% | 26.86% | 1.093 | 376 | 3.77 | -762.60 | 0 |
| supertrend_4h | +21.07% | +3.32% | 0.3495 | -11.56% | 31.17% | 1.120 | 324 | 6.59 | -611.56 | 0 |
| rsi_atr_trend_4h | +62.96% | +8.70% | 0.5262 | -39.06% | 22.06% | 1.921 | 68 | 15.35 | -1017.73 | 0 |
| bollinger_breakout | +9.83% | +1.62% | 0.1853 | -24.85% | 28.22% | 1.038 | 489 | 2.35 | -591.89 | 0 |
| keltner_breakout | +37.34% | +5.57% | 0.4807 | -16.49% | 32.45% | 1.207 | 265 | 4.08 | -742.87 | 0 |
| macd_ema_trend | +61.39% | +8.53% | 0.6281 | -25.80% | 34.33% | 1.103 | 1075 | 1.88 | -578.86 | 0 |
| jlaw_swing_breakout_4h | -0.04% | -0.01% | 0.0035 | -2.95% | 33.33% | 0.993 | 12 | 5.36 | -2.47 | 0 |
| ema_ribbon_4h | +1.23% | +0.21% | 0.0900 | -22.43% | 26.46% | 1.004 | 514 | 3.16 | -806.65 | 0 |
| adx_trend_4h | +17.66% | +2.82% | 0.2848 | -19.57% | 27.27% | 1.083 | 440 | 2.68 | -397.94 | 0 |
| ichimoku_4h | +62.93% | +8.70% | 0.6355 | -18.69% | 25.17% | 1.195 | 596 | 2.36 | -898.88 | 0 |
| rsi_reversion_4h | -60.40% | -14.64% | -1.6526 | -62.37% | 40.94% | 0.640 | 425 | 1.81 | +339.20 | 0 |
| bollinger_mean_reversion_4h | -48.71% | -10.78% | -1.0033 | -57.21% | 53.33% | 0.805 | 780 | 1.33 | +349.16 | 0 |
| buy_and_hold | -100.00% | -100.00% | -0.3910 | -100.00% | 0.00% | 0.000 | 1 | 533.83 | -11914.76 | 1 |

---

## Key Observations

1. **Systematic Swing Strategies Survived and Profited**: While 1x perpetual buy-and-hold was liquidated in both markets during the severe 2022 market drawdowns (compounded by paying high long funding rates), systematic trend and breakout strategies with disciplined ATR risk sizing survived with 0 liquidations and modest drawdowns.
2. **Keltner Breakout & Bollinger Breakout**: Demonstrated strong risk-adjusted performance on BTC (+69.31% and +60.14% return, Sharpe 0.717 and 0.635, with low double-digit maximum drawdown).
3. **RSI ATR Trend**: Demonstrated outstanding performance on ETH (+62.96% return, 1.921 profit factor, ~15.35 days average hold).
4. **Funding Drag**: Net long exposure across trend followers resulted in net funding paid (-$367 to -$1,126 USDT), but this was far lower than buy-and-hold (-$5,657 on BTC, -$11,914 on ETH) because systematic strategies are flat or short during downtrends.
5. **J Law Swing Trade underperformed**: -3.17% on BTC and -0.04% on ETH, the worst Sharpe on both, but also the smallest maximum drawdown (-8.06% BTC, -2.95% ETH). It is very selective — only 42 BTC trades and 12 ETH trades in ~6 years — and its 2R target was rarely reached (7 of 42 on BTC, 2 of 12 on ETH), so wins were smaller than losses (profit factor 0.834 BTC, 0.993 ETH) despite the highest BTC win rate (42.86%). The ETH result is effectively breakeven on a tiny sample. The strategy was implemented exactly as confirmed, with the range defined on the prior 30 closed bars (including the signal bar would make a breakout mathematically impossible) and the target capped at 15%.
6. **Mean reversion fails badly on crypto perpetuals**: `rsi_reversion_4h` (-59.20% BTC, -60.40% ETH) and `bollinger_mean_reversion_4h` (-67.74% BTC, -48.71% ETH) lost heavily on both coins, Sharpe -1.0 to -1.65, drawdowns -57% to -71%. Win rates were not low (39–53%, the Bollinger version's 53.33% on ETH is the highest of all 12), but profit factors were only 0.64–0.80 — small wins, big losses — and average holds were just 1.3–1.8 days, far below the 3–14 day target. In this market, trend/breakout wins and mean reversion pays.
7. **Ichimoku is inconsistent like MACD**: +62.93% on ETH (Sharpe 0.6355, among the best) but -16.72% on BTC. A single-coin leader misleads; cross-coin consistency is the test.
8. **Best new strategy is ADX trend**: `adx_trend_4h` (+22.59% BTC, +17.66% ETH) is the only new strategy positive on both coins with Sharpe near 0.3 on both; `ema_ribbon_4h` is also positive on both but nearly flat on ETH (+1.23%). **Best overall remains `keltner_breakout`** (+69.31% BTC, +37.34% ETH, combined +106.65pp), ahead of `rsi_atr_trend_4h` (+87.90pp) and `bollinger_breakout` (+69.97pp). Seven of the twelve strategies are positive on both coins.

## Robustness Validation (2026-11-09)

Full report: `results/VALIDATION.md`. The 7 strategies positive on both BTC and ETH were stress-tested four ways (same engine, same costs): split-sample 2021–2023 vs 2024–2026, cross-market SOL/USDT and BNB/USDT (both 12,822 4h bars from 2021-01-01; SOL funding 6,465 events, BNB 6,390), 1h timeframe with parameters unscaled, and a Keltner parameter-sensitivity sweep. No code changed; pytest still 64 passed; Antigravity ran everything, Codex was not needed.

- **3 hold up: `rsi_atr_trend_4h` (elite), `keltner_breakout` (core), `supertrend_4h` (defensive).** All three are positive in all four split-sample segments. RSI-ATR is the strongest cross-market (+297.3% SOL, +303.1% BNB) and the only strategy that profits on unscaled 1h (+85.7% BTC, +150.5% ETH), but with the largest drawdowns (BNB -52.4%, BTC 1h -60.1%). Keltner is the most balanced (Sharpe 1.17 SOL, 0.89 BNB) and parameter-immune: all 12 sensitivity variants positive on both coins (+32.7% to +90.9%), no sign flips — though the best-looking variants (multiplier 2.5, EMA 20 on ETH) are in-sample optima, not to be adopted without out-of-sample confirmation. Supertrend has the lowest drawdowns (-10% to -13% on BTC/ETH/SOL) but fails on 1h.
- **4 are luck / regime-dependent: `turtle_donchian_4h`, `bollinger_breakout`, `adx_trend_4h`, `ema_ribbon_4h`.** Each fails at least one split-sample segment (turtle ETH 2021–23 -8.6%, bollinger ETH 2021–23 -3.7%, ADX BTC 2024–26 -6.4%, EMA ribbon ETH 2021–23 -3.4%) and all four collapse on 1h (-57% to -83%). Turtle and Bollinger are strictly inferior versions of Keltner; EMA ribbon only works on high-beta SOL/BNB.
- **Confirmed dead:** MACD (BTC 2024–26 -28.3%, BNB -27.7%), J Law (5 trades on SOL in 6 years, +2.6%), both mean-reversion strategies (-95% to -99.9% on 1h), buy-and-hold liquidated -100% on SOL as well.
- **Next stage:** portfolio-combine the three survivors (`rsi_atr_trend_4h` + `keltner_breakout` + `supertrend_4h`), equal-weighted, to test whether diversification lifts Sharpe and cuts drawdown versus any single strategy.

## Portfolio Combination (2026-11-09)

Full report: `results/PORTFOLIO.md` (new module `backtest/portfolio.py`, tests `tests/test_portfolio.py`, pytest now 70 passed). The three validated strategies were combined by weighted-average of their equity curves (fees/funding already inside each curve, so no double counting; capital split, no shared margin). Three portfolios, 4 coins, 4h, $10,000 start. Recommended: **c_sharpe** (Sharpe-weighted: keltner 41.84%, rsi_atr 29.40%, supertrend 28.76%).

- **No portfolio beats the best single strategy on total return** in any coin (BTC keltner +69.31%, ETH rsi +62.96%, SOL rsi +297.34%, BNB rsi +303.12%); the highest-return portfolio is always b_equal2 (no supertrend). A weighted average mathematically cannot exceed its best component.
- **What the portfolio buys is drawdown control and, on ETH/BNB, Sharpe above every single strategy.** ETH: all three portfolios beat the best single Sharpe (b_equal2 0.5711 vs rsi 0.5262). BNB: all three beat it (b_equal2 0.9407 vs keltner 0.8897). BTC/SOL: no portfolio beats keltner alone (0.7173 / 1.1742).
- **Drawdown, c_sharpe vs worst single strategy (rsi_atr):** BTC -24.39% → -10.60%, ETH -39.06% → -18.41%, SOL -38.86% → -19.32%, BNB -52.39% → -23.80%. But vs the best single strategy (supertrend) it only improves on BTC (-10.60% vs -12.77%) and is deeper on ETH/SOL/BNB — the diversification benefit is relative to the high-return legs, not to the defensive anchor itself.
- **Why it works at all:** rsi_atr is the low-correlation leg (bar-return correlation 0.26–0.49 vs the other two); keltner and supertrend move together (0.76–0.87). All three in the market at once only ~24–31% of the time, and in the same direction <25% of the time. Supertrend is in the market >99.9% of the time (always-in-market design).
- **Bottom line:** the portfolio is a risk-reduction tool, not a return booster. If the goal is maximum return, a single strategy wins; if the goal is the best risk-adjusted ride, c_sharpe is the pick.

## Parameter Tuning with Out-of-Sample Validation (2026-11-09)

Full report: `results/TUNING.md` (Antigravity only, no Codex, no code changes, pytest still 70 passed). Only the two validated winners were tuned, with a strict one-touch rule: select parameters on 2021–2023 (P1), validate once on 2024–2026 (P2), no re-tuning on P2, cross-market confirmation only for accepted sets.

- **Result: all 5 candidates failed — default parameters stay.** Keltner grid 36 combos (multiplier 1.5–3 × EMA 20/35/50 × ATR 14/17/21); RSI grid 9 combos (stop_atr 1.0–2.0 × period 10/14/21). P1 winners were all EMA 20 with wide channels (K1 mult 3.0/ema 20/atr 21, P1 Sharpe sum 2.0894 vs default 1.1948), but on P2 they lost 10–23pp of return, mostly on ETH (K1 ETH -15.79pp, K3 ETH -20.43pp). The closest miss was RSI R2 (stop 1.0, period 10): P2 return sum +41.45pp over default (ETH +95.66%) but Sharpe sum -0.0043 short and BTC drawdown 13.21pp deeper (-29.28% vs -16.07%) — a miss is a miss, correctly not adopted.
- **Why it failed:** the P1 optima (short EMA 20, wide channels 2.5–3.0) filtered false breakouts in the 2021–2023 bull/bear mix, but in the 2024–2026 ETF bull market they entered too late and exited too early on ETH. The defaults (EMA 35, multiplier 2.0) are the more robust middle-of-the-road filter across regimes.
- **Step 3 was correctly not run:** zero variants passed P2, so no SOL/BNB confirmation runs were made. RSI tuning is additionally weak statistically (P1 default only 43 BTC / 35 ETH trades; R1 only 26/22).
- **Standing configuration:** keltner_breakout (ema_period=35, atr_period=17, multiplier=2, stop_atr=2) and rsi_atr_trend_4h (period=14, upper=70, lower=30, fast=100, slow=200, stop_atr=1.5) remain the defaults, and the c_sharpe portfolio weights are unchanged.

## Final Summary (2026-11-09)

The full research story is consolidated in `results/FINAL.md` (263 lines): the research question and "good strategy" definition, the 12-strategy full-period table, validation verdicts (3 hold up, 4 luck/regime, MACD/J Law/mean-reversion dead, buy-and-hold liquidated -100% on BTC/ETH/SOL), portfolio results (c_sharpe recommended), tuning outcome (all 5 candidates failed out-of-sample, defaults stand), the final configuration, honest limitations (full-history selection bias, no true forward test yet, capital-split/no-shared-margin assumption), and next steps (funding-rate round). All numbers in it were checked against the archived reports and summary CSVs.
