"""Cross-sectional momentum sleeve — freshly derived, with crash control baked in.

Ranks the equity-INDEX bloc against each other: long the strongest, short the weakest,
dollar-neutral. Being market-neutral, it reduces the book's NET directional exposure and
can profit when the whole index bloc sells off together (corr->1) — the robustness angle
the directional trend sleeves structurally lack.

THE DANGER (why naive cross-sectional momentum is risky for a robustness book):
"momentum crashes" (Daniel & Moskowitz 2016; Barroso & Santa-Clara 2015). Being SHORT
recent losers, it gets run over when a beaten-down market rebounds — the momentum factor
fell ~73% in 3 months in 2009. Unmitigated, that would defeat the whole point of v2.

Mitigations applied (from the literature):
  • "skip a month" 12-1 momentum (t-252 -> t-21) — avoids 1-month reversal contamination.
  • dollar-neutral cross-sectional z-scores — no net market bet.
  • CONSTANT-VOLATILITY SCALING (Barroso-Santa-Clara): scale the whole long-short book by
    its own trailing realized vol to a target, cutting exposure precisely when momentum
    vol spikes (the crash regime). This "virtually eliminated" the historical crashes.

Cross-sectional momentum in country/index universes is well documented (Asness-Moskowitz-
Pedersen, "Value and Momentum Everywhere") on ~18 markets, and is if anything stronger in
smaller universes — our 11 indices are a reasonable cross-sectional set.
"""

import numpy as np
import pandas as pd

from vertex.sleeves.base import Sleeve, register

TRADING_DAYS = 252


@register("xsect")
class XSectMomentum(Sleeve):
    def __init__(self, include=None, lookback=252, skip=21, vol_win=126, target_vol=0.12, max_leverage=2.0):
        self.include = list(include) if include else None
        self.lookback = lookback
        self.skip = skip
        self.vol_win = vol_win
        self.target_vol = target_vol
        self.max_leverage = max_leverage

    def raw_positions(self, close):
        cols = [c for c in (self.include or list(close.columns)) if c in close.columns]
        out = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        if len(cols) < 3:                      # cross-section needs a few names to rank
            return out
        sub = close[cols]
        rets = sub.pct_change()

        # 12-1 "skip a month" momentum, then cross-sectional demean + z-score (dollar-neutral)
        mom = sub.shift(self.skip) / sub.shift(self.lookback) - 1.0
        xstd = mom.std(axis=1).replace(0.0, np.nan)
        score = mom.sub(mom.mean(axis=1), axis=0).div(xstd, axis=0)

        # constant-vol scaling of the long-short book (Barroso-Santa-Clara crash control)
        ls_ret = (score.shift(1) * rets).sum(axis=1, min_count=1)
        ls_vol = ls_ret.rolling(self.vol_win).std() * np.sqrt(TRADING_DAYS)
        scale = (self.target_vol / ls_vol).replace([np.inf, -np.inf], np.nan).clip(upper=self.max_leverage)

        out[cols] = score.mul(scale, axis=0).fillna(0.0)
        return out
