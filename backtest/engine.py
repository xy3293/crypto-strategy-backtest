"""Next-open fills; isolated fixed entry margin; conservative OHLC event ordering.

Funding is signed cash flow (positive = earned), debited from isolated collateral.
Maintenance uses a configurable constant ratio, not Binance's changing tier schedule.
Mark OHLC is required in production; contract OHLC is allowed for synthetic tests.
Liquidation has priority over intrabar stop/target when both are touched; full isolated
collateral is forfeited. No cross-margin replenishment or liquidation fee is modeled.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .metrics import summarize


@dataclass
class Config:
    capital: float = 10000.
    leverage: float = 2.
    risk: float = .01
    fee: float = .0005
    slippage: float = .0005
    maintenance: float = .005

    def __post_init__(self):
        if not 1 <= self.leverage <= 5:
            raise ValueError('Leverage must be between 1 and 5')
        if self.capital <= 0 or not 0 < self.risk <= 1 or min(self.fee, self.slippage, self.maintenance) < 0:
            raise ValueError('Invalid account/cost parameters')


@dataclass
class Result:
    equity: pd.Series
    trades: list
    metrics: dict


def run(df, signals, funding=None, config=None, buy_hold=False):
    cfg = config or Config()
    if len(df) < 2 or not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError('Need at least two chronological unique bars')
    if not signals.index.equals(df.index):
        raise ValueError('Signals must align exactly with candles')
    cash, position, trades, curve = cfg.capital, None, [], [cfg.capital]
    total_funding, liquidations = 0., 0
    funding = funding if funding is not None else pd.DataFrame(columns=['rate'])
    events = list(funding.sort_index().itertuples())
    event_index = 0
    step = df.index[1]-df.index[0]

    def close(price, timestamp, reason, liquidated=False):
        nonlocal cash, position, liquidations
        p = position
        if liquidated:
            proceeds = 0.
            liquidations += 1
        else:
            fill = price*(1-p['side']*cfg.slippage)
            proceeds = max(0., p['margin']+p['funding']+p['side']*p['qty']*(fill-p['entry'])-p['qty']*fill*cfg.fee)
        cash += proceeds
        trades.append(dict(entry_time=p['time'], exit_time=timestamp, side=p['side'],
                           entry=p['entry'], exit=price, pnl=proceeds-p['margin']-p['entry_fee'],
                           funding=p['funding'], reason=reason,
                           holding_days=(timestamp-p['time']).total_seconds()/86400))
        position = None

    for i in range(1, len(df)):
        timestamp, bar = df.index[i], df.iloc[i]
        s = signals.iloc[i-1]  # The ONLY signal used for this bar comes from the preceding closed bar.
        desired = int(s.direction) if pd.notna(s.direction) else 0
        if position:
            p = position
            exit_flag = bool(s.exit_long if p['side'] == 1 else s.exit_short)
            expired = (timestamp-p['time']).total_seconds()/86400 >= p['max_days']
            if not buy_hold and (exit_flag or desired == -p['side'] or expired):
                close(bar.open, timestamp, 'signal/time')
        if position is None and cash > 0 and (desired or buy_hold):
            distance = float(s.stop_distance)
            if (np.isfinite(distance) and distance > 0) or buy_hold:
                side = 1 if buy_hold else desired
                fill = bar.open*(1+side*cfg.slippage)
                qty = cash*cfg.risk/distance if not buy_hold else cash/(fill*(1+cfg.fee))
                leverage = 1. if buy_hold else cfg.leverage
                qty = min(qty, cash/(fill*(1/leverage+cfg.fee)))
                margin, fee = qty*fill/leverage, qty*fill*cfg.fee
                cash -= margin+fee
                position = dict(side=side, qty=qty, margin=margin, entry_fee=fee, entry=fill,
                                time=timestamp, funding=0., stop=fill-side*distance,
                                distance=distance, target=float(s.get('target_r', np.inf)),
                                max_days=float(s.get('max_days', np.inf)))
        # Funding at a bar boundary belongs to positions open after that boundary's fills.
        while event_index < len(events) and events[event_index].Index < timestamp+step:
            event = events[event_index]
            if position and event.Index >= timestamp:
                mark = getattr(event, 'mark', np.nan)
                mark = mark if np.isfinite(mark) else bar.get('mark_open', bar.open)
                payment = -position['side']*position['qty']*mark*event.rate
                position['funding'] += payment
                total_funding += payment
            event_index += 1
        if position:
            p = position
            # Worst mark in the bar. Collateral + unrealized PnL <= maintenance notional.
            adverse = bar.get('mark_low', bar.low) if p['side'] == 1 else bar.get('mark_high', bar.high)
            collateral = p['margin']+p['funding']+p['side']*p['qty']*(adverse-p['entry'])
            if collateral <= cfg.maintenance*p['qty']*adverse:
                close(adverse, timestamp+step, 'liquidation', True)
            elif not buy_hold:
                stop_hit = bar.low <= p['stop'] if p['side'] == 1 else bar.high >= p['stop']
                target = p['entry']+p['side']*p['distance']*p['target']
                target_hit = bar.high >= target if p['side'] == 1 else bar.low <= target
                if stop_hit:
                    price = min(bar.open, p['stop']) if p['side'] == 1 else max(bar.open, p['stop'])
                    close(price, timestamp+step, 'stop')
                elif target_hit:
                    close(target, timestamp+step, 'target')
                elif bool(s.get('trailing', False)):
                    # Updated at close, effective on following bar only.
                    p['stop'] = max(p['stop'], bar.close-float(s.stop_distance)) if p['side'] == 1 else min(p['stop'], bar.close+float(s.stop_distance))
        if i == len(df)-1 and position:
            close(bar.close, timestamp+step, 'end')
        value = cash
        if position:
            p = position
            value += max(0., p['margin']+p['funding']+p['side']*p['qty']*(bar.get('mark_close', bar.close)-p['entry']))
        curve.append(value)
    # First point is initial capital at the first tradable open; all later points are closes.
    index = pd.DatetimeIndex([df.index[1]] + [t+step for t in df.index[1:]])
    equity = pd.Series(curve, index=index, name='equity')
    return Result(equity, trades, summarize(equity, trades, total_funding, liquidations))
