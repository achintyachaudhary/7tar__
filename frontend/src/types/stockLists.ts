export interface StockListEntry {
  symbol: string;
  list_type: "favorite" | "fishy" | "blacklist" | "following";
  note?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface StockListsPayload {
  favorites: StockListEntry[];
  fishy: StockListEntry[];
  blacklist: StockListEntry[];
  following?: StockListEntry[];
}

export function normalizeListSymbol(symbol: string): string {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return sym;
  if (!sym.endsWith(".NS") && !sym.endsWith(".BO")) return `${sym}.NS`;
  return sym;
}

export function parseSymbolLines(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}
