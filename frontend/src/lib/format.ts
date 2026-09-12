export function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatRelative(value: string): string {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const absolute = Math.abs(seconds);
  if (absolute < 60) return formatter.format(seconds, "second");
  if (absolute < 3600) return formatter.format(Math.round(seconds / 60), "minute");
  if (absolute < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
  return formatter.format(Math.round(seconds / 86400), "day");
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function shortId(value: string, leading = 10, trailing = 6): string {
  if (value.length <= leading + trailing + 1) return value;
  return `${value.slice(0, leading)}…${value.slice(-trailing)}`;
}

export function confidenceLabel(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

const LIMITATION_LABELS: Record<string, string> = {
  uncalibrated_confidence: "Raw / uncalibrated confidence",
  fault_severity_unavailable: "Fault severity not determined",
  risk_context_unavailable: "Operational risk context unavailable",
  single_modality_evidence: "Single-modality evidence",
};

export function limitationLabel(value: string): string {
  return LIMITATION_LABELS[value] ?? humanize(value);
}

