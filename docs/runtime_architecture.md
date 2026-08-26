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

The internal deterministic evidence, retrieval, and Copilot path is:

```text
Predictor binding -> InferenceResult(Prediction, ProducingModelContext)
    -> Decision Engine(Prediction) -> Analysis
    -> EvidencePackageService(Analysis, ProducingModelContext)
    -> Evidence Package -> Knowledge Retriever -> Retrieval Bundle
    -> MaintenanceCopilotService
        -> deterministic report path
        OR
        -> bounded LangGraph: generate -> validate -> one repair/fallback
    -> Maintenance Report
```

`InferenceOrchestrator` binds each registered predictor to immutable producing-model
metadata and returns both in `InferenceResult`. `Prediction` and `Analysis` remain free of
model lifecycle metadata, and `DecisionEngine` still receives only Predictions. The
application layer retains the producing contexts for later evidence construction.
`EvidencePackageService` fails closed when an evidence-bearing Analysis lacks an exact
context; it does not reconstruct identity from the current runtime default.

`PredictionProduced` remains Prediction-only. No new provenance event was added because
there is no current durable or asynchronous evidence workflow, and the application result
envelope is sufficient for explicit propagation.

Retriever V1 is an explicitly prepared internal component. It does not initialize on
FastAPI startup, expose a public endpoint, or add an event/subscriber. The Maintenance
Copilot has an explicitly constructed structured-generation provider and a bounded,
request-local internal orchestration service. It is not wired into application startup,
an API, persistence, or the EventBus. The graph has no retrieval, tools, checkpointing,
memory, or streaming. EventBus semantics are unchanged.

These boundaries are suitable while events coordinate synchronous, process-local V1
behavior. Before events trigger durable asynchronous workflows such as persisted
analyses, report generation, notifications, or external integrations—SentinelAI must
explicitly revisit durable event delivery and its operational guarantees.
