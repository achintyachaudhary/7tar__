import { useState } from "react";
import { useStockListsOptional } from "../context/StockListsContext";
import { displaySymbol } from "../utils/tradingView";

interface StockListActionsProps {
  symbol: string;
  compact?: boolean;
  /** Show the Follow (news) toggle alongside the list icons. */
  showFollow?: boolean;
}

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} aria-hidden>
      <path
        d="M12 2.5l2.95 5.98 6.6.96-4.78 4.65 1.13 6.58L12 17.57l-5.9 3.1 1.13-6.58L2.45 9.44l6.6-.96L12 2.5z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AlertIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} aria-hidden>
      <path
        d="M12 3.5L21.5 20h-19L12 3.5z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M12 9.5v4.5"
        stroke={filled ? "var(--surface)" : "currentColor"}
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="12" cy="17" r="0.9" fill={filled ? "var(--surface)" : "currentColor"} />
    </svg>
  );
}

function BanIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle
        cx="12"
        cy="12"
        r="8.5"
        stroke="currentColor"
        strokeWidth={filled ? 2.2 : 1.6}
        fill={filled ? "color-mix(in srgb, currentColor 15%, transparent)" : "none"}
      />
      <path d="M6 6l12 12" stroke="currentColor" strokeWidth={filled ? 2.2 : 1.6} strokeLinecap="round" />
    </svg>
  );
}

function BellIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} aria-hidden>
      <path
        d="M12 3a6 6 0 0 0-6 6v3.6l-1.7 3.2a.8.8 0 0 0 .7 1.2h14a.8.8 0 0 0 .7-1.2L18 12.6V9a6 6 0 0 0-6-6z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M9.8 19.8a2.3 2.3 0 0 0 4.4 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function StockListActions({
  symbol,
  compact = false,
  showFollow = true,
}: StockListActionsProps) {
  const lists = useStockListsOptional();
  const [busy, setBusy] = useState(false);

  if (!lists) return null;

  const {
    isFavorite,
    isFishy,
    isBlacklisted,
    isFollowing,
    toggleFavorite,
    toggleFishy,
    toggleBlacklist,
    toggleFollowing,
  } = lists;
  const fav = isFavorite(symbol);
  const fishy = isFishy(symbol);
  const blocked = isBlacklisted(symbol);
  const followed = isFollowing(symbol);

  const run = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  const handle =
    (fn: () => Promise<void>) => (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      void run(fn);
    };

  return (
    <span className={`stock-list-actions${compact ? " stock-list-actions-compact" : ""}`}>
      {showFollow && (
        <button
          type="button"
          className={`stock-list-btn stock-list-btn-follow${followed ? " active" : ""}`}
          title={followed ? "Unfollow — drops from your news feed" : "Follow — news appears on your dashboard"}
          disabled={busy}
          onClick={handle(() => toggleFollowing(symbol))}
          aria-label={`Follow ${displaySymbol(symbol)}`}
          aria-pressed={followed}
        >
          <BellIcon filled={followed} />
        </button>
      )}
      <button
        type="button"
        className={`stock-list-btn stock-list-btn-fav${fav ? " active" : ""}`}
        title={fav ? "Remove from favorites" : "Add to favorites"}
        disabled={busy || blocked}
        onClick={handle(() => toggleFavorite(symbol))}
        aria-label={`Favorite ${displaySymbol(symbol)}`}
        aria-pressed={fav}
      >
        <StarIcon filled={fav} />
      </button>
      <button
        type="button"
        className={`stock-list-btn stock-list-btn-fishy${fishy ? " active" : ""}`}
        title={fishy ? "Remove fishy flag" : "Mark as fishy — watch with suspicion (stays in scans)"}
        disabled={busy}
        onClick={handle(() => toggleFishy(symbol))}
        aria-label={`Mark ${displaySymbol(symbol)} fishy`}
        aria-pressed={fishy}
      >
        <AlertIcon filled={fishy} />
      </button>
      <button
        type="button"
        className={`stock-list-btn stock-list-btn-block${blocked ? " active" : ""}`}
        title={blocked ? "Remove from blacklist (will appear in scans again)" : "Blacklist — excluded from all scanners"}
        disabled={busy}
        onClick={handle(() => toggleBlacklist(symbol))}
        aria-label={`Blacklist ${displaySymbol(symbol)}`}
        aria-pressed={blocked}
      >
        <BanIcon filled={blocked} />
      </button>
    </span>
  );
}
