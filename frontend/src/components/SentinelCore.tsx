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
  return <div className={`static-core ${loading ? "static-core--loading" : ""}`} aria-label={loading ? "Loading Sentinel Core" : "Static Sentinel Core fallback"}><i /><i /><i /><span /></div>;
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(window.WebGLRenderingContext && (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")));
  } catch { return false; }
}

const moduleNodes = [
  { label: "Time-Series", icon: ChartSpline },
  { label: "Audio", icon: AudioLines },
  { label: "Vision", icon: Eye },
  { label: "Thermal", icon: Thermometer },
];

export function SentinelCore() {
  const reduced = useReducedMotion();
  const webgl = useMemo(supportsWebGL, []);
  const fallback = <StaticCore />;

  return (
    <section className="sentinel-core" aria-labelledby="core-title">
      <div className="sentinel-core__heading"><span>Sentinel Core / V1</span><strong id="core-title">Available intelligence modules</strong></div>
      <div className="sentinel-core__viewport" aria-hidden="true">
        {webgl ? <SceneBoundary fallback={fallback}><Suspense fallback={<StaticCore loading />}><Scene motionEnabled={!reduced} /></Suspense></SceneBoundary> : fallback}
      </div>
      <div className="module-nodes">
        {moduleNodes.map(({ label, icon: Icon }) => <div key={label}><Icon aria-hidden="true" /><span>{label}</span></div>)}
      </div>
      <p>Four independently available modules. No multimodal fusion or physical digital twin is implied.</p>
    </section>
  );
}
