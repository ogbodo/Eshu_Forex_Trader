"""Sleeve contract + registry.

Every alpha sleeve implements the SAME interface so the portfolio combiner can treat
them generically:

  • raw_positions(close) -> DataFrame of SIGNED, vol-scaled positions over time
      (portfolio-agnostic; each instrument scaled to equal ex-ante risk). The backtester
      needs the full path.
  • target_book(close)   -> the latest-bar book as a list of dicts
      {symbol, direction 'LONG'/'SHORT', weight (share of THIS sleeve's gross), raw (signed size)}.
      Execution needs only the last row.

A sleeve outputs its own internal book; the portfolio layer later scales sleeves by their
risk budgets and applies caps / vol targeting. Sleeves know nothing about the portfolio.
"""

REGISTRY = {}


def register(name):
    def deco(cls):
        REGISTRY[name] = cls
        cls.name = name
        return cls
    return deco


def positions_from_raw(raw_row):
    """Signed vol-scaled positions (a Series for one bar) -> the contract list."""
    last = raw_row.dropna()
    last = last[last != 0]
    if last.empty:
        return []
    gross = last.abs().sum() or 1.0
    book = [{"symbol": s, "direction": "LONG" if w > 0 else "SHORT",
             "weight": abs(w) / gross, "raw": float(w)} for s, w in last.items()]
    return sorted(book, key=lambda x: -x["weight"])


class Sleeve:
    name = "base"

    def raw_positions(self, close):
        """Return a DataFrame of signed vol-scaled positions (index=dates, cols=instruments)."""
        raise NotImplementedError

    def target_book(self, close, max_stale_days=7):
        """Latest-bar book from raw_positions (uniform contract).

        Markets keep different calendars (weekends, holidays), so the raw last row is
        sparse — on a Sunday only 24/7 crypto has a print. We compute each instrument's
        CURRENT position from its own most-recent real close (forward-filled), which is
        the correct "last closed bar" per instrument — NOT lookahead. But we DROP any
        instrument whose last real print is staler than `max_stale_days` (a dead/halted
        feed must not produce a phantom position). The backtester, by contrast, feeds
        RAW (un-filled) closes so historical vol/returns stay unbiased.
        """
        if close is None or len(close) == 0:
            return []
        rp = self.raw_positions(close.ffill())
        if rp is None or len(rp) == 0:
            return []
        row = rp.iloc[-1].copy()
        last_date = close.index[-1]
        for col in close.columns:
            lv = close[col].last_valid_index()
            if lv is None or (last_date - lv).days > max_stale_days:
                row[col] = float("nan")
        return positions_from_raw(row)
