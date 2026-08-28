import { apiRequest } from "./client";
import type { Machine } from "./types";

export function listMachines(signal?: AbortSignal): Promise<Machine[]> {
  return apiRequest<Machine[]>("/machines", { signal });
}

export function getMachine(machineId: string, signal?: AbortSignal): Promise<Machine> {
  return apiRequest<Machine>(`/machines/${encodeURIComponent(machineId)}`, { signal });
}

