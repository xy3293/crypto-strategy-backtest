from .common import atr, output


def generate_signals(df, **params):
    delta = df.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rsi = 100-100/(1+gain/loss)
    long = rsi < 30
    short = rsi > 70
    return output(df, long.astype(int)-short.astype(int), 2*atr(df, 14),
                  rsi > 50, rsi < 50, max_days=14)
