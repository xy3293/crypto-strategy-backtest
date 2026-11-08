from importlib import import_module

NAMES = ['turtle_donchian_4h', 'supertrend_4h', 'rsi_atr_trend_4h',
         'bollinger_breakout', 'keltner_breakout', 'macd_ema_trend',
         'jlaw_swing_breakout_4h']


def get_strategy(name):
    if name not in NAMES:
        raise ValueError(f'Unknown strategy: {name}')
    return import_module(f'{__name__}.{name}').generate_signals
