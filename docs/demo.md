# SentinelAI demo guide

This guide presents SentinelAI in five to eight minutes without fabricated data or a
provider key. It uses the real application, an external HTTP-only Edge Simulator, and a
persisted report. Have the model and retrieval artifacts from
[deployment.md](deployment.md) available before running the workflow.

## Prepare the demo

For normal Windows development, install dependencies once and start SentinelAI:

```powershell
uv sync
Set-Location frontend
npm ci
Set-Location ..
.\scripts\dev.ps1
```

The launcher starts or reuses PostgreSQL and development Redis, applies migrations,
starts FastAPI, waits for health, launches Vite, and opens the dashboard. No
`OPENAI_API_KEY` is required.

Create a compatible demonstration machine if the database does not already contain one:

```powershell
$body = @{ name = "Demo Motor"; asset_type = "rotating_electromechanical_system" } | ConvertTo-Json
$machine = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/machines" -ContentType "application/json" -Body $body
$machine.id
```

If a machine already exists, list it through the simulator and copy its UUID:

```powershell
uv run python -m edge_simulator machines
```

Run the bounded workflow:

```powershell
uv run python -m edge_simulator demo --machine-id <UUID>
```

The simulator prints links for the machine workspace and stored report. It sends a
deterministic Time-Series observation through HTTP, then retrieves the report, evidence,
and history through HTTP. It does not import backend services or connect to PostgreSQL.

For a controlled container deployment, set the API boundary before running the same
command:

```powershell
$env:SENTINELAI_API_BASE_URL = "http://127.0.0.1:8080/api"
uv run python -m edge_simulator demo --machine-id <UUID>
```

## Five-to-eight-minute walkthrough

1. **Start on Overview.** Let the Sentinel Core scene finish loading. Explain that the
   four nodes are independent available modules, not fused telemetry.
2. **Open Machines.** Show that the inventory comes from persisted machine records. No
   health or condition is invented for a machine without a stored report.
3. **Run the Edge Simulator.** Keep the dashboard visible beside the terminal. Execute
   the demo command and point out that the client uses HTTP only.
4. **Return to Machine Intelligence.** Refresh or open the URL printed by the simulator.
   Show the newest persisted report and its exact generation status.
5. **Open Finding Intelligence.** Read the model label and raw confidence semantics. State
   explicitly that confidence is not failure probability, severity, health, risk, or RUL.
6. **Show Scientific Boundaries.** Note the provisional/insufficient evidence semantics,
   null unsupported claims, and single-modality limitation.
7. **Show Evidence Chain.** Trace Source -> Analysis -> Evidence Package -> Retrieval
   Bundle -> Maintenance Report. This panel comes from the historical evidence endpoint.
8. **Show Producing Model provenance.** Point to model ID, lifecycle, validated scope, and
   confidence semantics captured during inference.
9. **Open Maintenance Reports.** Demonstrate that historical reads load stored artifacts;
   they do not rerun inference, retrieval, decision logic, or generation.
10. **Open Model Capabilities.** Contrast the validated Time-Series baseline with the
    experimental Audio/Vision/Thermal lines and the visible rejected AST experiment.
11. **Mention the negative CORA result.** Exact thermal-vibration alignment could not be
    reproduced, so frame-level fusion was not implemented.
12. **Close on architecture and deployment.** Show the README diagram or
    [runtime architecture](runtime_architecture.md), then mention tests, migrations,
    container health, and the local/controlled—not public—deployment verdict.

## Natural 5–7 minute narration

Use these as talking points rather than a script to memorize.

| Scene | Show | Key point |
| --- | --- | --- |
| 1 — Overview | Sentinel Core and four modality nodes | “SentinelAI turns one machine observation at a time into a stored, inspectable maintenance record. The modules are independent; V1 does not fuse modalities.” |
| 2 — Problem | Overview copy or README invariant | “Classifier confidence is useful model evidence, but it is not severity, health, failure probability, risk, or remaining life. The architecture preserves that distinction.” |
| 3 — External observation | Edge Simulator terminal | “This behaves like a device client. It creates or replays an observation and communicates only through HTTP—no backend imports or database shortcuts.” |
| 4 — Workflow result | Machine Intelligence and Finding Intelligence | “The server selected one model, produced a prediction, ran deterministic decision logic, and persisted the resulting Analysis. Unsupported claims remain null.” |
| 5 — Evidence | Evidence Chain and provenance panels | “The source digest, exact producing model, evidence package, retrieval bundle, and report are bound together. Opening this page reads stored lineage; it does not recompute it.” |
| 6 — Safe interpretation | Inspection Considerations and citations | “The Copilot is retrieval-bounded and non-directive. Output is validated, repaired at most once, and falls back safely when a provider is unavailable.” |
| 7 — Model governance | Model Capabilities | “Only Time-Series is a validated baseline. The other lanes display their experimental limits, and the AST result stays visible because it failed its promotion gate.” |
| 8 — Engineering boundary | Architecture/deployment diagram | “PostgreSQL owns durable history and idempotency. The EventBus is process-local, so the controlled deployment deliberately uses one worker. Public security controls remain future work.” |

## 90-second version

**0:00–0:15 — Problem.** Open Overview. “SentinelAI is an evidence-bounded industrial
machine-intelligence project. Its central rule is that model confidence is not failure
probability, severity, health, risk, or remaining useful life.”

**0:15–0:35 — Architecture.** Show the README flow. “One Time-Series, Audio, Vision, or
Thermal request produces a Prediction, deterministic Analysis, EvidencePackage,
RetrievalBundle, validated Maintenance Report, and atomic PostgreSQL record. V1 is
single-modality.”

**0:35–0:50 — Edge.** Run or show the Edge Simulator command. “The simulator is an
external HTTP client with deterministic simulation and explicit recorded replay. It
does not pretend a Raspberry Pi has been deployed.”

**0:50–1:10 — Evidence.** Open the created report and Evidence Chain. “Historical lineage
comes from stored verified artifacts. Reading this report reruns no model, retrieval, or
generation, and the exact producing-model context remains attached.”

**1:10–1:30 — Proof and limits.** Open Model Capabilities. “The UI distinguishes one
validated baseline, three experimental lines, and one rejected experiment. The stack has
682 passing backend tests with two optional real-encoder skips, 16 frontend tests, five
browser scenarios, and a validated local container deployment. It is not claimed to be
public-Internet ready.”

## Useful alternate demonstrations

```powershell
# Verify durable semantic replay behavior.
uv run python -m edge_simulator run idempotent_replay --machine-id <UUID>

# Exercise safe refusal of an operational-action question.
uv run python -m edge_simulator run high_impact_safe_request --machine-id <UUID>

# Exercise the no-provider fallback explicitly.
uv run python -m edge_simulator run provider_unavailable_fallback --machine-id <UUID>
```

Recorded Audio, Vision, and Thermal scenarios require an explicit local asset and the
corresponding compatible machine type. The assets remain local and are not included in
the repository.

## Demo integrity checklist

- Use a real persisted machine and the report created by the current run.
- Keep browser devtools, notifications, credentials, and local paths out of view.
- Do not call confidence a probability of failure or use it as a severity/risk score.
- Keep Inspection Considerations non-directive.
- Describe the dashboard 3D scenes as representational, not live telemetry or a digital twin.
- Do not claim a physical Raspberry Pi deployment, multimodal fusion, or public production readiness.
- If an artifact or dependency is unavailable, show the honest error/fallback instead of a fabricated state.
