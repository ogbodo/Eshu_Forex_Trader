//+------------------------------------------------------------------+
//| VertexPlacerV2.mq5 — v2 "dumb reconciler" EA for IC Markets (MT5) |
//|                                                                  |
//| Contains NO strategy logic. Python owns every decision; this EA  |
//| only: (1) reads the target book Python writes (vxq_v2_rebalance  |
//| _*.reb), (2) reads a freshness-stamped risk directive (vxq_v2_   |
//| risk_state.txt: a gross multiplier, or FLATTEN), (3) reconciles  |
//| its own positions (magic 8800333, isolated from v1) to           |
//| target_notional * gross, converting notional->lots via the live  |
//| contract size, and (4) publishes account state back.             |
//|                                                                  |
//| Safety: demo-only guard, per-symbol lot cap, local equity-floor  |
//| breaker, and a DEAD-MAN rule — if the directive is stale (Python |
//| down) it HOLDS existing positions and adds no new risk.          |
//|                                                                  |
//| UNTESTED against a live terminal — run with InpRebalanceDryRun=  |
//| true first and verify the logged intended lots before going live.|
//+------------------------------------------------------------------+
#include <Trade/Trade.mqh>

input long   InpMagic           = 8800333;   // v2 magic (never touches v1's 8800111/8800222)
input bool   InpDemoOnly        = true;      // refuse to trade on a REAL account
input int    InpPollSeconds     = 10;        // reconcile cadence
input bool   InpRebalanceDryRun = true;      // TRUE = log intended lots, place NOTHING (verify first!)
input double InpNoTradeBand     = 0.20;      // skip a symbol if current lots within this fraction of target
input double InpMaxLotsPerSym   = 50.0;      // hard per-symbol lot cap (safety)
input double InpEquityFloor     = 0.0;       // local last-resort: flatten all if equity < this (0 = off)

string RISK       = "vxq_v2_risk_state.txt";
string ACCT       = "vxq_v2_account.json";
string REB_PREFIX = "vxq_v2_rebalance_";

CTrade trade;

int OnInit()
{
   if(InpDemoOnly && (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL)
   {
      Print("VertexPlacerV2: REAL account + InpDemoOnly -> refusing to trade.");
      return(INIT_FAILED);
   }
   trade.SetExpertMagicNumber(InpMagic);
   EventSetTimer(MathMax(1, InpPollSeconds));
   PrintFormat("VertexPlacerV2 ready. magic=%d dryRun=%s band=%.0f%% floor=%.2f",
               (int)InpMagic, (string)InpRebalanceDryRun, InpNoTradeBand*100, InpEquityFloor);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   ExportAccount();

   if(InpEquityFloor > 0 && AccountInfoDouble(ACCOUNT_EQUITY) < InpEquityFloor)
   { CloseAll("equity floor"); return; }

   double gross = 0.0;
   int status = ReadDirective(gross);        // 1 = ok(gross), 0 = stale, -1 = FLATTEN
   if(status == -1) { CloseAll("FLATTEN directive"); return; }
   if(status == 0)  return;                   // dead-man: Python stale -> hold, add no new risk
   ReconcileToReb(gross);
}

//--- read the freshness-stamped risk directive -------------------------------
int ReadDirective(double &gross)
{
   int f = FileOpen(RISK, FILE_READ|FILE_TXT|FILE_ANSI);
   if(f == INVALID_HANDLE) return(0);          // no file -> treat as stale (hold)
   long validUntil = (long)StringToInteger(FileReadString(f));
   string line2 = FileReadString(f);
   FileClose(f);
   if((long)TimeGMT() > validUntil) return(0); // stale -> dead-man
   StringTrimLeft(line2); StringTrimRight(line2);
   if(StringFind(line2, "FLATTEN") >= 0) return(-1);
   gross = StringToDouble(line2);
   if(gross < 0) gross = 0;
   return(1);
}

//--- newest .reb file --------------------------------------------------------
string NewestReb()
{
   string best = ""; long bestTime = -1;
   string name; long h = FileFindFirst(REB_PREFIX + "*", name);
   if(h == INVALID_HANDLE) return("");
   do {
      // filenames are vxq_v2_rebalance_<epoch>.reb — pick the largest epoch
      string digits = name;
      StringReplace(digits, REB_PREFIX, ""); StringReplace(digits, ".reb", "");
      long t = (long)StringToInteger(digits);
      if(t > bestTime) { bestTime = t; best = name; }
   } while(FileFindNext(h, name));
   FileFindClose(h);
   return(best);
}

//--- signed net lots we hold on a symbol (our magic only) --------------------
double NetLots(string sym)
{
   double net = 0;
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      net += (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? v : -v;
   }
   return(net);
}

//--- convert a signed USD notional to snapped, capped signed lots ------------
double NotionalToLots(string sym, double notional)
{
   if(!SymbolInfoInteger(sym, SYMBOL_SELECT)) SymbolSelect(sym, true);
   double price = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(price <= 0) price = SymbolInfoDouble(sym, SYMBOL_BID);
   if(price <= 0) price = SymbolInfoDouble(sym, SYMBOL_LAST);
   double contract = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   if(price <= 0 || contract <= 0) return(0);

   double lots = notional / (contract * price);
   double sign = (lots >= 0) ? 1.0 : -1.0;
   double a = MathAbs(lots);

   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vstep= SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(vstep > 0) a = MathFloor(a/vstep)*vstep;
   if(a < vmin) return(0);                       // below broker min -> skip (don't oversize)
   if(a > vmax) a = vmax;
   if(a > InpMaxLotsPerSym) a = InpMaxLotsPerSym;
   return(sign * a);
}

//--- reconcile every target in the newest .reb to notional*gross -------------
void ReconcileToReb(double gross)
{
   string fn = NewestReb();
   if(fn == "") return;
   int f = FileOpen(fn, FILE_READ|FILE_TXT|FILE_ANSI);
   if(f == INVALID_HANDLE) return;

   string targets[]; int n = 0;
   while(!FileIsEnding(f))
   {
      string line = FileReadString(f);
      StringTrimLeft(line); StringTrimRight(line);
      if(StringLen(line) == 0) continue;
      ArrayResize(targets, n+1); targets[n] = line; n++;
   }
   FileClose(f);

   string tsyms[]; ArrayResize(tsyms, n);
   for(int i = 0; i < n; i++)
   {
      string parts[]; int k = StringSplit(targets[i], '|', parts);
      if(k < 2) { tsyms[i] = ""; continue; }
      string sym = parts[0];
      double notional = StringToDouble(parts[1]) * gross;
      tsyms[i] = sym;
      ReconcileSymbol(sym, notional);
   }
   CloseOrphans(tsyms);                           // close anything we hold that isn't a target
}

void ReconcileSymbol(string sym, double notional)
{
   double target = NotionalToLots(sym, notional);
   double cur = NetLots(sym);
   double diff = target - cur;
   double tol = MathMax(InpNoTradeBand * MathAbs(target), SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN));
   if(MathAbs(diff) < tol && (target == 0 || (target > 0) == (cur > 0) || cur == 0))
      return;                                      // already within band and same side -> leave it

   if(InpRebalanceDryRun)
   { PrintFormat("REBAL(DRY) %s: cur %.2f -> target %.2f lots (notional %.0f)", sym, cur, target, notional); return; }

   CloseSymbol(sym);                               // flatten then re-open to the target (mode-agnostic)
   if(MathAbs(target) >= SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN))
   {
      if(target > 0) trade.Buy(MathAbs(target), sym);
      else           trade.Sell(MathAbs(target), sym);
   }
}

void CloseSymbol(string sym)
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      trade.PositionClose(tk);
   }
}

void CloseOrphans(string &tsyms[])
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      bool keep = false;
      for(int j = 0; j < ArraySize(tsyms); j++) if(tsyms[j] == sym) { keep = true; break; }
      if(!keep)
      {
         if(InpRebalanceDryRun) PrintFormat("REBAL(DRY) %s: orphan -> would close", sym);
         else trade.PositionClose(tk);
      }
   }
}

void CloseAll(string why)
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(InpRebalanceDryRun) { PrintFormat("REBAL(DRY) close-all (%s): %s", why, PositionGetString(POSITION_SYMBOL)); continue; }
      trade.PositionClose(tk);
   }
}

//--- publish account state (+ heartbeat) so Python can size + detect a dead EA
void ExportAccount()
{
   int f = FileOpen(ACCT, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(f == INVALID_HANDLE) return;
   int openN = 0; double floating = 0;
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      openN++; floating += PositionGetDouble(POSITION_PROFIT);
   }
   FileWriteString(f, StringFormat(
      "{\"equity\":%.2f,\"balance\":%.2f,\"currency\":\"%s\",\"open\":%d,\"floating\":%.2f,\"ts\":%I64d}",
      AccountInfoDouble(ACCOUNT_EQUITY), AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoString(ACCOUNT_CURRENCY), openN, floating, (long)TimeGMT()));
   FileClose(f);
}
//+------------------------------------------------------------------+
