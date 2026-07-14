"""Versioned daily-close panel — the single frozen data source for signals AND backtest.

Design:
  • One panel, built from yfinance daily proxies for the whole universe. For the daily /
    monthly-rebalanced horizon this is adequate — it's exactly what the validated TSMOM
    edge was measured on. (FX/crypto could later be upgraded to Dukascopy/Binance feeds.)
  • LAST-CLOSED-BAR discipline: the still-forming current-day bar is dropped, so a signal
    can never peek at an incomplete day (fixes v1's weekend-ffill staleness).
  • VERSIONED: each build is snapshotted to disk with a version tag; every run reads the
    SAME frozen snapshot, so live trading and backtests can never diverge on their data.
"""

import os
from datetime import datetime, timezone


def universe_proxies(cfg):
    """Flat list of {proxy, exness, asset_class, bloc} in a stable order."""
    out = []
    u = cfg.get("universe", {})
    for grp, items in u.items():          # any groups present (indices/fx/commodities/crypto), in config order
        for item in (items or []):
            out.append({"proxy": item["proxy"], "exness": item.get("exness"),
                        "asset_class": grp, "bloc": item.get("bloc", grp)})
    return out


def _panels_dir(cfg):
    d = os.path.join(cfg["_root"], "data", "panels")
    os.makedirs(d, exist_ok=True)
    return d


def build_panel(cfg, drop_forming=True):
    """Download max daily history for the universe, return a close-price DataFrame
    (cols = proxies in universe order, rows = dates), forming bar dropped."""
    import pandas as pd
    import yfinance as yf

    proxies = [p["proxy"] for p in universe_proxies(cfg)]
    raw = yf.download(proxies, period="max", interval="1d", auto_adjust=True, progress=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.dropna(how="all")
    # preserve universe order; drop any proxy that returned nothing
    close = close.reindex(columns=[p for p in proxies if p in close.columns])

    # Unify the mixed trading calendars. Indices/FX trade weekdays only; crypto trades
    # 24/7, so the raw union index carries weekend rows that are NaN for everything but
    # crypto. Left as-is, those NaNs poison every rolling vol/momentum window for the
    # weekday instruments (pandas rolling needs a full non-NaN window) — silently
    # collapsing the book toward crypto-only. Reindex to a business-day calendar and
    # forward-fill prices: market-holiday gaps carry the last close, and crypto weekend
    # moves fold into the next business day's close-to-close return. No lookahead — a
    # carried-forward past close is information already known.
    if len(close):
        import pandas as pd
        bidx = pd.bdate_range(close.index.min(), close.index.max())
        close = close.reindex(bidx).ffill()

    if drop_forming and len(close):
        today = datetime.now(timezone.utc).date()
        close = close[close.index.date < today]   # keep only fully-closed days
    return close


def save_panel(cfg, close, version=None):
    """Freeze the panel to data/panels/panel_<version>.csv and point LATEST at it."""
    version = version or datetime.now(timezone.utc).strftime("%Y%m%d")
    d = _panels_dir(cfg)
    path = os.path.join(d, f"panel_{version}.csv")
    close.to_csv(path)
    with open(os.path.join(d, "LATEST"), "w") as f:
        f.write(version)
    return path, version


def load_panel(cfg, version="latest"):
    """Read a frozen panel back as a DataFrame (DatetimeIndex)."""
    import pandas as pd

    d = _panels_dir(cfg)
    if version == "latest":
        lp = os.path.join(d, "LATEST")
        if not os.path.exists(lp):
            raise FileNotFoundError("no panel built yet — run scripts/build_panel.py")
        version = open(lp).read().strip()
    path = os.path.join(d, f"panel_{version}.csv")
    return pd.read_csv(path, index_col=0, parse_dates=True)
