from . import common


def generate_signals(df, **params):
    close = df.close
    sma100 = close.rolling(100, min_periods=100).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    # Exclude the signal bar so its close can break out of the range.
    range_high = df.high.shift(1).rolling(30, min_periods=30).max()
    range_low = df.low.shift(1).rolling(30, min_periods=30).min()
    valid = (range_high - range_low) / range_low <= 0.05
    long = (valid & (close > sma100) & (sma100 > sma200)
            & (close > range_high) & (close <= range_high * 1.04))
    short = (valid & (close < sma100) & (sma100 < sma200)
             & (close < range_low) & (close >= range_low * 0.96))
    direction = long.astype(int) - short.astype(int)
    stop_distance = (close - range_low).where(long, range_high - close).where(direction != 0, 1.)
    target_distance = (2 * stop_distance).clip(lower=0.05 * close, upper=0.15 * close)
    target_r = target_distance / stop_distance
    return common.output(df, direction, stop_distance, False, False,
                         target_r=target_r, max_days=7)
