"""Portfolio backtester — freshly implemented, worst-case-honest.

Strategy-agnostic: it takes a stream of TARGET POSITIONS (signed, risk-scaled, per
instrument, over time) and the instruments' returns, and simulates the daily portfolio
return. A single sleeve, a blend, or the full risk-managed stack all present the same
positions interface, so the SAME engine validates all of them.

Honesty rules baked in:
  • strict no-lookahead — a position formed from data through t-1 earns day t's return
    (positions are shifted forward by `lag`);
  • rebalance cadence — positions update every `rebal_days` and are held in between,
    matching how the book actually trades (so turnover/cost are realistic, not per-day);
  • linear turnover cost — bps of the traded change, charged when the book moves.

Output is a daily portfolio-return Series at the book's natural gross. Sharpe (from
metrics) is scale-free; callers scale the series to a target vol only for interpretable
return/drawdown reporting.
"""

import numpy as np


def simulate(positions, rets, rebal_days=21, cost_bps=2.0, lag=1):
    """positions, rets: aligned DataFrames (index=dates, cols=instruments).
    Returns a daily portfolio-return Series."""
    positions, rets = positions.align(rets, join="inner")

    held = positions.copy()
    if rebal_days and rebal_days > 1:
        keep = (np.arange(len(held)) % rebal_days) == 0
        held.loc[~keep] = np.nan          # blank non-rebalance rows...
        held = held.ffill()               # ...hold the last rebalance position
    held = held.clip(-4, 4)               # per-instrument leverage sanity bound

    turnover = held.diff().abs().fillna(0.0)
    cost = turnover * (cost_bps / 1e4)

    per_instrument = held.shift(lag) * rets - cost   # shift => strictly no lookahead
    return per_instrument.sum(axis=1, min_count=1)
