from .common import atr, output


def generate_signals(df, ema_period=20, fast=12, slow=26, signal=9, atr_period=14, stop_atr=2., target_r=3., max_days=14):
    ema = df.close.ewm(span=ema_period, adjust=False, min_periods=ema_period).mean()
    macd = df.close.ewm(span=fast, adjust=False).mean()-df.close.ewm(span=slow, adjust=False).mean()
    hist = macd-macd.ewm(span=signal, adjust=False).mean()
    long, short = (df.close > ema) & (hist > 0), (df.close < ema) & (hist < 0)
    return output(df, long.astype(int)-short.astype(int), atr(df, atr_period)*stop_atr,
                  short, long, target_r=target_r, max_days=max_days, trailing=True)
