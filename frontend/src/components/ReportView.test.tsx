import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { evidence, report } from "../test/fixtures";
import { ReportView } from "./ReportView";

describe("ReportView", () => {
  it("renders bounded scientific semantics and historical provenance", () => {
    render(<ReportView report={report} evidence={evidence} />);

    expect(screen.getAllByText("Abnormal").length).toBeGreaterThan(0);
    expect(screen.getByText("0.910")).toBeInTheDocument();
    expect(screen.getByText("Raw model confidence — not failure probability.")).toBeInTheDocument();

    const claimGrid = screen.getByLabelText("Scientific claim availability");
    expect(within(claimGrid).getByText("Failure probability").nextElementSibling).toHaveTextContent("Not estimated");
    expect(within(claimGrid).getByText("Fault severity").nextElementSibling).toHaveTextContent("Not determined");
    expect(within(claimGrid).getByText("Health").nextElementSibling).toHaveTextContent("Not determined");
    expect(within(claimGrid).getByText("Operational risk").nextElementSibling).toHaveTextContent("Not determined");
    expect(within(claimGrid).getByText("Remaining useful life").nextElementSibling).toHaveTextContent("Not estimated");

    expect(screen.getByRole("heading", { name: "Inspection Considerations" })).toBeInTheDocument();
    expect(screen.getByText("Raw / uncalibrated confidence")).toBeInTheDocument();
    expect(screen.getByText("Single-modality evidence")).toBeInTheDocument();
    expect(screen.getByText("timeseries_random_forest_utk_v1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence Chain" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence Package" })).toBeInTheDocument();
    expect(screen.getByText(/semantic support remains subject to human review/i)).toBeInTheDocument();
  });

  it("treats a safe fallback and unsupported high-impact request as a valid report", () => {
    render(<ReportView report={report} evidence={evidence} />);
    expect(screen.getByText("Fallback report")).toBeInTheDocument();
    expect(screen.getByText(/interface adds no operational advice/i)).toBeInTheDocument();
    expect(screen.queryByText(/AI failed/i)).not.toBeInTheDocument();
    expect(screen.getByText(/No shutdown or continued-operation decision is supported/i)).toBeInTheDocument();
  });
});
