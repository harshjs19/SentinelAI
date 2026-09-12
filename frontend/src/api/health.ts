import { apiRequest } from "./client";
import { PUBLIC_DEMO } from "./demo";

export function getBackendHealth(signal?: AbortSignal): Promise<{ status: string }> {
  if (PUBLIC_DEMO) return Promise.resolve({ status: "demo" });
  return apiRequest<{ status: string }>("/health", { signal });
}

