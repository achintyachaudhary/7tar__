import type { ReactNode } from "react";
import SortToolbar from "./SortToolbar";
import type { ActiveSort, SortOption } from "../lib/filterSort";

interface ScanPageToolbarProps<T> {
  showFilters: boolean;
  onToggleFilters: () => void;
  scanning: boolean;
  onRunScan: () => void;
  onCancelScan?: () => void;
  runScanLabel?: string;
  leftExtra?: ReactNode;
  sortOptions?: SortOption<T>[];
  sortStack?: ActiveSort[];
  onSortToggle?: (id: string, event?: { shiftKey?: boolean }) => void;
  onClearSecondarySort?: () => void;
  multiSort?: boolean;
  rightExtra?: ReactNode;
}

export default function ScanPageToolbar<T>({
  showFilters,
  onToggleFilters,
  scanning,
  onRunScan,
  onCancelScan,
  runScanLabel = "▶ Run Scan",
  leftExtra,
  sortOptions,
  sortStack,
  onSortToggle,
  onClearSecondarySort,
  multiSort = true,
  rightExtra,
}: ScanPageToolbarProps<T>) {
  const hasSort = sortOptions && sortStack && onSortToggle && sortOptions.length > 0;

  return (
    <div className="toolbar-row">
      <div className="toolbar-left">
        <button
          type="button"
          className={`toolbar-toggle-btn${showFilters ? " active" : ""}`}
          onClick={onToggleFilters}
          title="Toggle cosmetic filters"
        >
          {showFilters ? "Hide" : "Show"} Cosmetic Filters
        </button>

        <button
          type="button"
          className="toolbar-btn btn-primary"
          onClick={onRunScan}
          disabled={scanning}
        >
          {scanning ? "Scanning\u2026" : runScanLabel}
        </button>

        {scanning && onCancelScan && (
          <button
            type="button"
            className="toolbar-btn btn-cancel"
            onClick={onCancelScan}
            title="Cancel scanning"
          >
            ⏹ Cancel
          </button>
        )}

        {leftExtra}
      </div>

      <div className="toolbar-right">
        {hasSort && (
          <SortToolbar
            options={sortOptions}
            stack={sortStack}
            onToggle={onSortToggle}
            onClearSecondary={onClearSecondarySort}
            multiSortHint={multiSort}
          />
        )}
        {rightExtra}
      </div>
    </div>
  );
}
