import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/States";

const OverviewPage = lazy(() => import("./pages/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const MachinesPage = lazy(() => import("./pages/MachinesPage").then((module) => ({ default: module.MachinesPage })));
const MachineDetailPage = lazy(() => import("./pages/MachineDetailPage").then((module) => ({ default: module.MachineDetailPage })));
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((module) => ({ default: module.ReportsPage })));
const ReportDetailPage = lazy(() => import("./pages/ReportDetailPage").then((module) => ({ default: module.ReportDetailPage })));
const ModelsPage = lazy(() => import("./pages/ModelsPage").then((module) => ({ default: module.ModelsPage })));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })));

export function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<LoadingState label="Opening SentinelAI workspace…" />}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="machines" element={<MachinesPage />} />
            <Route path="machines/:machineId" element={<MachineDetailPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="reports/:reportId" element={<ReportDetailPage />} />
            <Route path="models" element={<ModelsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
