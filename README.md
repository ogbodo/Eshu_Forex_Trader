# Vertex v2 — crisis-resilient systematic trading bot

A clean, from-scratch rebuild whose **#1 design goal is robustness**: trade well on bad
days and during unexpected market fluctuations (crashes, vol spikes, regime shifts), not
just in calm bull runs. See the full design in `../../.claude/plans/` (declarative-zooming-lemur).

**Honest frame:** realistic target ~0.7–1.0 Sharpe, high-single-digit %/yr with real
drawdowns (AQR ballpark). Robustness is *bought* by giving up bull-market upside.
Demo-first; every piece validated OOS before any real capital. This is not a moonshot.

## Universe (multi-asset, NOT crypto-only)
Majority global equity index CFDs (US / Europe / Asia-Pacific) + select FX majors +
a small, risk-capped crypto bloc (BTC/ETH treated as one correlated unit).

## Architecture (layers)
1. **data** — one versioned daily-close panel, last-closed-bar discipline (`vertex/data/panel.py`)
2. **sleeves** — alpha modules to a uniform contract: slow trend, fast trend, cross-sectional (`vertex/sleeves/`)
3. **portfolio** — fixed risk budgets, crypto-bloc cap, portfolio vol target w/ correlation floor
4. **risk** — Python-owned de-risk switch: stress score, drawdown throttle, −20% kill-switch, cash default
5. **execution** — file-queue seam; the EA is a dumb reconciler (magic 8800333, isolated from v1)
6. **validation** — portfolio backtester, deflated Sharpe, purged/embargo walk-forward, crisis-window gates

## Safety
- Distinct magic **8800333** so v2 can never touch v1's live positions.
- Secrets in `.env` (git-ignored); see `.env.example`. Rotate v1's leaked keys.

## Run
    .venv/bin/python scripts/build_panel.py     # build the frozen daily panel
    .venv/bin/python scripts/show_book.py        # current slow-trend target book
