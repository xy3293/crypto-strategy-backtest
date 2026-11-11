"""Public Binance USDT perpetual endpoints via ccxt with Binance Vision bulk fallback."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import time
import urllib.request
import zipfile
import ccxt
import pandas as pd
import yfinance as yf

from .tiingo import fetch_tiingo_eod, get_api_key


def utc(value):
    return pd.Timestamp(value, tz='UTC') if pd.Timestamp(value).tzinfo is None else pd.Timestamp(value).tz_convert('UTC')


def load_stocks(symbol, start, end, cache='data', source='auto'):
    root = Path(cache) / 'stocks'
    path = root / f'{symbol.replace(".", "_")}_daily_{start}_{end}.csv'
    cached = path.exists()
    if cached:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        df = None
        if source == 'auto':
            key = get_api_key()
            if key:
                try:
                    df = fetch_tiingo_eod(symbol, start, end, key)
                except Exception:
                    pass
        if df is None or df.empty:
            raw = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
            if raw.empty:
                raise ValueError(f'No stock bars returned for {symbol}')
            if isinstance(raw.columns, pd.MultiIndex):
                if 'Close' in raw.columns.get_level_values(0):
                    raw.columns = raw.columns.get_level_values(0)
                elif 'Close' in raw.columns.get_level_values(1):
                    raw.columns = raw.columns.get_level_values(1)
                else:
                    raw.columns = raw.columns.get_level_values(0)
            factor = raw['Adj Close'] / raw['Close']
            df = raw[['Open', 'High', 'Low', 'Close']].mul(factor, axis=0)
            df['Close'] = raw['Adj Close']
            df['Volume'] = raw['Volume']
            df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize().tz_localize('UTC')
    df.index.name = 'timestamp'
    df = df.sort_index()
    df = df[~df.index.duplicated()]
    df = df[(df.index >= utc(start)) & (df.index < utc(end)) &
            (df.index < pd.Timestamp.now(tz='UTC').normalize())]
    if len(df) < 50:
        raise ValueError(f'Need at least 50 stock bars for {symbol}')
    if not cached:
        root.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)
    return df, pd.DataFrame(columns=['rate'])


def _download_vision_file(url, local_path):
    if local_path.exists():
        try:
            with zipfile.ZipFile(local_path) as z:
                z.testzip()
            return local_path
        except Exception:
            local_path.unlink(missing_ok=True)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
            local_path.write_bytes(content)
            return local_path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == 2:
                return None
            time.sleep(1)
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1)
    return None


def _read_zip_csv(path):
    if path is None or not path.exists():
        return None
    try:
        with zipfile.ZipFile(path) as z:
            name = z.namelist()[0]
            with z.open(name) as f:
                df = pd.read_csv(f, header=None)
                if str(df.iloc[0, 0]).startswith(('open_time', 'openTime', 'calc_time', 'calcTime')):
                    df = df.iloc[1:]
                return df
    except Exception:
        return None


def _fetch_vision_klines(market, timeframe, start, end, category, vision_dir, executor):
    months = pd.date_range(start.floor('D').replace(day=1), end, freq='MS', tz='UTC')
    base = 'https://data.binance.vision/data/futures/um'
    m_tasks = []
    for m in months:
        m_str = m.strftime('%Y-%m')
        url = f'{base}/monthly/{category}/{market}/{timeframe}/{market}-{timeframe}-{m_str}.zip'
        local = vision_dir / f'monthly/{category}/{market}/{timeframe}/{market}-{timeframe}-{m_str}.zip'
        m_tasks.append((m, executor.submit(_download_vision_file, url, local)))

    dfs = []
    for m, fut in m_tasks:
        lp = fut.result()
        df = _read_zip_csv(lp)
        if df is not None:
            df = df.iloc[:, :6].copy()
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            dfs.append(df)
        else:
            month_end = m + pd.offsets.MonthEnd(1)
            days = pd.date_range(m, min(month_end, end), freq='D', tz='UTC')
            d_tasks = []
            for d in days:
                if d >= end:
                    continue
                d_str = d.strftime('%Y-%m-%d')
                url = f'{base}/daily/{category}/{market}/{timeframe}/{market}-{timeframe}-{d_str}.zip'
                local = vision_dir / f'daily/{category}/{market}/{timeframe}/{market}-{timeframe}-{d_str}.zip'
                d_tasks.append(executor.submit(_download_vision_file, url, local))
            for dfut in d_tasks:
                ddf = _read_zip_csv(dfut.result())
                if ddf is not None:
                    ddf = ddf.iloc[:, :6].copy()
                    ddf.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    dfs.append(ddf)

    if not dfs:
        return pd.DataFrame()

    comb = pd.concat(dfs, ignore_index=True)
    comb['timestamp'] = pd.to_datetime(comb['timestamp'].astype('int64'), unit='ms', utc=True)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        comb[col] = comb[col].astype(float)
    comb = comb.set_index('timestamp').sort_index()
    comb = comb[~comb.index.duplicated()]

    # Download daily files for any missing days (e.g. markPriceKlines monthly archive omissions)
    step = pd.Timedelta(timeframe)
    expected_index = pd.date_range(start, end - step, freq=step, tz='UTC')
    missing_bars = expected_index.difference(comb.index)
    if len(missing_bars):
        missing_dates = sorted(list(set(ts.strftime('%Y-%m-%d') for ts in missing_bars)))
        d_tasks = []
        for d_str in missing_dates:
            url = f'{base}/daily/{category}/{market}/{timeframe}/{market}-{timeframe}-{d_str}.zip'
            local = vision_dir / f'daily/{category}/{market}/{timeframe}/{market}-{timeframe}-{d_str}.zip'
            d_tasks.append(executor.submit(_download_vision_file, url, local))
        for dfut in d_tasks:
            ddf = _read_zip_csv(dfut.result())
            if ddf is not None:
                ddf = ddf.iloc[:, :6].copy()
                ddf.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                ddf['timestamp'] = pd.to_datetime(ddf['timestamp'].astype('int64'), unit='ms', utc=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    ddf[col] = ddf[col].astype(float)
                ddf = ddf.set_index('timestamp').sort_index()
                comb = pd.concat([comb, ddf]).sort_index()
                comb = comb[~comb.index.duplicated()]

    # If any contract klines are still missing from archives (e.g. 2026-10-28), reconstruct from trades
    missing_bars = expected_index.difference(comb.index)
    if len(missing_bars) and category == 'klines':
        missing_dates = sorted(list(set(ts.strftime('%Y-%m-%d') for ts in missing_bars)))
        t_dfs = []
        for d_str in missing_dates:
            t_url = f'{base}/daily/trades/{market}/{market}-trades-{d_str}.zip'
            t_local = vision_dir / f'daily/trades/{market}/{market}-trades-{d_str}.zip'
            tlp = _download_vision_file(t_url, t_local)
            if tlp:
                try:
                    with zipfile.ZipFile(tlp) as z:
                        tdf = pd.read_csv(z.open(z.namelist()[0]))
                    tdf['dt'] = pd.to_datetime(tdf['time'], unit='ms', utc=True)
                    tdf['bar'] = tdf['dt'].dt.floor(timeframe)
                    tbars = tdf.groupby('bar').agg(
                        open=('price', 'first'),
                        high=('price', 'max'),
                        low=('price', 'min'),
                        close=('price', 'last'),
                        volume=('qty', 'sum')
                    )
                    t_dfs.append(tbars)
                except Exception:
                    pass
        if t_dfs:
            comb = pd.concat([comb, *t_dfs]).sort_index()
            comb = comb[~comb.index.duplicated()]

    return comb[(comb.index >= start) & (comb.index + step <= end)]


def _fetch_vision_funding(market, start, end, vision_dir, executor):
    months = pd.date_range(start.floor('D').replace(day=1), end, freq='MS', tz='UTC')
    base = 'https://data.binance.vision/data/futures/um'
    tasks = []
    for m in months:
        m_str = m.strftime('%Y-%m')
        url = f'{base}/monthly/fundingRate/{market}/{market}-fundingRate-{m_str}.zip'
        local = vision_dir / f'monthly/fundingRate/{market}/{market}-fundingRate-{m_str}.zip'
        tasks.append(executor.submit(_download_vision_file, url, local))

    dfs = []
    for fut in tasks:
        df = _read_zip_csv(fut.result())
        if df is not None:
            dfs.append(df)

    if not dfs:
        raise ValueError(f'No funding history found on Binance Vision for {market}')

    funding = pd.concat(dfs, ignore_index=True)
    funding['timestamp'] = pd.to_datetime(funding[0].astype('int64'), unit='ms', utc=True).dt.floor('s')
    funding['rate'] = funding[2].astype(float)
    funding['mark'] = float('nan')
    funding = funding[['timestamp', 'rate', 'mark']].set_index('timestamp').sort_index()
    funding = funding[~funding.index.duplicated()]
    return funding[(funding.index >= start) & (funding.index < end)]


def load(symbol, timeframe, start, end, cache='data'):
    if timeframe not in ('1h', '4h'):
        raise ValueError('Timeframe must be 1h or 4h')
    start, end = utc(start), utc(end)
    if end <= start:
        raise ValueError('End must be after start (end is exclusive)')
    market = symbol.split(':')[0].replace('/', '')
    root = Path(cache)
    root.mkdir(parents=True, exist_ok=True)
    step = pd.Timedelta(timeframe)
    now = pd.Timestamp.now(tz='UTC')
    end = min(end, now.floor(timeframe))  # never include unfinished candles
    prefix = f'{market}_{timeframe}_{start.value}_{end.value}'

    kpath = root / f'{prefix}_klines.csv'
    mpath = root / f'{prefix}_mark.csv'
    fpath = root / f'{prefix}_funding.csv'

    if kpath.exists() and mpath.exists() and fpath.exists():
        df = pd.read_csv(kpath, index_col=0, parse_dates=True)
        mark = pd.read_csv(mpath, index_col=0, parse_dates=True)
        funding = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index.name = 'timestamp'
        mark.index.name = 'timestamp'
        funding.index.name = 'timestamp'
        if not df.index.equals(mark.index) or not df.index.to_series().diff().dropna().eq(step).all():
            raise ValueError('Missing or misaligned contract/mark candles; refusing to bridge gaps')
        df = df.join(mark[['open', 'high', 'low', 'close']].add_prefix('mark_'))
        df['funding_rate'] = funding['rate'].reindex(df.index, method='ffill').fillna(0.0)
        return df, funding

    # Try ccxt REST API first
    use_vision = False
    exchange = ccxt.binanceusdm({'enableRateLimit': True, 'options': {'defaultType': 'future'}, 'timeout': 10000,
                                 'requests_trust_env': True, 'verify': os.environ.get('SSL_CERT_FILE', True)})

    def request(method, params):
        for attempt in range(5):
            try:
                return getattr(exchange, method)(params)
            except ccxt.ExchangeNotAvailable as exc:
                if '451' in str(exc):
                    raise
                if attempt == 4:
                    raise
                time.sleep(2**attempt)
            except (ccxt.NetworkError, ccxt.RateLimitExceeded):
                if attempt == 4:
                    raise
                time.sleep(2**attempt)

    def fetch_ccxt_candles(mark=False):
        cursor, rows = int(start.timestamp()*1000), []
        finish = int(end.timestamp()*1000)
        while cursor < finish:
            batch = request('fapiPublicGetMarkPriceKlines' if mark else 'fapiPublicGetKlines',
                            dict(symbol=market, interval=timeframe, startTime=cursor, endTime=finish-1, limit=1500))
            if not batch:
                break
            rows.extend([r[:6] for r in batch])
            cursor = int(batch[-1][0])+int(step.total_seconds()*1000)
        if not rows:
            raise ValueError(f'No candles returned for {symbol}')
        cdf = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        cdf['timestamp'] = pd.to_datetime(cdf.timestamp.astype('int64'), unit='ms', utc=True)
        cdf = cdf.set_index('timestamp').astype(float).sort_index()
        cdf = cdf[~cdf.index.duplicated()]
        return cdf[(cdf.index >= start) & (cdf.index+step <= end)]

    def fetch_ccxt_funding():
        cursor, rows = int(start.timestamp()*1000), []
        finish = int(end.timestamp()*1000)
        while cursor < finish:
            batch = request('fapiPublicGetFundingRate', dict(symbol=market, startTime=cursor, endTime=finish-1, limit=1000))
            if not batch:
                break
            rows.extend(batch)
            cursor = int(batch[-1]['fundingTime'])+1
        cfund = pd.DataFrame([dict(timestamp=pd.to_datetime(int(r['fundingTime']), unit='ms', utc=True),
                                   rate=float(r['fundingRate']), mark=float(r.get('markPrice') or 'nan')) for r in rows],
                             columns=['timestamp', 'rate', 'mark']).set_index('timestamp')
        return cfund[(cfund.index >= start) & (cfund.index < end)]

    try:
        df = fetch_ccxt_candles(mark=False)
        mark = fetch_ccxt_candles(mark=True)
        funding = fetch_ccxt_funding()
    except Exception as exc:
        print(f'Binance REST API error ({exc}); falling back to Binance Vision bulk download...')
        use_vision = True

    if use_vision:
        vision_dir = root / 'vision' / 'data' / 'futures' / 'um'
        with ThreadPoolExecutor(max_workers=10) as executor:
            df = _fetch_vision_klines(market, timeframe, start, end, 'klines', vision_dir, executor)
            mark = _fetch_vision_klines(market, timeframe, start, end, 'markPriceKlines', vision_dir, executor)
            funding = _fetch_vision_funding(market, start, end, vision_dir, executor)

        # Align mark candles to contract candles (fall back to contract OHLC if mark omitted by Vision)
        missing_mark = df.index.difference(mark.index)
        if len(missing_mark):
            mark = pd.concat([mark, df.loc[missing_mark, ['open', 'high', 'low', 'close', 'volume']]]).sort_index()
        mark = mark.reindex(df.index)

    if not df.index.equals(mark.index) or not df.index.to_series().diff().dropna().eq(step).all():
        raise ValueError('Missing or misaligned contract/mark candles; refusing to bridge gaps')
    if funding.empty:
        raise ValueError('No funding history; refusing a funding-free production backtest')

    df.index.name = 'timestamp'
    mark.index.name = 'timestamp'
    funding.index.name = 'timestamp'
    df.to_csv(kpath)
    mark.to_csv(mpath)
    funding.to_csv(fpath)

    df = df.join(mark[['open', 'high', 'low', 'close']].add_prefix('mark_'))
    df['funding_rate'] = funding['rate'].reindex(df.index, method='ffill').fillna(0.0)
    return df, funding
