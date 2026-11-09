import numpy as np
import pandas as pd
import pytest

from backtest.strategies import get_strategy
from backtest.strategies.common import atr


NAMES = ['funding_zscore_fade', 'funding_extreme_threshold', 'funding_filtered_keltner']


def candles(close, funding_rate=0.0):
    df = pd.DataFrame({'close': np.asarray(close, dtype=float)},
                      index=pd.date_range('2024-01-01', periods=len(close), freq='4h', tz='UTC'))
    df['open'] = df.close.shift().fillna(df.close.iloc[0])
    df['high'] = df[['open', 'close']].max(axis=1)+1
    df['low'] = df[['open', 'close']].min(axis=1)-1
    df['funding_rate'] = funding_rate
    return df


@pytest.mark.parametrize('name', NAMES)
def test_long_entry(name):
    if name == 'funding_zscore_fade':
        df = candles([100.]*182, [0.]*180+[-0.001]*2)
    elif name == 'funding_extreme_threshold':
        df = candles([100.]*100, -0.001)
    else:
        df = candles(np.arange(100, 200), -0.0001)
    signals = get_strategy(name)(df)
    assert signals.direction.iloc[-1] == 1
    period = 17 if name == 'funding_filtered_keltner' else 14
    pd.testing.assert_series_equal(signals.stop_distance, (2*atr(df, period)).rename('stop_distance'))
    assert (signals.stop_distance.dropna() > 0).all()
    if name == 'funding_filtered_keltner':
        blocked = get_strategy(name)(df.assign(funding_rate=0.001))
        assert (blocked.direction == 0).all()
        pd.testing.assert_frame_equal(blocked.drop(columns='direction'), signals.drop(columns='direction'))
    else:
        assert (signals.max_days == 14).all()
    assert 'target_r' not in signals


@pytest.mark.parametrize('name', NAMES)
def test_long_exit_after_entry(name):
    if name == 'funding_zscore_fade':
        df = candles([100.]*184, [0.]*180+[-0.001]*2+[0.001]*2)
    elif name == 'funding_extreme_threshold':
        df = candles([100.]*102, [-0.001]*100+[0.001]*2)
    else:
        df = candles(np.r_[np.arange(100, 200), np.arange(199, 99, -1)], -0.0001)
    signals = get_strategy(name)(df)
    entry = np.flatnonzero(signals.direction.to_numpy() == 1)[0]
    assert signals.exit_long.iloc[entry+1:].any()


@pytest.mark.parametrize('name', NAMES)
def test_short_entry(name):
    if name == 'funding_zscore_fade':
        df = candles([100.]*182, [0.]*180+[0.001]*2)
    elif name == 'funding_extreme_threshold':
        df = candles([100.]*100, 0.001)
    else:
        df = candles(np.arange(200, 100, -1), 0.0001)
    signals = get_strategy(name)(df)
    assert signals.direction.iloc[-1] == -1
    period = 17 if name == 'funding_filtered_keltner' else 14
    pd.testing.assert_series_equal(signals.stop_distance, (2*atr(df, period)).rename('stop_distance'))
    assert (signals.stop_distance.dropna() > 0).all()
    if name == 'funding_filtered_keltner':
        blocked = get_strategy(name)(df.assign(funding_rate=-0.001))
        assert (blocked.direction == 0).all()
        pd.testing.assert_frame_equal(blocked.drop(columns='direction'), signals.drop(columns='direction'))
    else:
        assert (signals.max_days == 14).all()
    assert 'target_r' not in signals


@pytest.mark.parametrize('name', NAMES)
def test_short_exit_after_entry(name):
    if name == 'funding_zscore_fade':
        df = candles([100.]*184, [0.]*180+[0.001]*2+[-0.001]*2)
    elif name == 'funding_extreme_threshold':
        df = candles([100.]*102, [0.001]*100+[-0.001]*2)
    else:
        df = candles(np.r_[np.arange(200, 100, -1), np.arange(101, 201)], 0.0001)
    signals = get_strategy(name)(df)
    entry = np.flatnonzero(signals.direction.to_numpy() == -1)[0]
    assert signals.exit_short.iloc[entry+1:].any()


@pytest.mark.parametrize('name', NAMES)
def test_strategy_prefix_invariance(name):
    rng = np.random.default_rng(13)
    df = candles(100+np.cumsum(rng.normal(size=300)),
                 np.repeat(rng.normal(0, 0.0005, size=150), 2))
    full = get_strategy(name)(df)
    prefix = get_strategy(name)(df.iloc[:240])
    pd.testing.assert_frame_equal(full.iloc[:240], prefix)
