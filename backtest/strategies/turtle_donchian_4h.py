from .common import atr, output


def generate_signals(df, entry=20, exit=10, atr_period=20, stop_atr=2., ema_filter=False):
    """Prior-bar Donchian channels; optional EMA200 direction filter."""
    long = df.close > df.high.shift().rolling(entry).max()
    short = df.close < df.low.shift().rolling(entry).min()
    if ema_filter:
        ema = df.close.ewm(span=200, adjust=False, min_periods=200).mean()
        long &= df.close > ema
        short &= df.close < ema
    return output(df, long.astype(int)-short.astype(int), atr(df, atr_period)*stop_atr,
                  df.close < df.low.shift().rolling(exit).min(),
                  df.close > df.high.shift().rolling(exit).max())
