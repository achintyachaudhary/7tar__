import { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

type Theme = "light" | "dark";

interface SettingsMenuProps {
  theme: Theme;
  toggleTheme: () => void;
  emailEnabled: boolean;
  toggleEmail: () => void;
  emailReady: boolean;
}

export default function SettingsMenu({
  theme,
  toggleTheme,
  emailEnabled,
  toggleEmail,
  emailReady,
}: SettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const onDatabase = location.pathname.startsWith("/database");
  const onDataSources = location.pathname.startsWith("/data-sources");
  const onSchedule = location.pathname.startsWith("/schedule");
  const onScanProfiles = location.pathname.startsWith("/scan-profiles");
  const onSettingsPage = onDatabase || onDataSources || onSchedule || onScanProfiles;

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="settings-menu" ref={wrapRef}>
      <button
        type="button"
        className={`settings-menu-trigger${open ? " open" : ""}${onSettingsPage ? " active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Settings"
        aria-label="Settings"
      >
        <span aria-hidden="true">⚙</span>
      </button>

      {open && (
        <div className="settings-menu-dropdown" role="menu">
          <div className="settings-menu-section-label">Settings</div>

          <button
            type="button"
            className={`settings-menu-item${onDatabase ? " active" : ""}`}
            role="menuitem"
            onClick={() => {
              navigate("/database");
              setOpen(false);
            }}
          >
            <span className="settings-menu-item-icon" aria-hidden="true">
              🗄️
            </span>
            <span>Database</span>
          </button>

          <button
            type="button"
            className={`settings-menu-item${onDataSources ? " active" : ""}`}
            role="menuitem"
            onClick={() => {
              navigate("/data-sources");
              setOpen(false);
            }}
          >
            <span className="settings-menu-item-icon" aria-hidden="true">
              🔌
            </span>
            <span>Data sources</span>
          </button>

          <button
            type="button"
            className={`settings-menu-item${onSchedule ? " active" : ""}`}
            role="menuitem"
            onClick={() => {
              navigate("/schedule");
              setOpen(false);
            }}
          >
            <span className="settings-menu-item-icon" aria-hidden="true">
              🕐
            </span>
            <span>Schedule</span>
          </button>

          <button
            type="button"
            className={`settings-menu-item${onScanProfiles ? " active" : ""}`}
            role="menuitem"
            onClick={() => {
              navigate("/scan-profiles");
              setOpen(false);
            }}
          >
            <span className="settings-menu-item-icon" aria-hidden="true">
              📋
            </span>
            <span>Scan Profiles</span>
          </button>

          <button
            type="button"
            className="settings-menu-item"
            role="menuitemcheckbox"
            aria-checked={emailEnabled}
            disabled={!emailReady}
            onClick={() => toggleEmail()}
          >
            <span className="settings-menu-item-icon" aria-hidden="true">
              {emailEnabled ? "✉️" : "📭"}
            </span>
            <span>Email alerts</span>
            <span className="settings-menu-item-value">
              {emailEnabled ? "On" : "Off"}
            </span>
          </button>

          <button
            type="button"
            className="settings-menu-item"
            role="menuitemcheckbox"
            aria-checked={theme === "dark"}
            onClick={() => toggleTheme()}
          >
            <span className="settings-menu-item-icon" aria-hidden="true">
              {theme === "light" ? "🌙" : "☀️"}
            </span>
            <span>Theme</span>
            <span className="settings-menu-item-value">
              {theme === "light" ? "Light" : "Dark"}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
