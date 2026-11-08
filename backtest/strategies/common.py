import numpy as np
import pandas as pd


def atr(df, n=14):
    prev = df.close.shift()
    tr = pd.concat([df.high-df.low, (df.high-prev).abs(), (df.low-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()


def output(df, direction, stop, exit_long=False, exit_short=False, **kwargs):
    return pd.DataFrame(dict(direction=direction, stop_distance=stop,
                             exit_long=exit_long, exit_short=exit_short, **kwargs), index=df.index)
