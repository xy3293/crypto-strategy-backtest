import numpy as np
from .common import atr, output


def generate_signals(df, period=10, multiplier=3.):
    """Wilder ATR Supertrend; always directional after warmup, reentry after stops."""
    a = atr(df, period)
    upper = ((df.high+df.low)/2+multiplier*a).to_numpy().copy()
    lower = ((df.high+df.low)/2-multiplier*a).to_numpy().copy()
    c = df.close.to_numpy()
    direction = np.zeros(len(df), dtype=int)
    for i in range(1, len(df)):
        if not np.isfinite(a.iloc[i]):
            continue
        if not np.isfinite(upper[i-1]):
            direction[i] = 1
            continue
        upper[i] = upper[i] if upper[i] < upper[i-1] or c[i-1] > upper[i-1] else upper[i-1]
        lower[i] = lower[i] if lower[i] > lower[i-1] or c[i-1] < lower[i-1] else lower[i-1]
        previous = direction[i-1] or 1
        direction[i] = (1 if c[i] > upper[i] else -1) if previous == -1 else (-1 if c[i] < lower[i] else 1)
    # An ATR emergency stop is required for uniform risk sizing. Flips otherwise govern exits.
    return output(df, direction, a*multiplier)
