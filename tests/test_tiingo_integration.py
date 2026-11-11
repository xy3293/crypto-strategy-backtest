from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from backtest import data, tiingo


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch, tmp_path):
    monkeypatch.setenv('TIINGO_API_KEY', 'TEST_TOKEN')
    monkeypatch.setattr(tiingo.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(data, 'fetch_tiingo_eod', Mock(side_effect=AssertionError('Unexpected Tiingo call')))
    monkeypatch.setattr(data.yf, 'download', Mock(side_effect=AssertionError('Unexpected yfinance call')))
    monkeypatch.setattr(tiingo.requests, 'get', Mock(side_effect=AssertionError('Network forbidden')))


@pytest.fixture
def bars():
    return pd.DataFrame(
        {'open': 45.0, 'high': 55.0, 'low': 40.0, 'close': 50.0, 'volume': 1000},
        index=pd.date_range('2024-01-01', periods=60, tz='UTC', name='timestamp'),
    )


@pytest.fixture
def yahoo(monkeypatch, bars):
    raw = bars.rename(columns={col: col.title() for col in bars.columns})
    raw['Adj Close'] = raw['Close']
    download = Mock(return_value=raw)
    monkeypatch.setattr(data.yf, 'download', download)
    return download


def test_tiingo_has_priority_and_writes_shared_cache(tmp_path, bars):
    data.fetch_tiingo_eod.side_effect = None
    data.fetch_tiingo_eod.return_value = bars

    df, funding = data.load_stocks('AAPL', '2024-01-01', '2024-03-01', cache=tmp_path)

    pd.testing.assert_frame_equal(df, bars, check_freq=False)
    assert funding.empty and list(funding.columns) == ['rate']
    data.fetch_tiingo_eod.assert_called_once_with('AAPL', '2024-01-01', '2024-03-01', 'TEST_TOKEN')
    data.yf.download.assert_not_called()
    cached = pd.read_csv(tmp_path / 'stocks/AAPL_daily_2024-01-01_2024-03-01.csv',
                         index_col=0, parse_dates=True)
    pd.testing.assert_frame_equal(cached, df, check_freq=False)


@pytest.mark.parametrize('failure', [requests.ConnectionError('network'),
                                    requests.HTTPError('429'), ValueError('empty'),
                                    RuntimeError('provider failure'), pd.DataFrame()])
def test_tiingo_failure_falls_back(tmp_path, bars, yahoo, failure):
    if isinstance(failure, Exception):
        data.fetch_tiingo_eod.side_effect = failure
    else:
        data.fetch_tiingo_eod.side_effect = None
        data.fetch_tiingo_eod.return_value = failure

    df, _ = data.load_stocks('AAPL', '2024-01-01', '2024-03-01', cache=tmp_path)

    pd.testing.assert_frame_equal(df, bars, check_freq=False)
    data.fetch_tiingo_eod.assert_called_once()
    yahoo.assert_called_once_with('AAPL', start='2024-01-01', end='2024-03-01',
                                  progress=False, auto_adjust=False)


def test_no_key_uses_yfinance(monkeypatch, tmp_path, bars, yahoo):
    monkeypatch.delenv('TIINGO_API_KEY')

    df, _ = data.load_stocks('AAPL', '2024-01-01', '2024-03-01', cache=tmp_path)

    pd.testing.assert_frame_equal(df, bars, check_freq=False)
    data.fetch_tiingo_eod.assert_not_called()
    yahoo.assert_called_once()


@pytest.mark.parametrize('source', ['auto', 'yfinance'])
def test_cache_hit_skips_credentials_and_providers(monkeypatch, tmp_path, bars, source):
    root = tmp_path / 'stocks'
    root.mkdir()
    bars.to_csv(root / '510300_SH_daily_2024-01-01_2024-03-01.csv')
    key = Mock(side_effect=AssertionError('Credentials read on cache hit'))
    monkeypatch.setattr(data, 'get_api_key', key)

    df, _ = data.load_stocks('510300.SH', '2024-01-01', '2024-03-01',
                             cache=tmp_path, source=source)

    pd.testing.assert_frame_equal(df, bars, check_freq=False)
    key.assert_not_called()
    data.fetch_tiingo_eod.assert_not_called()
    data.yf.download.assert_not_called()


def test_explicit_yfinance_skips_tiingo_with_key(monkeypatch, tmp_path, bars, yahoo):
    key = Mock(side_effect=AssertionError('Credentials read for yfinance'))
    monkeypatch.setattr(data, 'get_api_key', key)

    df, _ = data.load_stocks('AAPL', '2024-01-01', '2024-03-01',
                             cache=tmp_path, source='yfinance')

    pd.testing.assert_frame_equal(df, bars, check_freq=False)
    key.assert_not_called()
    data.fetch_tiingo_eod.assert_not_called()
    yahoo.assert_called_once()


def test_key_sources(monkeypatch, tmp_path):
    monkeypatch.delenv('TIINGO_API_KEY')
    assert tiingo.get_api_key() is None
    token_file = tmp_path / '.tiingo_token'
    token_file.write_text(' TEST_TOKEN \nignored\n')
    assert tiingo.get_api_key() == 'TEST_TOKEN'
    token_file.write_text('\n')
    monkeypatch.setenv('TIINGO_API_KEY', ' TEST_TOKEN ')
    assert tiingo.get_api_key() == 'TEST_TOKEN'


def test_ported_adjustment_and_date_filtering(monkeypatch):
    row = {'open': 90, 'high': 110, 'low': 80, 'close': 100,
           'adjClose': 50, 'volume': 1000, 'adjVolume': 2000}
    response = Mock()
    response.json.return_value = [dict(row, date=f'2024-01-{day:02d}T00:00:00Z')
                                  for day in (5, 3, 4, 4)]
    request = Mock(return_value=response)
    monkeypatch.setattr(tiingo.requests, 'get', request)

    df = tiingo.fetch_tiingo_eod('AAPL', '2024-01-04', '2024-01-05', 'TEST_TOKEN')

    assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
    assert df.iloc[0].tolist() == [45, 55, 40, 50, 1000]
    assert df.index.equals(pd.DatetimeIndex(['2024-01-04'], tz='UTC', name='timestamp'))
    request.assert_called_once_with(
        'https://api.tiingo.com/tiingo/daily/AAPL/prices',
        params={'startDate': '2024-01-04', 'endDate': '2024-01-05', 'token': 'TEST_TOKEN'},
        timeout=30,
    )
