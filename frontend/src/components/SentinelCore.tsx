import { Component, lazy, Suspense, useMemo, type ReactNode } from "react";
import { useReducedMotion } from "framer-motion";
import { AudioLines, ChartSpline, Eye, Thermometer } from "lucide-react";

const Scene = lazy(() => import("./sentinel/SentinelCoreScene"));

class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { /* Decorative enhancement has a deliberate fallback. */ }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function StaticCore({ loading = false }: { loading?: boolean }) {
  return (
    <div className={`static-core ${loading ? "static-core--loading" : ""}`} aria-label={loading ? "Loading Sentinel Core" : "Static Sentinel Core fallback"}>
      <i className="static-core__orbit static-core__orbit--one" />
      <i className="static-core__orbit static-core__orbit--two" />
      <i className="static-core__orbit static-core__orbit--three" />
      <span className="static-core__shell"><b /></span>
      <em className="static-core__node static-core__node--one" />
      <em className="static-core__node static-core__node--two" />
      <em className="static-core__node static-core__node--three" />
      <em className="static-core__node static-core__node--four" />
    </div>
  );
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(window.WebGLRenderingContext && (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")));
  } catch { return false; }
}

const moduleNodes = [
  { label: "Time-Series", code: "SIG / 01", icon: ChartSpline },
  { label: "Audio", code: "SIG / 02", icon: AudioLines },
  { label: "Vision", code: "SIG / 03", icon: Eye },
  { label: "Thermal", code: "SIG / 04", icon: Thermometer },
];

export function SentinelCore() {
  const reduced = useReducedMotion();
  const webgl = useMemo(supportsWebGL, []);
  const compact = useMemo(() => window.matchMedia("(max-width: 900px)").matches, []);
  const fallback = <StaticCore />;

  return (
    <section className="sentinel-core" aria-labelledby="core-title">
      <div className="sentinel-core__heading"><span>Sentinel Core / V3</span><strong id="core-title">Orbital independent intelligence</strong></div>
      <div className="sentinel-core__coordinates" aria-hidden="true"><span>N 37.4</span><span>FIELD / 01</span><span>DEPTH 03</span></div>
      <div className="sentinel-core__viewport" aria-hidden="true">
        {webgl ? <SceneBoundary fallback={fallback}><Suspense fallback={<StaticCore loading />}><Scene motionEnabled={!reduced} compact={compact} /></Suspense></SceneBoundary> : fallback}
      </div>
      <div className="module-nodes">
        {moduleNodes.map(({ label, code, icon: Icon }) => <div key={label}><span className="module-nodes__icon"><Icon aria-hidden="true" /></span><span><small>{code}</small><strong>{label}</strong></span><i aria-hidden="true" /></div>)}
      </div>
      <div className="sentinel-core__sequence" aria-hidden="true"><span>Signals</span><i /><span>Intelligence</span><i /><span>Evidence</span></div>
      <p>Independent analysis modules are available — no sensor fusion, live telemetry, or physical digital twin is implied.</p>
    </section>
  );
}
