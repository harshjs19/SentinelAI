# Edge device simulator and end-to-end demo runner

The repository-root `edge_simulator` package is a development and demonstration client
for SentinelAI's existing public HTTP API. It runs outside the backend architecture. It
does not import backend workflows, models, the Decision Engine, evidence/retrieval
internals, persistence, or the EventBus. SentinelAI remains authoritative for inference,
analysis, evidence construction, retrieval, report generation, validation, and durable
persistence.

## Start SentinelAI

From the repository root:

```powershell
.\scripts\dev.ps1
```

The simulator checks `GET /health` before other connected commands. If the API is not
reachable, it reports a concise startup hint. The default API base URL is
`http://127.0.0.1:8000`; override it without changing code:

```powershell
$env:SENTINELAI_API_BASE_URL = "http://127.0.0.1:8000"
```

HTTP connect/read/write/pool timeouts are centralized, and failed requests are not
retried automatically.

## Commands

Run these from the repository root so the package is importable:

```powershell
uv run python -m edge_simulator list
uv run python -m edge_simulator health
uv run python -m edge_simulator machines
uv run python -m edge_simulator run timeseries_healthy --machine-id <uuid>
uv run python -m edge_simulator run timeseries_fault_demo --machine-id <uuid>
uv run python -m edge_simulator report <report-uuid>
uv run python -m edge_simulator evidence <report-uuid>
uv run python -m edge_simulator history --machine-id <uuid>
uv run python -m edge_simulator demo --machine-id <uuid>
```

If `--machine-id` is omitted, the simulator selects a machine only when the API returns
exactly one. With zero or multiple machines it stops and asks for an explicit choice. It
never creates machines automatically. If a disposable local demo machine is needed, use
the existing public contract deliberately:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/machines `
  -ContentType application/json `
  -Body '{"name":"Edge Simulator Demo","asset_type":"rotating_electromechanical_system"}'
```

## Scenario registry

| Scenario | Input label | Modality | Purpose |
| --- | --- | --- | --- |
| `timeseries_healthy` | `SIMULATED INPUT` | time-series | Deterministic bounded healthy-profile raw measurements |
| `timeseries_fault_demo` | `SIMULATED INPUT` | time-series | Deterministic elevated-signal profile; no diagnosis is assumed client-side |
| `audio_replay` | `RECORDED REPLAY` | audio | Explicit local WAV replay |
| `vision_replay` | `RECORDED REPLAY` | vision | Explicit local JPEG/PNG replay |
| `thermal_replay` | `RECORDED REPLAY` | thermal | Explicit local thermographic JPEG/PNG replay |
| `idempotent_replay` | `SIMULATED INPUT` | time-series | Exact same request and UUID key twice; same report ID is required |
| `high_impact_safe_request` | `SIMULATED INPUT` | time-series | Verify the deterministic high-impact safe fallback |
| `provider_unavailable_fallback` | `SIMULATED INPUT` | time-series | Verify the configured no-provider fallback |

Every new semantic request receives a fresh UUID `Idempotency-Key`. The key value is not
printed. The replay scenario deliberately reuses one key with byte-equivalent JSON and
requires the second response to carry the API replay signal and the same report ID.

Each request contains exactly one modality. The module names describe available
SentinelAI analysis lanes, not multimodal fusion or CORA synchronization.

## Media replay and privacy

Media scenarios require an explicit `--asset` path and perform local existence, size,
and extension checks before upload. Accepted inputs are bounded to 25 MiB. The client
streams the selected file in multipart form and never prints or base64-encodes its
contents. See [`demo_assets/README.md`](../demo_assets/README.md). The local audio,
vision, and thermal directories are targeted by `.gitignore`; no benchmark binary or
recorded media belongs in Git.

Example:

```powershell
uv run python -m edge_simulator run audio_replay --machine-id <uuid> `
  --asset demo_assets/audio/local-bearing-sample.wav
```

## Default demo and readback

`demo` performs this bounded sequence:

1. health check;
2. explicit/safe machine selection;
3. deterministic `SIMULATED INPUT` time-series acquisition;
4. maintenance-report creation through HTTP;
5. stored report GET;
6. authoritative evidence-lineage GET;
7. machine-history GET;
8. dashboard verification guidance.

Add `--include-idempotency` to run the exact-replay scenario too. Report output presents
the backend's actual condition, generation/fallback status, narrative, limitations, and
producing-model lifecycle. Evidence output is limited to the safe metadata returned by
`GET /maintenance-reports/{report_id}/evidence`: source metadata, analysis binding,
Evidence Package identity, Retrieval Bundle identity, report binding, corpus digest, and
embedding identity. It does not reconstruct provenance or expose raw sources, retrieval
chunks, local paths, prompts, environment variables, or payload bytes.

Use the report ID printed by the demo to verify Machine Detail, Maintenance History,
Maintenance Report, and Evidence Chain in the existing dashboard. The simulator does not
modify, embed, or automate the dashboard.

## Scientific and operational boundaries

- Model confidence is not failure probability, fault severity, health, operational
  risk, or remaining useful life.
- The simulator never predicts an expected output and never derives those unavailable
  quantities.
- Inspection Considerations are displayed as non-directive report content.
- Experimental and rejected model lifecycle states are displayed exactly as returned by
  the backend.
- The current workflow is single-modality. There is no fusion, modality synchronization,
  fake multimodal telemetry, streaming, daemon, MQTT, Kafka, WebSocket, or SSE behavior.
- `PHYSICAL LIVE SENSOR` is explicitly unsupported. No Raspberry Pi or hardware library
  is required or imported.
- A future `RaspberryPiSource` may implement `EdgeObservationSource` in a deployment-
  specific package, but it must preserve input labeling, single-modality requests,
  bounded acquisition, and the same external HTTP boundary. This milestone makes no
  Raspberry Pi deployment claim.
- No `OPENAI_API_KEY` is needed. The provider-unavailable path uses SentinelAI's existing
  deterministic, validated fallback; the simulator neither calls a provider nor creates
  a substitute report.

This tool is intended for local development and controlled demos. Authentication,
transport security, production device identity, fleet enrollment, secret management,
observability, and deployment/CI hardening remain outside this milestone.

