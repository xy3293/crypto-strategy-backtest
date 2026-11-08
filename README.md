# Crypto perpetual futures swing backtester

Python 3.12 research tool for **Binance USDT-margined perpetual futures**, supporting
longs and shorts on 4h (default) and 1h candles. It does not place orders.

## Setup and usage

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m backtest run --symbol BTC/USDT --strategy turtle_donchian_4h --timeframe 4h --start 2021-01-01 --end 2026-11-08
python -m backtest compare --symbol BTC/USDT --timeframe 4h --start 2021-01-01
python -m backtest compare --symbol ETH/USDT --timeframe 4h --start 2021-01-01
python -m backtest run --symbol ETH/USDT --strategy macd_ema_trend --timeframe 1h --leverage 3 --fee 0.0005 --slippage 0.0005 --params '{"stop_atr": 2.5, "max_days": 14}'
python -m pytest -q
```

`--end` is exclusive, in UTC; default is 2026-11-08 00:00 UTC. Only completed
candles are used. Both symbols map to Binance futures `BTCUSDT`/`ETHUSDT`, never
spot. CCXT's `binanceusdm` exchange has `defaultType='future'`. Its public raw
endpoint methods avoid unnecessary market metadata requests. Contract klines,
mark-price klines and actual funding history are paginated and cached separately
under `data/` as CSV. Repeating an identical historical range uses the cache.

### Binance Vision bulk-download fallback

If the CCXT REST API returns HTTP 451 (restricted location) or any connection error,
the data layer automatically falls back to **Binance Vision** (`https://data.binance.vision`)
bulk download archives:
* Monthly and daily contract klines (`/data/futures/um/monthly/klines/`, `/daily/klines/`).
* Monthly and daily mark-price klines (`/data/futures/um/monthly/markPriceKlines/`, `/daily/markPriceKlines/`).
* Monthly funding rate history (`/data/futures/um/monthly/fundingRate/`).
* For historical dates where Binance Vision omitted pre-aggregated kline zips (e.g. 2026-10-28),
  the loader downloads the official Binance futures tick-level `trades` archive and
  aggregates it directly into exact OHLCV candles. Only genuine Binance data is used;
  no synthetic, spot or third-party data is substituted.
* Bulk downloads are cached under `data/vision/` to avoid redundant network transfers.

`results/` receives a summary CSV, equity CSV and trade ledger CSV per run.
Summary rates are fractions (0.10 = 10%). Cash and funding are USDT. Defaults:
$10,000 starting equity, 1% risk, 2x leverage, maximum 5x, 0.05% taker fee and
0.05% adverse slippage on each side. CLI costs are decimal rates. Programmatic
`Config` also exposes capital, risk and maintenance ratio.

## Strategies and parameters

All parameters below are keyword arguments accepted by `generate_signals` and
CLI `--params` on `run`. Compare uses defaults. Lookbacks are bars; switching to
1h does not automatically rescale them. These are swing research rules targeting
roughly 3–14 day holds, **not a guarantee**: stops and trend reversals can produce
much shorter holds. The report exposes average holding days so that this target
can be checked rather than assumed. MACD and the five batch-5 strategies have a hard 14-day maximum; J Law Swing
Trade has a hard 7-day maximum.

| Strategy | Entry and exit rules | Defaults |
|---|---|---|
| turtle_donchian_4h | Close above prior 20 highs = long; below prior 20 lows = short. Exit long below prior 10 lows / short above prior 10 highs. Optional EMA200 direction filter. | entry=20, exit=10, atr_period=20, stop_atr=2, ema_filter=false |
| supertrend_4h | Wilder ATR Supertrend, directional continuously after warmup; flip when close crosses the active line. | period=10, multiplier=3 |
| rsi_atr_trend_4h | RSI crosses above 70 with SMA100>SMA200 = long; crosses below 30 with SMA100<SMA200 = short. Exit on adverse SMA regime or ATR stop. | period=14, upper=70, lower=30, fast=100, slow=200, stop_atr=1.5 |
| bollinger_breakout | Close above upper SMA band = long; below lower = short. Exit across midline or ATR stop. Population standard deviation. | period=20, k=2, atr_period=14, stop_atr=2 |
| keltner_breakout | Close above EMA+multiplier*ATR = long, below EMA-multiplier*ATR = short. Exit across EMA or ATR stop. | ema_period=35, atr_period=17, multiplier=2, stop_atr=2 |
| macd_ema_trend | Close above EMA20 and positive MACD histogram = long; mirror = short. Exit on opposite condition, 3R target, trailing ATR stop or 14 days. | ema_period=20, fast=12, slow=26, signal=9, atr_period=14, stop_atr=2, target_r=3, max_days=14 |
| jlaw_swing_breakout_4h | J Law Swing Trade (YouTube, 2020): close above the prior 30-bar tight range (high-low ≤5%) with close above SMA100 and SMA100 above SMA200 = long; mirror = short. Stop at the range edge, target max(2R, 5%) capped at 15%, 7-day maximum. No entry if close is already >4% beyond the range edge. | range=30 bars, max_width=5%, fast=100, slow=200, no_chase=4%, target_r=2 (floor 5%, cap 15%), max_days=7 |
| ema_ribbon_4h | EMA9 above EMA21 above EMA55 = long; reverse = short. Exit when the alignment breaks. ATR stop. | fast=9, mid=21, slow=55, atr_period=14, stop_atr=2, max_days=14 |
| adx_trend_4h | ADX(14) above 25 with +DI above −DI = long; mirror = short. Exit when ADX falls below 20 or DI flips. ATR stop. | period=14, adx_entry=25, adx_exit=20, atr_period=14, stop_atr=2, max_days=14 |
| ichimoku_4h | Close above the cloud with Tenkan above Kijun = long; mirror = short. Exit on Tenkan/Kijun cross or close re-entering the cloud. ATR stop. | tenkan=9, kijun=26, senkou_b=52, shift=26, atr_period=14, stop_atr=2, max_days=14 |
| rsi_reversion_4h | RSI(14) below 30 = long; above 70 = short. Exit at RSI 50. ATR stop. | period=14, lower=30, upper=70, exit=50, atr_period=14, stop_atr=2, max_days=14 |
| bollinger_mean_reversion_4h | Close below the lower SMA band = long; above the upper = short. Exit at the middle band. ATR stop. | period=20, k=2, atr_period=14, stop_atr=2, max_days=14 |

Supertrend also uses a 3 ATR emergency stop to provide finite risk sizing. After
an emergency stop it reenters its current direction on the next open; thus its
signal is always directional, but execution can be temporarily flat intrabar.
ATR uses a Wilder-alpha recursive EWMA seeded by the first true range, gated by
its lookback; RSI uses the same smoothing. EMAs use `adjust=False`. No lookback
before `--start` is loaded: warmup occurs inside the requested test interval.
No strategy pyramids; an opposite entry closes and reverses at the next open.

## Execution, funding and margin assumptions

* At bar `i` open, only signal row `i-1` is available. Indicators use closed bars;
  Donchian extremes additionally exclude the breakout bar. Prefix-invariance
  tests verify that future data cannot alter earlier strategy output.
* Entry and signal/time exits use the following open plus adverse slippage. ATR
  stop distance is frozen from the signal bar, anchored to actual entry fill.
  Quantity is 1% of total equity divided by stop distance, capped by available
  cash for isolated margin **and entry fee**. Costs and gaps can exceed 1% loss.
  Unused cash stays outside the position. No interest or collateral transfers.
* Stops/targets can fill intrabar. Gapped stops use the worse of open and stop;
  target fills use the target with adverse slippage and no favorable gap credit.
  When stop and target both touch, stop wins. Trailing stops update after close
  for the following bar. Time limits are checked at opens. Final open positions
  close at the last candle close, with costs; this is an explicit terminal rule.
* Funding uses actual historical Binance events (normally every 8h), not a
  constant estimate. Cash flow is `-side * quantity * funding_mark * rate`;
  positive funding costs longs and pays shorts. Positive **total_funding means
  earned**, negative means paid. Funding mark comes from event data, falling back
  to that candle's mark open when Binance omitted it. Funding reduces/increases
  isolated collateral, not free cash. No funding is charged while flat.
* Bar-boundary fills precede funding at that timestamp. Events within a candle
  are applied before intrabar stop/target/liquidation checks. OHLC cannot establish
  the true order of an intrabar exit and funding; this is an approximation.
* Isolated margin equals entry notional/leverage and stays fixed. Liquidation
  triggers if collateral plus unrealized PnL at the adverse **mark** high/low is
  at or below 0.5% of mark notional. This configurable constant maintenance rate
  approximates small positions, not Binance's historical tier tables, deductions,
  liquidation fees, ADL or insurance settlement. A liquidation forfeits all of
  the isolated collateral including accrued funding. Free cash is preserved.
  Liquidation takes priority if both it and a stop occur in the same bar; this is
  intentionally conservative because candle data cannot resolve event order.
  Synthetic unit tests may omit mark columns and use contract candles instead;
  the production loader always requires mark candles.
* Buy-and-hold is a **1x long perpetual**, invested at the first tradable open
  through the same terminal close, including both fees, slippage, funding and
  liquidation checks. It is not spot and is not risk-sized or ATR-stopped. It
  uses the same calendar period as every strategy, including strategy warmup.

Metrics: total return and CAGR from net equity; annualized zero-risk-free Sharpe
from bar returns using observed bar spacing and 365.25 days; maximum marked-equity
drawdown; net-of-all-costs win rate and profit factor; trade count; mean holding
days; signed total funding; liquidation count. Infinite profit factor means wins
with no losing trades. Trade PnL includes entry/exit fees and funding. Results are
sampled at candle closes, so drawdown can understate intrabar equity excursions.

## Layout and extensions

```
backtest/data.py          public futures data and CSV cache
backtest/engine.py        execution, margin, stop and funding accounting
backtest/metrics.py       performance calculations
backtest/strategies/      one module per strategy, common helpers and registry
backtest/__main__.py      run / compare CLI
 tests/                  deterministic units and real-data integration
 data/                   public CSV cache
 results/                ledgers, equity, summaries and execution logs
```

To add a strategy, create a module exposing `generate_signals(df, **parameters)`
returning a DataFrame with the identical index and `direction` (-1 short, 0 no
new entry, +1 long), positive `stop_distance`, `exit_long`, `exit_short` columns.
Zero direction does not close an existing trade. Optional columns: `target_r`,
`max_days`, `trailing`. Use only prefix data through each row; do not shift entry
signals forward yourself. Add the module name to `strategies.NAMES` and a
prefix-invariance test. Indicators are vectorized; the stateful execution and
Supertrend recurrences are deliberately explicit loops for auditability.

## Real backtest comparison results

Evaluated on Binance USDT perpetual futures, 4h timeframe, 2021-01-01 to 2026-11-08 (12,822 closed bars, 6,390 funding events). Defaults: $10,000 initial equity, 2x leverage, 1% risk per trade, 0.05% taker fee, 0.05% adverse slippage.

### BTC/USDT Perpetual
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

### ETH/USDT Perpetual
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

## Validation (2026-11-09)

Full report: `results/VALIDATION.md`. The 7 strategies positive on both BTC and ETH were
stress-tested four ways (same engine and costs): split-sample 2021–2023 vs 2024–2026,
cross-market SOL/USDT and BNB/USDT, 1h timeframe with parameters unscaled, and a
Keltner parameter-sensitivity sweep (multiplier 1.5/2.5, EMA 20/50, ATR 14/21).

**Verdict: 3 hold up, 4 are luck / regime-dependent.**

| Strategy | Verdict | Split-sample (4 segments) | SOL / BNB (4h) | 1h BTC / ETH |
|---|---|---|---|---|
| rsi_atr_trend_4h | Holds up (elite) | all 4 positive | +297.3% / +303.1% | +85.7% / +150.5% |
| keltner_breakout | Holds up (core) | all 4 positive | +169.9% / +149.0% | -25.4% / +18.6% |
| supertrend_4h | Holds up (defensive) | all 4 positive | +73.1% / +71.0% | -42.7% / -20.9% |
| turtle_donchian_4h | Luck / regime | ETH 2021–23 -8.6% | +84.2% / +80.5% | -79.8% / -62.0% |
| bollinger_breakout | Luck / regime | ETH 2021–23 -3.7% | +21.4% / +55.7% | -81.3% / -57.1% |
| adx_trend_4h | Luck / regime | BTC 2024–26 -6.4% | +33.9% / +16.0% | -79.9% / -57.0% |
| ema_ribbon_4h | Luck / regime | ETH 2021–23 -3.4% | +152.4% / +78.5% | -83.5% / -66.0% |

Keltner sensitivity: all 12 parameter variants positive on both coins (+32.7% to +90.9%),
no sign flips — but the best-looking variants (multiplier 2.5, EMA 20 on ETH) are
in-sample optima and must not be adopted without out-of-sample confirmation.
`rsi_atr_trend_4h` is the only strategy that profits on unscaled 1h, but its drawdowns
are the largest (up to -60.1% BTC 1h, -52.4% BNB 4h). Recommended portfolio trio for
the next stage: `rsi_atr_trend_4h` + `keltner_breakout` + `supertrend_4h`.
Also confirmed dead: MACD, J Law (5 trades on SOL in 6 years), both mean-reversion
strategies (-95% to -99.9% on 1h), and buy-and-hold liquidated -100% on SOL too.

## Risk disclaimer

Leverage and funding can erase paper profits. Gaps can exceed planned stop risk;
liquidation can destroy isolated margin. Simplified historical simulation is
not exchange-exact execution and does not predict live trading returns. This is
not financial advice. Past performance does not guarantee future results.
