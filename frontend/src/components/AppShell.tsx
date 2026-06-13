import { Outlet } from "react-router-dom";
import { useEffect } from "react";
import Sidebar from "./Sidebar";
import MarketIndexTicker from "./MarketIndexTicker";
import LivePnlTicker from "./LivePnlTicker";
import SettingsMenu from "./SettingsMenu";
import { DayScanSyncProvider } from "../context/DayScanSyncContext";
import { AppSocketProvider } from "../context/AppSocketContext";
import { NotificationProvider } from "../context/NotificationContext";
import { LiveTradeSSEProvider } from "../context/LiveTradeSSEContext";
import { LiveTicksProvider } from "../context/LiveTicksContext";
import GlobalScanProgressBar from "./GlobalScanProgressBar";
import { GlobalScanMonitorProvider } from "../context/GlobalScanMonitorContext";
import { StockListsProvider } from "../context/StockListsContext";
import { useTheme } from "../hooks/useTheme";
import { useEmailNotifications } from "../hooks/useEmailNotifications";
import { usePriceAlertSound } from "../hooks/usePriceAlertSound";
import { purgeLegacyLocalOnlyKeys } from "../lib/dbFirstStorage";

function AppShellContent() {
  const [theme, toggleTheme] = useTheme();
  const [emailEnabled, toggleEmail, emailReady] = useEmailNotifications();
  usePriceAlertSound();

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <div className="app-topbar">
          <div className="app-topbar-indices">
            <MarketIndexTicker />
          </div>
          <div className="app-topbar-actions">
            <LivePnlTicker />
            <SettingsMenu
              theme={theme}
              toggleTheme={toggleTheme}
              emailEnabled={emailEnabled}
              toggleEmail={toggleEmail}
              emailReady={emailReady}
            />
          </div>
        </div>
        <div className="app-content">
          <GlobalScanProgressBar />
          <Outlet />
        </div>
      </div>
    </div>
  );
}

export default function AppShell() {
  useEffect(() => {
    purgeLegacyLocalOnlyKeys();
  }, []);

  return (
    <AppSocketProvider>
      <LiveTicksProvider>
        <StockListsProvider>
          <GlobalScanMonitorProvider>
            <DayScanSyncProvider>
              <NotificationProvider>
                <LiveTradeSSEProvider>
                  <AppShellContent />
                </LiveTradeSSEProvider>
              </NotificationProvider>
            </DayScanSyncProvider>
          </GlobalScanMonitorProvider>
        </StockListsProvider>
      </LiveTicksProvider>
    </AppSocketProvider>
  );
}
