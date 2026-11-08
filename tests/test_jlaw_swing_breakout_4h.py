import numpy as np
import pandas as pd
import pytest

from backtest.strategies import get_strategy
from backtest.strategies.jlaw_swing_breakout_4h import generate_signals


def breakout(side=1, low=99., high=101., close=None):
    prices = [80. if side == 1 else 120.] * 170 + [100.] * 30
    prices.append((102. if side == 1 else 98.) if close is None else close)
    df = pd.DataFrame({'open': prices, 'close': prices},
                      index=pd.date_range('2024-01-01', periods=201, freq='4h', tz='UTC'))
    df['high'] = df.close + 0.1
    df['low'] = df.close - 0.1
    df.loc[df.index[170:200], ['high', 'low']] = [high, low]
    return df


@pytest.mark.parametrize('side,stop', [(1, 3.), (-1, 3.)])
def test_tight_range_breakout(side, stop):
    df = breakout(side)
    signals = get_strategy('jlaw_swing_breakout_4h')(df)
    assert signals.index.equals(df.index)
    assert signals.iloc[-1].direction == side
    assert signals.iloc[-1].stop_distance == pytest.approx(stop)
    active = signals.loc[signals.direction != 0, ['stop_distance', 'target_r']]
    assert np.isfinite(active.to_numpy()).all()
    assert (active > 0).all().all()


def test_wide_range_blocks_breakout():
    assert generate_signals(breakout(low=95.)).iloc[-1].direction == 0


@pytest.mark.parametrize('side,close', [(1, 106.), (-1, 94.)])
def test_no_chase(side, close):
    assert generate_signals(breakout(side, close=close)).iloc[-1].direction == 0


@pytest.mark.parametrize('low,high,close,expected_distance', [
    (99.9, 100.1, 100.2, 0.05 * 100.2),
    (99., 101., 102., 6.),
    (97., 101., 104.9, 0.15 * 104.9),
])
def test_target_math(low, high, close, expected_distance):
    row = generate_signals(breakout(low=low, high=high, close=close)).iloc[-1]
    assert row.direction == 1
    assert row.stop_distance == pytest.approx(close - low)
    assert row.target_r == pytest.approx(expected_distance / (close - low))
    if low == 99.9:
        assert row.target_r > 2
    elif low == 99.:
        assert row.target_r == pytest.approx(2.)


def test_time_stop_and_no_other_exits():
    signals = generate_signals(breakout())
    assert signals.max_days.eq(7).all()
    assert not signals[['exit_long', 'exit_short']].any().any()


@pytest.mark.parametrize('length', [20, 30, 199])
def test_insufficient_history(length):
    df = breakout().iloc[-length:]
    assert generate_signals(df).direction.eq(0).all()


@pytest.mark.parametrize('side,close', [(1, 98.), (-1, 102.)])
def test_counter_trend_breakout(side, close):
    assert generate_signals(breakout(side, close=close)).iloc[-1].direction == 0


def test_prefix_safety_through_breakout():
    df = breakout()
    future = df.iloc[-5:].copy()
    future.index = pd.date_range(df.index[-1] + pd.Timedelta(hours=4), periods=5, freq='4h')
    future[['open', 'high', 'low', 'close']] *= 2
    full = generate_signals(pd.concat([df, future]))
    pd.testing.assert_frame_equal(full.iloc[:len(df)], generate_signals(df))
