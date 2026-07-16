"""Phase-4 learning loop — the HONEST version of "the bot learns":

  fixed rules trade live  →  every day is journaled  →  live results are compared to
  what the model expected  →  drift raises alarms  →  rule changes happen only through
  the validation rig (versioned in git), never by silent self-tuning.

Why no self-tuning: a weekly gold book makes ~50 decisions/yr; distinguishing a ~0.4-
Sharpe edge from luck takes years of data, so any faster "learning" fits noise. This
module MEASURES truth; it does not modify behavior.

Artifacts:
  • data/track.jsonl        — one line/day: equity, model exposure, expected vs realized
  • <queue_dir>/vxq_v2_fills.csv — EA-written deal log (profit/swap/commission = cost truth)
"""

import json
import os
from datetime import datetime, timezone

import numpy as np

TRADING_DAYS = 252


def _track_path(cfg):
    d = os.path.join(cfg["_root"], "data")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "track.jsonl")


def _read_track(cfg):
    try:
        with open(_track_path(cfg)) as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except Exception:
        return []


def snapshot(cfg, close, diag, equity, login, directive):
    """Append today's tracking row. expected_ret uses YESTERDAY's recorded exposure ×
    today's instrument returns (strictly causal); realized_ret is the account-equity
    change vs the previous fresh row (same login only)."""
    rows = _read_track(cfg)
    prev = rows[-1] if rows else None
    bar_date = str(close.index[-1].date())
    if prev and prev.get("bar_date") == bar_date:
        return None                                   # no new market bar — don't double-log

    rets = close.pct_change().iloc[-1]
    expected = None
    realized = None
    if prev:
        exp = 0.0
        for proxy, frac in (prev.get("exposure") or {}).items():
            r = rets.get(proxy)
            if r is not None and not np.isnan(r):
                exp += float(frac) * float(r)
        expected = round(exp, 6)
        if login and prev.get("login") == login and prev.get("equity"):
            realized = round(equity / float(prev["equity"]) - 1.0, 6)

    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "bar_date": bar_date, "equity": round(float(equity), 2), "login": login,
           "directive": directive, "exposure": diag.get("target_exposure", {}),
           "expected_ret": expected, "realized_ret": realized}
    with open(_track_path(cfg), "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _week_costs(cfg):
    """Sum profit/swap/commission from the EA's fills CSV over the last 7 days. Fail-soft."""
    qd = (cfg.get("execution", {}) or {}).get("queue_dir")
    path = os.path.join(qd, "vxq_v2_fills.csv") if qd else None
    if not path or not os.path.exists(path):
        return None
    now = datetime.now(timezone.utc).timestamp()
    n, profit, swap, comm = 0, 0.0, 0.0, 0.0
    try:
        for ln in open(path):
            parts = ln.strip().split(",")
            if len(parts) < 10:
                continue
            if now - float(parts[0]) <= 7 * 86400:
                n += 1
                profit += float(parts[6]); swap += float(parts[7]); comm += float(parts[8])
    except Exception:
        return None
    return {"deals": n, "profit": profit, "swap": swap, "commission": comm}


def weekly_report(cfg, window=20):
    """(text, alarms) — live vs expected over the last `window` tracked bars, cost truth
    from the fills log, and drift alarms. Honest framing: informational at small n."""
    rows = _read_track(cfg)
    pairs = [(r["realized_ret"], r["expected_ret"]) for r in rows
             if r.get("realized_ret") is not None and r.get("expected_ret") is not None]
    pairs = pairs[-window:]
    alarms = []
    lines = ["📚 <b>Eshu — learning-loop weekly</b>"]

    if len(pairs) < 5:
        lines.append(f"Tracking has {len(pairs)} usable day(s) — report becomes meaningful from ~5. Collecting.")
    else:
        live = np.array([p[0] for p in pairs]); exp = np.array([p[1] for p in pairs])
        cum_live, cum_exp = (1 + live).prod() - 1, (1 + exp).prod() - 1
        gap = cum_live - cum_exp
        te = float((live - exp).std())
        rvol = float(live.std() * np.sqrt(TRADING_DAYS))
        tvol = float(cfg.get("risk", {}).get("vol_target", 0.10))
        lines += [f"Last {len(pairs)} bars: live <b>{cum_live*100:+.2f}%</b> vs model {cum_exp*100:+.2f}% "
                  f"(gap {gap*100:+.2f}%)",
                  f"Daily tracking error {te*100:.2f}% · realized vol {rvol*100:.1f}% (target {tvol*100:.0f}%)"]
        if abs(gap) > 0.02:
            alarms.append(f"live-vs-model gap {gap*100:+.1f}% (>2%) — fills/costs/data may be drifting")
        if rvol > 2 * tvol:
            alarms.append(f"realized vol {rvol*100:.0f}% is >2x the {tvol*100:.0f}% target — sizing off?")

    costs = _week_costs(cfg)
    if costs:
        lines.append(f"Costs (7d, {costs['deals']} deals): P&L ${costs['profit']:+.2f} · "
                     f"swap ${costs['swap']:+.2f} · commission ${costs['commission']:+.2f}")
        if costs["swap"] < -0.01:
            alarms.append(f"swap paid ${costs['swap']:+.2f} — swap-free status may have lapsed")

    logins = {r.get("login") for r in rows[-window:] if r.get("login")}
    if len(logins) > 1:
        alarms.append(f"multiple logins in window {sorted(logins)} — state was rebased")

    if alarms:
        lines.append("🚨 <b>Drift alarms:</b>\n" + "\n".join(f"• {a}" for a in alarms))
    else:
        lines.append("No drift alarms.")
    lines.append("<i>Measurement only — rules change ONLY via the validation rig, never self-tune.</i>")
    return "\n".join(lines), alarms
