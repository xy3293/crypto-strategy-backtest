import os
import sys
import numpy as np
import pandas as pd

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backtest.portfolio import (
    combine,
    load_equity,
    portfolio_metrics,
    position_overlap,
    return_correlations,
    sharpe_weights,
)

SYMBOLS = ['BTC', 'ETH', 'SOL', 'BNB']
STRATEGIES = ['rsi_atr_trend_4h', 'keltner_breakout', 'supertrend_4h']
PERIOD = '2021-01-01_2026-11-08'
TIMEFRAME = '4h'


def main():
    results_dir = os.path.dirname(__file__)

    # 1. Compute Sharpe weights from BTC and ETH summary CSVs
    btc_summary_path = os.path.join(results_dir, f'BTCUSDT_{TIMEFRAME}_{PERIOD}_summary.csv')
    eth_summary_path = os.path.join(results_dir, f'ETHUSDT_{TIMEFRAME}_{PERIOD}_summary.csv')

    btc_summary = pd.read_csv(btc_summary_path, index_col=0)
    eth_summary = pd.read_csv(eth_summary_path, index_col=0)

    combined_sharpes = {}
    for s in STRATEGIES:
        s_btc = float(btc_summary.loc[s, 'sharpe'])
        s_eth = float(eth_summary.loc[s, 'sharpe'])
        combined_sharpes[s] = s_btc + s_eth

    c_weights = sharpe_weights(combined_sharpes)
    print("Computed combined Sharpe ratios (BTC+ETH):", combined_sharpes)
    print("Computed Sharpe weights (c_sharpe):", c_weights)

    # Check approximate expected weights (rsi ~ 29.4%, keltner ~ 41.8%, supertrend ~ 28.8%)
    expected_approx = {'rsi_atr_trend_4h': 0.294, 'keltner_breakout': 0.418, 'supertrend_4h': 0.288}
    for k, exp in expected_approx.items():
        if abs(c_weights[k] - exp) > 0.01:
            raise ValueError(f"Weight for {k} ({c_weights[k]:.4f}) differs materially from expected approx {exp:.4f}")

    portfolios = [
        ('a_equal3', {s: 1.0 / 3.0 for s in STRATEGIES}),
        ('b_equal2', {'rsi_atr_trend_4h': 0.5, 'keltner_breakout': 0.5, 'supertrend_4h': 0.0}),
        ('c_sharpe', c_weights),
    ]

    summary_rows = []
    correlation_rows = []
    overlap_rows = []

    for sym in SYMBOLS:
        print(f"\nProcessing {sym}...")
        # Check files
        equities = {}
        missing = False
        for s in STRATEGIES:
            eq_path = os.path.join(results_dir, f'{sym}USDT_{TIMEFRAME}_{PERIOD}_{s}_equity.csv')
            if not os.path.exists(eq_path):
                print(f"Missing {eq_path}, skipping {sym}")
                missing = True
                break
            equities[s] = load_equity(eq_path)

        if missing:
            continue

        # Compute portfolios
        for p_name, p_weights in portfolios:
            p_eq = combine(equities, p_weights)
            assert len(p_eq) == 12822, f"Expected 12822 rows, got {len(p_eq)}"
            assert p_eq.iloc[0] == 10000.0, f"Expected first equity 10000.0, got {p_eq.iloc[0]}"

            # Save equity CSV
            out_eq_path = os.path.join(results_dir, f'{sym}USDT_{TIMEFRAME}_{PERIOD}_portfolio_{p_name}_equity.csv')
            p_eq.index.name = None
            p_eq.to_csv(out_eq_path)

            # Compute metrics
            m = portfolio_metrics(p_eq)
            weights_str = ';'.join(f'{k}={p_weights.get(k, 0.0):.4f}' for k in STRATEGIES)
            summary_rows.append({
                'symbol': sym,
                'portfolio': p_name,
                'weights': weights_str,
                'total_return': m['total_return'],
                'cagr': m['cagr'],
                'sharpe': m['sharpe'],
                'max_drawdown': m['max_drawdown'],
                'final_equity': m['final_equity'],
            })

        # Correlations
        corr = return_correlations(equities)
        for i in range(len(STRATEGIES)):
            for j in range(i, len(STRATEGIES)):
                s_a = STRATEGIES[i]
                s_b = STRATEGIES[j]
                correlation_rows.append({
                    'symbol': sym,
                    'strategy_a': s_a,
                    'strategy_b': s_b,
                    'correlation': float(corr.loc[s_a, s_b]),
                })

        # Position overlap
        trades_dict = {}
        for s in STRATEGIES:
            tr_path = os.path.join(results_dir, f'{sym}USDT_{TIMEFRAME}_{PERIOD}_{s}_trades.csv')
            trades_dict[s] = pd.read_csv(tr_path)

        ov = position_overlap(trades_dict, equities[STRATEGIES[0]].index)
        overlap_rows.append({
            'symbol': sym,
            'frac_all_three_in': ov['frac_all_three_in'],
            'frac_all_three_in_same_dir': ov['frac_all_three_in_same_dir'],
            'avg_strategies_in': ov['avg_strategies_in'],
            'rsi_keltner_same_dir': ov['pairwise_same_dir']['rsi_atr_trend_4h-keltner_breakout'],
            'rsi_supertrend_same_dir': ov['pairwise_same_dir']['rsi_atr_trend_4h-supertrend_4h'],
            'keltner_supertrend_same_dir': ov['pairwise_same_dir']['keltner_breakout-supertrend_4h'],
        })

    # Write summary CSVs
    summary_df = pd.DataFrame(summary_rows)
    summary_csv_path = os.path.join(results_dir, 'portfolio_summary.csv')
    summary_df.to_csv(summary_csv_path, index=False)
    print(f"\nWrote {summary_csv_path} ({len(summary_df)} rows)")

    corr_df = pd.DataFrame(correlation_rows)
    corr_csv_path = os.path.join(results_dir, 'portfolio_correlations.csv')
    corr_df.to_csv(corr_csv_path, index=False)
    print(f"Wrote {corr_csv_path} ({len(corr_df)} rows)")

    overlap_df = pd.DataFrame(overlap_rows)
    overlap_csv_path = os.path.join(results_dir, 'portfolio_overlap.csv')
    overlap_df.to_csv(overlap_csv_path, index=False)
    print(f"Wrote {overlap_csv_path} ({len(overlap_df)} rows)")


if __name__ == '__main__':
    main()
