import { AlertTriangle, Database, LoaderCircle, RefreshCw, ShieldX } from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({ label = "Loading verified intelligence…" }: { label?: string }) {
  return (
    <div className="state-panel state-panel--loading" role="status">
      <div className="loading-orbit" aria-hidden="true">
        <i />
        <LoaderCircle />
      </div>
      <div>
        <strong>{label}</strong>
        <span>Authoritative data is being requested from SentinelAI.</span>
      </div>
      <div className="skeleton-lines" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-panel state-panel--empty">
      <div className="state-glyph" aria-hidden="true"><i /><Database /></div>
      <p className="eyebrow">No verified records</p>
      <h2>{title}</h2>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const normalized = error.message.toLowerCase();
  const kind = normalized.includes("not found")
    ? "not-found"
    : normalized.includes("conflict") || normalized.includes("processing")
      ? "conflict"
      : normalized.includes("model") || normalized.includes("unavailable")
        ? "unavailable"
        : normalized.includes("integrity")
          ? "integrity"
          : "connection";
  const label = kind === "not-found" ? "Record not found" : kind === "conflict" ? "Request conflict" : kind === "integrity" ? "Integrity check" : kind === "unavailable" ? "Capability unavailable" : "Connection issue";
  return (
    <div className={`state-panel state-panel--error state-panel--${kind}`} role="alert">
      <div className="state-glyph" aria-hidden="true"><i />{kind === "integrity" ? <ShieldX /> : <AlertTriangle />}</div>
      <p className="eyebrow">{label}</p>
      <h2>Verified data is unavailable</h2>
      <p>{error.message}</p>
      {onRetry && (
        <button className="button button--secondary" type="button" onClick={onRetry}>
          <RefreshCw size={16} /> Retry
        </button>
      )}
    </div>
  );
}
