//+------------------------------------------------------------------+
//| DumpSymbols.mq5 — one-shot utility: writes each broker symbol +   |
//| its category path to MQL5/Files/ic_symbols.txt (skips the         |
//| thousands of stock/share CFDs so indices/bonds/commodities/crypto |
//| are easy to read). Places no trades.                              |
//+------------------------------------------------------------------+
void OnStart()
{
   int total = SymbolsTotal(false);
   int f = FileOpen("ic_symbols.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(f == INVALID_HANDLE)
   {
      PrintFormat("DumpSymbols: could not open file (err=%d)", GetLastError());
      return;
   }
   int n = 0;
   for(int i = 0; i < total; i++)
   {
      string s = SymbolName(i, false);
      string p = SymbolInfoString(s, SYMBOL_PATH);
      string pl = p;
      StringToLower(pl);
      if(StringFind(pl, "stock") >= 0 || StringFind(pl, "share") >= 0)
         continue;                          // skip the stock CFDs (the bulk of the 10k+)
      FileWrite(f, s + "  |  " + p);
      n++;
   }
   FileClose(f);
   PrintFormat("DumpSymbols: wrote %d non-stock symbols (with category) to ic_symbols.txt", n);
}
