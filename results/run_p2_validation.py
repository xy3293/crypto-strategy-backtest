#!/usr/bin/env python3
"""P2 out-of-sample validation runner.

Performs exactly 14 P2 runs (2024-01-01 to 2026-11-08, 4h timeframe, BTC/USDT and ETH/USDT):
- Keltner Breakout: K-default, K1, K2, K3 (8 runs)
- RSI ATR Trend: R-default, R1, R2 (6 runs)

Touches P2 exactly ONCE.
Immediately extracts summary metrics, renames equity/trades files to variant tags,
appends to results/p2_validation.csv, and logs progress to results/p2_log.txt.
At the end, restores original compare files from backup_validation_20261109/.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / 'results'
BACKUP_DIR = RESULTS_DIR / 'backup_validation_20261109'
VENV_PYTHON = PROJECT_ROOT / '.venv' / 'bin' / 'python'
LOG_FILE = RESULTS_DIR / 'p2_log.txt'
CSV_OUT = RESULTS_DIR / 'p2_validation.csv'

START_DATE = '2024-01-01'
END_DATE = '2026-11-08'
TIMEFRAME = '4h'


def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def run_cli_with_technical_retry(symbol, strategy, params):
    """Run CLI backtest. Only technical failures are retried once."""
    cmd = [
        str(VENV_PYTHON), '-m', 'backtest', 'run',
        '--symbol', symbol,
        '--strategy', strategy,
        '--timeframe', TIMEFRAME,
        '--start', START_DATE,
        '--end', END_DATE,
        '--params', json.dumps(params),
    ]
    market = symbol.replace('/', '')
    prefix = f"{market}_{TIMEFRAME}_{START_DATE}_{END_DATE}"
    summary_path = RESULTS_DIR / f"{prefix}_summary.csv"

    log(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    technical_failure = (res.returncode != 0) or (not summary_path.exists())

    if technical_failure:
        reason = f"returncode={res.returncode}, summary_exists={summary_path.exists()}, stderr={res.stderr.strip()}"
        log(f"TECHNICAL FAILURE on first attempt: {reason}. Retrying ONCE as allowed by protocol...")
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        technical_failure = (res.returncode != 0) or (not summary_path.exists())
        if technical_failure:
            err = f"FATAL: Technical retry also failed: returncode={res.returncode}, stderr={res.stderr.strip()}"
            log(err)
            raise RuntimeError(err)
        log("Technical retry succeeded.")

    return res.stdout


def extract_metrics_and_rename(symbol, strategy, tag):
    """Read summary row for strategy and rename variant equity/trades files."""
    market = symbol.replace('/', '')
    prefix = f"{market}_{TIMEFRAME}_{START_DATE}_{END_DATE}"
    summary_path = RESULTS_DIR / f"{prefix}_summary.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Summary file not found: {summary_path}")

    df_summary = pd.read_csv(summary_path, index_col=0)
    if strategy not in df_summary.index:
        raise KeyError(f"Strategy {strategy} not in {summary_path}")

    row = df_summary.loc[strategy]
    metrics = {
        'return': float(row['total_return']),
        'sharpe': float(row['sharpe']),
        'maxdd': float(row['max_drawdown']),
        'trades': int(round(float(row['trade_count']))),
    }

    # Rename equity and trades files to variant-tagged names
    src_equity = RESULTS_DIR / f"{prefix}_{strategy}_equity.csv"
    dst_equity = RESULTS_DIR / f"{prefix}_{strategy}_{tag}_equity.csv"
    src_trades = RESULTS_DIR / f"{prefix}_{strategy}_trades.csv"
    dst_trades = RESULTS_DIR / f"{prefix}_{strategy}_{tag}_trades.csv"

    if not src_equity.exists():
        raise FileNotFoundError(f"Source equity file not found: {src_equity}")
    if not src_trades.exists():
        raise FileNotFoundError(f"Source trades file not found: {src_trades}")

    os.replace(src_equity, dst_equity)
    os.replace(src_trades, dst_trades)

    log(f"Renamed -> {dst_equity.name} and {dst_trades.name}")
    return metrics


def sanity_check_default(strategy, symbol, metrics):
    """Check default metrics against VALIDATION.md benchmarks."""
    benchmarks = {
        ('keltner_breakout', 'BTC/USDT'): {'return': 0.1537, 'sharpe': 0.4354, 'maxdd': -0.1345, 'trades': 139},
        ('keltner_breakout', 'ETH/USDT'): {'return': 0.3333, 'sharpe': 0.8120, 'maxdd': -0.1649, 'trades': 127},
        ('rsi_atr_trend_4h', 'BTC/USDT'): {'return': 0.2050, 'sharpe': 0.4848, 'maxdd': -0.1607, 'trades': 39},
        ('rsi_atr_trend_4h', 'ETH/USDT'): {'return': 0.6032, 'sharpe': 1.0164, 'maxdd': -0.1310, 'trades': 31},
    }

    exp = benchmarks[(strategy, symbol)]
    ret_diff = abs(metrics['return'] - exp['return'])
    shp_diff = abs(metrics['sharpe'] - exp['sharpe'])
    dd_diff = abs(metrics['maxdd'] - exp['maxdd'])
    tr_diff = abs(metrics['trades'] - exp['trades'])

    log(f"Sanity check for {strategy} on {symbol}:")
    log(f"  Observed: return={metrics['return']:.4f}, sharpe={metrics['sharpe']:.4f}, maxdd={metrics['maxdd']:.4f}, trades={metrics['trades']}")
    log(f"  Expected: return={exp['return']:.4f}, sharpe={exp['sharpe']:.4f}, maxdd={exp['maxdd']:.4f}, trades={exp['trades']}")
    log(f"  Diffs: return_diff={ret_diff:.4f} (<=0.005), sharpe_diff={shp_diff:.4f} (<=0.02), maxdd_diff={dd_diff:.4f} (<=0.005), trade_diff={tr_diff} (<=2)")

    if ret_diff > 0.005 or shp_diff > 0.02 or dd_diff > 0.005 or tr_diff > 2:
        msg = f"SANITY CHECK MISMATCH for {strategy} on {symbol} exceeds threshold! Halting."
        log(msg)
        raise ValueError(msg)
    log(f"Sanity check PASSED for {strategy} on {symbol}.\n")


def append_to_p2_csv(row_dict):
    """Append a single row to results/p2_validation.csv."""
    row_df = pd.DataFrame([row_dict])
    row_df['ema_period'] = row_df['ema_period'].astype('Int64')
    row_df['atr_period'] = row_df['atr_period'].astype('Int64')
    row_df['period'] = row_df['period'].astype('Int64')
    row_df['trades'] = row_df['trades'].astype(int)
    columns = [
        'strategy', 'variant', 'multiplier', 'ema_period', 'atr_period',
        'stop_atr', 'period', 'symbol', 'return', 'sharpe', 'maxdd',
        'trades', 'return_diff_pp', 'sharpe_diff', 'maxdd_diff_pp'
    ]
    row_df = row_df[columns]
    header = not CSV_OUT.exists()
    row_df.to_csv(CSV_OUT, mode='a', index=False, header=header)


def main():
    # Clear log and CSV file for a clean run
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write("=== P2 OUT-OF-SAMPLE VALIDATION LOG ===\n")
    if CSV_OUT.exists():
        CSV_OUT.unlink()

    # Verify backup exists before doing anything
    if not BACKUP_DIR.exists():
        raise RuntimeError(f"Backup directory {BACKUP_DIR} is missing!")
    backup_file_count = len(list(BACKUP_DIR.iterdir()))
    log(f"Verified backup directory {BACKUP_DIR} contains {backup_file_count} files (must be 168).")
    if backup_file_count != 168:
        raise RuntimeError(f"Expected 168 backup files, found {backup_file_count}!")

    # Define the 14 runs
    # 1-4: defaults
    default_runs = [
        {
            'strategy': 'keltner_breakout',
            'variant': 'K-default',
            'symbol': 'BTC/USDT',
            'multiplier': 2.0,
            'ema_period': 35,
            'atr_period': 17,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 2, "ema_period": 35, "atr_period": 17, "stop_atr": 2},
            'tag': 'm2.0_e35_a17',
        },
        {
            'strategy': 'keltner_breakout',
            'variant': 'K-default',
            'symbol': 'ETH/USDT',
            'multiplier': 2.0,
            'ema_period': 35,
            'atr_period': 17,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 2, "ema_period": 35, "atr_period": 17, "stop_atr": 2},
            'tag': 'm2.0_e35_a17',
        },
        {
            'strategy': 'rsi_atr_trend_4h',
            'variant': 'R-default',
            'symbol': 'BTC/USDT',
            'multiplier': None,
            'ema_period': None,
            'atr_period': None,
            'stop_atr': 1.5,
            'period': 14,
            'params': {"stop_atr": 1.5, "period": 14, "upper": 70, "lower": 30, "fast": 100, "slow": 200},
            'tag': 's1.5_p14',
        },
        {
            'strategy': 'rsi_atr_trend_4h',
            'variant': 'R-default',
            'symbol': 'ETH/USDT',
            'multiplier': None,
            'ema_period': None,
            'atr_period': None,
            'stop_atr': 1.5,
            'period': 14,
            'params': {"stop_atr": 1.5, "period": 14, "upper": 70, "lower": 30, "fast": 100, "slow": 200},
            'tag': 's1.5_p14',
        },
    ]

    tuned_runs = [
        # K1
        {
            'strategy': 'keltner_breakout',
            'variant': 'K1',
            'symbol': 'BTC/USDT',
            'multiplier': 3.0,
            'ema_period': 20,
            'atr_period': 21,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 3.0, "ema_period": 20, "atr_period": 21, "stop_atr": 2},
            'tag': 'm3.0_e20_a21',
        },
        {
            'strategy': 'keltner_breakout',
            'variant': 'K1',
            'symbol': 'ETH/USDT',
            'multiplier': 3.0,
            'ema_period': 20,
            'atr_period': 21,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 3.0, "ema_period": 20, "atr_period": 21, "stop_atr": 2},
            'tag': 'm3.0_e20_a21',
        },
        # K2
        {
            'strategy': 'keltner_breakout',
            'variant': 'K2',
            'symbol': 'BTC/USDT',
            'multiplier': 2.5,
            'ema_period': 20,
            'atr_period': 14,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 2.5, "ema_period": 20, "atr_period": 14, "stop_atr": 2},
            'tag': 'm2.5_e20_a14',
        },
        {
            'strategy': 'keltner_breakout',
            'variant': 'K2',
            'symbol': 'ETH/USDT',
            'multiplier': 2.5,
            'ema_period': 20,
            'atr_period': 14,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 2.5, "ema_period": 20, "atr_period": 14, "stop_atr": 2},
            'tag': 'm2.5_e20_a14',
        },
        # K3
        {
            'strategy': 'keltner_breakout',
            'variant': 'K3',
            'symbol': 'BTC/USDT',
            'multiplier': 3.0,
            'ema_period': 20,
            'atr_period': 14,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 3.0, "ema_period": 20, "atr_period": 14, "stop_atr": 2},
            'tag': 'm3.0_e20_a14',
        },
        {
            'strategy': 'keltner_breakout',
            'variant': 'K3',
            'symbol': 'ETH/USDT',
            'multiplier': 3.0,
            'ema_period': 20,
            'atr_period': 14,
            'stop_atr': 2.0,
            'period': None,
            'params': {"multiplier": 3.0, "ema_period": 20, "atr_period": 14, "stop_atr": 2},
            'tag': 'm3.0_e20_a14',
        },
        # R1
        {
            'strategy': 'rsi_atr_trend_4h',
            'variant': 'R1',
            'symbol': 'BTC/USDT',
            'multiplier': None,
            'ema_period': None,
            'atr_period': None,
            'stop_atr': 1.5,
            'period': 21,
            'params': {"stop_atr": 1.5, "period": 21, "upper": 70, "lower": 30, "fast": 100, "slow": 200},
            'tag': 's1.5_p21',
        },
        {
            'strategy': 'rsi_atr_trend_4h',
            'variant': 'R1',
            'symbol': 'ETH/USDT',
            'multiplier': None,
            'ema_period': None,
            'atr_period': None,
            'stop_atr': 1.5,
            'period': 21,
            'params': {"stop_atr": 1.5, "period": 21, "upper": 70, "lower": 30, "fast": 100, "slow": 200},
            'tag': 's1.5_p21',
        },
        # R2
        {
            'strategy': 'rsi_atr_trend_4h',
            'variant': 'R2',
            'symbol': 'BTC/USDT',
            'multiplier': None,
            'ema_period': None,
            'atr_period': None,
            'stop_atr': 1.0,
            'period': 10,
            'params': {"stop_atr": 1.0, "period": 10, "upper": 70, "lower": 30, "fast": 100, "slow": 200},
            'tag': 's1.0_p10',
        },
        {
            'strategy': 'rsi_atr_trend_4h',
            'variant': 'R2',
            'symbol': 'ETH/USDT',
            'multiplier': None,
            'ema_period': None,
            'atr_period': None,
            'stop_atr': 1.0,
            'period': 10,
            'params': {"stop_atr": 1.0, "period": 10, "upper": 70, "lower": 30, "fast": 100, "slow": 200},
            'tag': 's1.0_p10',
        },
    ]

    all_results = []
    defaults_by_key = {}  # (strategy, symbol) -> metrics

    log("\n--- STEP A: RUNNING DEFAULTS AND CHECKING BENCHMARKS ---")
    for r in default_runs:
        strat = r['strategy']
        sym = r['symbol']
        var = r['variant']
        params = r['params']
        tag = r['tag']

        log(f"\n[Default Run] {strat} {var} on {sym} with params {params}")
        run_cli_with_technical_retry(sym, strat, params)
        m = extract_metrics_and_rename(sym, strat, tag)
        sanity_check_default(strat, sym, m)

        defaults_by_key[(strat, sym)] = m
        row = {
            'strategy': strat,
            'variant': var,
            'multiplier': r['multiplier'],
            'ema_period': r['ema_period'],
            'atr_period': r['atr_period'],
            'stop_atr': r['stop_atr'],
            'period': r['period'],
            'symbol': sym,
            'return': m['return'],
            'sharpe': m['sharpe'],
            'maxdd': m['maxdd'],
            'trades': m['trades'],
            'return_diff_pp': 0.0,
            'sharpe_diff': 0.0,
            'maxdd_diff_pp': 0.0,
        }
        all_results.append(row)
        append_to_p2_csv(row)

    log("\n--- STEP B: RUNNING TUNED VARIANTS (10 runs) ---")
    for r in tuned_runs:
        strat = r['strategy']
        sym = r['symbol']
        var = r['variant']
        params = r['params']
        tag = r['tag']

        log(f"\n[Tuned Run] {strat} {var} on {sym} with params {params}")
        run_cli_with_technical_retry(sym, strat, params)
        m = extract_metrics_and_rename(sym, strat, tag)

        def_m = defaults_by_key[(strat, sym)]
        ret_diff_pp = (m['return'] - def_m['return']) * 100.0
        shp_diff = m['sharpe'] - def_m['sharpe']
        maxdd_diff_pp = (m['maxdd'] - def_m['maxdd']) * 100.0

        log(f"  Result: return={m['return']:.4f} (diff={ret_diff_pp:+.2f}pp), "
            f"sharpe={m['sharpe']:.4f} (diff={shp_diff:+.4f}), "
            f"maxdd={m['maxdd']:.4f} (diff={maxdd_diff_pp:+.2f}pp), "
            f"trades={m['trades']}")

        row = {
            'strategy': strat,
            'variant': var,
            'multiplier': r['multiplier'],
            'ema_period': r['ema_period'],
            'atr_period': r['atr_period'],
            'stop_atr': r['stop_atr'],
            'period': r['period'],
            'symbol': sym,
            'return': m['return'],
            'sharpe': m['sharpe'],
            'maxdd': m['maxdd'],
            'trades': m['trades'],
            'return_diff_pp': ret_diff_pp,
            'sharpe_diff': shp_diff,
            'maxdd_diff_pp': maxdd_diff_pp,
        }
        all_results.append(row)
        append_to_p2_csv(row)

    df_results = pd.DataFrame(all_results)
    df_results['ema_period'] = df_results['ema_period'].astype('Int64')
    df_results['atr_period'] = df_results['atr_period'].astype('Int64')
    df_results['period'] = df_results['period'].astype('Int64')
    df_results['trades'] = df_results['trades'].astype(int)

    # Sort order: strategy, variant, symbol
    # Define custom ordering for variants to ensure K-default < K1 < K2 < K3 and R-default < R1 < R2
    variant_order = {'K-default': 0, 'K1': 1, 'K2': 2, 'K3': 3, 'R-default': 4, 'R1': 5, 'R2': 6}
    df_results['var_rank'] = df_results['variant'].map(variant_order)
    df_results = df_results.sort_values(by=['strategy', 'var_rank', 'symbol']).drop(columns=['var_rank'])

    # Format empty cells as blank in CSV
    columns = [
        'strategy', 'variant', 'multiplier', 'ema_period', 'atr_period',
        'stop_atr', 'period', 'symbol', 'return', 'sharpe', 'maxdd',
        'trades', 'return_diff_pp', 'sharpe_diff', 'maxdd_diff_pp'
    ]
    df_results = df_results[columns]
    df_results.to_csv(CSV_OUT, index=False)
    log(f"\nWrote results to {CSV_OUT} ({len(df_results)} rows).")

    # Compute verdicts for tuned variants (K1, K2, K3, R1, R2)
    log("\n=== SECTION 6: VERDICTS ===")
    variants_to_eval = [
        ('keltner_breakout', 'K1', 'K-default'),
        ('keltner_breakout', 'K2', 'K-default'),
        ('keltner_breakout', 'K3', 'K-default'),
        ('rsi_atr_trend_4h', 'R1', 'R-default'),
        ('rsi_atr_trend_4h', 'R2', 'R-default'),
    ]

    verdicts = {}
    for strat, var, def_var in variants_to_eval:
        btc_var = df_results[(df_results['strategy'] == strat) & (df_results['variant'] == var) & (df_results['symbol'] == 'BTC/USDT')].iloc[0]
        eth_var = df_results[(df_results['strategy'] == strat) & (df_results['variant'] == var) & (df_results['symbol'] == 'ETH/USDT')].iloc[0]
        btc_def = df_results[(df_results['strategy'] == strat) & (df_results['variant'] == def_var) & (df_results['symbol'] == 'BTC/USDT')].iloc[0]
        eth_def = df_results[(df_results['strategy'] == strat) & (df_results['variant'] == def_var) & (df_results['symbol'] == 'ETH/USDT')].iloc[0]

        # (a) sharpe_sum(var) > sharpe_sum(def)
        var_sharpe_sum = btc_var['sharpe'] + eth_var['sharpe']
        def_sharpe_sum = btc_def['sharpe'] + eth_def['sharpe']
        sharpe_sum_diff = var_sharpe_sum - def_sharpe_sum
        a_pass = sharpe_sum_diff > 0

        # (b) return_sum(var) > return_sum(def)
        var_ret_sum = btc_var['return'] + eth_var['return']
        def_ret_sum = btc_def['return'] + eth_def['return']
        ret_sum_diff_pp = (var_ret_sum - def_ret_sum) * 100.0
        b_pass = ret_sum_diff_pp > 0

        # (c) per coin: variant return >= default return - 0.05
        btc_ret_diff_pp = (btc_var['return'] - btc_def['return']) * 100.0
        eth_ret_diff_pp = (eth_var['return'] - eth_def['return']) * 100.0
        if btc_ret_diff_pp <= eth_ret_diff_pp:
            worst_ret_pp = btc_ret_diff_pp
            worst_ret_coin = 'BTC'
        else:
            worst_ret_pp = eth_ret_diff_pp
            worst_ret_coin = 'ETH'
        c_pass = (btc_var['return'] >= btc_def['return'] - 0.05) and (eth_var['return'] >= eth_def['return'] - 0.05)

        # (d) per coin: variant maxdd >= default maxdd - 0.05
        btc_maxdd_diff_pp = (btc_var['maxdd'] - btc_def['maxdd']) * 100.0
        eth_maxdd_diff_pp = (eth_var['maxdd'] - eth_def['maxdd']) * 100.0
        if btc_maxdd_diff_pp <= eth_maxdd_diff_pp:
            worst_maxdd_pp = btc_maxdd_diff_pp
            worst_maxdd_coin = 'BTC'
        else:
            worst_maxdd_pp = eth_maxdd_diff_pp
            worst_maxdd_coin = 'ETH'
        d_pass = (btc_var['maxdd'] >= btc_def['maxdd'] - 0.05) and (eth_var['maxdd'] >= eth_def['maxdd'] - 0.05)

        passed = a_pass and b_pass and c_pass and d_pass
        verdict_str = "PASS" if passed else "FAIL"
        verdicts[var] = {
            'verdict': verdict_str,
            'sharpe_sum_diff': sharpe_sum_diff,
            'return_sum_diff_pp': ret_sum_diff_pp,
            'worst_ret_pp': worst_ret_pp,
            'worst_ret_coin': worst_ret_coin,
            'worst_maxdd_pp': worst_maxdd_pp,
            'worst_maxdd_coin': worst_maxdd_coin,
            'a_pass': a_pass,
            'b_pass': b_pass,
            'c_pass': c_pass,
            'd_pass': d_pass,
        }

        log(f"Variant {var} ({strat}): {verdict_str}")
        log(f"  (a) sharpe_sum diff: {sharpe_sum_diff:+.4f} (pass={a_pass}) [var={var_sharpe_sum:.4f}, def={def_sharpe_sum:.4f}]")
        log(f"  (b) return_sum diff: {ret_sum_diff_pp:+.2f}pp (pass={b_pass}) [var={var_ret_sum*100:.2f}%, def={def_ret_sum*100:.2f}%]")
        log(f"  (c) worst per-coin return diff: {worst_ret_pp:+.2f}pp on {worst_ret_coin} (pass={c_pass}, threshold >= -5.00pp)")
        log(f"  (d) worst per-coin maxdd diff: {worst_maxdd_pp:+.2f}pp on {worst_maxdd_coin} (pass={d_pass}, threshold >= -5.00pp)")

    log("\n=== FULL P2 VALIDATION TABLE ===")
    log(df_results.to_string(index=False))

    # Restore backups
    log("\n=== RESTORING BACKUP FILES ===")
    for backup_file in BACKUP_DIR.iterdir():
        if backup_file.is_file():
            shutil.copy2(backup_file, RESULTS_DIR / backup_file.name)
    log(f"Restored all files from {BACKUP_DIR} to {RESULTS_DIR}")

    # Verify line counts of touched summary files
    for sym_prefix in ['BTCUSDT_4h_2024-01-01_2026-11-08', 'ETHUSDT_4h_2024-01-01_2026-11-08']:
        sum_file = RESULTS_DIR / f"{sym_prefix}_summary.csv"
        with open(sum_file, 'r', encoding='utf-8') as f:
            lines = len(f.readlines())
        log(f"Verified {sum_file.name}: {lines} lines (14 expected)")
        if lines != 14:
            raise RuntimeError(f"{sum_file.name} has {lines} lines, expected 14!")

    # Verify untouched full period summaries
    for full_sum in ['BTCUSDT_4h_2021-01-01_2026-11-08_summary.csv', 'ETHUSDT_4h_2021-01-01_2026-11-08_summary.csv']:
        sum_file = RESULTS_DIR / full_sum
        with open(sum_file, 'r', encoding='utf-8') as f:
            lines = len(f.readlines())
        log(f"Verified full-period {sum_file.name}: {lines} lines (14 expected)")
        if lines != 14:
            raise RuntimeError(f"{sum_file.name} has {lines} lines, expected 14!")

    # Verify p2_validation.csv survived
    if not CSV_OUT.exists():
        raise RuntimeError(f"{CSV_OUT} was lost during restore!")
    with open(CSV_OUT, 'r', encoding='utf-8') as f:
        csv_lines = len(f.readlines())
    log(f"Verified {CSV_OUT.name} survived restore: {csv_lines} lines (15 expected: 1 header + 14 rows).")
    if csv_lines != 15:
        raise RuntimeError(f"{CSV_OUT.name} has {csv_lines} lines, expected 15!")

    log("\n=== P2 VALIDATION COMPLETED SUCCESSFULLY ===")


if __name__ == '__main__':
    main()
