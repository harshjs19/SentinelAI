# Runtime architecture

SentinelAI V1 is a modular monolith. Its `EventBus` is intentionally in-process and
coordinates local application behavior only.

- Subscribers receive only events published inside the same Python process.
- Handlers execute sequentially in registration order.
- Handler failures propagate to the publisher.
- There is no event durability, retry, replay, dead-letter queue, or cross-process
  broadcast.
- Each Uvicorn worker has its own `EventBus` instance. An event published in one worker
  is not delivered to subscribers in another worker.
- Redis does not carry inference events in the current architecture.

The authoritative server-owned evidence, retrieval, and Copilot path is:

```text
MaintenanceWorkflowService(typed single-modality request)
    -> authoritative Machine lookup
    -> modality inference -> InferenceResult(Prediction, ProducingModelContext)
    -> Decision Engine(Prediction) -> Analysis
    -> EvidencePackageService(Analysis, ProducingModelContext)
    -> Evidence Package -> Knowledge Retriever -> Retrieval Bundle
    -> MaintenanceCopilotService
        -> deterministic report path
        OR
        -> bounded LangGraph: generate -> validate -> one repair/fallback
    -> Maintenance Report
```

`MaintenanceWorkflowService` is a thin application orchestrator. Clients provide only a
machine ID, one typed modality source, a closed Copilot intent, and an optional bounded
question. The server derives source provenance from the exact samples or bytes used for
inference and constructs `Prediction`, `Analysis`, `EvidencePackage`, `RetrievalBundle`,
and `MaintenanceReport` internally. Those derived objects are not workflow inputs.

One execution is deliberately one modality, one Prediction, and one Analysis. It does
not combine Time-Series, Audio, Vision, and Thermal evidence. The Decision Engine's
`SINGLE_MODALITY_EVIDENCE` limitation remains visible through the final report, and CORA
multimodal fusion remains scientifically deferred.

`InferenceOrchestrator` binds each registered predictor to immutable producing-model
metadata and returns both in `InferenceResult`. `Prediction` and `Analysis` remain free of
model lifecycle metadata, and `DecisionEngine` still receives only Predictions. The
application layer retains the producing context for evidence construction in the same
workflow execution.
`EvidencePackageService` fails closed when an evidence-bearing Analysis lacks an exact
context; it does not reconstruct identity from the current runtime default.

`PredictionProduced` remains Prediction-only. No new provenance event was added because
the workflow is request-local and non-durable, and the application result envelope is
sufficient for explicit propagation.

Retriever V1 is an explicitly prepared internal component. The composition root resolves
its local assets lazily only when a validated workflow reaches retrieval; it does not
initialize on FastAPI startup, expose a public endpoint, or add an event/subscriber. The
Maintenance Copilot remains a bounded, request-local internal service. The default
application wiring supplies no generation provider, so deterministic paths work offline
and provider-required paths use the existing safe unavailable result. There is no public
maintenance endpoint, persistence, or workflow event. The Copilot graph has no retrieval,
tools, checkpointing, memory, or streaming. EventBus semantics are unchanged.

These boundaries are suitable while events coordinate synchronous, process-local V1
behavior. Before events trigger durable asynchronous workflows such as persisted
analyses, report generation, notifications, or external integrations—SentinelAI must
explicitly revisit durable event delivery and its operational guarantees.
