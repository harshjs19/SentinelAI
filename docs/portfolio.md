# SentinelAI portfolio and interview notes

This file is a compact source for resume tailoring, portfolio copy, and technical
interviews. Metrics are limited to tracked evaluations and final repository gates.

## Resume bullets

### A. ML Engineer

- Built four independently governed industrial ML baselines across Time-Series, Audio,
  Vision, and Thermal data, with frozen evaluation protocols and explicit lifecycle states.
- Achieved 0.9418 macro F1 on the UTK blocked chronological Time-Series test while
  documenting the one-recording-per-class generalization limit.
- Preserved weak and negative evidence: near-chance MIMII Audio ROC AUC (0.5213), failed
  AST promotion, and CORA speed-shift Thermal macro F1 (0.1291) remained visible rather
  than being tuned away.
- Implemented exact producing-model provenance and confidence semantics so classifier
  output cannot silently become failure probability, severity, health, or risk.

### B. Software / Backend Engineer

- Built a FastAPI/PostgreSQL modular monolith that atomically persists Analysis,
  EvidencePackage, RetrievalBundle, MaintenanceReport, and durable semantic idempotency.
- Designed server-owned workflow boundaries and historical evidence APIs that read
  verified stored lineage without rerunning inference, retrieval, or generation.
- Added request-scoped transactions, migration-gated deployment, safe readiness,
  correlation IDs, bounded structured logs, and unprivileged CPU-only containers.
- Verified 682 passing backend tests with two optional real-encoder skips, plus
  API-restart persistence/idempotency and an external HTTP-only Edge Simulator against
  the containerized stack.

### C. AI / Applied ML Engineer

- Built an evidence-bounded maintenance interpretation workflow combining single-modality
  ML, deterministic decision logic, digest-bound retrieval, constrained generation, and
  post-generation safety validation.
- Implemented a closed-book Maintenance Copilot with citation checks, non-directive output,
  one repair attempt, and deterministic fallback when generation is invalid or unavailable.
- Exposed model lifecycle, scientific limitations, exact provenance, and rejected
  experiments in a React/TypeScript dashboard with WebGL and reduced-motion fallbacks.
- Delivered an external device-style demo from simulated observation through persisted
  report and dashboard, requiring no provider key or claimed Raspberry Pi deployment.

## Portfolio descriptions

### Short (64 words)

SentinelAI is an evidence-bounded industrial machine-intelligence platform supporting
independent Time-Series, Audio, Vision, and Thermal analysis. It turns one model output at
a time into deterministic findings, provenance-aware evidence, retrieval-bounded
maintenance interpretation, and a durable PostgreSQL report. A FastAPI backend, external
HTTP Edge Simulator, and React dashboard expose exact historical lineage, model lifecycle,
negative experiments, and the scientific distinction between confidence, severity,
health, failure probability, and risk.

### Medium (176 words)

SentinelAI explores what happens after an industrial ML model returns a prediction. Four
independent analysis lines—Time-Series, Audio, Vision, and Thermal—use frozen evaluation
protocols and explicit lifecycle states. V1 runs one modality per analysis; it does not
claim fused inference or field validation. A deterministic Decision Engine converts model
labels into bounded findings while refusing to derive severity, health, failure
probability, operational risk, or remaining useful life from raw confidence.

The FastAPI application owns the complete workflow: authoritative machine lookup,
inference, source hashing, exact producing-model capture, immutable EvidencePackage
construction, digest-bound retrieval, constrained Maintenance Copilot execution, safety
validation, and atomic PostgreSQL persistence. Historical evidence endpoints reload the
stored chain without recomputation. Durable semantic idempotency survives API restarts.

The React/TypeScript dashboard presents machine history, scientific boundaries, Evidence
Chain, provenance, and model governance—including weak and rejected experiments. An
external HTTP-only Edge Simulator exercises deterministic simulation and recorded replay
without backend imports, direct database access, a provider key, or unsupported Raspberry
Pi claims. The controlled Docker deployment uses CPU-only PyTorch, migration gating,
readiness checks, correlation IDs, structured request logs, and one worker because the
EventBus is process-local.

### Long (349 words)

SentinelAI is an evidence-bounded industrial machine-intelligence project built around a
simple concern: a classifier score is often presented as if it were a maintenance
decision. In reality, model confidence, physical fault severity, machine health, future
failure probability, operational risk, and remaining useful life are different claims
that require different evidence. SentinelAI makes that distinction an architectural
invariant rather than a UI disclaimer.

The project contains four independent ML lines. A UTK Time-Series fault classifier is the
only validated baseline within its declared blocked chronological protocol. MIMII DG
Audio, VisA PCB1 Vision, and CORA Thermal models remain experimental because their domain
shift or threshold behavior limits the evidence. A frozen-AST Audio experiment is retained
as rejected after missing a predeclared promotion score. CORA thermal-vibration frame
fusion was not implemented because exact cross-sensor alignment could not be reproduced
from the released metadata. These results remain visible in tracked evaluation artifacts
and the dashboard.

For each request, FastAPI selects one modality and the Inference Orchestrator returns both
a Prediction and its exact producing-model context. The deterministic Decision Engine
creates an Analysis with explicit limitations and null unsupported claims. The server
then hashes the source, constructs an immutable EvidencePackage, retrieves from a curated
local knowledge corpus, binds results and embedding identity into a RetrievalBundle, and
runs a constrained Maintenance Copilot. Generated output is closed-book, citation-bound,
non-directive, validated after generation, repaired at most once, and replaced by a safe
fallback when necessary.

The complete verified chain is committed atomically to PostgreSQL. Historical report and
evidence endpoints verify and return the stored artifacts without rerunning inference,
decision logic, retrieval, or generation. Durable semantic idempotency prevents duplicate
reports across concurrency and process restart.

A React/TypeScript dashboard presents the workflow through Machine Intelligence,
Maintenance Reports, Evidence Lineage, and Model Governance views. Its representational 3D
graphics do not claim live telemetry, fusion, or a physical digital twin. The external
Edge Simulator uses only HTTP and supports deterministic synthetic Time-Series inputs and
explicit local media replay.

The controlled Docker topology includes PostgreSQL, one-shot migrations, a single-worker
FastAPI service, and unprivileged Nginx. CPU-only PyTorch avoids unused CUDA dependencies;
model and retrieval artifacts remain explicit external mounts. Tests cover backend,
scientific contracts, persistence, UI behavior, and browser fallbacks. Public deployment
would still require authentication, TLS, device identity, rate limiting, retention,
secret management, backups, and durable multi-instance event delivery.

## Interview narrative

### Why did you build SentinelAI?

I wanted to explore the engineering gap between a model prediction and a maintenance
artifact someone could inspect later. The core problem was semantic: keeping confidence
from quietly turning into severity or risk while still producing a useful, traceable
workflow.

### What was the hardest engineering problem?

Maintaining one verified chain across inference, deterministic analysis, source and model
provenance, retrieval, generation, validation, persistence, and historical reads. Every
layer had to preserve exact identity without letting clients submit derived facts or
letting current configuration rewrite history.

### What did you deliberately not build?

I did not add unsupported health/risk formulas, forced CORA fusion, public authentication,
streaming, distributed events, a second LLM provider, or a claimed Raspberry Pi
deployment. Each would require evidence or operational requirements that V1 does not have.

### Why no Kafka?

Current events coordinate sequential work inside one process. Kafka would add deployment,
delivery, schema, and failure semantics without a V1 asynchronous consumer. The current
limitation is explicit: one worker. A durable broker becomes justified when work must
survive process boundaries or run asynchronously.

### Why no multimodal fusion?

The datasets represent different machines and experimental contexts. Even CORA's thermal
and vibration streams lacked enough published timing evidence for exact frame alignment.
Combining them anyway would create an attractive result with an unverifiable evidence
path.

### Why separate confidence from severity and risk?

Confidence describes model behavior under a declared calibration or classifier. Severity
describes physical extent; risk also needs failure likelihood and consequence. Mapping one
to the others without measured evidence would be a semantic error, not a product feature.

### Why preserve rejected models?

An explicit promotion gate is meaningful only if failed candidates remain inspectable.
The rejected AST experiment records what was tried, which metric governed the decision,
and why the runtime default did not change.

### Why exact historical provenance?

Runtime defaults evolve. A historical report must identify the model that actually
produced its prediction, not whichever model is configured when someone opens the page.
Capturing context during inference prevents that reconstruction error.

### Why is EvidencePackage server-owned?

If clients could submit predictions, analyses, source hashes, or model identity, the
server could persist a coherent-looking but unverifiable chain. The server derives every
downstream artifact from the exact request input and authoritative machine record.

### Why one worker?

The current EventBus is in-process. Multiple workers would create isolated subscriber
domains. One worker is the honest deployment choice until durable cross-process delivery
is designed.

### Why an Edge Simulator instead of claiming Raspberry Pi deployment?

The important contract is the device/API boundary. The simulator proves that boundary
with deterministic and replayable observations over HTTP. A Pi adapter can later replace
the source, but hardware performance, installation, and device identity have not been
tested.

### What would you build next for public production?

Authentication and authorization, TLS, device enrollment/identity, rate limits, managed
secrets, retention/deletion controls, backups, hardened ingress, artifact distribution,
and multi-instance workflow delivery. Field data and calibration would be prerequisites
for stronger scientific claims.

## Hard problems solved

1. **Confidence-to-risk leakage:** encoded unavailable claims in domain and report
   contracts instead of relying on presentation copy.
2. **Exact producing-model provenance:** captured execution-time identity, lifecycle,
   scope, and confidence semantics before prediction left the orchestrator.
3. **Durable request idempotency:** tied semantic request identity to persisted results
   across concurrency and API restart.
4. **Reproducible artifact chain:** gave evidence, retrieval, and report payloads stable
   canonical identities and verification rules.
5. **Bounded LLM behavior:** constrained prompts, citations, report schema, validation,
   one repair, and safe fallback.
6. **Negative CORA alignment result:** stopped before training when exact frame mapping
   could not be reproduced.
7. **External-client demo:** proved the workflow through HTTP without backend or database
   shortcuts.
8. **CPU container correction:** removed unintended Linux CUDA/Triton resolution while
   retaining frozen model behavior and package versions.
9. **Artifact portability boundary:** separated image buildability from full inference
   readiness and documented exact mounts.
10. **Honest dashboard:** built a polished interface around stored evidence without fake
    telemetry, health scores, severity, risk, or RUL.

## Architectural tradeoffs

| Decision | Benefit | Cost / trigger to revisit |
| --- | --- | --- |
| Modular monolith over microservices | one transaction and inspectable request path | split only when independent scaling or ownership is real |
| In-process EventBus over Kafka | low operational cost and deterministic sequential handlers | one worker; revisit for durable asynchronous or cross-process delivery |
| HTTP simulator over streaming device protocol | reproducible external boundary with no new infrastructure | no continuous ingestion; revisit for actual device requirements |
| Embedded Chroma over vector service | local, provider-free retrieval | writable local SQLite store and single-node operations |
| CPU over GPU deployment | smaller, portable controlled runtime | slower heavy encoders; profile before choosing acceleration |
| External artifacts over Git binaries | clean history and explicit model provenance | clean clone is not full-inference-ready; needs artifact distribution |
| Controlled localhost deployment over cloud | reproducible without paid services | no public auth, TLS, ingress, device identity, or managed operations |
| Single-modality V1 over fusion | honest evidence and independent model governance | no cross-modal conclusions; revisit only with aligned data and fusion protocol |
