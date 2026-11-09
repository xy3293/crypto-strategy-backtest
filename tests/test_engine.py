import numpy as np
import pandas as pd
import pytest
from backtest.engine import run, Config
from backtest.metrics import summarize
from backtest.strategies.common import output
from backtest.strategies import NAMES, get_strategy


def candles(n=8):
    return pd.DataFrame({'open': 100., 'high': 101., 'low': 99., 'close': 100., 'funding_rate': 0.0},
                        index=pd.date_range('2024-01-01', periods=n, freq='4h', tz='UTC'))


def test_next_open_no_lookahead():
    df = candles()
    df.loc[df.index[2], 'close'] = 110
    df.loc[df.index[3], 'open'] = 112
    signals = output(df, (df.close > 105).astype(int), 30.)
    result = run(df, signals, config=Config(fee=0, slippage=0))
    assert result.trades[0]['entry_time'] == df.index[3]
    assert result.trades[0]['entry'] == 112


@pytest.mark.parametrize('side,expected', [(1, -1.), (-1, 1.)])
def test_funding_sign(side, expected):
    df = candles()
    funding = pd.DataFrame({'rate': [.001], 'mark': [100.]}, index=[df.index[2]])
    result = run(df, output(df, side, 10.), funding, Config(fee=0, slippage=0))
    assert result.metrics['total_funding'] == pytest.approx(expected)
    assert result.metrics['total_return'] == pytest.approx(expected/10000)


def test_fee_and_slippage():
    df = candles()
    result = run(df, output(df, 1, 10.))
    trade = result.trades[0]
    qty = 100/10
    entry = 100*1.0005
    exit = 100*.9995
    assert trade['pnl'] == pytest.approx(qty*(exit-entry)-qty*(entry+exit)*.0005)


@pytest.mark.parametrize('side,field,value', [(1, 'mark_low', 1.), (-1, 'mark_high', 1000.)])
def test_liquidation(side, field, value):
    df = candles()
    df[field] = 100.
    df.loc[df.index[2], field] = value
    direction = pd.Series(0, index=df.index)
    direction.iloc[0] = side
    result = run(df, output(df, direction, 50.), config=Config(fee=0, slippage=0))
    assert result.metrics['liquidations'] == 1
    assert result.trades[0]['reason'] == 'liquidation'
    assert result.trades[0]['pnl'] == pytest.approx(-100.)


def test_stop_gap_and_risk():
    df = candles()
    df.loc[df.index[2], ['open', 'low']] = [85., 84.]
    direction = pd.Series(0, index=df.index)
    direction.iloc[0] = 1
    result = run(df, output(df, direction, 10.), config=Config(fee=0, slippage=0))
    assert result.trades[0]['exit'] == 85
    assert result.trades[0]['pnl'] == -150


def test_metrics():
    equity = pd.Series([100., 120., 90., 110.], index=pd.date_range('2023-01-01', periods=4, freq='1D'))
    trades = [dict(pnl=20., holding_days=3.), dict(pnl=-10., holding_days=5.)]
    metrics = summarize(equity, trades)
    assert metrics['total_return'] == pytest.approx(.1)
    assert metrics['max_drawdown'] == pytest.approx(-.25)
    assert metrics['win_rate'] == .5
    assert metrics['profit_factor'] == 2
    assert metrics['average_holding_days'] == 4
    r = equity.pct_change().dropna()
    assert metrics['sharpe'] == pytest.approx(r.mean()/r.std()*np.sqrt(365.25))
    assert metrics['cagr'] == pytest.approx(1.1**(365.25/3)-1)


@pytest.mark.parametrize('name', NAMES)
def test_strategy_prefix_invariance(name):
    df = candles(300)
    rng = np.random.default_rng(13)
    df['close'] = 100+np.cumsum(rng.normal(size=len(df)))
    df['open'] = df.close.shift().fillna(100)
    df['high'] = df[['open', 'close']].max(axis=1)+1
    df['low'] = df[['open', 'close']].min(axis=1)-1
    full = get_strategy(name)(df)
    prefix = get_strategy(name)(df.iloc[:240])
    pd.testing.assert_frame_equal(full.iloc[:240], prefix)


def test_leverage_cap():
    with pytest.raises(ValueError):
        Config(leverage=6)


def test_stop_risks_one_percent_before_costs():
    df = candles()
    df.loc[df.index[2], 'low'] = 89.
    direction = pd.Series(0, index=df.index)
    direction.iloc[0] = 1
    result = run(df, output(df, direction, 10.), config=Config(fee=0, slippage=0))
    assert result.trades[0]['pnl'] == -100.
    assert result.equity.iloc[-1] == 9900.


def test_round_trip_pnl_reconciles_equity():
    df = candles()
    direction = pd.Series([1, -1, 1, -1, 0, 0, 0, 0], index=df.index)
    funding = pd.DataFrame({'rate': [.001], 'mark': [100.]}, index=[df.index[2]])
    result = run(df, output(df, direction, 20.), funding)
    assert sum(t['pnl'] for t in result.trades) == pytest.approx(result.equity.iloc[-1]-10000)
