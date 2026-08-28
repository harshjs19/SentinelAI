import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { capabilities, evidence, machine, report } from "./test/fixtures";

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("dashboard routing and API rendering", () => {
  it("renders authoritative machines without inventing a health value", async () => {
    window.history.pushState({}, "", "/machines");
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return json({ status: "ok" });
      if (url.endsWith("/machines")) return json([machine]);
      return json({ detail: "not found" }, 404);
    }));
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: machine.name }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByText(machine.asset_type)).toBeInTheDocument();
    expect(screen.getByText(/Condition is shown only when a stored report exists/i)).toBeInTheDocument();
    expect(screen.queryByText(/Machine Health/i)).not.toBeInTheDocument();
  });

  it("keeps experimental and rejected lifecycle results visibly distinct", async () => {
    window.history.pushState({}, "", "/models");
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return json({ status: "ok" });
      if (url.endsWith("/capabilities/models")) return json({ models: capabilities });
      return json({ detail: "not found" }, 404);
    }));
    render(<App />);
    expect(await screen.findByText("audio_ast_rejected_v1")).toBeInTheDocument();
    expect(screen.getByText("Rejected Experiment")).toBeInTheDocument();
    expect(screen.getByText("Experimental")).toBeInTheDocument();
    expect(screen.getByText("Validated Baseline")).toBeInTheDocument();
  });

  it("opens stored report and evidence endpoints without reconstructing provenance", async () => {
    window.history.pushState({}, "", `/reports/${report.report_id}`);
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/health")) return json({ status: "ok" });
      if (url.endsWith(`/maintenance-reports/${report.report_id}/evidence`)) return json(evidence);
      if (url.endsWith(`/maintenance-reports/${report.report_id}`)) return json(report);
      return json({ detail: "not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Evidence Chain" })).toBeInTheDocument();
    expect(screen.getByText("timeseries_random_forest_utk_v1")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/evidence"))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/capabilities/models"))).toBe(false);
  });
});
