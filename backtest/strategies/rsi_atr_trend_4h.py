from .common import atr, output


def generate_signals(df, period=14, upper=70, lower=30, fast=100, slow=200, stop_atr=1.5):
    delta = df.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rsi = 100-100/(1+gain/loss)
    bullish = df.close.rolling(fast).mean() > df.close.rolling(slow).mean()
    bearish = df.close.rolling(fast).mean() < df.close.rolling(slow).mean()
    long = (rsi > upper) & (rsi.shift() <= upper) & bullish
    short = (rsi < lower) & (rsi.shift() >= lower) & bearish
    return output(df, long.astype(int)-short.astype(int), atr(df, period)*stop_atr,
                  bearish, bullish)
