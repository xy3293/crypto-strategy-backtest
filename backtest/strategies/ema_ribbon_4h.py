from .common import atr, output


def generate_signals(df, **params):
    ema9 = df.close.ewm(span=9, adjust=False, min_periods=9).mean()
    ema21 = df.close.ewm(span=21, adjust=False, min_periods=21).mean()
    ema55 = df.close.ewm(span=55, adjust=False, min_periods=55).mean()
    long = (ema9 > ema21) & (ema21 > ema55)
    short = (ema9 < ema21) & (ema21 < ema55)
    return output(df, long.astype(int)-short.astype(int), 2*atr(df, 14),
                  ~long, ~short, max_days=14)
