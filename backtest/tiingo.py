"""Tiingo EOD prices with the existing yfinance loader as fallback."""

import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests


def get_api_key():
    key = os.environ.get('TIINGO_API_KEY', '').strip()
    if key:
        return key
    try:
        with (Path.home() / '.tiingo_token').open() as handle:
            return handle.readline().strip() or None
    except (FileNotFoundError, OSError):
        return None


def fetch_tiingo_eod(symbol, start, end, api_key):
    start, end = pd.to_datetime(start, utc=True), pd.to_datetime(end, utc=True)
    if end <= start:
        raise ValueError('End must be after start (end is exclusive)')
    try:
        response = requests.get(
            f'https://api.tiingo.com/tiingo/daily/{quote(symbol, safe="")}/prices',
            params={'startDate': start.strftime('%Y-%m-%d'),
                    'endDate': end.strftime('%Y-%m-%d'), 'token': api_key},
            timeout=30,
        )
        response.raise_for_status()
        raw = pd.DataFrame(response.json())
    except (requests.RequestException, ValueError):
        # requests errors can contain the URL, including its token query parameter.
        raise ValueError('Tiingo request failed') from None
    if raw.empty:
        raise ValueError('No Tiingo stock bars returned')
    required = {'date', 'open', 'high', 'low', 'close', 'adjClose', 'volume'}
    if not required.issubset(raw.columns):
        raise ValueError('Missing required columns in Tiingo response')
    factor = raw['adjClose'] / raw['close']
    df = raw[['open', 'high', 'low', 'close']].mul(factor, axis=0)
    df['close'] = raw['adjClose']
    df['volume'] = raw['volume']
    df.index = pd.DatetimeIndex(pd.to_datetime(raw['date'], utc=True)).normalize()
    df.index.name = 'timestamp'
    df = df.sort_index()
    df = df[~df.index.duplicated()]
    df = df[(df.index >= start) & (df.index < end) &
            (df.index < pd.Timestamp.now(tz='UTC').normalize())]
    if df.empty:
        raise ValueError('No Tiingo stock bars in requested interval')
    return df

