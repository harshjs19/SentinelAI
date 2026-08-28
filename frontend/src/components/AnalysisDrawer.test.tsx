import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MaintenanceReport } from "../api/types";
import { capabilities, machine, report } from "../test/fixtures";
import { AnalysisDrawer } from "./AnalysisDrawer";

afterEach(() => vi.unstubAllGlobals());

describe("AnalysisDrawer", () => {
  it("sends only user input and reuses the idempotency key for a transport-uncertain retry", async () => {
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      if (requests.length === 1) throw new TypeError("network uncertainty");
      return new Response(JSON.stringify(report), { status: 201, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(value: MaintenanceReport) => void>();
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={onCreated} />);

    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(await screen.findByRole("button", { name: "Retry exact request" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry exact request" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(report));

    expect(requests).toHaveLength(2);
    const firstRequest = requests[0]!;
    const secondRequest = requests[1]!;
    const firstHeaders = firstRequest.headers as Record<string, string>;
    const secondHeaders = secondRequest.headers as Record<string, string>;
    expect(firstHeaders["Idempotency-Key"]).toBeTruthy();
    expect(secondHeaders["Idempotency-Key"]).toBe(firstHeaders["Idempotency-Key"]);
    expect(secondRequest.body).toBe(firstRequest.body);
    const payload = JSON.parse(String(firstRequest.body)) as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual(["intent", "question", "samples"]);
    expect(payload).not.toHaveProperty("prediction");
    expect(payload).not.toHaveProperty("analysis");
    expect(payload).not.toHaveProperty("evidence_package");
    expect(payload).not.toHaveProperty("retrieval_bundle");
    expect(payload).not.toHaveProperty("producing_model_context");
  });

  it("uploads media as the original browser File in multipart form data", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void url;
      void init;
      return new Response(JSON.stringify(report), { status: 201, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "Audio" }));
    const file = new File([new Uint8Array([1, 2, 3])], "bearing.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText(/Select audio source/i), file);
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });
});
