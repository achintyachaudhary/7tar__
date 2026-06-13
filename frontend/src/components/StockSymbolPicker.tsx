import { useEffect, useId, useRef, useState } from "react";
import { fetchStockSymbolSuggestions } from "../api";

export interface StockSymbolOption {
  symbol: string;
  company_name: string;
  last_price: number | null;
}

interface StockSymbolPickerProps {
  value: StockSymbolOption | null;
  onChange: (option: StockSymbolOption | null) => void;
  disabled?: boolean;
  placeholder?: string;
}

function displaySymbol(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/i, "");
}

export default function StockSymbolPicker({
  value,
  onChange,
  disabled = false,
  placeholder = "Search symbol or company…",
}: StockSymbolPickerProps) {
  const listId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<StockSymbolOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (value) {
      setQuery(`${displaySymbol(value.symbol)} — ${value.company_name}`);
    } else {
      setQuery("");
    }
  }, [value]);

  useEffect(() => {
    if (!open || query.trim().length < 1) {
      setSuggestions([]);
      return;
    }

    const q = query.split("—")[0].trim();
    if (value && query === `${displaySymbol(value.symbol)} — ${value.company_name}`) {
      return;
    }

    const timer = window.setTimeout(() => {
      setLoading(true);
      fetchStockSymbolSuggestions(q)
        .then((res) => setSuggestions(res.suggestions))
        .catch(() => setSuggestions([]))
        .finally(() => setLoading(false));
    }, 200);

    return () => window.clearTimeout(timer);
  }, [query, open, value]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const pick = (opt: StockSymbolOption) => {
    onChange(opt);
    setQuery(`${displaySymbol(opt.symbol)} — ${opt.company_name}`);
    setOpen(false);
  };

  const handleInputChange = (text: string) => {
    setQuery(text);
    onChange(null);
    setOpen(true);
  };

  return (
    <div className="stock-symbol-picker" ref={wrapRef}>
      <input
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder={placeholder}
        value={query}
        onChange={(e) => handleInputChange(e.target.value)}
        onFocus={() => setOpen(true)}
        disabled={disabled}
        autoComplete="off"
      />
      {open && (loading || suggestions.length > 0 || query.trim().length > 0) && (
        <ul id={listId} className="stock-symbol-picker-list" role="listbox">
          {loading && <li className="stock-symbol-picker-hint">Searching…</li>}
          {!loading && suggestions.length === 0 && query.trim().length > 0 && (
            <li className="stock-symbol-picker-hint">No matching stocks</li>
          )}
          {!loading &&
            suggestions.map((opt) => (
              <li key={opt.symbol}>
                <button
                  type="button"
                  role="option"
                  className="stock-symbol-picker-option"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pick(opt)}
                >
                  <span className="stock-symbol-picker-sym">{displaySymbol(opt.symbol)}</span>
                  <span className="stock-symbol-picker-name">{opt.company_name}</span>
                  {opt.last_price != null && (
                    <span className="stock-symbol-picker-price">
                      ₹{opt.last_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                    </span>
                  )}
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
