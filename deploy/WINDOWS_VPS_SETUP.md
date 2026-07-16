# Eshu Forex Trader — Windows VPS deployment

Runs the WHOLE stack on one always-on Windows box: the Python brain (daily risk directive
+ weekly gold rebalance) and MT5 with the VertexPlacerV2 reconciler. Provider-agnostic —
any ~$10/mo Windows VPS (2 GB RAM is enough for one terminal), or Exness's free VPS if
your balance ever qualifies (~$500+).

The Mac stays untouched (v1 lives there); the VPS is a clean, isolated home for Eshu.

## 0. What you need
- A Windows Server VPS (2+ GB RAM), RDP access.
- Your Exness account login + password + server name (demo first; real cent account later).
- The Telegram token/chat-id (same values as your Mac `.env`).

## 1. Install the pieces (in an RDP session)
1. **Python 3.11+** — in PowerShell: `winget install Python.Python.3.12`
   (or download from python.org; tick "Add to PATH").
2. **Exness MT5** — download the MT5 installer from your Exness Personal Area, install,
   log in to the account Eshu will trade. Keep the terminal running.
3. **The repo** — either `git clone https://github.com/ogbodo/Eshu_Forex_Trader.git C:\Eshu`
   (GitHub login needed — private repo), or download the ZIP from GitHub in the VPS
   browser and extract to `C:\Eshu`.

## 2. Configure
1. In `C:\Eshu`, copy `.env.example` → `.env` and fill in:
   - `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` (same as on the Mac)
   - `QUEUE_DIR` = this terminal's Files folder. Find it: MT5 → **File → Open Data
     Folder** → open `MQL5\Files` → copy the full path from Explorer's address bar.
2. If this is the **cent** account: in `config.yaml` set `"GC=F": "XAUUSDc"` (confirm the
   exact symbol in Market Watch).

## 3. Install the EA
1. MT5 → File → Open Data Folder → `MQL5\Experts` → copy `C:\Eshu\mt5\VertexPlacerV2.mq5` in.
2. MT5 → press **F4** (MetaEditor) → open VertexPlacerV2 → **F7** compile → 0 errors.
3. Back in MT5: drag **VertexPlacerV2** onto any chart:
   - Common tab: ✅ Allow Algo Trading
   - Inputs: `InpAllowedLogin` = **this account's login number** (hard safety lock),
     `InpRebalanceDryRun` = **true** for the first days, `InpEquityFloor` ≈ 50% of the
     account (last-resort local breaker; e.g. 50 on a $100 account).
4. Toolbar **Algo Trading** button = green.

## 4. Automate the daily brain
In PowerShell **as Administrator**, from `C:\Eshu`:

    powershell -ExecutionPolicy Bypass -File deploy\setup_windows.ps1

This creates the venv, installs requirements, and registers a Scheduled Task
(**EshuDailyRun**, 07:00 server time daily, catches up if the VPS was rebooting).
It finishes with a manual test run so you see the pipeline work once.

## 5. Verify (before trusting it)
1. `C:\Eshu\.venv\Scripts\python scripts\test_telegram.py` → ping arrives on your phone.
2. `C:\Eshu\.venv\Scripts\python scripts\rebalance.py` → writes the gold book + directive.
3. MT5 → Toolbox → Experts: `REBAL(DRY) XAUUSD…` lines with sane lots.
4. Only then set `InpRebalanceDryRun = false` on the chart. Eshu is live.

## 6. Going real ($100 cent account) — the month-end flip
1. Create the **Standard Cent** account in the Exness Personal Area; check swap-free
   status; fund it.
2. MT5 on the VPS → log into the cent account.
3. `config.yaml`: `"GC=F": "XAUUSDc"`. Re-attach the EA with `InpAllowedLogin` = the cent
   login, dry-run true → verify one cycle → false.
4. Reset the risk state for the new account:
   `C:\Eshu\.venv\Scripts\python scripts\rebalance.py --reset-state`
   (the login binding would also catch it, but explicit is better).

## Ops notes
- **Reboots:** MT5 must auto-start or be reopened after a VPS reboot — put a shortcut to
  `terminal64.exe` in `shell:startup`, and MT5 re-attaches EAs to their charts itself.
- **Dead-man behavior:** if the Python task dies, the EA holds positions and adds no new
  risk (stale directive); if MT5 dies, Telegram's daily report keeps coming from Python —
  and the weekly REBAL confirmations stopping is your alarm.
- **Time zone:** the task runs at 07:00 *server* time; anywhere within a few hours of the
  daily close is fine for a daily-bar strategy.
