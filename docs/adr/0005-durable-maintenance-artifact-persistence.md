# ADR 0005: Durable maintenance artifact persistence

- Status: Accepted
- Date: 2026-08-26

## Context

The server-owned workflow now produces one verified immutable result containing an
Analysis, EvidencePackage, RetrievalBundle, and MaintenanceReport. Historical review
must retain exactly what the workflow used. Reconstructing history through current model
defaults, current retrieval data, or another provider call would make old reports
mutable and unauditable.

V1 persists complete results only, so a separate workflow-run state machine is not needed
for partial progress or failure tracking. Public endpoint authorization and request
identity have not yet been designed.

## Decision

Persist the four verified artifacts atomically in one existing async SQLAlchemy
transaction. Use one append-only table per artifact with indexed relational identity and
references plus a complete validated JSONB payload. Repository methods flush but do not
commit; the outer request/application session owns commit and rollback.

Historical reads reconstruct authoritative typed artifacts from their stored payloads,
compare relational metadata, run the existing evidence, retrieval, and report integrity
verifiers, and fail closed on corruption. Reads never rerun inference, provenance lookup,
retrieval, or generation.

Support artifact-level idempotency: exact identity/content replay is safe, while identity
reuse with different content is a hard conflict. Report UUID remains the report identity;
reports are not deduplicated merely because they share evidence. Request-level
idempotency is deferred to the API milestone.

Use restrictive foreign keys so Machine deletion cannot casually erase history. Store no
raw source data or arbitrary Python objects. Do not introduce a `WorkflowRun` table,
partial checkpointing, public API, authorization system, or persistence events in V1.

## Rejected alternatives

- Rerun inference or retrieval to reconstruct historical reports.
- Rebuild producing-model provenance from current runtime defaults.
- Make evidence, retrieval, or report records mutable/updatable.
- Archive raw samples or source media in the database.
- Persist after every intermediate workflow step.
- Add a partial `WorkflowRun` state machine before complete-result requirements need it.
- Expose an immediate public report API without authorization and request idempotency.
- Store pickles, object representations, estimators, or generic opaque blobs.

## Consequences

- The complete verified chain either commits together or rolls back together.
- Old reports retain their exact Evidence Package, RetrievalBundle, model provenance,
  citations, generation provenance, and limitations despite later configuration changes.
- Corrupt or conflicting history is rejected rather than repaired or overwritten.
- JSONB avoids excessive relational decomposition while relational keys and indexes
  provide identity, history ordering, uniqueness, and referential defense.
- Public authorization, request-level idempotency, retention, and partial workflow
  recovery remain explicit future design work.
