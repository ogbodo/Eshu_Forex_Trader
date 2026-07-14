"""Build + freeze the versioned daily-close panel for the whole universe."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vertex.config import load_config
from vertex.data import panel


def main():
    cfg = load_config()
    uni = panel.universe_proxies(cfg)
    print(f"Building daily panel for {len(uni)} instruments...")
    close = panel.build_panel(cfg)
    path, ver = panel.save_panel(cfg, close)
    print(f"saved {path}")
    print(f"  {close.shape[0]} days x {close.shape[1]} instruments | version {ver}")
    print(f"  range: {close.index[0].date()} -> {close.index[-1].date()}")
    got = set(close.columns)
    missing_cols = [p["proxy"] for p in uni if p["proxy"] not in got]
    if missing_cols:
        print(f"  WARNING: no data returned for: {missing_cols}")
    miss = (close.isna().mean() * 100).round(1).sort_values(ascending=False)
    print("  missing % per instrument (top 6 — expected for younger series like crypto/indices):")
    for sym, pct in miss.head(6).items():
        print(f"    {sym:<12} {pct:5.1f}%")


if __name__ == "__main__":
    main()
