import type { SortDirection } from "../hooks/useTableSort";

interface SortableThProps {
  label: string;
  sortKey: string;
  activeKey: string;
  direction: SortDirection;
  onSort: (key: string) => void;
  sortable?: boolean;
}

export default function SortableTh({
  label,
  sortKey,
  activeKey,
  direction,
  onSort,
  sortable = true,
}: SortableThProps) {
  if (!sortable) {
    return <th>{label}</th>;
  }

  const active = activeKey === sortKey;
  const indicator = active ? (direction === "asc" ? " ▲" : " ▼") : " ⇅";

  return (
    <th>
      <button
        type="button"
        className={`th-sort${active ? " active" : ""}`}
        onClick={() => onSort(sortKey)}
        aria-sort={
          active ? (direction === "asc" ? "ascending" : "descending") : "none"
        }
      >
        {label}
        <span className="sort-indicator" aria-hidden>
          {indicator}
        </span>
      </button>
    </th>
  );
}
