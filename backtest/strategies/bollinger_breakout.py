from .common import atr, output


def generate_signals(df, period=20, k=2., atr_period=14, stop_atr=2.):
    mid = df.close.rolling(period).mean()
    std = df.close.rolling(period).std(ddof=0)
    return output(df, (df.close > mid+k*std).astype(int)-(df.close < mid-k*std).astype(int),
                  atr(df, atr_period)*stop_atr, df.close < mid, df.close > mid)
