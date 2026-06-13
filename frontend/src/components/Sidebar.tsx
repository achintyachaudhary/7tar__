import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useNotifications } from "../context/NotificationContext";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  exact?: boolean;
  scanType?: string;
}

interface NavSection {
  label: string;
  collapsible: boolean;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "Main",
    collapsible: false,
    items: [
      { to: "/", label: "Dashboard", icon: "⊞", exact: true },
      { to: "/live-trades", label: "Portfolio", icon: "💼" },
      { to: "/bulk-deals", label: "Bulk Deals", icon: "💰", scanType: "bulk_deals" },
      { to: "/sector-rotation", label: "Sector Rotation", icon: "🔄" },
    ],
  },
  {
    label: "Stock Finder",
    collapsible: true,
    items: [
      { to: "/screener", label: "Screener", icon: "📊" },
      { to: "/golden-stocks", label: "Golden Stocks", icon: "✨", scanType: "golden" },
      { to: "/weekly-stocks", label: "Weekly Stocks", icon: "📆", scanType: "weekly" },
      { to: "/brst", label: "Year Breakout", icon: "📈", scanType: "brst" },
      { to: "/multi-year-breakout", label: "Multi Year Breakout", icon: "📊", scanType: "multi_year" },
      { to: "/darvas-box", label: "Darvas Box", icon: "📦", scanType: "darvas" },
      { to: "/mean-reversion", label: "Mean Reversion", icon: "🔄", scanType: "mean_reversion" },
      { to: "/vol-squeeze", label: "Volatility Squeeze", icon: "🎯", scanType: "vol_squeeze" },
      { to: "/volume-surge", label: "Volume Surge", icon: "📶", scanType: "volume_surge" },
    ],
  },
  {
    label: "IPO",
    collapsible: false,
    items: [
      { to: "/ipo-intel", label: "IPO GMP & Subs", icon: "💹" },
      { to: "/ipo-research", label: "IPO Research", icon: "🔬" },
    ],
  },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    "Stock Finder": true,
  });
  const location = useLocation();
  const { badges, clearBadge } = useNotifications();

  // Clear badge when user navigates to a scan page
  useEffect(() => {
    for (const section of NAV_SECTIONS) {
      for (const item of section.items) {
        if (item.scanType && location.pathname.startsWith(item.to)) {
          clearBadge(item.scanType);
        }
      }
    }
  }, [location.pathname, clearBadge]);

  const toggleSection = (sectionLabel: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionLabel]: !prev[sectionLabel],
    }));
  };

  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">₹</div>
        {!collapsed && <span className="sidebar-brand">Goldium</span>}
        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "▶" : "◀"}
        </button>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav" aria-label="Main navigation">
        {NAV_SECTIONS.map((section) => {
          const isExpanded = expandedSections[section.label] !== false;
          return (
            <div key={section.label} className="sidebar-section">
              {!collapsed && (
                <div
                  className={`sidebar-section-label${section.collapsible ? " collapsible" : ""}`}
                  onClick={() => section.collapsible && toggleSection(section.label)}
                  role={section.collapsible ? "button" : undefined}
                  tabIndex={section.collapsible ? 0 : undefined}
                  onKeyDown={(e) => {
                    if (section.collapsible && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      toggleSection(section.label);
                    }
                  }}
                >
                  <span>{section.label}</span>
                  {section.collapsible && (
                    <span className="section-toggle-icon">
                      {isExpanded ? "▼" : "▶"}
                    </span>
                  )}
                </div>
              )}
              {(collapsed || isExpanded) && (
                <div className="sidebar-section-items">
                  {section.items.map((item) => {
                    const isActive = item.exact
                      ? location.pathname === item.to
                      : location.pathname.startsWith(item.to);
                    const badgeCount = item.scanType ? badges[item.scanType] : undefined;
                    return (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        className={`sidebar-link${isActive ? " active" : ""}`}
                        title={collapsed ? item.label : undefined}
                      >
                        <span className="nav-icon" aria-hidden="true">
                          {item.icon}
                        </span>
                        <span className="nav-label">{item.label}</span>
                        {badgeCount != null && badgeCount > 0 && (
                          <span className="nav-badge" title={`${badgeCount} new results`} />
                        )}
                      </NavLink>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer" />
    </aside>
  );
}
