import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import ScreenerPage from "./pages/ScreenerPage";
import BrStPage from "./pages/BrStPage";
import MultiYearBreakoutPage from "./pages/MultiYearBreakoutPage";
import LiveTradesPage from "./pages/LiveTradesPage";
import GoldenStocksPage from "./pages/GoldenStocksPage";
import WeeklyStocksPage from "./pages/WeeklyStocksPage";
import IpoPage from "./pages/IpoPage";
import IpoIntelPage from "./pages/IpoIntelPage";
import IpoResearchPage from "./pages/IpoResearchPage";
import DashboardPage from "./pages/DashboardPage";
import DatabasePage from "./pages/DatabasePage";
import DataSourcesPage from "./pages/DataSourcesPage";
import SchedulePage from "./pages/SchedulePage";
import BulkDealsPage from "./pages/BulkDealsPage";
import SectorRotationPage from "./pages/SectorRotationPage";
import DarvasBoxPage from "./pages/DarvasBoxPage";
import MeanReversionPage from "./pages/MeanReversionPage";
import VolSqueezePage from "./pages/VolSqueezePage";
import VolumeSurgePage from "./pages/VolumeSurgePage";
import AlertsPage from "./pages/AlertsPage";
import ScanProfilesPage from "./pages/ScanProfilesPage";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="screener" element={<ScreenerPage />} />
          <Route path="brst" element={<BrStPage />} />
          <Route path="multi-year-breakout" element={<MultiYearBreakoutPage />} />
          <Route path="darvas-box" element={<DarvasBoxPage />} />
          <Route path="mean-reversion" element={<MeanReversionPage />} />
          <Route path="vol-squeeze" element={<VolSqueezePage />} />
          <Route path="volume-surge" element={<VolumeSurgePage />} />
          <Route path="live-trades" element={<LiveTradesPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="scan-profiles" element={<ScanProfilesPage />} />
          <Route path="golden-stocks" element={<GoldenStocksPage />} />
          <Route path="weekly-stocks" element={<WeeklyStocksPage />} />
          <Route path="ipo" element={<IpoPage />} />
          <Route path="ipo-intel" element={<IpoIntelPage />} />
          <Route path="ipo-research" element={<IpoResearchPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="bulk-deals" element={<BulkDealsPage />} />
          <Route path="sector-rotation" element={<SectorRotationPage />} />
          <Route path="database" element={<DatabasePage />} />
          <Route path="data-sources" element={<DataSourcesPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
