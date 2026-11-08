"""A real Binance integration test; requires public network or the local CSV cache."""
from backtest.data import load
from backtest.engine import run
from backtest.strategies import get_strategy


def test_real_perpetual_end_to_end():
    df, funding = load('BTC/USDT', '4h', '2024-01-01', '2024-04-01')
    assert len(df) == 91*6
    assert df.mark_close.notna().all()
    assert len(funding) > 250
    result = run(df, get_strategy('turtle_donchian_4h')(df), funding)
    assert result.metrics['trade_count'] > 0
    assert result.equity.notna().all()
