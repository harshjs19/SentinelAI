import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { EmptyState, ErrorState, LoadingState } from "./States";

describe("intentional resource states", () => {
  it("renders an honest indeterminate loading state", () => {
    render(<LoadingState label="Preparing maintenance intelligence…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Preparing maintenance intelligence…");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("renders deliberate empty and safe error states", () => {
    const retry = vi.fn();
    const { rerender } = render(<EmptyState title="No reports yet" message="Run an analysis to create the first verified maintenance record." />);
    expect(screen.getByRole("heading", { name: "No reports yet" })).toBeInTheDocument();
    rerender(<ErrorState error={new Error("Unexpected end of JSON input at C:\\private\\snapshot.json")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Verified data could not be loaded. Retry the request.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("JSON");
    rerender(<ErrorState error={new ApiError("Required analysis infrastructure is unavailable.", 503)} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Required analysis infrastructure is unavailable.");
    screen.getByRole("button", { name: /Retry/ }).click();
    expect(retry).toHaveBeenCalledOnce();
  });
});
