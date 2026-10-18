import { apiRequest } from "./client";
import { array, listDemoCapabilities, PUBLIC_DEMO, record, validateCapability } from "./demo";
import type { ModelCapabilitiesResponse } from "./types";

export function listModelCapabilities(signal?: AbortSignal): Promise<ModelCapabilitiesResponse> {
  if (PUBLIC_DEMO) return listDemoCapabilities();
  return apiRequest<ModelCapabilitiesResponse>("/capabilities/models", { signal }, (payload) => {
    const models = array(record(payload, "capabilities").models, "capabilities.models");
    models.forEach((value, index) => validateCapability(value, `capabilities.models[${index}]`));
  });
}

