# ADR 0003: Exact producing-model provenance propagation

- Status: Accepted
- Date: 2026-08-26

## Context

Evidence Package V1 previously reconstructed model provenance from each Prediction's
modality and the model capability configured as the runtime default when packaging
occurred. That was safe only for an immediate in-process workflow where the current
default was necessarily the producer. A later default change could misattribute
historical Analysis evidence before persistence or report reconstruction.

Runtime configuration and execution provenance are different facts:

```text
runtime_default = model selected by current configuration
producing_model = exact model that produced this Prediction
```

Historical Evidence Packages and Maintenance Reports must preserve the latter without
consulting mutable current configuration.

## Decision

Bind every concrete runtime predictor to an immutable `ProducingModelContext`. The
context snapshots model ID, modality, lifecycle status, runtime-default status at
execution, validated scope, evaluation reference, and confidence semantics. It contains
no predictor, estimator, artifact, filesystem path, raw input, or credential.

`InferenceOrchestrator` returns an immutable `InferenceResult` containing the Prediction
and its producing context while preserving the existing Prediction-only EventBus event.
Decision Engine continues to receive only Predictions. Application orchestration retains
the contexts and supplies them explicitly to `EvidencePackageService`.

Evidence packaging requires exactly one producing context per Prediction modality. It
fails closed for missing provenance and rejects wrong, duplicate, or extra contexts. An
insufficient-evidence Analysis with no Predictions has no producing contexts. Evidence
model provenance is copied from the captured snapshot and never reconstructed from a
current runtime-default lookup.

## Rejected alternatives

- Add model lifecycle and scope fields to `Prediction` or `Analysis`.
- Reconstruct producing identity later from Prediction modality and current defaults.
- Put model selection or provenance resolution in Decision Engine.
- Add a new EventBus event solely to carry request-local context.
- Introduce a model/artifact registry, MLflow, training-run store, or invented artifact
  lineage before those systems exist.

## Consequences

- A later runtime-default change cannot silently rewrite historical producing identity.
- Evidence-bearing packaging fails when exact provenance is unavailable.
- Current prediction, analysis, capability API, and EventBus response/event contracts
  remain backward compatible.
- Evidence Package canonical identity continues to include the model snapshot, so a model
  identity change changes the package digest and derived ID.
- Static bindings still lack artifact digests, training-run identity, registry identity,
  and cryptographic attestation; those remain future MLOps concerns.
- The evidence chain is safe enough for persistence and server-owned historical workflow
  design to proceed as separate milestones, but no persistence is added here.
