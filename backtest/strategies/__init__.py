from importlib import import_module

NAMES = ['turtle_donchian_4h', 'supertrend_4h', 'rsi_atr_trend_4h',
         'bollinger_breakout', 'keltner_breakout', 'macd_ema_trend',
         'jlaw_swing_breakout_4h', 'ema_ribbon_4h', 'adx_trend_4h',
         'ichimoku_4h', 'rsi_reversion_4h', 'bollinger_mean_reversion_4h',
         'funding_zscore_fade', 'funding_extreme_threshold', 'funding_filtered_keltner']


def get_strategy(name):
    if name not in NAMES:
        raise ValueError(f'Unknown strategy: {name}')
    return import_module(f'{__name__}.{name}').generate_signals
