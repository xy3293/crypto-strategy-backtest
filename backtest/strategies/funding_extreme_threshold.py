from .common import atr, output


def generate_signals(df, high=0.0005, low=-0.0005, atr_period=14, stop_atr=2.0, max_days=14):
    funding = df['funding_rate']
    direction = (funding < low).astype(int)-(funding > high).astype(int)
    return output(df, direction, atr(df, atr_period)*stop_atr,
                  funding > 0, funding < 0, max_days=max_days)
