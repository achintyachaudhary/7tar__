import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  addToStockList,
  fetchStockLists,
  removeFromStockList,
  replaceStockLists,
} from "../api";
import {
  normalizeListSymbol,
  type StockListEntry,
  type StockListsPayload,
} from "../types/stockLists";

interface StockListsContextValue {
  loading: boolean;
  favorites: StockListEntry[];
  fishy: StockListEntry[];
  blacklist: StockListEntry[];
  following: StockListEntry[];
  favoriteSet: Set<string>;
  fishySet: Set<string>;
  blacklistSet: Set<string>;
  followingSet: Set<string>;
  isFavorite: (symbol: string) => boolean;
  isFishy: (symbol: string) => boolean;
  isBlacklisted: (symbol: string) => boolean;
  isFollowing: (symbol: string) => boolean;
  refresh: () => Promise<void>;
  toggleFavorite: (symbol: string) => Promise<void>;
  toggleFishy: (symbol: string) => Promise<void>;
  toggleBlacklist: (symbol: string) => Promise<void>;
  toggleFollowing: (symbol: string) => Promise<void>;
  saveLists: (favorites: string[], blacklist: string[]) => Promise<void>;
}

const StockListsContext = createContext<StockListsContextValue | null>(null);

function toSet(entries: StockListEntry[]): Set<string> {
  return new Set(entries.map((e) => normalizeListSymbol(e.symbol)));
}

export function StockListsProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [favorites, setFavorites] = useState<StockListEntry[]>([]);
  const [fishy, setFishy] = useState<StockListEntry[]>([]);
  const [blacklist, setBlacklist] = useState<StockListEntry[]>([]);
  const [following, setFollowing] = useState<StockListEntry[]>([]);

  const applyPayload = useCallback((data: StockListsPayload) => {
    setFavorites(data.favorites ?? []);
    setFishy(data.fishy ?? []);
    setBlacklist(data.blacklist ?? []);
    setFollowing(data.following ?? []);
  }, []);

  const refresh = useCallback(async () => {
    const data = await fetchStockLists();
    applyPayload(data);
  }, [applyPayload]);

  useEffect(() => {
    refresh()
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refresh]);

  const favoriteSet = useMemo(() => toSet(favorites), [favorites]);
  const fishySet = useMemo(() => toSet(fishy), [fishy]);
  const blacklistSet = useMemo(() => toSet(blacklist), [blacklist]);
  const followingSet = useMemo(() => toSet(following), [following]);

  const isFavorite = useCallback(
    (symbol: string) => favoriteSet.has(normalizeListSymbol(symbol)),
    [favoriteSet],
  );

  const isFishy = useCallback(
    (symbol: string) => fishySet.has(normalizeListSymbol(symbol)),
    [fishySet],
  );

  const isBlacklisted = useCallback(
    (symbol: string) => blacklistSet.has(normalizeListSymbol(symbol)),
    [blacklistSet],
  );

  const isFollowing = useCallback(
    (symbol: string) => followingSet.has(normalizeListSymbol(symbol)),
    [followingSet],
  );

  const toggleFavorite = useCallback(
    async (symbol: string) => {
      const sym = normalizeListSymbol(symbol);
      if (blacklistSet.has(sym)) return;
      if (favoriteSet.has(sym)) {
        const data = await removeFromStockList("favorite", sym);
        applyPayload(data);
      } else {
        const data = await addToStockList("favorite", sym);
        applyPayload(data);
      }
    },
    [applyPayload, blacklistSet, favoriteSet],
  );

  const toggleFishy = useCallback(
    async (symbol: string) => {
      const sym = normalizeListSymbol(symbol);
      if (fishySet.has(sym)) {
        const data = await removeFromStockList("fishy", sym);
        applyPayload(data);
      } else {
        const data = await addToStockList("fishy", sym);
        applyPayload(data);
      }
    },
    [applyPayload, fishySet],
  );

  const toggleBlacklist = useCallback(
    async (symbol: string) => {
      const sym = normalizeListSymbol(symbol);
      if (blacklistSet.has(sym)) {
        const data = await removeFromStockList("blacklist", sym);
        applyPayload(data);
      } else {
        const data = await addToStockList("blacklist", sym);
        applyPayload(data);
      }
    },
    [applyPayload, blacklistSet],
  );

  const toggleFollowing = useCallback(
    async (symbol: string) => {
      const sym = normalizeListSymbol(symbol);
      if (followingSet.has(sym)) {
        const data = await removeFromStockList("following", sym);
        applyPayload(data);
      } else {
        const data = await addToStockList("following", sym);
        applyPayload(data);
      }
    },
    [applyPayload, followingSet],
  );

  const saveLists = useCallback(
    async (favLines: string[], blLines: string[]) => {
      const data = await replaceStockLists(favLines, blLines);
      applyPayload(data);
    },
    [applyPayload],
  );

  const value = useMemo(
    () => ({
      loading,
      favorites,
      fishy,
      blacklist,
      following,
      favoriteSet,
      fishySet,
      blacklistSet,
      followingSet,
      isFavorite,
      isFishy,
      isBlacklisted,
      isFollowing,
      refresh,
      toggleFavorite,
      toggleFishy,
      toggleBlacklist,
      toggleFollowing,
      saveLists,
    }),
    [
      loading,
      favorites,
      fishy,
      blacklist,
      following,
      favoriteSet,
      fishySet,
      blacklistSet,
      followingSet,
      isFavorite,
      isFishy,
      isBlacklisted,
      isFollowing,
      refresh,
      toggleFavorite,
      toggleFishy,
      toggleBlacklist,
      toggleFollowing,
      saveLists,
    ],
  );

  return (
    <StockListsContext.Provider value={value}>
      {children}
    </StockListsContext.Provider>
  );
}

export function useStockLists() {
  const ctx = useContext(StockListsContext);
  if (!ctx) {
    throw new Error("useStockLists must be used within StockListsProvider");
  }
  return ctx;
}

export function useStockListsOptional() {
  return useContext(StockListsContext);
}
