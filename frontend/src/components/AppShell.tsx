import { useCallback, useState } from "react";
import {
  Activity,
  Boxes,
  Cpu,
  FileClock,
  LayoutDashboard,
  Menu,
  ShieldCheck,
  X,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { PUBLIC_DEMO } from "../api/demo";
import { getBackendHealth } from "../api/health";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { BrandMark } from "./BrandMark";

const navigation = [
  { to: "/", label: "Overview", code: "01", icon: LayoutDashboard, exact: true },
  { to: "/machines", label: "Machines", code: "02", icon: Boxes },
  { to: "/reports", label: "Maintenance Reports", code: "03", icon: FileClock },
  { to: "/models", label: "Model Capabilities", code: "04", icon: Cpu },
];

const pageTitles: Record<string, string> = {
  "/": "Intelligence overview",
  "/machines": "Stored machines",
  "/reports": "Maintenance history",
  "/models": "Model capabilities",
};

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const healthLoader = useCallback((signal: AbortSignal) => getBackendHealth(signal), []);
  const health = useAsyncResource(healthLoader);
  const pageTitle =
    pageTitles[location.pathname] ??
    (location.pathname.startsWith("/machines/")
      ? "Machine workspace"
      : location.pathname.startsWith("/reports/")
        ? "Verified report"
        : "SentinelAI");

  return (
    <div className="app-shell">
      <div className="ambient-canvas" aria-hidden="true">
        <i className="ambient-canvas__glow ambient-canvas__glow--one" />
        <i className="ambient-canvas__glow ambient-canvas__glow--two" />
        <i className="ambient-canvas__grid" />
        <i className="ambient-canvas__noise" />
      </div>

      <button
        className="mobile-menu-button"
        type="button"
        aria-label="Open navigation"
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen(true)}
      >
        <Menu />
      </button>

      <aside className={`sidebar glass-panel ${menuOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <BrandMark />
          <button
            className="icon-button sidebar__close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          >
            <X />
          </button>
        </div>

        <nav aria-label="Primary navigation">
          {navigation.map(({ to, label, code, icon: Icon, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? "nav-link--active" : ""}`}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="nav-link__indicator" />
                  )}
                  <Icon aria-hidden="true" />
                  <span>{label}</span>
                  <small aria-hidden="true">{code}</small>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__boundary glass-card">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>Evidence bounded</strong>
            <span>Single-modality V1</span>
          </div>
        </div>

        <footer className="sidebar__footer">
          <span>{PUBLIC_DEMO ? "Public demo / read only" : "Local / controlled"}</span>
          <small>{PUBLIC_DEMO ? "Stored demonstration records" : "Authorization required before public use"}</small>
        </footer>
      </aside>

      {menuOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <div className="workspace">
        <header className="topbar glass-panel">
          <div>
            <span className="topbar__kicker">SentinelAI workspace</span>
            <strong>{pageTitle}</strong>
          </div>
          <div className="topbar__sequence" aria-hidden="true"><span>Signals</span><i /><span>Intelligence</span><i /><span>Evidence</span><i /><span>Decision support</span></div>
          <div
            className={`connection-state ${PUBLIC_DEMO ? "is-demo" : health.loading ? "is-loading" : health.data?.status === "ok" ? "is-online" : "is-offline"}`}
            title={health.error?.message}
          >
            <span aria-hidden="true" />
            <Activity aria-hidden="true" />
            {PUBLIC_DEMO
              ? "Public demo · read only"
              : health.loading
              ? "Checking backend"
              : health.data?.status === "ok"
                ? "Backend connected"
                : "Backend unavailable"}
          </div>
        </header>

        {PUBLIC_DEMO && (
          <aside className="public-demo-banner" aria-label="Public demonstration environment">
            <strong>PUBLIC DEMO · READ ONLY</strong>
            <span>Demonstration records generated through SentinelAI's simulation/replay workflow.</span>
          </aside>
        )}

        <main className="workspace__content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
