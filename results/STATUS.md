# Validation Status

Requested period: 2021-01-01 00:00 UTC to 2026-11-08 00:00 UTC (exclusive).  
Requested markets: Binance BTCUSDT and ETHUSDT USDT-margined perpetual futures (`BTC/USDT` and `ETH/USDT`).  
Requested timeframe: 4h; all seven default strategies plus 1x perpetual buy-and-hold.

## Verification & Test Results

- **pytest**: **34 passed, 0 failed** in ~3s (see `results/pytest.log`).
- **All unit and integration tests passing**, including:
  - `test_next_open_no_lookahead`
  - `test_funding_sign` (long pays positive funding, short earns)
  - `test_fee_and_slippage` (taker fee 0.05% and adverse slippage 0.05% per side)
  - `test_liquidation` (isolated margin, 0.5% maintenance margin against adverse mark price)
  - `test_stop_gap_and_risk` & `test_stop_risks_one_percent_before_costs` (1% equity risk at ATR stop)
  - `test_strategy_prefix_invariance` across all 7 strategies
  - `test_tight_range_breakout`, `test_no_chase`, `test_target_math`, `test_time_stop_and_no_other_exits` for `jlaw_swing_breakout_4h` (16 new cases)
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
| buy_and_hold | -100.00% | -100.00% | -0.3910 | -100.00% | 0.00% | 0.000 | 1 | 533.83 | -11914.76 | 1 |

---

## Key Observations

1. **Systematic Swing Strategies Survived and Profited**: While 1x perpetual buy-and-hold was liquidated in both markets during the severe 2022 market drawdowns (compounded by paying high long funding rates), systematic trend and breakout strategies with disciplined ATR risk sizing survived with 0 liquidations and modest drawdowns.
2. **Keltner Breakout & Bollinger Breakout**: Demonstrated strong risk-adjusted performance on BTC (+69.31% and +60.14% return, Sharpe 0.717 and 0.635, with low double-digit maximum drawdown).
3. **RSI ATR Trend**: Demonstrated outstanding performance on ETH (+62.96% return, 1.921 profit factor, ~15.35 days average hold).
4. **Funding Drag**: Net long exposure across trend followers resulted in net funding paid (-$367 to -$1,126 USDT), but this was far lower than buy-and-hold (-$5,657 on BTC, -$11,914 on ETH) because systematic strategies are flat or short during downtrends.
5. **J Law Swing Trade underperformed**: -3.17% on BTC and -0.04% on ETH, the worst Sharpe on both, but also the smallest maximum drawdown (-8.06% BTC, -2.95% ETH). It is very selective — only 42 BTC trades and 12 ETH trades in ~6 years — and its 2R target was rarely reached (7 of 42 on BTC, 2 of 12 on ETH), so wins were smaller than losses (profit factor 0.834 BTC, 0.993 ETH) despite the highest BTC win rate (42.86%). The ETH result is effectively breakeven on a tiny sample. The strategy was implemented exactly as confirmed, with the range defined on the prior 30 closed bars (including the signal bar would make a breakout mathematically impossible) and the target capped at 15%.
