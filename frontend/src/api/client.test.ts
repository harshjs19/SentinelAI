import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("central API error handling", () => {
  it.each([
    [400, "Unsupported input"],
    [404, "Machine not found"],
    [409, "already processing"],
    [422, "Submitted fields are invalid"],
    [503, "Model unavailable"],
  ])("renders safe backend detail for %s", async (status, detail) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/test")).rejects.toMatchObject({ status });
  });

  it("suppresses server filesystem detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Model missing at C:\\private\\model.joblib" }), { status: 500, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("/test")).rejects.toEqual(expect.objectContaining({ message: "The server could not safely complete this request." }));
  });

  it("marks network failures as transport uncertain", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await expect(apiRequest("/test")).rejects.toEqual(expect.objectContaining({ status: 0, transportUncertain: true }));
  });
});
