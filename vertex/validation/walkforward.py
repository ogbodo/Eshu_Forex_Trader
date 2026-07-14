"""Walk-forward validation — the rigorous answer to "is the Sharpe an artifact?".

Two tests:
  • rolling_folds — split the causal return stream into K sequential blocks and report each
    block's Sharpe. Answers "is the edge consistent across time, or concentrated in one
    lucky window?" (For a pre-registered causal strategy this is clean — returns are
    already realized without lookahead.)
  • purged_wf — an anchored walk-forward WITH config SELECTION and an embargo gap. For each
    fold, pick the best config on the training history (minus an embargo), then record that
    config's return on the held-out fold. Guards against the possibility that OUR design
    choices (signal type, sleeve budgets) were themselves an overfit: if the selected-
    per-fold OOS ≈ the pre-registered OOS, the choices didn't matter (robust). Embargo
    prevents selection using data that overlaps the test via the strategy's long lookback.
"""

import numpy as np
import pandas as pd

from vertex.validation import metrics


def rolling_folds(daily, k=8):
    d = daily.dropna()
    n = len(d)
    size = n // k
    out = []
    for i in range(k):
        seg = d.iloc[i * size:(i + 1) * size] if i < k - 1 else d.iloc[i * size:]
        if len(seg) < 20:
            continue
        out.append({"start": seg.index[0].date(), "end": seg.index[-1].date(),
                    "sharpe": metrics.sharpe(seg), "ann_ret": metrics.ann_return(seg),
                    "maxdd": metrics.max_drawdown(seg), "n": len(seg)})
    return out


def purged_wf(config_returns, min_train=756, n_folds=6, embargo=21):
    """config_returns: {name: daily-return Series}. Anchored WF with embargoed selection.
    Returns (wf_oos_series, picks) where picks lists (fold_start, chosen_config, train_sharpe)."""
    df = pd.DataFrame(config_returns).dropna()
    idx = df.index
    n = len(idx)
    names = list(df.columns)
    if n <= min_train + n_folds * 20:
        return pd.Series(dtype=float), []

    bounds = np.linspace(min_train, n, n_folds + 1).astype(int)
    picks, chunks = [], []
    for f in range(n_folds):
        a, b = bounds[f], bounds[f + 1]
        train_end = max(1, a - embargo)                     # embargo gap before the test fold
        train = df.iloc[:train_end]
        sh = {c: metrics.sharpe(train[c]) for c in names}
        best = max(sh, key=sh.get)
        picks.append((idx[a].date(), best, sh[best]))
        chunks.append(df[best].iloc[a:b])
    return pd.concat(chunks), picks
