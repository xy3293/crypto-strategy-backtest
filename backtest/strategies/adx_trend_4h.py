from .common import atr, output


def generate_signals(df, **params):
    up = df.high.diff()
    down = -df.low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.)
    minus_dm = down.where((down > up) & (down > 0), 0.)
    tr = atr(df, 14)
    plus_di = 100*plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean()/tr
    minus_di = 100*minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean()/tr
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di)
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    long = (adx > 25) & (plus_di > minus_di)
    short = (adx > 25) & (minus_di > plus_di)
    return output(df, long.astype(int)-short.astype(int), 2*tr,
                  (adx < 20) | (plus_di < minus_di),
                  (adx < 20) | (minus_di < plus_di), max_days=14)
