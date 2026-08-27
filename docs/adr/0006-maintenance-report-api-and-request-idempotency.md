# ADR 0006: Maintenance report API and request-level idempotency

- Status: Accepted
- Date: 2026-08-27

## Context

SentinelAI already owns and verifies the complete single-modality maintenance workflow and
atomically persists its four derived artifacts. An internal dashboard needs a bounded way to
create reports and read exact history. Retries must not duplicate expensive inference,
retrieval, or generation, and concurrent workers must not both pass a check-then-run race.

Source transports differ by modality. Historical reports must remain tied to the exact model
and corpus evidence used at execution, while public authorization is not yet implemented.

## Decision

Expose four modality-specific POST endpoints. Clients provide only Machine identity, actual
source input, intent, an optional bounded question, and an opaque required
`Idempotency-Key`. The server constructs every Prediction, Analysis, EvidencePackage,
RetrievalBundle, and MaintenanceReport through `MaintenanceWorkflowService` and persists
complete verified results through `MaintenanceWorkflowPersistenceService`.

Use PostgreSQL-backed request idempotency. Store the SHA-256 key digest and a versioned
request digest covering Machine, modality, intent, normalized question, and exact source
identity/content type—not the raw key, source, filename, or question. Atomically reserve a
unique key digest in a short transaction, run the workflow without a long database
transaction, then persist artifacts and mark the reservation completed in one final
transaction.

Use only `PROCESSING` and `COMPLETED`, plus a claim token and five-minute lease. Matching
active duplicates return an in-progress conflict. Expired claims can be reclaimed, and
token-checked completion fences stale workers. Exact completed replay loads the stored
verified report and never reruns the workflow. A different request bound to the same key is
rejected.

Expose verified GET-by-report and bounded Machine history. Historical reads use existing
persistence mappers and verifiers and never consult current inference, model-default,
retrieval, corpus, or generator state.

Keep the API internal/demo only. Authorization remains a mandatory pre-public promotion
gate. Keep history append-only and defer retention/deletion. Do not add workflow events,
multimodal fusion, broad CORS, model changes, or new dependencies.

## Rejected alternatives

- One generic maintenance endpoint with an arbitrary modality payload.
- Client-supplied Prediction, EvidencePackage, RetrievalBundle, or report objects.
- In-memory-only locks or idempotency state, which do not coordinate workers.
- Check-then-run followed by insertion, which permits duplicate concurrent execution.
- A long PostgreSQL transaction around inference, retrieval, or provider latency.
- Report digest alone as request identity; it exists only after execution and does not bind
  the incoming request.
- Persisting raw keys, raw source data, filenames, paths, or question text for replay.
- Public unauthenticated promotion or a hard-coded shared-secret substitute.

## Consequences

- A fresh request returns one newly persisted verified report; exact replay returns that
  stored report without workflow work.
- The unique key digest and short atomic reservation coordinate concurrent processes without
  Redis or a process-local lock.
- Final transaction rollback cannot leave `COMPLETED` without a report. A crashed final
  attempt remains `PROCESSING` until bounded reclaim.
- History retains execution-time model provenance and stored citations across later runtime
  or corpus changes and fails closed on corruption.
- Public deployment remains blocked on real authorization. Upload-size enforcement and
  retention/delete policy remain explicit API-wide/future work.

