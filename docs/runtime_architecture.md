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
Analysis -> Evidence Package -> Knowledge Retriever -> Retrieval Bundle
    -> MaintenanceCopilotService
        -> deterministic report path
        OR
        -> bounded LangGraph: generate -> validate -> one repair/fallback
    -> Maintenance Report
```

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
