from .common import atr, output


def generate_signals(df, z_entry=2.5, z_exit=0.5, atr_period=14, stop_atr=2.0, max_days=14):
    funding = df['funding_rate']
    window = funding.rolling(180, min_periods=90)
    z = (funding-window.mean())/window.std(ddof=0)
    direction = (z < -z_entry).astype(int)-(z > z_entry).astype(int)
    return output(df, direction, atr(df, atr_period)*stop_atr,
                  z > -z_exit, z < z_exit, max_days=max_days)
