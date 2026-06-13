import { useCallback, useMemo, useState } from "react";
import {
  applySort,
  applySortStack,
  type ActiveSort,
  type SortDirection,
  type SortOption,
} from "../lib/filterSort";

interface UseSortStateOptions {
  /** Primary sort on load */
  defaultId: string;
  /** Allow shift+click to add secondary/tertiary sorts (max 3) */
  multiSort?: boolean;
}

export function useSortState<T>(options: SortOption<T>[], config: UseSortStateOptions) {
  const defaultOption = options.find((o) => o.id === config.defaultId) ?? options[0];

  const [stack, setStack] = useState<ActiveSort[]>([
    {
      id: defaultOption.id,
      direction: defaultOption.defaultDirection ?? "desc",
    },
  ]);

  const primary = stack[0];

  const toggle = useCallback(
    (id: string, event?: { shiftKey?: boolean }) => {
      const opt = options.find((o) => o.id === id);
      if (!opt) return;

      const shift = event?.shiftKey && config.multiSort;

      setStack((prev) => {
        const existingIdx = prev.findIndex((s) => s.id === id);

        if (shift) {
          if (existingIdx >= 0) {
            const next = [...prev];
            next[existingIdx] = {
              id,
              direction: next[existingIdx].direction === "desc" ? "asc" : "desc",
            };
            return next;
          }
          if (prev.length >= 3) return prev;
          return [...prev, { id, direction: opt.defaultDirection ?? "desc" }];
        }

        if (existingIdx === 0 && prev.length === 1) {
          return [{ id, direction: prev[0].direction === "desc" ? "asc" : "desc" }];
        }

        return [{ id, direction: opt.defaultDirection ?? "desc" }];
      });
    },
    [options, config.multiSort],
  );

  const clearSecondary = useCallback(() => {
    setStack((prev) => (prev.length > 0 ? [prev[0]] : prev));
  }, []);

  const applyTo = useCallback(
    (items: T[]) => {
      if (stack.length <= 1) {
        return applySort(items, stack[0] ?? { id: defaultOption.id, direction: "desc" }, options);
      }
      return applySortStack(items, stack, options);
    },
    [stack, options, defaultOption.id],
  );

  const directionArrow = (dir: SortDirection) => (dir === "desc" ? "▼" : "▲");

  const labelFor = useMemo(
    () => (id: string) => options.find((o) => o.id === id)?.label ?? id,
    [options],
  );

  return {
    stack,
    primary,
    toggle,
    clearSecondary,
    applyTo,
    directionArrow,
    labelFor,
    options,
  };
}
