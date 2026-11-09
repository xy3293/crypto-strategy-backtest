from . import keltner_breakout


def generate_signals(df, ema_period=35, atr_period=17, multiplier=2.0, stop_atr=2.0,
                     long_max_funding=0.0001, short_min_funding=-0.0001):
    signals = keltner_breakout.generate_signals(df, ema_period, atr_period, multiplier, stop_atr)
    allowed = ((signals.direction == 1) & (df['funding_rate'] <= long_max_funding)
               | (signals.direction == -1) & (df['funding_rate'] >= short_min_funding))
    signals['direction'] = signals.direction.where(allowed, 0)
    return signals
