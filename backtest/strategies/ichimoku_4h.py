from .common import atr, output


def generate_signals(df, **params):
    tenkan = (df.high.rolling(9).max()+df.low.rolling(9).min())/2
    kijun = (df.high.rolling(26).max()+df.low.rolling(26).min())/2
    senkou_a = ((tenkan+kijun)/2).shift(26)
    senkou_b = ((df.high.rolling(52).max()+df.low.rolling(52).min())/2).shift(26)
    top = senkou_a.where(senkou_a >= senkou_b, senkou_b)
    bottom = senkou_a.where(senkou_a <= senkou_b, senkou_b)
    long = (df.close > top) & (tenkan > kijun)
    short = (df.close < bottom) & (tenkan < kijun)
    in_cloud = (df.close >= bottom) & (df.close <= top)
    cross_down = (tenkan < kijun) & (tenkan.shift() >= kijun.shift())
    cross_up = (tenkan > kijun) & (tenkan.shift() <= kijun.shift())
    return output(df, long.astype(int)-short.astype(int), 2*atr(df, 14),
                  cross_down | in_cloud, cross_up | in_cloud, max_days=14)
