from .common import atr, output


def generate_signals(df, **params):
    mid = df.close.rolling(20).mean()
    std = df.close.rolling(20).std(ddof=0)
    long = df.close < mid-2*std
    short = df.close > mid+2*std
    return output(df, long.astype(int)-short.astype(int), 2*atr(df, 14),
                  df.close >= mid, df.close <= mid, max_days=14)
