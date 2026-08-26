# ADR 0004: Server-owned maintenance workflow composition

- Status: Accepted
- Date: 2026-08-26

## Context

SentinelAI already had independently tested machine lookup, modality inference, exact
producing-model provenance, deterministic decision/evidence construction, retrieval, and
bounded Maintenance Copilot services. Without one authoritative application boundary, a
future caller could be tempted to assemble trusted derived objects or mix evidence and
retrieval results itself.

The four modalities come from different datasets and physical systems. CORA does not
provide sufficient frame-level alignment evidence for scientifically defensible
multimodal fusion.

## Decision

Add one thin `MaintenanceWorkflowService` that accepts a typed single-modality source
request and composes existing services in this order:

```text
Machine lookup -> modality inference -> InferenceResult
    -> DecisionService -> Analysis
    -> EvidencePackageService -> verified EvidencePackage
    -> KnowledgeRetriever -> verified, package-bound RetrievalBundle
    -> MaintenanceCopilotService -> verified MaintenanceReport
```

The workflow derives source provenance from the exact structured sample snapshot or media
bytes passed to inference. It passes `InferenceResult.prediction` to DecisionService and
passes `InferenceResult.producing_model` separately to EvidencePackageService. It never
reconstructs producing identity from a later runtime default.

Clients cannot provide Prediction, Analysis, EvidencePackage, or RetrievalBundle to this
boundary. One execution produces one Prediction and one Analysis from one modality;
`SINGLE_MODALITY_EVIDENCE` remains intact. Model and retriever assets are resolved lazily.
The default composition uses no generation provider, preserving offline deterministic and
safe provider-unavailable behavior.

Persistence, transactions, a public endpoint, and new workflow events are deferred until
this internal boundary is proven. Copilot remains downstream of completed retrieval and
cannot invoke inference or retrieval.

## Rejected alternatives

- Let clients compose authoritative Evidence Packages or Retrieval Bundles.
- Give Copilot tools for inference, retrieval, or query rewriting.
- Expose an immediate public maintenance-report endpoint.
- Design persistence and transactions before proving the application boundary.
- Force Time-Series, Audio, Vision, and Thermal into a synthetic fused conclusion.
- Use LangGraph or another orchestration framework for the application workflow.

## Consequences

- Source, model, evidence, retrieval, and report identities remain bound end to end.
- Machine-not-found and upstream failures stop downstream work; invariant failures remain
  visible rather than becoming generated fallback content.
- Existing inference validation, Decision Engine rules, retrieval ranking, Copilot request
  policy, `MaintenanceSafetyValidator`, and EventBus semantics remain authoritative.
- The result is immutable and request-local, contains no raw source payload, and is not
  persisted.
- Public API, transaction, authorization, idempotency, and retention design remain future
  work.
