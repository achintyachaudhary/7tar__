import { useEffect, useRef, useState } from "react";

export type MarketCapFilterValue = "all" | "micro" | "small" | "mid" | "large" | "mega";

const OPTIONS: { value: MarketCapFilterValue; label: string }[] = [
  { value: "all", label: "All Market Caps" },
  { value: "micro", label: "Micro Cap (< ₹500 Cr)" },
  { value: "small", label: "Small Cap (₹500 - ₹5,000 Cr)" },
  { value: "mid", label: "Mid Cap (₹5,000 - ₹20,000 Cr)" },
  { value: "large", label: "Large Cap (₹20,000 - ₹1L Cr)" },
  { value: "mega", label: "Mega Cap (> ₹1L Cr)" },
];

export function marketCapFilterToApi(value: MarketCapFilterValue): {
  min_market_cap_cr?: number;
  max_market_cap_cr?: number;
} {
  switch (value) {
    case "micro":
      return { max_market_cap_cr: 500 };
    case "small":
      return { min_market_cap_cr: 500, max_market_cap_cr: 5000 };
    case "mid":
      return { min_market_cap_cr: 5000, max_market_cap_cr: 20000 };
    case "large":
      return { min_market_cap_cr: 20000, max_market_cap_cr: 100000 };
    case "mega":
      return { min_market_cap_cr: 100000 };
    case "all":
    default:
      return {};
  }
}

interface MarketCapFilterSelectProps {
  value: MarketCapFilterValue;
  onChange: (value: MarketCapFilterValue) => void;
  disabled?: boolean;
}

export default function MarketCapFilterSelect({
  value,
  onChange,
  disabled = false,
}: MarketCapFilterSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = OPTIONS.find((o) => o.value === value) ?? OPTIONS[0];

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div className="market-cap-filter" ref={rootRef}>
      <button
        type="button"
        className="market-cap-filter-btn"
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span>{selected.label}</span>
        <span className="market-cap-filter-chevron">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <ul className="market-cap-filter-menu" role="listbox">
          {OPTIONS.map((opt) => (
            <li key={opt.value}>
              <button
                type="button"
                role="option"
                aria-selected={opt.value === value}
                className={`market-cap-filter-option${opt.value === value ? " active" : ""}`}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
