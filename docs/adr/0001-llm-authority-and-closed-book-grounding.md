# ADR 0001: LLM authority and closed-book grounding boundary

- Status: Accepted
- Date: 2026-08-25

## Context

SentinelAI has deterministic predictors, a Decision Engine, an Evidence Package, and a
source-attributed Retriever. A future Maintenance Copilot will improve presentation and
explanation, but generated language must not become a second source of machine truth or
silently expand the supported maintenance claims.

## Decision

- `Analysis` and `EvidencePackage` remain authoritative for condition, findings,
  confidence, health, risk, limitations, claim support, and producing-model provenance.
- `RetrievalBundle` is the closed-book technical knowledge ceiling for generated
  maintenance content.
- An LLM may summarize deterministic facts and produce bounded source-backed explanations
  and inspection considerations. It may not diagnose independently.
- Generated technical finding explanations and inspection considerations require
  application-assigned citations compatible with the source finding and asset scope.
- Anomaly findings cannot be converted into physical faults, and one physical finding
  cannot absorb another fault category.
- High-impact operational actions are prohibited, even when a retrieved source discusses
  them.
- Failure probability, severity, health, risk, and remaining useful life are unavailable
  unless authoritative upstream contracts explicitly support them. Generated text cannot
  infer them from labels or confidence.
- A deterministic validator must accept generated content before report assembly. Unsafe
  or ungrounded output fails closed and may be replaced by a deterministic same-schema
  fallback.

## Consequences

- The generated draft deliberately excludes authoritative analysis fields and source
  metadata.
- Retrieval and citation assignment happen outside the future generator.
- Final reports are assembled deterministically from accepted text and trusted inputs.
- The system sacrifices open-ended conversational flexibility and some potentially useful
  general maintenance knowledge in exchange for auditability and a narrow safety surface.
- Metadata-compatible citations still require human evaluation for semantic relevance;
  deterministic validation does not prove factual correctness.
- Provider selection and LangGraph orchestration remain separate future decisions.
