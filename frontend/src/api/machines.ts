import { apiRequest } from "./client";
import { getDemoMachine, listDemoMachines, PUBLIC_DEMO } from "./demo";
import type { Machine } from "./types";

export function listMachines(signal?: AbortSignal): Promise<Machine[]> {
  if (PUBLIC_DEMO) return listDemoMachines();
  return apiRequest<Machine[]>("/machines", { signal });
}

export function getMachine(machineId: string, signal?: AbortSignal): Promise<Machine> {
  if (PUBLIC_DEMO) return getDemoMachine(machineId);
  return apiRequest<Machine>(`/machines/${encodeURIComponent(machineId)}`, { signal });
}

