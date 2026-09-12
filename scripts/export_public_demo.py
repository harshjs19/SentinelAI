"""Export an explicitly selected, read-only public-demo snapshot from SentinelAI."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from backend.app.schemas.capability import ModelCapabilitiesResponse
from backend.app.schemas.machine import MachineResponse
from backend.app.schemas.maintenance_report import (
    MaintenanceReportEvidenceResponse,
    MaintenanceReportResponse,
    MaintenanceReportSummaryResponse,
)

REPORT_PAGE_SIZE = 100
PROVENANCE = (
    "Demonstration records generated through SentinelAI simulation/replay workflow and "
    "exported from authoritative read endpoints."
)


def _get_json(client: httpx.Client, path: str) -> Any:
    response = client.get(path.lstrip("/"))
    response.raise_for_status()
    return response.json()


def _list_reports(
    client: httpx.Client,
    machine_id: UUID,
) -> list[MaintenanceReportSummaryResponse]:
    records: list[MaintenanceReportSummaryResponse] = []
    offset = 0
    adapter = TypeAdapter(list[MaintenanceReportSummaryResponse])
    while True:
        payload = _get_json(
            client,
            f"/machines/{machine_id}/maintenance-reports?limit={REPORT_PAGE_SIZE}&offset={offset}",
        )
        page = adapter.validate_python(payload)
        records.extend(page)
        if len(page) < REPORT_PAGE_SIZE:
            return records
        offset += len(page)


def build_snapshot(client: httpx.Client, selected_ids: set[UUID]) -> dict[str, Any]:
    machine_adapter = TypeAdapter(list[MachineResponse])
    available = machine_adapter.validate_python(_get_json(client, "/machines"))
    machines = [machine for machine in available if machine.id in selected_ids]
    missing = selected_ids.difference(machine.id for machine in machines)
    if missing:
        raise ValueError(f"Selected machine IDs were not returned by the API: {len(missing)}")

    capabilities = ModelCapabilitiesResponse.model_validate(
        _get_json(client, "/capabilities/models")
    )
    summaries_by_machine: dict[str, list[dict[str, Any]]] = {}
    reports: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}

    for machine in machines:
        summaries = _list_reports(client, machine.id)
        summaries_by_machine[str(machine.id)] = [
            summary.model_dump(mode="json") for summary in summaries
        ]
        for summary in summaries:
            report_id = str(summary.report_id)
            if report_id in reports:
                raise ValueError("A report was returned for more than one selected machine")
            report = MaintenanceReportResponse.model_validate(
                _get_json(client, f"/maintenance-reports/{report_id}")
            )
            report_evidence = MaintenanceReportEvidenceResponse.model_validate(
                _get_json(client, f"/maintenance-reports/{report_id}/evidence")
            )
            if (
                report.machine_id != machine.id
                or report.report_id != summary.report_id
                or report_evidence.report.report_id != summary.report_id
                or report_evidence.analysis.machine_id != machine.id
            ):
                raise ValueError("Historical report bindings do not match the selected machine")
            reports[report_id] = report.model_dump(mode="json")
            evidence[report_id] = report_evidence.model_dump(mode="json")

    return {
        "schema_version": "1",
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "environment": "PUBLIC DEMO",
        "read_only": True,
        "provenance": PROVENANCE,
        "machines": [machine.model_dump(mode="json") for machine in machines],
        "capabilities": capabilities.model_dump(mode="json"),
        "reports_by_machine": summaries_by_machine,
        "reports": reports,
        "evidence": evidence,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="SentinelAI API origin; it is never written to the snapshot.",
    )
    parser.add_argument(
        "--machine-id",
        action="append",
        required=True,
        type=UUID,
        help="Explicit machine UUID to export. Repeat for each reviewed demo machine.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("frontend/public/demo/snapshot.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_ids = set(args.machine_id)
    with httpx.Client(base_url=f"{args.api_base_url.rstrip('/')}/", timeout=30.0) as client:
        snapshot = build_snapshot(client, selected_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_count = len(snapshot["reports"])
    print(f"Exported {len(snapshot['machines'])} machines and {report_count} reports.")


if __name__ == "__main__":
    main()
