# Maintenance workflow persistence

## Boundary

SentinelAI persists only a complete `MaintenanceWorkflowResult` after the existing
workflow has produced and verified all four authoritative artifacts:

```text
Analysis -> EvidencePackage -> RetrievalBundle -> MaintenanceReport
```

`MaintenanceWorkflowPersistenceService` performs one final cross-artifact validation and
saves the chain in dependency order. It does not run inference, the Decision Engine,
retrieval, or Maintenance Copilot and does not alter artifact content. A workflow that
fails before it produces a verified complete result is not persisted. V1 has no partial
checkpoint or `WorkflowRun` state machine. Verified deterministic, generated, and
provider-unavailable fallback reports all use the same artifact contract.

## Transaction semantics

All four writes use one async SQLAlchemy session and one surrounding transaction.
Repository methods add/query/flush only; they never commit. The existing request-scoped
`get_session()` dependency, configured with FastAPI function scope, commits after the
path operation and before the response is sent, or rolls back when any operation raises.
Non-HTTP application callers must provide the equivalent outer commit/rollback boundary.

A failure while staging any later artifact therefore rolls back the Analysis,
EvidencePackage, RetrievalBundle, and MaintenanceReport together. Persistence does not
claim partial progress.

## Storage model

Four append-only PostgreSQL tables combine indexed relational metadata with a complete
validated JSONB payload:

- `analyses`: Analysis UUID, Machine FK, condition, status, creation time, internal
  payload schema version, and complete Analysis JSON.
- `evidence_packages`: authoritative package ID and unique full digest, Machine and
  Analysis FKs, creation time, schema version, and complete package JSON.
- `retrieval_bundles`: authoritative bundle digest, exact Evidence Package ID/full-digest
  binding, corpus digest, embedding model ID/revision, schema version, and complete bundle
  JSON including queries and selected chunks.
- `maintenance_reports`: report UUID and unique digest, Machine, Evidence Package, and
  Retrieval Bundle references, generation status/time, schema version, and complete
  report JSON.

Foreign keys use `RESTRICT`; historical artifacts are not cascade-deleted with a Machine.
Machine history is ordered by `generated_at DESC`, then `report_id DESC` as a stable
tie-breaker. There are no general update or delete methods for authoritative artifacts.

JSONB contains ordinary JSON only. It does not contain pickle, estimators, model
artifacts, raw samples, audio, images, thermal media, base64, filenames, or local paths.
The intentionally bounded Evidence Package source provenance remains hashes, sizes,
source kinds, modalities, and content types.

## Integrity and historical reads

Serialization and reconstruction are centralized in typed persistence mappers. Reads
reconstruct the authoritative domain/Pydantic types, require JSON to round-trip to the
exact schema, compare indexed columns with reconstructed content, and fail closed on any
mismatch. They then run:

- Analysis domain construction and cross-reference checks;
- `verify_evidence_package_digest()`;
- `verify_retrieval_bundle_digest()` and exact Evidence Package binding;
- `verify_maintenance_report()` against the stored package and bundle.

Loading a report returns its exact stored report, RetrievalBundle, EvidencePackage,
Analysis, and historical Machine snapshot. It never reruns ML, rebuilds producing-model
provenance from current defaults, consults the current corpus, reruns retrieval, or
invokes a generation provider. Corpus, embeddings, rankings, runtime model defaults, and
generator configuration can change without rewriting old history.

## Idempotency

Artifact-level idempotency is supported now. Replaying the exact same identity, digest,
metadata, and payload reuses the existing row. Reusing an identity with different content
raises an integrity conflict and never overwrites history. Distinct report IDs remain
distinct even when they refer to the same Evidence Package.

The internal maintenance report API now adds a separate request-level idempotency table.
It hashes the opaque `Idempotency-Key`, binds it to the exact semantic request, coordinates
concurrent claims with a bounded lease, and associates one completed request with its
report in the same final transaction as artifact persistence. Evidence Package identity
alone is still not used as request identity. See
[Internal maintenance report API](maintenance_report_api.md).

## Deferred concerns

There is no public maintenance report promotion, authentication/authorization layer,
retention/delete API, durable workflow event, or partial artifact checkpointing.
Persistence and request idempotency are not authorization boundaries. The internal/demo
routes must not be publicly exposed until authorization is added. The process-local
EventBus and all Copilot safety, retrieval, inference, and model behavior remain unchanged.
