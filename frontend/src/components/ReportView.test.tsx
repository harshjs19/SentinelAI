import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { evidence, report } from "../test/fixtures";
import { ReportView } from "./ReportView";

describe("ReportView", () => {
  it("renders bounded scientific semantics and historical provenance", () => {
    render(<ReportView report={report} evidence={evidence} />);

    expect(screen.getAllByText("Abnormal").length).toBeGreaterThan(0);
    expect(screen.getByText("91.0%")).toBeInTheDocument();
    expect(screen.getByText("Raw / uncalibrated classifier confidence")).toBeInTheDocument();
    expect(screen.getByText(/Not failure probability, fault severity, machine health/i)).toBeInTheDocument();

    const boundaries = screen.getByLabelText("Scientific claim boundaries");
    expect(boundaries).toHaveTextContent("Failure probability was not inferred");
    expect(boundaries).toHaveTextContent("Fault severity was not inferred");
    expect(boundaries).toHaveTextContent("Machine health was not inferred");
    expect(boundaries).toHaveTextContent("Operational risk was not inferred");
    expect(boundaries).toHaveTextContent("Remaining useful life is not produced");

    expect(screen.getByRole("heading", { name: "Inspection Considerations" })).toBeInTheDocument();
    expect(screen.getByText("Raw / uncalibrated confidence")).toBeInTheDocument();
    expect(screen.getByText("Single-modality evidence")).toBeInTheDocument();
    expect(screen.getAllByText("timeseries_random_forest_utk_v1").length).toBeGreaterThan(0);
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
