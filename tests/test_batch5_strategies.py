import numpy as np
import pandas as pd
import pytest

from backtest.strategies import get_strategy
from backtest.strategies.common import atr


NAMES = ['ema_ribbon_4h', 'adx_trend_4h', 'ichimoku_4h',
         'rsi_reversion_4h', 'bollinger_mean_reversion_4h']


def candles(close):
    df = pd.DataFrame({'close': np.asarray(close, dtype=float)},
                      index=pd.date_range('2024-01-01', periods=len(close), freq='4h', tz='UTC'))
    df['open'] = df.close.shift().fillna(df.close.iloc[0])
    df['high'] = df[['open', 'close']].max(axis=1)+1
    df['low'] = df[['open', 'close']].min(axis=1)-1
    return df


@pytest.mark.parametrize('name', NAMES)
def test_long_entry(name):
    if name == 'rsi_reversion_4h':
        df = candles(np.arange(200, 100, -1))
    elif name == 'bollinger_mean_reversion_4h':
        df = candles([100.]*30+[80.])
    else:
        df = candles(np.arange(100, 200))
    signals = get_strategy(name)(df)
    assert signals.direction.iloc[-1] == 1
    pd.testing.assert_series_equal(signals.stop_distance, (2*atr(df, 14)).rename('stop_distance'))
    assert (signals.stop_distance.dropna() > 0).all()
    assert (signals.max_days == 14).all()
    assert 'target_r' not in signals


@pytest.mark.parametrize('name', NAMES)
def test_long_exit_after_entry(name):
    if name == 'rsi_reversion_4h':
        close = np.r_[np.arange(200, 100, -1), np.arange(101, 201)]
    elif name == 'bollinger_mean_reversion_4h':
        close = [100.]*30+[80., 100.]
    else:
        close = np.r_[np.arange(100, 200), np.arange(199, 99, -1)]
    signals = get_strategy(name)(candles(close))
    entry = np.flatnonzero(signals.direction.to_numpy() == 1)[0]
    assert signals.exit_long.iloc[entry+1:].any()


@pytest.mark.parametrize('name', NAMES)
def test_short_entry(name):
    if name == 'rsi_reversion_4h':
        df = candles(np.arange(100, 200))
    elif name == 'bollinger_mean_reversion_4h':
        df = candles([100.]*30+[120.])
    else:
        df = candles(np.arange(200, 100, -1))
    signals = get_strategy(name)(df)
    assert signals.direction.iloc[-1] == -1
    pd.testing.assert_series_equal(signals.stop_distance, (2*atr(df, 14)).rename('stop_distance'))
    assert (signals.stop_distance.dropna() > 0).all()
    assert (signals.max_days == 14).all()
    assert 'target_r' not in signals


@pytest.mark.parametrize('name', NAMES)
def test_short_exit_after_entry(name):
    if name == 'rsi_reversion_4h':
        close = np.r_[np.arange(100, 200), np.arange(199, 99, -1)]
    elif name == 'bollinger_mean_reversion_4h':
        close = [100.]*30+[120., 100.]
    else:
        close = np.r_[np.arange(200, 100, -1), np.arange(101, 201)]
    signals = get_strategy(name)(candles(close))
    entry = np.flatnonzero(signals.direction.to_numpy() == -1)[0]
    assert signals.exit_short.iloc[entry+1:].any()


@pytest.mark.parametrize('name', NAMES)
def test_strategy_prefix_invariance(name):
    rng = np.random.default_rng(13)
    df = candles(100+np.cumsum(rng.normal(size=300)))
    full = get_strategy(name)(df)
    prefix = get_strategy(name)(df.iloc[:240])
    pd.testing.assert_frame_equal(full.iloc[:240], prefix)
