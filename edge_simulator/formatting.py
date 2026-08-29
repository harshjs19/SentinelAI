import re
from collections.abc import Iterable, Mapping

from edge_simulator.models import MachineRecord, ScenarioOutcome
from edge_simulator.scenarios import ScenarioDefinition

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def format_health(status: str, base_url: str) -> str:
    return _section("API HEALTH", (f"Status: {_clean(status)}", f"Endpoint: {_clean(base_url)}"))


def format_scenarios(scenarios: Iterable[ScenarioDefinition]) -> str:
    lines: list[str] = []
    for scenario in scenarios:
        lines.extend(
            (
                scenario.name,
                f"  Input: {scenario.input_label.value}",
                f"  Modality: {scenario.modality.value}",
                f"  {scenario.description}",
            )
        )
    return _section("AVAILABLE SCENARIOS", lines)


def format_machines(machines: Iterable[MachineRecord]) -> str:
    rows = list(machines)
    if not rows:
        return _section("MACHINES", ("No machines are registered.",))
    lines: list[str] = []
    for machine in rows:
        lines.extend(
            (
                f"{machine.name} [{machine.asset_type}]",
                f"  ID: {machine.machine_id}",
            )
        )
    return _section("MACHINES", lines)


def format_outcome(outcome: ScenarioOutcome) -> str:
    receipt = outcome.receipt
    lines = [
        f"Scenario: {outcome.scenario_name}",
        f"Input classification: {outcome.observation.input_label.value}",
        f"Single modality: {outcome.observation.modality.value}",
        f"HTTP status: {receipt.status_code}",
        f"Report ID: {receipt.report_id}",
        "Idempotency-Key: generated for this semantic request (value not displayed)",
    ]
    if receipt.replayed:
        lines.append("Idempotent replay: verified by API response header")
    lines.extend(outcome.notes)
    return _section("SCENARIO RESULT", lines) + "\n\n" + format_report(receipt.document)


def format_report(document: Mapping[str, object]) -> str:
    analysis = _mapping(document.get("analysis"))
    narrative = _mapping(document.get("narrative"))
    limitations = _mapping(document.get("limitations"))
    lines = [
        f"Report ID: {_value(document.get('report_id'))}",
        f"Machine ID: {_value(document.get('machine_id'))}",
        f"Generated at: {_value(document.get('generated_at'))}",
        f"Generation status: {_value(document.get('generation_status'))}",
        f"Fallback reason: {_value(document.get('fallback_reason'))}",
        f"Request disposition: {_value(document.get('request_disposition'))}",
        f"Condition: {_value(analysis.get('condition'))}",
        f"Analysis status: {_value(analysis.get('status'))}",
        "",
        "Executive summary:",
        f"  {_value(narrative.get('executive_summary'))}",
    ]
    findings = _sequence(analysis.get("findings"))
    lines.append("")
    lines.append("Findings (model confidence is model-specific):")
    if not findings:
        lines.append("  None reported")
    for item in findings:
        finding = _mapping(item)
        lines.append(
            "  "
            f"{_value(finding.get('code'))}: condition={_value(finding.get('condition'))}, "
            f"confidence={_value(finding.get('confidence'))}, "
            f"kind={_value(finding.get('confidence_kind'))}"
        )
    lines.extend(
        (
            "",
            "Scientific boundary:",
            "  Model confidence is not failure probability, severity, health, "
            "operational risk, or RUL.",
            "  No unavailable quantity is inferred by the simulator.",
        )
    )
    considerations = _sequence(narrative.get("inspection_considerations"))
    lines.append("")
    lines.append("Inspection Considerations (non-directive):")
    if not considerations:
        lines.append("  None reported")
    for item in considerations:
        consideration = _mapping(item)
        lines.append(f"  - {_value(consideration.get('text'))}")
    unavailable = _sequence(limitations.get("unavailable_claims"))
    lines.append("")
    lines.append("Unavailable claims:")
    lines.extend(f"  - {_value(item)}" for item in unavailable) if unavailable else lines.append(
        "  None reported"
    )
    models = _sequence(document.get("producing_models"))
    lines.append("")
    lines.append("Producing model metadata recorded by the backend:")
    if not models:
        lines.append("  None reported")
    for item in models:
        model = _mapping(item)
        lines.extend(
            (
                f"  Model ID: {_value(model.get('model_id'))}",
                f"    Modality: {_value(model.get('modality'))}",
                f"    Lifecycle: {_value(model.get('status'))}",
                f"    Validated scope: {_value(model.get('validated_scope'))}",
                f"    Confidence semantics: {_value(model.get('confidence_semantics'))}",
            )
        )
    return _section("MAINTENANCE REPORT", lines)


def format_evidence(document: Mapping[str, object]) -> str:
    report = _mapping(document.get("report"))
    analysis = _mapping(document.get("analysis"))
    package = _mapping(document.get("evidence_package"))
    bundle = _mapping(document.get("retrieval_bundle"))
    lines = [
        "Stored historical lineage (authoritative backend readback):",
        f"Report ID: {_value(report.get('report_id'))}",
        f"Report digest: {_value(report.get('report_digest_sha256'))}",
        f"Report schema: {_value(report.get('schema_version'))}",
        f"Analysis ID: {_value(analysis.get('analysis_id'))}",
        "Analysis condition/status: "
        f"{_value(analysis.get('condition'))} / {_value(analysis.get('status'))}",
        f"Evidence Package ID: {_value(package.get('package_id'))}",
        f"Evidence Package digest: {_value(package.get('package_digest_sha256'))}",
        f"Evidence Package schema: {_value(package.get('schema_version'))}",
        f"Retrieval Bundle digest: {_value(bundle.get('retrieval_bundle_digest_sha256'))}",
        f"Retrieval Bundle schema: {_value(bundle.get('schema_version'))}",
        f"Corpus digest: {_value(bundle.get('corpus_digest_sha256'))}",
        f"Embedding model: {_value(bundle.get('embedding_model_id'))}",
        f"Embedding revision: {_value(bundle.get('embedding_model_revision'))}",
        "Sources (safe metadata only):",
    ]
    sources = _sequence(document.get("sources"))
    if not sources:
        lines.append("  None reported")
    for item in sources:
        source = _mapping(item)
        lines.extend(
            (
                f"  {_value(source.get('modality'))} / {_value(source.get('source_kind'))}",
                f"    SHA-256: {_value(source.get('sha256'))}",
                f"    Bytes: {_value(source.get('size_bytes'))}",
                f"    Content type: {_value(source.get('content_type'))}",
            )
        )
    return _section("EVIDENCE CHAIN", lines)


def format_history(items: Iterable[Mapping[str, object]]) -> str:
    rows = list(items)
    if not rows:
        return _section("MAINTENANCE HISTORY", ("No stored reports were returned.",))
    lines: list[str] = []
    for item in rows:
        lines.extend(
            (
                f"{_value(item.get('generated_at'))} | {_value(item.get('condition'))}",
                f"  Report ID: {_value(item.get('report_id'))}",
                f"  Generation: {_value(item.get('generation_status'))}",
                f"  Summary: {_value(item.get('executive_summary'))}",
            )
        )
    return _section("MAINTENANCE HISTORY", lines)


def format_dashboard_guidance(machine: MachineRecord, report_id: str) -> str:
    return _section(
        "DASHBOARD VERIFICATION",
        (
            "Open the dashboard URL reported by .\\scripts\\dev.ps1.",
            f"Machine: {machine.name} ({machine.machine_id})",
            f"Stored report: {report_id}",
            "Verify Machine Detail, Maintenance History, Report, and Evidence Chain views.",
        ),
    )


def _section(title: str, lines: Iterable[str]) -> str:
    safe_lines = [_clean(str(line)) for line in lines]
    return "\n".join((title, "=" * len(title), *safe_lines))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _value(value: object) -> str:
    if value is None or value == "":
        return "not available"
    return _clean(str(value))


def _clean(value: str) -> str:
    return _CONTROL_CHARACTERS.sub("?", value)
