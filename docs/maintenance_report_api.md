# Internal maintenance report API

## Status and boundary

The maintenance report API is an internal/demo interface over the existing server-owned,
single-modality workflow. **Do not expose it publicly without authorization.** Authorization
is a separate pre-public deployment gate; this milestone does not add authentication, broad
CORS, static shared secrets, or any other substitute for authorization.

Clients supply only a Machine UUID, one actual modality source, a `CopilotIntent`, an
optional question, and an opaque `Idempotency-Key`. The server alone runs:

```text
source -> inference -> Analysis -> EvidencePackage -> RetrievalBundle
       -> MaintenanceReport -> atomic durable persistence
```

Clients cannot submit a Prediction, Finding, Analysis, model identity, EvidencePackage,
RetrievalBundle, report, report digest, source digest, risk, health score, or severity as an
authoritative input. Each request remains single-modality; no multimodal fusion is performed.

## Creation endpoints

All creation endpoints require the `Idempotency-Key` request header:

| Endpoint | Body |
|---|---|
| `POST /machines/{machine_id}/maintenance-reports/timeseries` | JSON: typed `samples`, `intent`, optional `question` |
| `POST /machines/{machine_id}/maintenance-reports/audio` | multipart: `file`, `intent`, optional `question` |
| `POST /machines/{machine_id}/maintenance-reports/vision` | multipart: `file`, `intent`, optional `question` |
| `POST /machines/{machine_id}/maintenance-reports/thermal` | multipart: `file`, `intent`, optional `question` |

Fresh completion returns `201 Created`. An exact completed replay returns `200 OK`, the
same stored report, and `Idempotent-Replay: true`. The response is a bounded projection of
the verified `MaintenanceReport`: authoritative analysis fields, narrative, limitations,
safe citation metadata, producing-model provenance captured at execution, safety outcome,
generation metadata, and disclaimer. It omits persistence JSONB details, internal retrieval
IDs and hashes, local paths, source data, prompts, and provider responses.

The existing inference routes have no explicit application-level byte limit for multipart
uploads. That API-wide gap remains documented rather than introducing a separate upload
subsystem in this milestone. Each maintenance media route reads the upload once and reuses
the same immutable bytes for the request fingerprint, inference, and source provenance.

## Request-level idempotency

`Idempotency-Key` is opaque, nonblank, at most 200 Unicode characters, and may not contain
Unicode control/format/surrogate/private-use/unassigned characters. SentinelAI neither logs
nor stores the raw value. PostgreSQL stores only its SHA-256 digest.

The versioned request digest binds:

- Machine UUID and modality;
- `CopilotIntent` and the same normalized optional question used by Copilot;
- source kind, content type, size, and SHA-256 identity;
- fingerprint version `maintenance_request_v1`.

For media, the source hash covers the exact uploaded bytes passed to inference. It excludes
the filename, path, base64, and upload metadata that do not affect interpretation. For
time-series data, it covers the exact canonical structured sample snapshot passed to the
workflow. Raw source and question text are not stored in the idempotency table.

The database atomically claims the unique key digest in a short transaction. Inference,
retrieval, and possible generation run after that transaction commits and without a long
PostgreSQL transaction. A second active duplicate receives `409 Conflict` and does not run
the workflow. Reusing a key for a different request digest also receives `409 Conflict`.

Claims use `PROCESSING` and `COMPLETED` states, an unguessable claim token, and a five-minute
lease. An expired matching claim may be atomically reclaimed. Token-checked completion and
release prevent an old worker from completing or deleting a reclaimed claim. Ordinary
workflow failure releases the owned claim for immediate retry. If the final transaction
fails, both artifacts and `COMPLETED` roll back; the durable `PROCESSING` claim becomes
retryable after lease expiry. The final transaction stages the verified artifact chain and
marks the claim completed with its report UUID together.

A completed exact replay loads the stored, digest-verified historical chain. It performs
zero inference, Decision Engine, retrieval, and generator calls and creates no duplicate
artifact rows.

## Historical reads

`GET /maintenance-reports/{report_id}` returns the verified stored report or `404` when the
report is unknown. A corrupted stored chain fails closed with a safe `500` response. The
read never reruns inference, consults current model defaults or current corpus state, reruns
retrieval, or invokes a provider.

`GET /machines/{machine_id}/maintenance-reports` first verifies that the Machine exists and
then returns concise report summaries. `limit` defaults to 20 and is bounded to 1–100;
`offset` defaults to zero. Ordering is stable: `generated_at DESC`, then `report_id DESC`.
Unknown Machines return `404` without querying their history.

V1 history is append-only. There is no DELETE route, cascade deletion, or retention policy;
retention/delete policy is deferred. Machine foreign keys remain restrictive.

## Availability and safety behavior

Known boundary failures use safe responses: missing Machine `404`; invalid input/key `4xx`;
key conflict or active processing `409`; unavailable model or retrieval infrastructure
`503`; and stored/workflow integrity failure `500`. Responses do not include stack traces,
database messages, raw provider errors, environment values, secrets, or filesystem paths.

`EXPLAIN_CONFIDENCE` and `EXPLAIN_LIMITATIONS` remain deterministic and need no provider.
Provider-required intents with no configured generator persist and return the existing
verified `GENERATION_UNAVAILABLE` fallback. High-impact questions such as shutdown requests
bypass the provider and persist the verified `UNSUPPORTED_REQUEST` fallback. The existing
`MaintenanceSafetyValidator` remains the only semantic safety validator; this API does not
bypass or weaken it.

