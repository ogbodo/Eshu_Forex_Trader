"""Crisis-window stress gates — robustness is judged by BEHAVIOUR IN KNOWN CRISES,
not just full-sample Sharpe. Windows are chosen a priori from market history (no fitting).

The research distinguishes two crisis shapes and what trend-following can do in each:
  • SUSTAINED bear (2008, 2022) — persistent downtrends → trend SHOULD profit ("crisis alpha").
  • SHARP V-shock (2020 COVID, 2018 Volmageddon) — too fast for slow trend → the goal is
    only to LIMIT the loss (this is where the fast sleeve + the de-risk switch must earn
    their keep; slow trend alone will whipsaw).

These are the pass/fail gates for v2: a sustained bear should be green, a sharp shock
should at worst be a small, controlled red.
"""

import pandas as pd

from vertex.validation import metrics

CRISES = [
    {"name": "GFC 2008",         "start": "2007-10-01", "end": "2009-03-31", "kind": "sustained",
     "expect": "trend SHOULD profit"},
    {"name": "2018 Volmageddon", "start": "2018-01-26", "end": "2018-04-10", "kind": "shock",
     "expect": "sharp shock — de-risk should LIMIT loss"},
    {"name": "2018 Q4 selloff",  "start": "2018-10-01", "end": "2018-12-31", "kind": "grind",
     "expect": "grinding selloff — trend should help"},
    {"name": "COVID crash",      "start": "2020-02-19", "end": "2020-04-30", "kind": "shock",
     "expect": "sharp V-shock — de-risk should LIMIT loss"},
    {"name": "2022 bear",        "start": "2022-01-01", "end": "2022-10-31", "kind": "sustained",
     "expect": "trend SHOULD profit"},
]


def window_stats(daily, start, end):
    seg = daily.loc[(daily.index >= pd.Timestamp(start)) & (daily.index <= pd.Timestamp(end))].dropna()
    if len(seg) < 5:
        return None
    return {"n": len(seg), "total_ret": float((1 + seg).prod() - 1),
            "maxdd": metrics.max_drawdown(seg), "sharpe": metrics.sharpe(seg)}


def report(daily):
    """List of crisis dicts with a `stats` sub-dict (None if the window predates the data)."""
    return [{**c, "stats": window_stats(daily, c["start"], c["end"])} for c in CRISES]
