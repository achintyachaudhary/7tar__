import { useEffect, useState } from "react";
import type { SelectedStock } from "../types";
import StockDetailContent from "./StockDetailContent";
import SymbolLink from "./SymbolLink";
import StockListActions from "./StockListActions";
import QuickAlertForm from "./QuickAlertForm";
import { displaySymbol } from "../utils/tradingView";

interface StockDetailModalProps {
  stock: SelectedStock | null;
  onClose: () => void;
  showIpoResearch?: boolean;
}

export default function StockDetailModal({
  stock,
  onClose,
  showIpoResearch = false,
}: StockDetailModalProps) {
  const [showAlertForm, setShowAlertForm] = useState(false);

  useEffect(() => {
    if (!stock) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [stock, onClose]);

  useEffect(() => {
    setShowAlertForm(false);
  }, [stock?.symbol]);

  if (!stock) return null;

  const sym = stock.yfSymbol || stock.symbol;
  const symDisplay = displaySymbol(sym);
  const subtitle =
    stock.label && stock.label !== symDisplay && stock.label !== stock.symbol.replace(/\.(NS|BO)$/i, "")
      ? stock.label
      : null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stock-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div className="modal-title-wrap">
            <h2 id="stock-modal-title">
              <SymbolLink symbol={sym} showListActions={false} showBadges={false} />
              {subtitle ? ` — ${subtitle}` : null}
            </h2>
          </div>
          <div className="modal-header-flags">
            <StockListActions symbol={stock.symbol} />
            <button
              type="button"
              className="modal-quick-alert-btn"
              onClick={() => setShowAlertForm((v) => !v)}
              aria-expanded={showAlertForm}
              title="Add price alert for this stock"
            >
              <span className="plus" aria-hidden="true">+</span>
              <span>Alert</span>
            </button>
            <button
              type="button"
              className="modal-close"
              onClick={onClose}
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </header>

        <div className="modal-body">
          {showAlertForm && (
            <QuickAlertForm
              symbol={stock.symbol}
              companyName={stock.label}
              onClose={() => setShowAlertForm(false)}
            />
          )}
          <StockDetailContent
            symbol={stock.symbol}
            yfSymbol={stock.yfSymbol}
            companyName={stock.label}
            showIpoResearch={showIpoResearch}
          />
        </div>
      </div>
    </div>
  );
}
