export type SortDirection = "asc" | "desc";

export interface SortOption<T> {
  id: string;
  label: string;
  getValue: (item: T) => number | string | null | undefined;
  defaultDirection?: SortDirection;
}

export interface ActiveSort {
  id: string;
  direction: SortDirection;
}

export function compareValues(
  a: number | string | null | undefined,
  b: number | string | null | undefined,
  direction: SortDirection,
): number {
  const aNum = typeof a === "number" ? a : a == null ? null : Number(a);
  const bNum = typeof b === "number" ? b : b == null ? null : Number(b);

  if (aNum != null && bNum != null && !Number.isNaN(aNum) && !Number.isNaN(bNum)) {
    const diff = aNum - bNum;
    return direction === "asc" ? diff : -diff;
  }

  const aStr = String(a ?? "");
  const bStr = String(b ?? "");
  const diff = aStr.localeCompare(bStr);
  return direction === "asc" ? diff : -diff;
}

/** Apply a single active sort (primary). */
export function applySort<T>(items: T[], active: ActiveSort, options: SortOption<T>[]): T[] {
  const option = options.find((o) => o.id === active.id);
  if (!option) return [...items];

  const sorted = [...items];
  sorted.sort((a, b) => {
    const diff = compareValues(option.getValue(a), option.getValue(b), active.direction);
    return diff;
  });
  return sorted;
}

/** Apply ordered multi-sort stack (first entry = primary). */
export function applySortStack<T>(
  items: T[],
  stack: ActiveSort[],
  options: SortOption<T>[],
): T[] {
  if (stack.length === 0) return [...items];

  const sorted = [...items];
  sorted.sort((a, b) => {
    for (const active of stack) {
      const option = options.find((o) => o.id === active.id);
      if (!option) continue;
      const diff = compareValues(option.getValue(a), option.getValue(b), active.direction);
      if (diff !== 0) return diff;
    }
    return 0;
  });
  return sorted;
}

export type FilterValues = Record<string, boolean | number | string>;

export function buildDefaultFilterValues(
  sections: { fields: { id: string; default: boolean | number | string }[] }[],
): FilterValues {
  const values: FilterValues = {};
  for (const section of sections) {
    for (const field of section.fields) {
      if ("id" in field && "default" in field) {
        values[field.id] = field.default;
      }
    }
  }
  return values;
}
