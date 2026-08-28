import { apiRequest } from "./client";

export function getBackendHealth(signal?: AbortSignal): Promise<{ status: string }> {
  return apiRequest<{ status: string }>("/health", { signal });
}

