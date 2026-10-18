import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes, useParams } from "react-router-dom";

import type { MaintenanceReport } from "../api/types";
import { capabilities, machine, report } from "../test/fixtures";
import { AnalysisDrawer } from "./AnalysisDrawer";
import { MaintenanceSubmissionProvider } from "./MaintenanceSubmissionProvider";
import { useMaintenanceSubmission } from "./maintenanceSubmissionContext";

const machineB = "33333333-3333-4333-8333-333333333333";
const samples = JSON.stringify([
  { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
  { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
]);

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Workspace({ onCreated }: { onCreated: (machineId: string, value: MaintenanceReport) => void }) {
  const { machineId = "" } = useParams();
  return <AnalysisDrawer key={machineId} open machineId={machineId} machineName={machineId} capabilities={capabilities} onClose={() => undefined} onCreated={(value) => onCreated(machineId, value)} />;
}

function OperationProbe() {
  const { operation } = useMaintenanceSubmission();
  return <output data-testid="operation">{JSON.stringify({
    status: operation?.status,
    retainsSubmission: operation !== null && "submission" in operation,
    reportId: operation?.status === "succeeded" ? operation.report.report_id : null,
  })}</output>;
}

function renderRoutes(onCreated: (machineId: string, value: MaintenanceReport) => void, showOperation = false) {
  return render(
    <MemoryRouter initialEntries={[`/machines/${machine.id}`]}>
      <MaintenanceSubmissionProvider>
        {showOperation && <OperationProbe />}
        <nav>
          <Link to={`/machines/${machine.id}`}>Go to machine A</Link>
          <Link to={`/machines/${machineB}`}>Go to machine B</Link>
        </nav>
        <Routes><Route path="/machines/:machineId" element={<Workspace onCreated={onCreated} />} /></Routes>
      </MaintenanceSubmissionProvider>
    </MemoryRouter>,
  );
}

async function submitOnA() {
  fireEvent.change(screen.getByRole("textbox", { name: /Time-series samples/ }), { target: { value: samples } });
  await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
}

describe("route-independent maintenance submission", () => {
  it("retains one key and payload through an initial 409 and repeated 409 responses", async () => {
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      return Promise.resolve(requests.length < 3
        ? new Response(JSON.stringify({ detail: "An identical maintenance request is already processing" }), { status: 409 })
        : new Response(JSON.stringify(report), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(machineId: string, value: MaintenanceReport) => void>();
    renderRoutes(onCreated);
    await submitOnA();

    for (let index = 0; index < 2; index += 1) {
      const retry = await screen.findByRole("button", { name: "Retry exact request" });
      expect(screen.getByRole("textbox", { name: /Time-series samples/ })).toBeDisabled();
      await userEvent.click(retry);
    }
    await waitFor(() => expect(onCreated).toHaveBeenCalledExactlyOnceWith(machine.id, report));
    expect(requests).toHaveLength(3);
    expect(new Set(requests.map((item) => (item.headers as Record<string, string>)["Idempotency-Key"])).size).toBe(1);
    expect(new Set(requests.map((item) => String(item.body))).size).toBe(1);
  });

  it("does not navigate or invoke obsolete callbacks when a valid POST completes after repeated machine switches", async () => {
    let resolveFirst!: (response: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveFirst = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(machineId: string, value: MaintenanceReport) => void>();
    renderRoutes(onCreated);
    await submitOnA();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", { name: "Analyzing..." })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Analyzing..." }));
    expect(fetchMock).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("link", { name: "Go to machine B" }));
    fireEvent.click(screen.getByRole("link", { name: "Go to machine A" }));
    fireEvent.click(screen.getByRole("link", { name: "Go to machine B" }));

    await act(async () => resolveFirst(new Response(JSON.stringify(report), { status: 201 })));
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("complete");
    expect(screen.queryByRole("button", { name: "Create verified report" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("link", { name: "Go to machine A" }));
    expect(screen.getByRole("status")).toHaveTextContent("report was created while this view was inactive");
    await userEvent.click(screen.getByRole("button", { name: "Open created report" }));
    expect(onCreated).toHaveBeenCalledExactlyOnceWith(machine.id, report);
  });

  it("preserves the exact request through late malformed success, 409 processing, and transport uncertainty", async () => {
    let resolveFirst!: (response: Response) => void;
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      if (requests.length === 1) return new Promise<Response>((resolve) => { resolveFirst = resolve; });
      if (requests.length === 2) return Promise.resolve(new Response(JSON.stringify({ detail: "An identical maintenance request is already processing" }), { status: 409 }));
      if (requests.length === 3) return Promise.reject(new TypeError("offline"));
      return Promise.resolve(new Response(JSON.stringify(report), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(machineId: string, value: MaintenanceReport) => void>();
    renderRoutes(onCreated);
    await submitOnA();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("link", { name: "Go to machine B" }));
    await act(async () => resolveFirst(new Response(JSON.stringify({ report_id: report.report_id }), { status: 201 })));
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("unresolved");
    expect(screen.queryByRole("button", { name: "Create verified report" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Go to machine A" }));
    for (let index = 0; index < 3; index += 1) {
      await userEvent.click(screen.getByRole("button", { name: "Retry exact request" }));
      if (index < 2) expect(await screen.findByRole("button", { name: "Retry exact request" })).toBeInTheDocument();
    }
    await waitFor(() => expect(onCreated).toHaveBeenCalledExactlyOnceWith(machine.id, report));
    expect(requests).toHaveLength(4);
    expect(new Set(requests.map((item) => (item.headers as Record<string, string>)["Idempotency-Key"])).size).toBe(1);
    expect(new Set(requests.map((item) => String(item.body))).size).toBe(1);
  });

  it("retains the original browser File and key when transport fails after navigation", async () => {
    let rejectFirst!: (reason: Error) => void;
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      if (requests.length === 1) return new Promise<Response>((_resolve, reject) => { rejectFirst = reject; });
      return Promise.resolve(new Response(JSON.stringify(report), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(machineId: string, value: MaintenanceReport) => void>();
    renderRoutes(onCreated);
    await userEvent.click(screen.getByRole("button", { name: "Audio" }));
    const file = new File([new Uint8Array([82, 73, 70, 70, 0, 0, 0, 0, 87, 65, 86, 69])], "bearing.data", { type: "application/octet-stream" });
    await userEvent.upload(screen.getByLabelText(/Select audio source/i), file, { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("link", { name: "Go to machine B" }));
    await act(async () => rejectFirst(new TypeError("offline")));
    expect(screen.getByRole("alert")).toHaveTextContent("unresolved");
    fireEvent.click(screen.getByRole("link", { name: "Go to machine A" }));
    await userEvent.click(screen.getByRole("button", { name: "Retry exact request" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledExactlyOnceWith(machine.id, report));
    expect(requests).toHaveLength(2);
    expect((requests[1]?.headers as Record<string, string>)["Idempotency-Key"])
      .toBe((requests[0]?.headers as Record<string, string>)["Idempotency-Key"]);
    for (const request of requests) {
      const body = request.body as FormData;
      expect(body.get("file")).toBe(file);
      expect(body.get("intent")).toBe("summarize_analysis");
    }
  });

  it("releases the submission File after a late confirmed upload while retaining the completed report", async () => {
    let resolveFirst!: (response: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveFirst = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(machineId: string, value: MaintenanceReport) => void>();
    renderRoutes(onCreated, true);
    await userEvent.click(screen.getByRole("button", { name: "Audio" }));
    const file = new File([new Uint8Array([82, 73, 70, 70, 0, 0, 0, 0, 87, 65, 86, 69])], "bearing.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText(/Select audio source/i), file);
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(JSON.parse(screen.getByTestId("operation").textContent ?? "")).toMatchObject({ status: "submitting", retainsSubmission: true });

    fireEvent.click(screen.getByRole("link", { name: "Go to machine B" }));
    await act(async () => resolveFirst(new Response(JSON.stringify(report), { status: 201 })));
    expect(onCreated).not.toHaveBeenCalled();
    expect(JSON.parse(screen.getByTestId("operation").textContent ?? "")).toEqual({
      status: "succeeded", retainsSubmission: false, reportId: report.report_id,
    });
    fireEvent.click(screen.getByRole("link", { name: "Go to machine A" }));
    await userEvent.click(screen.getByRole("button", { name: "Open created report" }));
    expect(onCreated).toHaveBeenCalledExactlyOnceWith(machine.id, report);
  });

  it("releases a definitively rejected initial request after navigation", async () => {
    let resolveFirst!: (response: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveFirst = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(machineId: string, value: MaintenanceReport) => void>();
    renderRoutes(onCreated);
    await submitOnA();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("link", { name: "Go to machine B" }));
    await act(async () => resolveFirst(new Response(JSON.stringify({ detail: "Invalid input" }), { status: 422 })));
    expect(onCreated).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Create verified report" })).toBeEnabled();
  });
});
