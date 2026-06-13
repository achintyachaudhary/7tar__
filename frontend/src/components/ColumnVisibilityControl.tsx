import { useState, useRef, useEffect } from "react";
import "../styles/ColumnVisibilityControl.css";

export interface ColumnDefinition {
  key: string;
  label: string;
  alwaysVisible?: boolean; // If true, column cannot be hidden
}

interface ColumnVisibilityControlProps {
  columns: ColumnDefinition[];
  visibleColumns: string[];
  onVisibleColumnsChange: (columns: string[]) => void;
}

export default function ColumnVisibilityControl({
  columns,
  visibleColumns,
  onVisibleColumnsChange,
}: ColumnVisibilityControlProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [isOpen]);

  const toggleColumn = (columnKey: string) => {
    const column = columns.find((c) => c.key === columnKey);
    if (column?.alwaysVisible) return;

    if (visibleColumns.includes(columnKey)) {
      onVisibleColumnsChange(visibleColumns.filter((k) => k !== columnKey));
    } else {
      onVisibleColumnsChange([...visibleColumns, columnKey]);
    }
  };

  const showAll = () => {
    onVisibleColumnsChange(columns.map((c) => c.key));
  };

  const hideOptional = () => {
    onVisibleColumnsChange(columns.filter((c) => c.alwaysVisible).map((c) => c.key));
  };

  return (
    <div className="column-visibility-control" ref={dropdownRef}>
      <button
        type="button"
        className="column-visibility-btn"
        onClick={() => setIsOpen(!isOpen)}
        title="Show/hide columns"
      >
        ⚙️ Columns
      </button>
      {isOpen && (
        <div className="column-visibility-dropdown">
          <div className="column-visibility-header">
            <span>Show Columns</span>
            <div className="column-visibility-actions">
              <button type="button" onClick={showAll} className="link-btn">
                All
              </button>
              <span className="separator">|</span>
              <button type="button" onClick={hideOptional} className="link-btn">
                Default
              </button>
            </div>
          </div>
          <div className="column-visibility-list">
            {columns.map((col) => (
              <label key={col.key} className="column-visibility-item">
                <input
                  type="checkbox"
                  checked={visibleColumns.includes(col.key)}
                  onChange={() => toggleColumn(col.key)}
                  disabled={col.alwaysVisible}
                />
                <span>{col.label}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
