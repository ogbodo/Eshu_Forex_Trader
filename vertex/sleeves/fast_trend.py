"""Fast-trend / breakout sleeve — freshly derived. Its purpose is NOT a great standalone
Sharpe; it is to react to SHARP, FAST moves that the slow-trend sleeve (63/126/252d) is
structurally too late to catch — the V-shocks (2020 COVID, 2018 Volmageddon) where slow
trend whipsaws. It pays for that responsiveness with more whipsaw in calm chop; its value
is DIVERSIFICATION of the slow sleeve, realised when the two are combined (Phase 2).

Derived from primary sources (implemented independently):
  • Moskowitz-Ooi-Pedersen / AQR — short-lookback time-series momentum.
  • Donchian channel breakout (the classic Turtle system, ~20-day) — lean in the
    direction of a push to recent highs/lows; this fires EARLY in sharp moves.
  • Barroso & Santa-Clara — vol-scale each position to equal ex-ante risk.

Signal (pre-registered from the literature — NOT fitted):
  momentum = mean over fast lookbacks (10/20/40d) of tanh(return_L / vol-of-an-L-day-move)
  breakout = position within the 20-day Donchian channel, mapped to [-1, +1]
  signal   = 0.5*momentum + 0.5*breakout
  position = signal * (target_vol / ex-ante annual vol), clipped ±4
"""

import numpy as np

from vertex.sleeves.base import Sleeve, register

TRADING_DAYS = 252


@register("fast_trend")
class FastTrend(Sleeve):
    def __init__(self, lookbacks=(10, 20, 40), vol_win=20, breakout_win=20, target_vol=0.15):
        self.lookbacks = tuple(lookbacks)
        self.vol_win = vol_win
        self.breakout_win = breakout_win
        self.target_vol = target_vol

    def raw_positions(self, close):
        rets = close.pct_change()
        daily_vol = rets.rolling(self.vol_win).std()
        ann_vol = (daily_vol * np.sqrt(TRADING_DAYS)).replace(0.0, np.nan)

        # (a) fast risk-adjusted momentum ensemble (bounded ±1 per lookback)
        mom = None
        for L in self.lookbacks:
            r = close / close.shift(L) - 1.0
            move_vol = (daily_vol * np.sqrt(L)).replace(0.0, np.nan)
            s = np.tanh(r / move_vol)
            mom = s if mom is None else mom + s
        mom = mom / len(self.lookbacks)

        # (b) Donchian channel position: where price sits in its recent range (+1 = at new highs)
        hi = close.rolling(self.breakout_win).max()
        lo = close.rolling(self.breakout_win).min()
        rng = (hi - lo).replace(0.0, np.nan)
        breakout = (2.0 * (close - lo) / rng - 1.0).clip(-1, 1)

        signal = 0.5 * mom + 0.5 * breakout
        pos = (signal * (self.target_vol / ann_vol)).replace([np.inf, -np.inf], np.nan).clip(-4, 4)
        return pos
