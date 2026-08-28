import { AlertTriangle, Database, LoaderCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({ label = "Loading verified intelligence…" }: { label?: string }) {
  return (
    <div className="state-panel state-panel--loading" role="status">
      <div className="loading-orbit" aria-hidden="true">
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
      <Database aria-hidden="true" />
      <p className="eyebrow">No verified records</p>
      <h2>{title}</h2>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <AlertTriangle aria-hidden="true" />
      <p className="eyebrow">Unable to load</p>
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
