import { apiRequest } from "./client";
import { array, getDemoMachine, listDemoMachines, PUBLIC_DEMO, validateMachine } from "./demo";
import type { Machine } from "./types";

export function listMachines(signal?: AbortSignal): Promise<Machine[]> {
  if (PUBLIC_DEMO) return listDemoMachines();
  return apiRequest<Machine[]>("/machines", { signal }, (payload) => {
    array(payload, "machines").forEach((value, index) => validateMachine(value, `machines[${index}]`));
  });
}

export function getMachine(machineId: string, signal?: AbortSignal): Promise<Machine> {
  if (PUBLIC_DEMO) return getDemoMachine(machineId);
  return apiRequest<Machine>(`/machines/${encodeURIComponent(machineId)}`, { signal }, (payload) => validateMachine(payload, "machine"));
}

