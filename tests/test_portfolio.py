import numpy as np
import pandas as pd
import pytest

from backtest import metrics
from backtest.portfolio import (
    combine,
    load_equity,
    portfolio_metrics,
    position_overlap,
    return_correlations,
    sharpe_weights,
)


def test_combine():
    idx = pd.date_range('2021-01-01 00:00', periods=3, freq='4h', tz='UTC')
    s1 = pd.Series([10000.0, 10100.0, 10200.0], index=idx, name='equity')
    s2 = pd.Series([10000.0, 10050.0, 10100.0], index=idx, name='equity')
    s3 = pd.Series([10000.0, 9950.0, 9900.0], index=idx, name='equity')

    equities = {'s1': s1, 's2': s2, 's3': s3}
    weights = {'s1': 0.5, 's2': 0.3, 's3': 0.2}

    res = combine(equities, weights)
    expected = pd.Series([10000.0, 10055.0, 10110.0], index=idx, name='equity')
    pd.testing.assert_series_equal(res, expected)
    assert res.iloc[0] == 10000.0

    # Key mismatch
    with pytest.raises(ValueError, match="keys must match"):
        combine(equities, {'s1': 0.5, 's2': 0.5})

    # Weights sum mismatch
    with pytest.raises(ValueError, match="weights must sum to 1"):
        combine(equities, {'s1': 0.5, 's2': 0.3, 's3': 0.3})

    # Index mismatch
    idx2 = pd.date_range('2021-01-02 00:00', periods=3, freq='4h', tz='UTC')
    s3_bad = pd.Series([10000.0, 9950.0, 9900.0], index=idx2, name='equity')
    with pytest.raises(ValueError, match="Index mismatch"):
        combine({'s1': s1, 's2': s2, 's3': s3_bad}, weights)


def test_portfolio_metrics():
    idx = pd.date_range('2021-01-01 00:00', periods=10, freq='4h', tz='UTC')
    eq = pd.Series(np.linspace(10000.0, 12000.0, 10), index=idx, name='equity')

    pm = portfolio_metrics(eq)
    sm = metrics.summarize(eq, trades=[])

    assert pm['total_return'] == sm['total_return']
    assert pm['cagr'] == sm['cagr']
    assert pm['sharpe'] == sm['sharpe']
    assert pm['max_drawdown'] == sm['max_drawdown']
    assert pm['final_equity'] == float(eq.iloc[-1])
    assert set(pm.keys()) == {'total_return', 'cagr', 'sharpe', 'max_drawdown', 'final_equity'}


def test_sharpe_weights():
    sharpes = {'s1': 0.5, 's2': 1.0, 's3': 0.5}
    w = sharpe_weights(sharpes)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w['s1'] == pytest.approx(0.25)
    assert w['s2'] == pytest.approx(0.5)
    assert w['s3'] == pytest.approx(0.25)

    with pytest.raises(ValueError):
        sharpe_weights({'s1': -0.1, 's2': 0.5})

    with pytest.raises(ValueError):
        sharpe_weights({})


def test_return_correlations():
    idx = pd.date_range('2021-01-01 00:00', periods=5, freq='4h', tz='UTC')
    equities = {
        's1': pd.Series([100.0, 102.0, 101.0, 103.0, 105.0], index=idx),
        's2': pd.Series([100.0, 101.0, 102.0, 104.0, 103.0], index=idx),
        's3': pd.Series([100.0, 99.0, 98.0, 97.0, 96.0], index=idx),
    }
    corr = return_correlations(equities)
    assert corr.shape == (3, 3)
    for col in corr.columns:
        assert corr.loc[col, col] == pytest.approx(1.0)
    assert np.allclose(corr.values, corr.values.T)


def test_position_overlap():
    idx = pd.date_range('2021-01-01 00:00', periods=4, freq='4h', tz='UTC')
    # t0: 00:00, t1: 04:00, t2: 08:00, t3: 12:00

    # s1: [t1, t2) side 1 -> pos on t1=1, on t2=0 (boundary test)
    s1_trades = pd.DataFrame([
        {'entry_time': idx[1], 'exit_time': idx[2], 'side': 1}
    ])

    # s2: [t0, t2) side 1 and [t1, t3) side 1 -> overlap on t1 counts ONCE
    # pos: t0=1, t1=1, t2=1, t3=0
    s2_trades = pd.DataFrame([
        {'entry_time': idx[0], 'exit_time': idx[2], 'side': 1},
        {'entry_time': idx[1], 'exit_time': idx[3], 'side': 1},
    ])

    # s3: [t0, t2) side 1 and [t1, t3) side -1 -> overlap on t1 has opposite sides -> flat (0)
    # pos: t0=1, t1=0, t2=-1, t3=0
    s3_trades = pd.DataFrame([
        {'entry_time': idx[0], 'exit_time': idx[2], 'side': 1},
        {'entry_time': idx[1], 'exit_time': idx[3], 'side': -1},
    ])

    trades_by_strat = {'s1': s1_trades, 's2': s2_trades, 's3': s3_trades}
    res = position_overlap(trades_by_strat, idx)

    # All three in: t0(0,1,1)=F, t1(1,1,0)=F, t2(0,1,-1)=F, t3(0,0,0)=F -> 0.0
    assert res['frac_all_three_in'] == pytest.approx(0.0)
    assert res['frac_all_three_in_same_dir'] == pytest.approx(0.0)

    # Active counts per bar: t0=2, t1=2, t2=2, t3=0 -> mean = 6/4 = 1.5
    assert res['avg_strategies_in'] == pytest.approx(1.5)

    # Pairwise same dir:
    # s1 vs s2: t0(0,1)=F, t1(1,1)=T, t2(0,1)=F, t3(0,0)=F -> 1/4 = 0.25
    assert res['pairwise_same_dir']['s1-s2'] == pytest.approx(0.25)
    # s2 vs s3: t0(1,1)=T, t1(1,0)=F, t2(1,-1)=F, t3(0,0)=F -> 1/4 = 0.25
    assert res['pairwise_same_dir']['s2-s3'] == pytest.approx(0.25)
    # s1 vs s3: t0(0,1)=F, t1(1,0)=F, t2(0,-1)=F, t3(0,0)=F -> 0/4 = 0.0
    assert res['pairwise_same_dir']['s1-s3'] == pytest.approx(0.0)


def test_load_equity():
    eq = load_equity('results/BTCUSDT_4h_2021-01-01_2026-11-08_rsi_atr_trend_4h_equity.csv')
    assert isinstance(eq, pd.Series)
    assert eq.name == 'equity'
    assert eq.index.tz is not None
    assert len(eq) == 12822
    assert eq.iloc[0] == 10000.0
