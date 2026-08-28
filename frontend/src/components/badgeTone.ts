import type { BadgeTone } from "./StatusBadge";

export function conditionTone(condition: string): BadgeTone {
  if (condition === "normal") return "positive";
  if (condition === "abnormal") return "warning";
  return "neutral";
}

export function lifecycleTone(status: string): BadgeTone {
  if (status === "validated_baseline") return "positive";
  if (status === "experimental") return "warning";
  return "danger";
}
