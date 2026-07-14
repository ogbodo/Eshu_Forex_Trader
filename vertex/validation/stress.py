"""Correlation-breakdown stress test.

In a crisis, correlations go to 1 and diversification vanishes exactly when you need it
(2008, 2022). This asks: for the ACTUAL risk-managed positions the book holds, what would
a single day's loss be if every instrument moved adversely AND in lockstep (corr = 1)?
If that worst-case day is within the kill-switch tolerance, the sizing is not secretly
relying on diversification that disappears under stress.
"""


def corr1_worst_day(positions, rets, vol_win=60, z=3.0):
    """Series of hypothetical 1-day losses under corr=1, all-adverse, at each day's held
    positions: sum_i |position_i| * (z * daily_vol_i). Returned as positive loss fractions."""
    daily_vol = rets.rolling(vol_win).std()
    return (positions.abs() * (z * daily_vol)).sum(axis=1, min_count=1).dropna()
