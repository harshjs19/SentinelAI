import { apiRequest } from "./client";
import { listDemoCapabilities, PUBLIC_DEMO } from "./demo";
import type { ModelCapabilitiesResponse } from "./types";

export function listModelCapabilities(signal?: AbortSignal): Promise<ModelCapabilitiesResponse> {
  if (PUBLIC_DEMO) return listDemoCapabilities();
  return apiRequest<ModelCapabilitiesResponse>("/capabilities/models", { signal });
}

