import type { MouseEvent, ReactNode } from "react";
import { useStockListsOptional } from "../context/StockListsContext";
import { displaySymbol, tradingViewChartUrl } from "../utils/tradingView";
import StockListActions from "./StockListActions";

interface SymbolLinkProps {
  symbol: string;
  yfSymbol?: string | null;
  className?: string;
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
  children?: ReactNode;
  showListActions?: boolean;
  showBadges?: boolean;
}

export default function SymbolLink({
  symbol,
  yfSymbol,
  className = "",
  onClick,
  children,
  showListActions = true,
  showBadges = true,
}: SymbolLinkProps) {
  const lists = useStockListsOptional();
  const label = children ?? displaySymbol(symbol);
  const href = tradingViewChartUrl(symbol, yfSymbol);
  const titleLabel = typeof label === "string" ? label : displaySymbol(symbol);
  const blocked = lists?.isBlacklisted(symbol) ?? false;
  const fav = lists?.isFavorite(symbol) ?? false;
  const fishy = lists?.isFishy(symbol) ?? false;

  return (
    <span className={`symbol-link-wrap${blocked ? " symbol-link-blacklisted" : ""}`}>
      {showBadges && blocked && (
        <span className="symbol-blacklist-badge" title="Blacklisted — excluded from scanners">
          ⚠
        </span>
      )}
      {showBadges && fishy && !blocked && (
        <span className="symbol-fishy-badge" title="Fishy — watch with suspicion">
          🐟
        </span>
      )}
      {showBadges && fav && !blocked && (
        <span className="symbol-favorite-badge" title="Favorite">
          ★
        </span>
      )}
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={`symbol-link${className ? ` ${className}` : ""}${blocked ? " symbol-link-muted" : ""}`}
        title={`Open ${titleLabel} on TradingView`}
        onClick={onClick}
      >
        <strong>{label}</strong>
      </a>
      {showListActions && <StockListActions symbol={symbol} compact showFollow={false} />}
    </span>
  );
}
