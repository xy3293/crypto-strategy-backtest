#!/usr/bin/env python3
"""Runner script for P1 parameter selection grid.

Evaluates Keltner Breakout (36 combos) and RSI ATR Trend (9 combos)
on 4h timeframe across BTC/USDT and ETH/USDT for Period 1 (2021-01-01 to 2023-12-31).
Calls the CLI via subprocess.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / 'results'
VENV_PYTHON = PROJECT_ROOT / '.venv' / 'bin' / 'python'
LOG_FILE = RESULTS_DIR / 'p1_grid_log.txt'

START_DATE = '2021-01-01'
END_DATE = '2023-12-31'
TIMEFRAME = '4h'
SYMBOLS = ['BTC/USDT', 'ETH/USDT']


def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def run_cli_backtest(symbol, strategy, params):
    """Run backtest CLI for a given symbol, strategy, and params."""
    cmd = [
        str(VENV_PYTHON), '-m', 'backtest', 'run',
        '--symbol', symbol,
        '--strategy', strategy,
        '--timeframe', TIMEFRAME,
        '--start', START_DATE,
        '--end', END_DATE,
        '--params', json.dumps(params),
    ]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"FAILED CLI RUN: {symbol} {strategy} {params}\nSTDERR: {res.stderr}\nSTDOUT: {res.stdout}")
        return None
    return res.stdout


def extract_metrics_and_rename(symbol, strategy, variant_tag):
    """Read summary row for strategy, rename equity and trades files, return metrics."""
    market = symbol.replace('/', '')
    prefix = f"{market}_{TIMEFRAME}_{START_DATE}_{END_DATE}"
    summary_path = RESULTS_DIR / f"{prefix}_summary.csv"
    if not summary_path.exists():
        log(f"ERROR: Summary file not found: {summary_path}")
        return None

    try:
        df_summary = pd.read_csv(summary_path, index_col=0)
        if strategy not in df_summary.index:
            log(f"ERROR: Strategy {strategy} not in summary {summary_path}")
            return None
        row = df_summary.loc[strategy]
        metrics = {
            'total_return': float(row['total_return']),
            'sharpe': float(row['sharpe']),
            'max_drawdown': float(row['max_drawdown']),
            'trade_count': int(round(float(row['trade_count']))),
        }
    except Exception as e:
        log(f"ERROR reading summary {summary_path}: {e}")
        return None

    # Rename equity and trades files to variant-specific names
    src_equity = RESULTS_DIR / f"{prefix}_{strategy}_equity.csv"
    dst_equity = RESULTS_DIR / f"{prefix}_{strategy}_{variant_tag}_equity.csv"
    src_trades = RESULTS_DIR / f"{prefix}_{strategy}_trades.csv"
    dst_trades = RESULTS_DIR / f"{prefix}_{strategy}_{variant_tag}_trades.csv"

    if src_equity.exists():
        os.replace(src_equity, dst_equity)
    else:
        log(f"WARNING: Source equity not found: {src_equity}")

    if src_trades.exists():
        os.replace(src_trades, dst_trades)
    else:
        log(f"WARNING: Source trades not found: {src_trades}")

    return metrics


def sanity_check_defaults():
    """Verify default parameters on P1 against VALIDATION.md expected benchmarks."""
    log("=== RUNNING SANITY CHECK DEFAULTS ===")

    expected = {
        'keltner_breakout': {
            'params': {'multiplier': 2.0, 'ema_period': 35, 'atr_period': 17, 'stop_atr': 2.0},
            'tag': 'm2.0_e35_a17',
            'BTC/USDT': {'return': 0.4845, 'sharpe': 1.0070, 'maxdd': -0.1057, 'trades': 130},
            'ETH/USDT': {'return': 0.0481, 'sharpe': 0.1878, 'maxdd': -0.1171, 'trades': 136},
        },
        'rsi_atr_trend_4h': {
            'params': {'stop_atr': 1.5, 'period': 14, 'upper': 70, 'lower': 30, 'fast': 100, 'slow': 200},
            'tag': 's1.5_p14',
            'BTC/USDT': {'return': 0.1220, 'sharpe': 0.3307, 'maxdd': -0.2439, 'trades': 43},
            'ETH/USDT': {'return': 0.0395, 'sharpe': 0.1689, 'maxdd': -0.3906, 'trades': 35},
        }
    }

    results = {}

    for strat, data in expected.items():
        params = data['params']
        tag = data['tag']
        results[strat] = {}
        for symbol in SYMBOLS:
            log(f"Sanity run: {strat} on {symbol} (variant=default, params={params})")
            out = run_cli_backtest(symbol, strat, params)
            if out is None:
                raise RuntimeError(f"Sanity check run failed for {strat} on {symbol}")
            m = extract_metrics_and_rename(symbol, strat, tag)
            if m is None:
                raise RuntimeError(f"Failed to extract metrics for {strat} on {symbol}")
            results[strat][symbol] = m

            exp = data[symbol]
            ret_diff = abs(m['total_return'] - exp['return'])
            shp_diff = abs(m['sharpe'] - exp['sharpe'])
            dd_diff = abs(m['max_drawdown'] - exp['maxdd'])
            tr_diff = abs(m['trade_count'] - exp['trades'])

            log(f"  Result: return={m['total_return']:.4f} (exp {exp['return']:.4f}), "
                f"sharpe={m['sharpe']:.4f} (exp {exp['sharpe']:.4f}), "
                f"maxdd={m['max_drawdown']:.4f} (exp {exp['maxdd']:.4f}), "
                f"trades={m['trade_count']} (exp {exp['trades']})")

            if ret_diff > 0.005 or shp_diff > 0.02 or dd_diff > 0.005 or tr_diff > 2:
                err_msg = (f"SANITY CHECK FAILED for {strat} on {symbol}!\n"
                           f"Return diff: {ret_diff:.4f} (> 0.005)\n"
                           f"Sharpe diff: {shp_diff:.4f} (> 0.02)\n"
                           f"MaxDD diff: {dd_diff:.4f} (> 0.005)\n"
                           f"Trade diff: {tr_diff} (> 2)")
                log(err_msg)
                raise RuntimeError(err_msg)
            log(f"  Sanity check PASSED for {strat} on {symbol}")

    log("=== SANITY CHECK DEFAULTS PASSED SUCCESSFULLY ===\n")
    return results


def run_keltner_grid(default_metrics=None):
    """Run Keltner Breakout 36 combinations."""
    log("=== STARTING KELTNER BREAKOUT GRID (36 combos) ===")
    multipliers = [1.5, 2.0, 2.5, 3.0]
    ema_periods = [20, 35, 50]
    atr_periods = [14, 17, 21]
    stop_atr = 2.0

    combos = []
    # Ensure default is first
    default_combo = (2.0, 35, 17)
    combos.append(default_combo)
    for m in multipliers:
        for e in ema_periods:
            for a in atr_periods:
                c = (m, e, a)
                if c != default_combo:
                    combos.append(c)

    rows = []
    csv_path = RESULTS_DIR / 'keltner_tuning_grid.csv'

    for idx, (m, e, a) in enumerate(combos, 1):
        params = {'multiplier': m, 'ema_period': e, 'atr_period': a, 'stop_atr': stop_atr}
        tag = f"m{m:.1f}_e{e}_a{a}"
        is_default = (m == 2.0 and e == 35 and a == 17)
        label = "variant=default" if is_default else f"variant={tag}"
        log(f"[{idx}/36] Keltner combo: multiplier={m}, ema_period={e}, atr_period={a}, stop_atr={stop_atr} ({label})")

        combo_metrics = {}
        for symbol in SYMBOLS:
            coin = 'btc' if 'BTC' in symbol else 'eth'
            if is_default and default_metrics and 'keltner_breakout' in default_metrics:
                m_sym = default_metrics['keltner_breakout'][symbol]
                log(f"  {symbol} using sanity default run metrics")
            else:
                out = run_cli_backtest(symbol, 'keltner_breakout', params)
                if out is None:
                    log(f"  {symbol} FAILED run")
                    m_sym = None
                else:
                    m_sym = extract_metrics_and_rename(symbol, 'keltner_breakout', tag)
            combo_metrics[coin] = m_sym

        btc_m = combo_metrics.get('btc')
        eth_m = combo_metrics.get('eth')

        if btc_m and eth_m:
            btc_ret = btc_m['total_return']
            btc_shp = btc_m['sharpe']
            btc_dd = btc_m['max_drawdown']
            btc_tr = btc_m['trade_count']

            eth_ret = eth_m['total_return']
            eth_shp = eth_m['sharpe']
            eth_dd = eth_m['max_drawdown']
            eth_tr = eth_m['trade_count']

            sharpe_sum = btc_shp + eth_shp
            return_sum = btc_ret + eth_ret
            eligible = "YES" if (btc_dd >= -0.25 and eth_dd >= -0.25) else "NO"

            row = {
                'multiplier': m,
                'ema_period': e,
                'atr_period': a,
                'stop_atr': stop_atr,
                'btc_return': btc_ret,
                'btc_sharpe': btc_shp,
                'btc_maxdd': btc_dd,
                'btc_trades': btc_tr,
                'eth_return': eth_ret,
                'eth_sharpe': eth_shp,
                'eth_maxdd': eth_dd,
                'eth_trades': eth_tr,
                'sharpe_sum': sharpe_sum,
                'return_sum': return_sum,
                'eligible': eligible,
            }
            log(f"  -> btc_ret={btc_ret:.4f}, eth_ret={eth_ret:.4f}, sharpe_sum={sharpe_sum:.4f}, return_sum={return_sum:.4f}, eligible={eligible}")
        else:
            row = {
                'multiplier': m,
                'ema_period': e,
                'atr_period': a,
                'stop_atr': stop_atr,
                'btc_return': None,
                'btc_sharpe': None,
                'btc_maxdd': None,
                'btc_trades': None,
                'eth_return': None,
                'eth_sharpe': None,
                'eth_maxdd': None,
                'eth_trades': None,
                'sharpe_sum': None,
                'return_sum': None,
                'eligible': 'FAILED',
            }
            log("  -> FAILED")

        rows.append(row)
        pd.DataFrame(rows).to_csv(csv_path, index=False)

    df_keltner = pd.DataFrame(rows)
    # Sort by sharpe_sum descending, return_sum descending
    df_keltner = df_keltner.sort_values(by=['sharpe_sum', 'return_sum'], ascending=[False, False])
    df_keltner.to_csv(csv_path, index=False)
    log(f"Saved sorted Keltner grid to {csv_path} ({len(df_keltner)} rows)\n")
    return df_keltner


def run_rsi_grid(default_metrics=None):
    """Run RSI ATR Trend 9 combinations."""
    log("=== STARTING RSI ATR TREND GRID (9 combos) ===")
    stop_atrs = [1.0, 1.5, 2.0]
    periods = [10, 14, 21]
    upper = 70
    lower = 30
    fast = 100
    slow = 200

    combos = []
    # Ensure default is first
    default_combo = (1.5, 14)
    combos.append(default_combo)
    for s in stop_atrs:
        for p in periods:
            c = (s, p)
            if c != default_combo:
                combos.append(c)

    rows = []
    csv_path = RESULTS_DIR / 'rsi_atr_tuning_grid.csv'

    for idx, (s, p) in enumerate(combos, 1):
        params = {'stop_atr': s, 'period': p, 'upper': upper, 'lower': lower, 'fast': fast, 'slow': slow}
        tag = f"s{s:.1f}_p{p}"
        is_default = (s == 1.5 and p == 14)
        label = "variant=default" if is_default else f"variant={tag}"
        log(f"[{idx}/9] RSI combo: stop_atr={s}, period={p} ({label})")

        combo_metrics = {}
        for symbol in SYMBOLS:
            coin = 'btc' if 'BTC' in symbol else 'eth'
            if is_default and default_metrics and 'rsi_atr_trend_4h' in default_metrics:
                m_sym = default_metrics['rsi_atr_trend_4h'][symbol]
                log(f"  {symbol} using sanity default run metrics")
            else:
                out = run_cli_backtest(symbol, 'rsi_atr_trend_4h', params)
                if out is None:
                    log(f"  {symbol} FAILED run")
                    m_sym = None
                else:
                    m_sym = extract_metrics_and_rename(symbol, 'rsi_atr_trend_4h', tag)
            combo_metrics[coin] = m_sym

        btc_m = combo_metrics.get('btc')
        eth_m = combo_metrics.get('eth')

        if btc_m and eth_m:
            btc_ret = btc_m['total_return']
            btc_shp = btc_m['sharpe']
            btc_dd = btc_m['max_drawdown']
            btc_tr = btc_m['trade_count']

            eth_ret = eth_m['total_return']
            eth_shp = eth_m['sharpe']
            eth_dd = eth_m['max_drawdown']
            eth_tr = eth_m['trade_count']

            sharpe_sum = btc_shp + eth_shp
            return_sum = btc_ret + eth_ret

            row = {
                'stop_atr': s,
                'period': p,
                'upper': upper,
                'lower': lower,
                'fast': fast,
                'slow': slow,
                'btc_return': btc_ret,
                'btc_sharpe': btc_shp,
                'btc_maxdd': btc_dd,
                'btc_trades': btc_tr,
                'eth_return': eth_ret,
                'eth_sharpe': eth_shp,
                'eth_maxdd': eth_dd,
                'eth_trades': eth_tr,
                'sharpe_sum': sharpe_sum,
                'return_sum': return_sum,
            }
            log(f"  -> btc_ret={btc_ret:.4f}, eth_ret={eth_ret:.4f}, sharpe_sum={sharpe_sum:.4f}, return_sum={return_sum:.4f}")
        else:
            row = {
                'stop_atr': s,
                'period': p,
                'upper': upper,
                'lower': lower,
                'fast': fast,
                'slow': slow,
                'btc_return': None,
                'btc_sharpe': None,
                'btc_maxdd': None,
                'btc_trades': None,
                'eth_return': None,
                'eth_sharpe': None,
                'eth_maxdd': None,
                'eth_trades': None,
                'sharpe_sum': None,
                'return_sum': None,
            }
            log("  -> FAILED")

        rows.append(row)
        pd.DataFrame(rows).to_csv(csv_path, index=False)

    df_rsi = pd.DataFrame(rows)
    # Sort by sharpe_sum descending, return_sum descending
    df_rsi = df_rsi.sort_values(by=['sharpe_sum', 'return_sum'], ascending=[False, False])
    df_rsi.to_csv(csv_path, index=False)
    log(f"Saved sorted RSI grid to {csv_path} ({len(df_rsi)} rows)\n")
    return df_rsi


def main():
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write("=== P1 Parameter Selection Grid Log ===\n")

    default_metrics = sanity_check_defaults()
    run_keltner_grid(default_metrics)
    run_rsi_grid(default_metrics)
    log("=== ALL P1 GRID RUNS COMPLETED SUCCESSFULLY ===")


if __name__ == '__main__':
    main()
