"""Daily v2 run (for the launchd agent): refresh the data panel, then write the risk
directive (every day) and — on the monthly rebalance window (days 1-3, redundant so it
never misses on a weekend/holiday) — the full target book.

Safe to run before the IC Markets demo exists: equity falls back to the config value and
the files simply sit unread. Fail-soft throughout so one bad day never kills the agent.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vertex.config import load_config
from vertex.data import panel
from vertex.execution import rebalance


def _clear_old_rebs(qdir):
    """Keep only the newest .reb — the EA uses the latest, so old ones just accumulate."""
    try:
        for f in os.listdir(qdir):
            if f.startswith("vxq_v2_rebalance_") and f.endswith(".reb"):
                os.remove(os.path.join(qdir, f))
    except Exception:
        pass


def main():
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cfg = load_config()

    # 1) refresh the frozen panel (fall back to the last one if the feed is down)
    try:
        close = panel.build_panel(cfg)
        panel.save_panel(cfg, close)
        src = "refreshed"
    except Exception as e:
        close = panel.load_panel(cfg)
        src = f"stale (refresh failed: {e})"

    # 2) compute + write the directive daily; the full book only on the rebalance window
    is_rebal_day = datetime.now().day in (1, 2, 3)
    equity = rebalance.account_equity(cfg)
    state = rebalance.load_state(cfg)
    notionals, directive, new_state, diag = rebalance.compute(close, cfg, equity, state)

    qdir = (cfg.get("execution", {}) or {}).get("queue_dir")
    if is_rebal_day and qdir:
        _clear_old_rebs(qdir)
    rebalance.write_files(cfg, notionals, directive, write_reb=is_rebal_day)
    rebalance.save_state(cfg, new_state)

    kind = "FULL REBALANCE (.reb + directive)" if is_rebal_day else "risk directive only"
    print(f"[{stamp}] panel {src} | {kind} | equity ${equity:,.0f} | "
          f"gross={diag['gross']:.3f} directive={directive} | {len(notionals)} targets"
          + (f" | UNMAPPED {diag['unmapped']}" if diag["unmapped"] else ""))


if __name__ == "__main__":
    main()
