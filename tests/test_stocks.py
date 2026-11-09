import json
import sys
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from backtest.__main__ import long_only_mask, main
from backtest.data import load_stocks
from backtest.engine import run, Config
from backtest.strategies.common import output
from backtest.strategies import get_strategy


def make_synthetic_yf_df(n_bars=60, start_date='2024-01-01', split_at=30, split_factor=0.5):
    dates = pd.date_range(start_date, periods=n_bars, freq='B')
    base_price = 100.0 + np.arange(n_bars, dtype=float)
    close = base_price.copy()
    open_p = close - 0.5
    high_p = close + 1.0
    low_p = close - 1.0
    volume = np.full(n_bars, 1000000, dtype=np.int64)

    adj_close = close.copy()
    # Before split_at, historical close is unadjusted, so Adj Close is scaled by split_factor
    adj_close[:split_at] = close[:split_at] * split_factor

    cols = pd.MultiIndex.from_tuples([
        ('Adj Close', 'TEST'),
        ('Close', 'TEST'),
        ('High', 'TEST'),
        ('Low', 'TEST'),
        ('Open', 'TEST'),
        ('Volume', 'TEST'),
    ], names=['Price', 'Ticker'])

    data = np.column_stack([adj_close, close, high_p, low_p, open_p, volume])
    return pd.DataFrame(data, index=dates, columns=cols)


def test_load_stocks_adjustment_math_and_no_lookahead(tmp_path):
    raw = make_synthetic_yf_df(n_bars=60, split_at=30, split_factor=0.5)

    with patch('yfinance.download', return_value=raw.copy()):
        df, funding = load_stocks('TEST', '2024-01-01', '2024-04-01', cache=str(tmp_path))

    assert funding.empty
    assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
    assert len(df) == 60

    # Bar 0 (before split): factor is 0.5
    assert df['close'].iloc[0] == pytest.approx(raw[('Adj Close', 'TEST')].iloc[0])
    assert df['open'].iloc[0] == pytest.approx(raw[('Open', 'TEST')].iloc[0] * 0.5)
    assert df['high'].iloc[0] == pytest.approx(raw[('High', 'TEST')].iloc[0] * 0.5)
    assert df['low'].iloc[0] == pytest.approx(raw[('Low', 'TEST')].iloc[0] * 0.5)

    # Bar 35 (after split): factor is 1.0
    assert df['close'].iloc[35] == pytest.approx(raw[('Close', 'TEST')].iloc[35])
    assert df['open'].iloc[35] == pytest.approx(raw[('Open', 'TEST')].iloc[35])

    # No lookahead: changing future bars does not affect past bars' adjustment
    raw_mod = raw.copy()
    raw_mod.iloc[40:, raw_mod.columns.get_loc(('Adj Close', 'TEST'))] *= 0.1
    with patch('yfinance.download', return_value=raw_mod):
        df_mod, _ = load_stocks('TEST_MOD', '2024-01-01', '2024-04-01', cache=str(tmp_path))
    pd.testing.assert_frame_equal(df.iloc[:30], df_mod.iloc[:30])


def test_load_stocks_cache_roundtrip(tmp_path):
    raw = make_synthetic_yf_df(n_bars=60)
    with patch('yfinance.download', return_value=raw) as mock_dl:
        df1, _ = load_stocks('TEST', '2024-01-01', '2024-04-01', cache=str(tmp_path))
        assert mock_dl.call_count == 1

        # Second call must load from cache without downloading
        df2, _ = load_stocks('TEST', '2024-01-01', '2024-04-01', cache=str(tmp_path))
        assert mock_dl.call_count == 1

    pd.testing.assert_frame_equal(df1, df2)


def test_load_stocks_multiindex_levels_handling(tmp_path):
    raw = make_synthetic_yf_df(n_bars=60)
    # Swap levels to (Ticker, Price)
    raw_swapped = raw.swaplevel(0, 1, axis=1)

    with patch('yfinance.download', return_value=raw_swapped):
        df, _ = load_stocks('TEST_SWAP', '2024-01-01', '2024-04-01', cache=str(tmp_path))
    assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
    assert len(df) == 60


def test_load_stocks_date_filtering(tmp_path):
    dates = pd.date_range('2024-01-01', periods=80, freq='D')
    raw = pd.DataFrame({
        'Adj Close': 100.0,
        'Close': 100.0,
        'High': 105.0,
        'Low': 95.0,
        'Open': 100.0,
        'Volume': 1000,
    }, index=dates)

    # End is exclusive: request start 2024-01-01, end 2024-03-01 (60 days, should exclude 2024-03-01)
    with patch('yfinance.download', return_value=raw):
        df, _ = load_stocks('TEST_DATE', '2024-01-01', '2024-03-01', cache=str(tmp_path))
    assert df.index[0] == pd.Timestamp('2024-01-01', tz='UTC')
    assert df.index[-1] == pd.Timestamp('2024-02-29', tz='UTC')
    assert pd.Timestamp('2024-03-01', tz='UTC') not in df.index

    # Today is dropped
    today_utc = pd.Timestamp.now(tz='UTC').normalize()
    dates_with_today = pd.date_range(today_utc - pd.Timedelta(days=60), today_utc + pd.Timedelta(days=5), freq='D')
    raw_with_today = pd.DataFrame({
        'Adj Close': 100.0,
        'Close': 100.0,
        'High': 105.0,
        'Low': 95.0,
        'Open': 100.0,
        'Volume': 1000,
    }, index=dates_with_today)
    with patch('yfinance.download', return_value=raw_with_today):
        df_today, _ = load_stocks('TEST_TODAY', (today_utc - pd.Timedelta(days=60)).strftime('%Y-%m-%d'),
                                  (today_utc + pd.Timedelta(days=5)).strftime('%Y-%m-%d'), cache=str(tmp_path))
    assert (df_today.index < today_utc).all()

    # Raises if < 50 bars
    with pytest.raises(ValueError, match='Need at least 50 stock bars'):
        with patch('yfinance.download', return_value=raw.iloc[:30]):
            load_stocks('TEST_SHORT', '2024-01-01', '2024-01-20', cache=str(tmp_path))


def test_engine_exit_fee_asymmetry():
    # Asymmetric fees: entry fee 0.001 (0.1%), exit fee 0.005 (0.5%)
    fee = 0.001
    exit_fee = 0.005
    slippage = 0.0005
    capital = 10000.0
    cfg = Config(capital=capital, leverage=1.0, risk=0.01, fee=fee, exit_fee=exit_fee,
                 slippage=slippage, maintenance=0.0)

    dates = pd.date_range('2024-01-01', periods=5, freq='D', tz='UTC')
    df = pd.DataFrame({
        'open': [100.0, 100.0, 110.0, 110.0, 110.0],
        'high': [102.0, 102.0, 112.0, 112.0, 112.0],
        'low': [98.0, 98.0, 108.0, 108.0, 108.0],
        'close': [101.0, 101.0, 111.0, 111.0, 111.0],
        'volume': [1000, 1000, 1000, 1000, 1000],
    }, index=dates)

    # Signal: enter long on bar 0 (executes at bar 1 open), exit long on bar 1 (executes at bar 2 open)
    # Stop distance = 10.0, risk = 0.01 -> risk capital = 100. Qty = 100 / 10 = 10.0
    signals = pd.DataFrame({
        'direction': [1, 0, 0, 0, 0],
        'stop_distance': [10.0, 10.0, 10.0, 10.0, 10.0],
        'exit_long': [False, True, False, False, False],
        'exit_short': [False, False, False, False, False],
    }, index=dates)

    result = run(df, signals, config=cfg)
    assert len(result.trades) == 1
    t = result.trades[0]

    # Hand calculations:
    entry_price_raw = 100.0
    entry_fill = entry_price_raw * (1 + slippage)  # 100.05
    qty = 10.0
    entry_fee_cost = qty * entry_fill * fee  # 10 * 100.05 * 0.001 = 1.0005
    margin = qty * entry_fill  # 1000.5

    exit_price_raw = 110.0
    exit_fill = exit_price_raw * (1 - slippage)  # 110 * 0.9995 = 109.945
    exit_fee_cost = qty * exit_fill * exit_fee  # 10 * 109.945 * 0.005 = 5.49725

    unrealized_pnl = qty * (exit_fill - entry_fill)  # 10 * (109.945 - 100.05) = 98.95
    proceeds = margin + unrealized_pnl - exit_fee_cost  # 1000.5 + 98.95 - 5.49725 = 1093.95275
    expected_pnl = proceeds - margin - entry_fee_cost  # 98.95 - 5.49725 - 1.0005 = 92.45225

    assert t['entry'] == pytest.approx(entry_fill)
    assert t['exit'] == pytest.approx(exit_price_raw)
    assert t['pnl'] == pytest.approx(expected_pnl)
    # Verify that if fee had been used for exit, PnL would differ
    symmetric_exit_fee_cost = qty * exit_fill * fee  # 1.09945
    symmetric_pnl = unrealized_pnl - symmetric_exit_fee_cost - entry_fee_cost  # 96.85005
    assert abs(t['pnl'] - symmetric_pnl) > 4.0  # Asymmetry clearly detected!


def test_cn_long_only_masking_closes_long_and_prevents_short():
    dates = pd.date_range('2024-01-01', periods=6, freq='D', tz='UTC')
    df = pd.DataFrame({
        'open': [100.0, 100.0, 105.0, 102.0, 95.0, 95.0],
        'high': [102.0, 106.0, 107.0, 103.0, 96.0, 96.0],
        'low': [99.0, 99.0, 102.0, 98.0, 94.0, 94.0],
        'close': [101.0, 105.0, 103.0, 99.0, 95.0, 95.0],
        'volume': [1000, 1000, 1000, 1000, 1000, 1000],
    }, index=dates)

    # Strategy signals: like supertrend, exit_long is always False, short signal fires on bar 2
    raw_signals = pd.DataFrame({
        'direction': [1, 0, -1, -1, 0, 0],
        'stop_distance': [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
        'exit_long': [False, False, False, False, False, False],
        'exit_short': [False, False, False, False, False, False],
    }, index=dates)

    cfg = Config(capital=100000, leverage=1.0, maintenance=0.0, fee=0.0003, exit_fee=0.0008, slippage=0.0005)

    # Without fix (just direction < 0 to 0): open long would NOT close on bar 3
    bad_signals = raw_signals.copy()
    bad_signals.loc[bad_signals.direction < 0, 'direction'] = 0
    bad_res = run(df, bad_signals, config=cfg)
    # With bad masking, the position survives past bar 3 until end of data
    assert len(bad_res.trades) == 1
    assert bad_res.trades[0]['reason'] == 'end'

    # With proper CN masking:
    cn_signals = raw_signals.copy()
    short_mask = cn_signals.direction < 0
    cn_signals.loc[short_mask, 'exit_long'] = True
    cn_signals.loc[short_mask, 'direction'] = 0

    cn_res = run(df, cn_signals, config=cfg)
    assert len(cn_res.trades) == 1
    t = cn_res.trades[0]
    # Trade entered at bar 1 open, exited at bar 3 open due to 'signal/time'
    assert t['side'] == 1
    assert t['entry_time'] == dates[1]
    assert t['exit_time'] == dates[3]
    assert t['reason'] == 'signal/time'
    # No short position opened!
    assert all(tr['side'] == 1 for tr in cn_res.trades)


def test_compare_stocks_smoke(tmp_path):
    # Verify compare-stocks logic on a synthetic 60-bar stock series
    raw = make_synthetic_yf_df(n_bars=60)
    with patch('yfinance.download', return_value=raw):
        df, _ = load_stocks('SPY_TEST', '2024-01-01', '2024-04-01', cache=str(tmp_path))

    cfg = Config(capital=10000, leverage=1, maintenance=0, fee=0.0005, slippage=0.0005)
    names = ['rsi_atr_trend_4h', 'keltner_breakout', 'supertrend_4h', 'buy_and_hold']
    results = {}
    for name in names:
        signals = output(df, 1, float('nan')) if name == 'buy_and_hold' else get_strategy(name)(df)
        res = run(df, signals, config=cfg, buy_hold=(name == 'buy_and_hold'))
        results[name] = res.metrics

    summary = pd.DataFrame(results).T
    assert summary.shape == (4, 10)
    assert list(summary.index) == names
    expected_cols = ['total_return', 'cagr', 'sharpe', 'max_drawdown', 'win_rate',
                     'profit_factor', 'trade_count', 'average_holding_days', 'total_funding', 'liquidations']
    assert list(summary.columns) == expected_cols

    # Buy and hold sanity
    bh = results['buy_and_hold']
    assert bh['total_funding'] == 0.0
    assert bh['liquidations'] == 0.0
    assert bh['trade_count'] == 1.0


def test_long_only_mask_unit_behavior():
    dates = pd.date_range('2024-01-01', periods=5, freq='D', tz='UTC')
    raw_signals = pd.DataFrame({
        'direction': [1, 0, -1, 0, -1],
        'stop_distance': [5.0, 5.0, 5.0, 5.0, 5.0],
        'exit_long': [False, False, False, False, False],
        'exit_short': [False, False, False, False, False],
    }, index=dates)

    masked = long_only_mask(raw_signals)

    # Original DataFrame must not be mutated
    assert raw_signals.loc[dates[2], 'direction'] == -1
    assert bool(raw_signals.loc[dates[2], 'exit_long']) is False

    # Masked DataFrame: where direction < 0, direction becomes 0 and exit_long becomes True
    assert list(masked['direction']) == [1, 0, 0, 0, 0]
    assert [bool(x) for x in masked['exit_long']] == [False, False, True, False, True]
    assert [bool(x) for x in masked['exit_short']] == [False, False, False, False, False]
    assert list(masked['stop_distance']) == [5.0, 5.0, 5.0, 5.0, 5.0]


def test_long_only_mask_supertrend_execution():
    dates = pd.date_range('2024-01-01', periods=6, freq='D', tz='UTC')
    df = pd.DataFrame({
        'open': [100.0, 100.0, 105.0, 102.0, 95.0, 95.0],
        'high': [102.0, 106.0, 107.0, 103.0, 96.0, 96.0],
        'low': [99.0, 99.0, 102.0, 98.0, 94.0, 94.0],
        'close': [101.0, 105.0, 103.0, 99.0, 95.0, 95.0],
        'volume': [1000, 1000, 1000, 1000, 1000, 1000],
    }, index=dates)

    # Supertrend-like signals: exit_long is always False; direction flips to short on bar 2
    raw_signals = pd.DataFrame({
        'direction': [1, 0, -1, -1, 0, 0],
        'stop_distance': [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
        'exit_long': [False, False, False, False, False, False],
        'exit_short': [False, False, False, False, False, False],
    }, index=dates)

    masked_signals = long_only_mask(raw_signals)
    cfg = Config(capital=10000, leverage=1.0, maintenance=0.0, fee=0.0005, slippage=0.0005)
    res = run(df, masked_signals, config=cfg)

    # Open long at bar 1 must close at bar 3 open due to exit_long=True from masked short flip
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t['side'] == 1
    assert t['entry_time'] == dates[1]
    assert t['exit_time'] == dates[3]
    assert t['reason'] == 'signal/time'
    # Masked signals must never open a short
    assert all(tr['side'] == 1 for tr in res.trades)


def test_compare_stocks_cli_variants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_df = pd.DataFrame({
        'open': [100.0 + i for i in range(60)],
        'high': [102.0 + i for i in range(60)],
        'low': [98.0 + i for i in range(60)],
        'close': [101.0 + i for i in range(60)],
        'volume': [1000 for _ in range(60)],
    }, index=pd.date_range('2024-01-01', periods=60, freq='D', tz='UTC'))

    variants_dict = {
        'keltner_v1': {'strategy': 'keltner_breakout', 'params': {'ema_period': 10}},
        'supertrend_v1': {'strategy': 'supertrend_4h', 'params': {'period': 7}},
    }
    variants_json = json.dumps(variants_dict)

    cli_args = [
        'backtest', 'compare-stocks',
        '--market', 'us',
        '--symbols', 'TEST',
        '--start', '2024-01-01',
        '--end', '2024-04-01',
        '--variants', variants_json,
    ]

    with patch('backtest.__main__.load_stocks', return_value=(fake_df.copy(), pd.DataFrame(columns=['rate']))):
        with patch.object(sys, 'argv', cli_args):
            main()

    results_dir = tmp_path / 'results'
    assert results_dir.exists()

    summary_file = results_dir / 'TEST_daily_2024-01-01_2024-04-01_summary.csv'
    assert summary_file.exists()
    summary_df = pd.read_csv(summary_file, index_col=0)

    # Summary rows are the variant names plus buy_and_hold
    expected_rows = list(variants_dict.keys()) + ['buy_and_hold']
    assert list(summary_df.index) == expected_rows

    # No trades file contains a short trade
    trade_files = list(results_dir.glob('*_trades.csv'))
    assert len(trade_files) == len(expected_rows)
    for trade_csv in trade_files:
        try:
            tdf = pd.read_csv(trade_csv)
            if not tdf.empty and 'side' in tdf.columns:
                assert (tdf['side'] == 1).all(), f'Found non-long trade in {trade_csv}'
        except pd.errors.EmptyDataError:
            pass


def test_compare_stocks_cli_variants_unknown_strategy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_df = pd.DataFrame({
        'open': [100.0 + i for i in range(60)],
        'high': [102.0 + i for i in range(60)],
        'low': [98.0 + i for i in range(60)],
        'close': [101.0 + i for i in range(60)],
        'volume': [1000 for _ in range(60)],
    }, index=pd.date_range('2024-01-01', periods=60, freq='D', tz='UTC'))

    bad_variants = json.dumps({'bad_strat': {'strategy': 'unknown_strategy_name'}})
    cli_args = [
        'backtest', 'compare-stocks',
        '--market', 'us',
        '--symbols', 'TEST',
        '--start', '2024-01-01',
        '--end', '2024-04-01',
        '--variants', bad_variants,
    ]

    with patch('backtest.__main__.load_stocks', return_value=(fake_df.copy(), pd.DataFrame(columns=['rate']))):
        with patch.object(sys, 'argv', cli_args):
            with pytest.raises(ValueError, match='Unknown strategy'):
                main()

