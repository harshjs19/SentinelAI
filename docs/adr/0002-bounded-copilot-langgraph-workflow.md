# ADR 0002: Bounded Maintenance Copilot LangGraph workflow

- Status: Accepted
- Date: 2026-08-25

## Context

SentinelAI already has deterministic evidence/retrieval contracts, a strict structured
generation provider, one semantic safety validator, deterministic report assembly, and
safe fallback. The internal service needs a visible and testable transition model for
initial generation, validation, one possible repair, and finalization without creating an
open-ended agent or expanding model authority.

## Decision

Use LangGraph only as request-local bounded control flow for these nodes:

```text
generate_draft -> validate_draft -> finalize_report
                         |
                         v
                   repair_draft -> validate_draft
                         |
                         v
                   fallback_report
```

Provider failure may route directly from generation or repair to fallback. Deterministic
request integrity and policy routing occur before graph entry. Confidence, limitation,
unsupported, insufficient-evidence, and ungrounded paths do not enter the graph.

The workflow enforces at most one repair and therefore no more than two logical content
generation calls. Provider transport retries retain their independent Milestone 2 limit.
Every accepted draft uses the existing `MaintenanceSafetyValidator`, and every returned
report passes deterministic invariant verification.

The graph has no tools, retrieval, query rewriting, checkpointing, memory, streaming,
conversation state, database access, persistence, or EventBus behavior. Dependencies are
injected into the request-local workflow and are not serialized as graph state.

## Rejected alternatives

- Autonomous agent planning or multiple collaborating agents.
- Tool nodes, function calling, web/file search, or MCP.
- Retrieval, query planning, or query rewriting inside the graph.
- Checkpoint stores, resumable threads, or conversational memory.
- Unlimited self-correction or heuristic acceptance of invalid drafts.
- LangChain provider, prompt, retriever, or chain abstractions around existing SentinelAI
  components.

## Consequences

- The control flow and repair budget are explicit and independently testable.
- Deterministic request policy remains authoritative and avoids unnecessary provider use.
- Rejected generated content remains transient and cannot enter fallback reports.
- Programming and report-integrity failures remain visible rather than being mislabeled as
  provider outages.
- LangGraph introduces required transitive packages, but no checkpoint implementation or
  LangChain application abstraction is used.
