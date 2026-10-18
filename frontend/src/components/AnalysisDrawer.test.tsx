import { cleanup, fireEvent, render as baseRender, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MaintenanceReport } from "../api/types";
import { capabilities, machine, report } from "../test/fixtures";
import { AnalysisDrawer } from "./AnalysisDrawer";
import { MaintenanceSubmissionProvider } from "./MaintenanceSubmissionProvider";

function render(ui: ReactElement) {
  return baseRender(<MemoryRouter><MaintenanceSubmissionProvider>{ui}</MaintenanceSubmissionProvider></MemoryRouter>);
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// Real one-channel WAV and 1x1 image bytes; the backend decoders accept these formats.
const riffWav = "UklGRmQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const rifxWav = "UklGWAAAAGRXQVZFZm10IAAAABAAAQABAAA+gAAAfQAAAgAQZGF0YQAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const pngImage = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC";
const jpegImage = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD5/ooooA//2Q==";

function mediaFile(bytes: string, name: string): File {
  return new File([Uint8Array.from(Buffer.from(bytes, "base64"))], name, { type: "application/octet-stream" });
}

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

    fireEvent.change(screen.getByRole("textbox", { name: /Time-series samples/ }), {
      target: { value: JSON.stringify([
        { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
        { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
      ]) },
    });
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

  it("does not expose JSON parser errors", async () => {
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    fireEvent.change(screen.getByRole("textbox", { name: /Time-series samples/ }), { target: { value: "[" } });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter samples as a valid JSON array.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("Unexpected end");
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
    const file = new File([new Uint8Array([82, 73, 70, 70, 0, 0, 0, 0, 87, 65, 86, 69])], "bearing.wav", { type: "application/octet-stream" });
    await userEvent.upload(screen.getByLabelText(/Select audio source/i), file);
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("does not submit unsupported or empty files despite browser MIME claims", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "Audio" }));
    const input = screen.getByLabelText(/Select audio source/i);
    expect(input).toHaveAttribute("accept", ".wav,audio/wav,audio/x-wav");
    await userEvent.upload(input, new File([new Uint8Array([1, 2, 3])], "recording.wav", { type: "audio/wav" }));
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(screen.getByRole("alert")).toHaveTextContent("WAV");
    expect(fetchMock).not.toHaveBeenCalled();

    await userEvent.upload(input, new File([], "empty.wav", { type: "audio/wav" }));
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(screen.getByRole("alert")).toHaveTextContent("empty");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("offers only PNG/JPEG images and clears the selected source when modality changes", async () => {
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL() { return "blob:test-preview"; }
      static revokeObjectURL() { return undefined; }
    });
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "Vision" }));
    const input = screen.getByLabelText(/Select vision source/i);
    expect(input).toHaveAttribute("accept", ".png,.jpg,.jpeg,image/png,image/jpeg");
    await userEvent.upload(input, new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], "inspection.png", { type: "image/png" }));
    expect(screen.getByText("inspection.png")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Thermal" }));
    expect(screen.getByLabelText(/Select thermal source/i)).toHaveValue("");
    expect(screen.getByText("Select thermal source")).toBeInTheDocument();
  });

  it.each([
    ["Vision", "camera.png", [137, 80, 78, 71, 13, 10, 26, 10]],
    ["Thermal", "surface.jpg", [255, 216, 255, 224]],
  ])("allows supported %s source bytes even with generic MIME metadata", async (label, name, bytes) => {
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL() { return "blob:test-preview"; }
      static revokeObjectURL() { return undefined; }
    });
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void url;
      void init;
      return new Response(JSON.stringify(report), { status: 201 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: label }));
    const input = screen.getByLabelText(new RegExp(`Select ${label.toLowerCase()} source`, "i"));
    await userEvent.upload(input, new File([new Uint8Array(bytes)], name, { type: "application/octet-stream" }));
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects unsupported image bytes despite a PNG filename and clears the error on cancellation", async () => {
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL() { return "blob:test-preview"; }
      static revokeObjectURL() { return undefined; }
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "Vision" }));
    const input = screen.getByLabelText(/Select vision source/i);
    await userEvent.upload(input, new File([new Uint8Array([1, 2, 3])], "misnamed.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("PNG or JPEG");
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { files: [] } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Select vision source")).toBeInTheDocument();
  });

  it.each([
    ["RIFF WAV", "Audio", "bearing.wav", riffWav],
    ["RIFX WAV", "Audio", "bearing.wav", rifxWav],
    ["WAV with an unusual name", "Audio", "bearing.data", riffWav],
    ["WAV without an extension", "Audio", "bearing", riffWav],
    ["PNG with an unusual name", "Vision", "inspection.data", pngImage],
    ["JPEG with an unusual name", "Thermal", "inspection.data", jpegImage],
  ])("submits supported %s bytes regardless of filename metadata", async (_case, modality, name, bytes) => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void url;
      void init;
      return new Response(JSON.stringify(report), { status: 201 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: modality }));
    const input = screen.getByLabelText(new RegExp(`Select ${modality.toLowerCase()} source`, "i"));
    const file = mediaFile(bytes, name);
    await userEvent.upload(input, file, { applyAccept: false });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).body).toBeInstanceOf(FormData);
    expect(((fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData).get("file")).toBe(file);
  });

  it("retains one idempotent request across repeated malformed successful responses", async () => {
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      if (requests.length < 3) return new Response(JSON.stringify({ report_id: report.report_id }), { status: 201 });
      return new Response(JSON.stringify(report), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(value: MaintenanceReport) => void>();
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={onCreated} />);
    const samples = screen.getByRole("textbox", { name: /Time-series samples/ });
    fireEvent.change(samples, { target: { value: JSON.stringify([
      { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
      { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
    ]) } });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(await screen.findByRole("button", { name: "Retry exact request" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("could not be confirmed");
    expect(samples).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Copilot intent" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Retry exact request" }));
    expect(await screen.findByRole("button", { name: "Retry exact request" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry exact request" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(report));
    expect(requests).toHaveLength(3);
    expect(new Set(requests.map((request) => (request.headers as Record<string, string>)["Idempotency-Key"])).size).toBe(1);
    expect(new Set(requests.map((request) => String(request.body))).size).toBe(1);
  });

  it("keeps an unresolved request pending if its first replay is still processing", async () => {
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      if (requests.length === 1) return new Response(JSON.stringify({ report_id: report.report_id }), { status: 201 });
      if (requests.length === 2) return new Response(JSON.stringify({ detail: "An identical maintenance request is already processing" }), { status: 409 });
      return new Response(JSON.stringify(report), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn<(value: MaintenanceReport) => void>();
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={onCreated} />);
    fireEvent.change(screen.getByRole("textbox", { name: /Time-series samples/ }), { target: { value: JSON.stringify([
      { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
      { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
    ]) } });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await userEvent.click(await screen.findByRole("button", { name: "Retry exact request" }));
    expect(await screen.findByRole("button", { name: "Retry exact request" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry exact request" }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(report));
    expect(requests).toHaveLength(3);
    expect(new Set(requests.map((request) => (request.headers as Record<string, string>)["Idempotency-Key"])).size).toBe(1);
    expect(new Set(requests.map((request) => String(request.body))).size).toBe(1);
  });

  it("treats explicit backend validation rejection as definitive and permits changed input", async () => {
    const requests: RequestInit[] = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      requests.push(init ?? {});
      if (requests.length === 1) return new Response(JSON.stringify({ detail: "Rejected" }), { status: 422 });
      return new Response(JSON.stringify(report), { status: 201 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisDrawer open machineId={machine.id} machineName={machine.name} capabilities={capabilities} onClose={() => undefined} onCreated={() => undefined} />);
    const samples = screen.getByRole("textbox", { name: /Time-series samples/ });
    fireEvent.change(samples, { target: { value: JSON.stringify([
      { ch1_bias: 1, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
      { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
    ]) } });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("submitted input is not valid");
    expect(screen.queryByRole("button", { name: "Retry exact request" })).not.toBeInTheDocument();
    expect(samples).toBeEnabled();
    fireEvent.change(samples, { target: { value: JSON.stringify([
      { ch1_bias: 2, ch1_derivedPk: 2, ch1_direct: 3, ch1_directRMS: 4, ch1_velocityPk: 5, ch1_velocityRMS: 6 },
      { ch1_bias: 7, ch1_derivedPk: 8, ch1_direct: 9, ch1_directRMS: 10, ch1_velocityPk: 11, ch1_velocityRMS: 12 },
    ]) } });
    await userEvent.click(screen.getByRole("button", { name: "Create verified report" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect((requests[0]?.headers as Record<string, string>)["Idempotency-Key"]).not.toBe((requests[1]?.headers as Record<string, string>)["Idempotency-Key"]);
    expect(requests[0]?.body).not.toBe(requests[1]?.body);
  });
});
