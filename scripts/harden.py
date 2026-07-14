"""Validation hardening for the full stack: rolling walk-forward (consistency),
purged+embargoed walk-forward with config selection (choice-overfit guard), and a
corr->1 worst-day stress test.

  .venv/bin/python scripts/harden.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from vertex.config import load_config
from vertex.data import panel
from vertex.portfolio import construct
from vertex.risk import overlay
from vertex.validation import metrics, stress, walkforward

EVAL_START = "2000-01-01"


def _stack_returns(close, rets, cfg):
    return overlay.run_stack(construct.combine(close, cfg), rets, cfg,
                             rebal_days=cfg.get("rebalance_days", 21))


def main():
    cfg = load_config()
    close = panel.load_panel(cfg)
    close = close[close.index >= pd.Timestamp(EVAL_START)]
    rets = close.pct_change()

    # pre-registered full stack (+ positions for the corr->1 stress)
    combined = construct.combine(close, cfg)
    daily, positions = overlay.run_stack(combined, rets, cfg,
                                         rebal_days=cfg.get("rebalance_days", 21), return_detail=True)
    daily = daily.dropna()
    base = metrics.summary(daily)
    print(f"\n{'='*74}\nVALIDATION HARDENING — full stack   base OOS/full Sharpe context")
    print(f"  pre-registered full-sample Sharpe {base['sharpe']:+.2f}  (ann {base['ann_ret']*100:+.1f}%, vol {base['ann_vol']*100:.1f}%)")

    # 1) ROLLING WALK-FORWARD — consistency across 8 sequential windows
    print("\n1) ROLLING WALK-FORWARD (is the edge consistent, or one lucky window?)")
    folds = walkforward.rolling_folds(daily, k=8)
    pos_n = sum(1 for f in folds if f["sharpe"] > 0)
    for f in folds:
        print(f"   {f['start']} → {f['end']}   Sharpe {f['sharpe']:+5.2f} | ann {f['ann_ret']*100:+6.1f}% | maxDD {f['maxdd']*100:6.1f}%")
    print(f"   => {pos_n}/{len(folds)} folds positive")

    # 2) PURGED + EMBARGOED WALK-FORWARD with config selection (did OUR choices overfit?)
    print("\n2) PURGED WALK-FORWARD with config selection (guard vs choosing tanh / 50-25-25)")
    variants = {
        "tanh/50-25-25": {},
        "sign/50-25-25": {"sleeve_params": {"slow_trend": {"signal": "sign"}}},
        "tanh/equal":     {"sleeves": {"slow_trend": 1, "fast_trend": 1, "xsect": 1}},
        "sign/equal":     {"sleeve_params": {"slow_trend": {"signal": "sign"}},
                            "sleeves": {"slow_trend": 1, "fast_trend": 1, "xsect": 1}},
    }
    config_returns = {}
    for name, over in variants.items():
        c = copy.deepcopy(cfg)
        c.update(over)
        config_returns[name] = _stack_returns(close, rets, c)
    wf, picks = walkforward.purged_wf(config_returns)
    for start, best, tsh in picks:
        print(f"   fold from {start}: selected '{best}' (train Sharpe {tsh:+.2f})")
    print(f"   => purged-WF out-of-sample Sharpe {metrics.sharpe(wf):+.2f}  (vs pre-registered {base['sharpe']:+.2f})")
    print("   standalone full-sample Sharpe by config:")
    for name, ret in config_returns.items():
        print(f"     {name:<16} {metrics.sharpe(ret.dropna()):+.2f}")

    # 3) CORR->1 WORST-DAY STRESS
    print("\n3) CORR->1 WORST-DAY STRESS (if all diversification vanishes at once)")
    stressed = stress.corr1_worst_day(positions, rets)
    actual_worst = -daily.min()
    kill = cfg.get("risk", {}).get("kill_switch_dd", 0.20)
    print(f"   worst ACTUAL 1-day loss (diversified):        {actual_worst*100:5.2f}%")
    print(f"   worst STRESSED 1-day loss (corr=1, 3-sigma):  {stressed.max()*100:5.2f}%")
    print(f"   kill-switch tolerance:                        {kill*100:5.1f}%")
    verdict = "OK — survives corr->1" if stressed.max() < kill else "REVIEW — corr->1 day breaches kill tolerance"
    print(f"   => {verdict}")
    print()


if __name__ == "__main__":
    main()
