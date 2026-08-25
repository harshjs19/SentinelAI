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

When a future application workflow needs retrieval or reporting evidence, it may
synchronously build the immutable internal contract after Analysis:

```text
Analysis -> Evidence Package -> future Retriever / Maintenance Copilot
```

The Retriever and Maintenance Copilot do not exist yet. V1 adds no Evidence Package
event/subscriber and does not change EventBus semantics.

These boundaries are suitable while events coordinate synchronous, process-local V1
behavior. Before events trigger durable asynchronous workflows such as persisted
analyses, report generation, notifications, or external integrations—SentinelAI must
explicitly revisit durable event delivery and its operational guarantees.
