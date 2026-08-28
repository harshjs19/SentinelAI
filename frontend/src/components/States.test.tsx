import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
    rerender(<ErrorState error={new Error("Model is unavailable.")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Model is unavailable.");
    screen.getByRole("button", { name: /Retry/ }).click();
    expect(retry).toHaveBeenCalledOnce();
  });
});
