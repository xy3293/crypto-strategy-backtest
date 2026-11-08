import numpy as np
import pandas as pd


def summarize(equity, trades, funding=0., liquidations=0):
    elapsed = (equity.index[-1]-equity.index[0]).total_seconds()/86400
    returns = equity.pct_change().dropna()
    periods = 365.25*86400 / equity.index.to_series().diff().dt.total_seconds().median()
    net = equity.iloc[-1]/equity.iloc[0]-1
    pnl = np.array([t['pnl'] for t in trades])
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return dict(total_return=float(net), cagr=float((1+net)**(365.25/elapsed)-1) if elapsed and net > -1 else -1.,
                sharpe=float(returns.mean()/returns.std(ddof=1)*np.sqrt(periods)) if returns.std(ddof=1) > 0 else 0.,
                max_drawdown=float((equity/equity.cummax()-1).min()),
                win_rate=float((pnl > 0).mean()) if len(pnl) else 0.,
                profit_factor=float(wins/losses) if losses else (float('inf') if wins else 0.),
                trade_count=len(trades), average_holding_days=float(np.mean([t['holding_days'] for t in trades])) if trades else 0.,
                total_funding=float(funding), liquidations=liquidations)
