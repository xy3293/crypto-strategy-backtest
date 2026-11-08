import numpy as np
import pandas as pd
from . import metrics


def load_equity(path):
    df = pd.read_csv(path, index_col=0)
    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize('UTC')
    s = pd.Series(df['equity'].astype(float).values, index=idx, name='equity')
    return s


def combine(equities, weights):
    if set(equities.keys()) != set(weights.keys()):
        raise ValueError("equities and weights keys must match")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1 within 1e-9")
    keys = list(equities.keys())
    first_idx = equities[keys[0]].index
    for k in keys[1:]:
        if not equities[k].index.equals(first_idx):
            raise ValueError(f"Index mismatch between {keys[0]} and {k}")
    res = sum(weights[k] * equities[k] for k in keys)
    if all(np.isclose(equities[k].iloc[0], 10000.0) for k in keys):
        res.iloc[0] = 10000.0
    res.name = 'equity'
    return res


def portfolio_metrics(equity):
    m = metrics.summarize(equity, trades=[])
    return {
        'total_return': float(m['total_return']),
        'cagr': float(m['cagr']),
        'sharpe': float(m['sharpe']),
        'max_drawdown': float(m['max_drawdown']),
        'final_equity': float(equity.iloc[-1]),
    }


def sharpe_weights(sharpes):
    if not sharpes:
        raise ValueError("sharpes dict cannot be empty")
    if any(s <= 0 for s in sharpes.values()):
        raise ValueError("All sharpe values must be positive")
    total = sum(sharpes.values())
    if total <= 0:
        raise ValueError("Sum of sharpe values must be positive")
    return {k: float(v / total) for k, v in sharpes.items()}


def return_correlations(equities):
    df_returns = pd.DataFrame({name: eq.pct_change().dropna() for name, eq in equities.items()})
    return df_returns.corr(method='pearson')


def position_overlap(trades_by_strategy, index):
    n_bars = len(index)
    if n_bars == 0:
        return {
            'frac_all_three_in': 0.0,
            'frac_all_three_in_same_dir': 0.0,
            'pairwise_same_dir': {},
            'avg_strategies_in': 0.0,
        }

    pos_dict = {}
    for name, df in trades_by_strategy.items():
        has_long = np.zeros(n_bars, dtype=bool)
        has_short = np.zeros(n_bars, dtype=bool)
        if df is not None and not df.empty:
            entries = pd.to_datetime(df['entry_time'])
            exits = pd.to_datetime(df['exit_time'])
            if index.tz is not None:
                if entries.dt.tz is None:
                    entries = entries.dt.tz_localize(index.tz)
                else:
                    entries = entries.dt.tz_convert(index.tz)
                if exits.dt.tz is None:
                    exits = exits.dt.tz_localize(index.tz)
                else:
                    exits = exits.dt.tz_convert(index.tz)
            elif entries.dt.tz is not None:
                entries = entries.dt.tz_localize(None)
                exits = exits.dt.tz_localize(None)

            s_idxs = index.searchsorted(entries, side='left')
            e_idxs = index.searchsorted(exits, side='left')
            sides = df['side'].values
            for s_idx, e_idx, side in zip(s_idxs, e_idxs, sides):
                if side > 0:
                    has_long[s_idx:e_idx] = True
                elif side < 0:
                    has_short[s_idx:e_idx] = True

        dir_arr = np.zeros(n_bars, dtype=int)
        dir_arr[has_long & ~has_short] = 1
        dir_arr[has_short & ~has_long] = -1
        pos_dict[name] = dir_arr

    pos_df = pd.DataFrame(pos_dict, index=index)
    strat_names = list(pos_dict.keys())

    all_in = (pos_df != 0).all(axis=1)
    frac_all_three_in = float(all_in.mean())

    if len(strat_names) >= 2:
        all_same = (pos_df.iloc[:, 0] != 0) & all_in
        for col in strat_names[1:]:
            all_same = all_same & (pos_df[col] == pos_df.iloc[:, 0])
        frac_all_three_in_same_dir = float(all_same.mean())
    else:
        frac_all_three_in_same_dir = frac_all_three_in

    avg_strategies_in = float((pos_df != 0).sum(axis=1).mean())

    pairwise_same_dir = {}
    for i in range(len(strat_names)):
        for j in range(i + 1, len(strat_names)):
            s1, s2 = strat_names[i], strat_names[j]
            same_dir = (pos_df[s1] != 0) & (pos_df[s2] != 0) & (pos_df[s1] == pos_df[s2])
            pairwise_same_dir[f"{s1}-{s2}"] = float(same_dir.mean())

    return {
        'frac_all_three_in': frac_all_three_in,
        'frac_all_three_in_same_dir': frac_all_three_in_same_dir,
        'pairwise_same_dir': pairwise_same_dir,
        'avg_strategies_in': avg_strategies_in,
    }
