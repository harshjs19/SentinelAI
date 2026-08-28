import type { ReactNode } from "react";

export type BadgeTone = "positive" | "warning" | "neutral" | "danger" | "accent";

export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: BadgeTone;
  children: ReactNode;
}) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}
