import argparse
import json
from pathlib import Path
import pandas as pd
from .data import load
from .engine import run, Config
from .strategies import NAMES, get_strategy
from .strategies.common import output


def main():
    parser = argparse.ArgumentParser(description='Binance USDT perpetual swing backtests; end is exclusive')
    parser.add_argument('command', choices=['run', 'compare'])
    parser.add_argument('--symbol', default='BTC/USDT')
    parser.add_argument('--strategy', choices=NAMES, default=NAMES[0])
    parser.add_argument('--timeframe', choices=['1h', '4h'], default='4h')
    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2026-11-08')
    parser.add_argument('--leverage', type=float, default=2.)
    parser.add_argument('--fee', type=float, default=.0005)
    parser.add_argument('--slippage', type=float, default=.0005)
    parser.add_argument('--params', default='{}', help='JSON strategy keyword parameters (run only)')
    args = parser.parse_args()
    cfg = Config(leverage=args.leverage, fee=args.fee, slippage=args.slippage)
    df, funding = load(args.symbol, args.timeframe, args.start, args.end)
    print(f'{args.symbol} perpetual | {len(df)} closed bars | {df.index[0]} through {df.index[-1]} | {len(funding)} funding events')
    names = NAMES if args.command == 'compare' else [args.strategy]
    results = {}
    root = Path('results')
    root.mkdir(exist_ok=True)
    prefix = f'{args.symbol.replace("/", "")}_{args.timeframe}_{args.start}_{args.end}'
    for name in names+['buy_and_hold']:
        signals = output(df, 1, float('nan')) if name == 'buy_and_hold' else get_strategy(name)(df, **(json.loads(args.params) if args.command == 'run' else {}))
        result = run(df, signals, funding, cfg, buy_hold=name == 'buy_and_hold')
        results[name] = result.metrics
        result.equity.to_csv(root/f'{prefix}_{name}_equity.csv')
        pd.DataFrame(result.trades).to_csv(root/f'{prefix}_{name}_trades.csv', index=False)
    table = pd.DataFrame(results).T
    table.to_csv(root/f'{prefix}_summary.csv')
    print(table.to_string(float_format=lambda x: f'{x:.4f}'))
    print('Returns/drawdowns/win rates are fractions; total_funding is signed USDT cash flow (+ earned).')


if __name__ == '__main__':
    main()
