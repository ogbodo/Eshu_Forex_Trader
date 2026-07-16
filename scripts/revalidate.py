"""Quarterly re-validation — the deliberate half of the learning loop.

Re-runs the FULL honesty rig (stack backtest, IS/OOS, deflated Sharpe, crisis gates,
rolling folds) on freshly downloaded data and reports whether the live rules still earn
their place. If this degrades materially, the answer is a HUMAN decision through the
validation rig — never silent self-tuning.

  .venv/bin/python scripts/revalidate.py [--telegram]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from vertex.config import load_config
from vertex.data import panel
from vertex.portfolio import construct
from vertex.risk import overlay
from vertex.validation import crisis, metrics, walkforward
from vertex import notify

EVAL_START = "2000-01-01"
N_TRIALS = 30    # honest cumulative trial tally (update when new variants are tested)


def run(cfg):
    close = panel.build_panel(cfg)
    panel.save_panel(cfg, close)
    close = close[close.index >= pd.Timestamp(EVAL_START)]
    rets = close.pct_change()
    daily = overlay.run_stack(construct.combine(close, cfg), rets, cfg,
                              rebal_days=cfg.get("rebalance_days", 5)).dropna()

    cut = int(len(daily) * 0.70)
    full, oos = metrics.summary(daily), metrics.summary(daily.iloc[cut:])
    dsr = metrics.deflated_sharpe(daily, n_trials=N_TRIALS)
    folds = walkforward.rolling_folds(daily, k=8)
    pos = sum(1 for f in folds if f["sharpe"] > 0)
    recent = folds[-1] if folds else None

    flags = []
    if oos["sharpe"] < 0.2:
        flags.append(f"OOS Sharpe {oos['sharpe']:+.2f} < 0.2 — edge may be decaying")
    if recent and recent["sharpe"] < 0:
        flags.append(f"most-recent fold negative ({recent['sharpe']:+.2f})")
    if dsr < 0.5:
        flags.append(f"deflated Sharpe {dsr*100:.0f}% < 50%")
    bad_shocks = [c for c in crisis.report(daily)
                  if c["stats"] and c["kind"] != "sustained" and c["stats"]["total_ret"] < -0.10]
    if bad_shocks:
        flags.append("a shock window exceeds -10%: " + ", ".join(c["name"] for c in bad_shocks))

    lines = [f"🧪 <b>Eshu — quarterly re-validation</b> (to {close.index[-1].date()})",
             f"Full Sharpe {full['sharpe']:+.2f} · OOS {oos['sharpe']:+.2f} · "
             f"DSR(N={N_TRIALS}) {dsr*100:.0f}% · maxDD {full['maxdd']*100:.1f}%",
             f"Rolling folds positive: {pos}/{len(folds)}"
             + (f" · latest fold {recent['sharpe']:+.2f}" if recent else "")]
    if flags:
        lines.append("🚩 <b>Review needed:</b>\n" + "\n".join(f"• {x}" for x in flags))
        lines.append("<i>Rules stay FIXED until a validated, versioned change ships. Do not self-tune.</i>")
    else:
        lines.append("✅ Rules still earn their place — no change warranted.")
    return "\n".join(lines), flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    text, flags = run(cfg)
    import re
    print(re.sub("<[^>]+>", "", text))
    if args.telegram:
        sec = cfg.get("secrets", {})
        if sec.get("telegram_token"):
            notify.send_message(sec["telegram_token"], sec.get("telegram_chat_id"), text)
            print("(sent to Telegram)")


if __name__ == "__main__":
    main()
