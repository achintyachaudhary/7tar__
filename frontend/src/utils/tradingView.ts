/** Build TradingView India chart URL for an NSE/BSE symbol. */
export function tradingViewChartUrl(symbol: string, yfSymbol?: string | null): string {
  const tvSymbol = tradingViewSymbol(symbol, yfSymbol);
  return `https://in.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;
}

export function displaySymbol(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/i, "");
}

/** TradingView widget symbol format, e.g. NSE:RELIANCE */
export function tradingViewSymbol(symbol: string, yfSymbol?: string | null): string {
  const raw = displaySymbol(yfSymbol || symbol);
  let exchange = "NSE";
  const s = (yfSymbol || symbol).toUpperCase();
  if (s.endsWith(".BO")) {
    exchange = "BSE";
  }
  return `${exchange}:${raw}`;
}
