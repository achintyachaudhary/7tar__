import type { ActiveSort, SortOption } from "../lib/filterSort";

interface SortToolbarProps<T> {
  options: SortOption<T>[];
  stack: ActiveSort[];
  onToggle: (id: string, event?: { shiftKey?: boolean }) => void;
  onClearSecondary?: () => void;
  multiSortHint?: boolean;
}

export default function SortToolbar<T>({
  options,
  stack,
  onToggle,
  onClearSecondary,
  multiSortHint = true,
}: SortToolbarProps<T>) {
  const primaryId = stack[0]?.id;
  const secondaryCount = stack.length - 1;

  return (
    <div className="sort-toolbar">
      <span className="toolbar-label">Sort by:</span>
      {options.map((opt) => {
        const activeEntry = stack.find((s) => s.id === opt.id);
        const isPrimary = primaryId === opt.id;
        const isSecondary = activeEntry && !isPrimary;
        const direction = activeEntry?.direction;

        return (
          <button
            key={opt.id}
            type="button"
            className={`toolbar-sort-btn${activeEntry ? " active" : ""}${isSecondary ? " secondary" : ""}`}
            onClick={(e) => onToggle(opt.id, { shiftKey: e.shiftKey })}
            title={
              multiSortHint
                ? `Sort by ${opt.label}. Shift+click to add secondary sort.`
                : `Sort by ${opt.label}`
            }
          >
            {opt.label}
            {activeEntry && direction ? (direction === "desc" ? " ▼" : " ▲") : ""}
            {isSecondary ? ` (${stack.findIndex((s) => s.id === opt.id) + 1})` : ""}
          </button>
        );
      })}
      {secondaryCount > 0 && onClearSecondary && (
        <button
          type="button"
          className="toolbar-sort-clear"
          onClick={onClearSecondary}
          title="Clear secondary sorts"
        >
          ✕
        </button>
      )}
    </div>
  );
}
