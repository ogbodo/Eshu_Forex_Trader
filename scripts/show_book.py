"""Print the current slow-trend target book from the frozen panel (proof the sleeve works)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vertex.config import load_config
from vertex.data import panel
from vertex import sleeves


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "slow_trend"
    cfg = load_config()
    close = panel.load_panel(cfg)
    sleeve = sleeves.build(name)
    book = sleeve.target_book(close)
    print(f"{name} book as of {close.index[-1].date()}  ({len(book)} positions):")
    for b in book:
        arrow = "L" if b["direction"] == "LONG" else "S"
        print(f"  {arrow} {b['symbol']:<12} weight {b['weight']*100:5.1f}%   raw {b['raw']:+.2f}")


if __name__ == "__main__":
    main()
