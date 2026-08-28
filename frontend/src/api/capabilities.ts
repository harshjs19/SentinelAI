import { apiRequest } from "./client";
import type { ModelCapabilitiesResponse } from "./types";

export function listModelCapabilities(signal?: AbortSignal): Promise<ModelCapabilitiesResponse> {
  return apiRequest<ModelCapabilitiesResponse>("/capabilities/models", { signal });
}

