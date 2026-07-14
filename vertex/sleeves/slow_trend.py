"""Trend sleeve (slow / medium horizon) — freshly derived from the trend-following
literature. NOT ported from v1; implemented independently from primary sources:

  • Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum" — the core anomaly:
    a market's own past return predicts its next return across asset classes.
  • Hurst, Ooi & Pedersen / AQR, "A Century of Evidence on Trend-Following Investing"
    — ensemble across multiple horizons is more robust than any single lookback.
  • Barroso & Santa-Clara (2015), "Momentum Has Its Moments" — scale each position by
    forecast volatility (risk-managed momentum), which "virtually eliminates" crashes.
  • Baz et al. (2015) / Lim, Zohren & Roberts (2019) — use a CONTINUOUS, volatility-
    normalized trend signal (conviction-weighted), squashed to bound outliers, instead
    of a raw sign.

Design (pre-registered from the literature — NOT parameter-fitted to our data):
    signal_L  = tanh( momentum_L / vol_of_an_L-day-move )     # risk-adjusted, bounded ±1
    ensemble  = mean of signal_L over lookbacks (63/126/252d) # multi-horizon robustness
    position  = ensemble * (target_vol / ex-ante annual vol)  # equal-risk + risk-managed
    (clipped to ±4 per instrument as a leverage sanity bound)

Why the tanh(return/vol) signal rather than sign(return): it down-weights weak,
low-conviction trends and saturates on extreme ones, which is what reduces the whipsaw
that hurts naive trend models — but whether it actually beats a plain sign is a question
for the validation module (OOS / deflated Sharpe), not an assertion made here.
"""

import numpy as np

from vertex.sleeves.base import Sleeve, register

TRADING_DAYS = 252


@register("slow_trend")
class SlowTrend(Sleeve):
    def __init__(self, lookbacks=(63, 126, 252), vol_win=60, target_vol=0.15, signal="tanh"):
        self.lookbacks = tuple(lookbacks)
        self.vol_win = vol_win
        self.target_vol = target_vol
        self.signal = signal              # "tanh" (risk-adjusted, our default) or "sign" (plain, v1-style)

    def raw_positions(self, close):
        rets = close.pct_change()
        daily_vol = rets.rolling(self.vol_win).std()
        ann_vol = (daily_vol * np.sqrt(TRADING_DAYS)).replace(0.0, np.nan)

        # ensemble of risk-adjusted, volatility-normalized trend signals (each bounded ±1)
        sig = None
        for L in self.lookbacks:
            momentum = close / close.shift(L) - 1.0
            move_vol = (daily_vol * np.sqrt(L)).replace(0.0, np.nan)   # vol of an L-day return
            s = np.sign(momentum) if self.signal == "sign" else np.tanh(momentum / move_vol)
            sig = s if sig is None else sig + s
        sig = sig / len(self.lookbacks)

        # risk-managed sizing: scale to a constant ex-ante vol so every market = equal risk
        pos = (sig * (self.target_vol / ann_vol)).replace([np.inf, -np.inf], np.nan).clip(-4, 4)
        return pos
