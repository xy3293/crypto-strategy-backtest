from .common import atr, output


def generate_signals(df, ema_period=35, atr_period=17, multiplier=2., stop_atr=2.):
    mid = df.close.ewm(span=ema_period, adjust=False, min_periods=ema_period).mean()
    a = atr(df, atr_period)
    return output(df, (df.close > mid+multiplier*a).astype(int)-(df.close < mid-multiplier*a).astype(int),
                  a*stop_atr, df.close < mid, df.close > mid)
