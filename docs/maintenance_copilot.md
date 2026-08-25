# Maintenance Copilot safety foundation

Maintenance Copilot V1 Milestone 1 provides the deterministic contracts and safety
boundary for a source-grounded maintenance report generator. Milestone 2 adds one
explicitly constructed structured-output provider boundary. There is still no LangGraph
workflow, public API, report persistence, or report event.

## Authority boundary

SentinelAI's authoritative path remains deterministic:

```text
Input -> Predictor -> InferenceOrchestrator -> Prediction -> Decision Engine
    -> Analysis -> EvidencePackage -> KnowledgeRetriever -> RetrievalBundle
```

The future language path is bounded by those outputs:

```text
EvidencePackage + RetrievalBundle
    -> CopilotDraft
    -> MaintenanceSafetyValidator
    -> MaintenanceReport
```

`EvidencePackage` is the source of machine truth. It exclusively owns the machine
snapshot, condition, status, findings, confidence, health, risk, claim-support flags,
limitations, and producing-model provenance. `RetrievalBundle` is the closed-book
technical knowledge ceiling. The generator may not diagnose independently or add
maintenance knowledge from pretraining.

## Internal request and intent policy

`MaintenanceCopilotRequest` is immutable and contains a trusted `EvidencePackage`, its
matching `RetrievalBundle`, one `CopilotIntent`, and an optional question. It is an
internal contract; public clients are not expected to construct trusted packages.

The closed intent set is:

- `SUMMARIZE_ANALYSIS`
- `EXPLAIN_FINDING`
- `EXPLAIN_CONFIDENCE`
- `INSPECTION_CONSIDERATIONS`
- `EXPLAIN_LIMITATIONS`

There is no general chat, shutdown decision, risk assessment, RUL, or work-order intent.
Optional questions are Unicode-normalized, trimmed, limited to 500 characters, and
rejected when they contain NUL, disallowed controls, HTML, Markdown links, or URLs.
Bounded phrase rules identify high-impact and prompt-override requests before any future
provider invocation.

`EXPLAIN_CONFIDENCE` and `EXPLAIN_LIMITATIONS` have deterministic explanations and do not
require a provider. Current confidence templates preserve these exact semantics:

- `raw_selected_class_predict_proba`
- `bounded_empirical_anomaly_evidence_from_normal_calibration`
- `bounded_empirical_visual_anomaly_evidence_from_normal_calibration`

They explicitly avoid interpreting model scores as machine failure probability.
Limitation text is derived only from current `AnalysisLimitation` values and
`EvidenceClaimSupport` flags.

Fault-specific generation is ineligible when the analysis has insufficient evidence,
condition support is unavailable, or no compatible retrieved content exists. Normal
condition does not enable inspection considerations by default.

## Integrity before context construction

Before a provider-safe context can be built, SentinelAI verifies:

1. The Evidence Package canonical digest and content-derived package ID.
2. The Retrieval Bundle canonical digest.
3. The bundle's Evidence Package ID and digest against the supplied package.
4. Complete citation metadata for every eligible retrieved chunk.
5. That each chunk's matched retrieval intent resolves to an existing deterministic
   retrieval query and lane.

Failures use small application error codes:

- `INVALID_EVIDENCE_PACKAGE`
- `INVALID_RETRIEVAL_BUNDLE`
- `EVIDENCE_RETRIEVAL_MISMATCH`
- `INCOMPLETE_CITATION_METADATA`

These are hard failures. They do not produce a friendly fallback report because there is
no trustworthy evidence/retrieval binding from which to assemble one. Error text omits
package content, retrieved text, local paths, and secrets.

## Citations and provider-safe context

Eligible chunks retain Retrieval Bundle order and receive request-local citation IDs:

```text
first chunk  -> K1
second chunk -> K2
third chunk  -> K3
```

Application citation metadata retains the chunk and source IDs, source digest, title,
publisher, section, local source URI, fault code, asset scope, matched intent, and source
lane. The provider view contains only the citation label, title, publisher, section,
fault code, asset scope, lane, and retrieved text. It does not contain source URLs or
digests. The generator returns citation IDs only; final source metadata is
restored from the validated application mapping.

`CopilotGenerationContext` contains only:

- Asset type, condition, and analysis status.
- At most three deterministically selected `Analysis.top_findings`, referenced as `F1`,
  `F2`, and `F3`.
- Finding modality, canonical code, condition, confidence kind and semantics, model
  lifecycle status, and validated scope.
- Deterministic model-scope snapshots, limitations, and claim-support flags.
- Provider-safe cited excerpts.
- Intent and bounded optional question.

It omits the machine name and UUID, source payload hashes, evidence/retrieval digests,
source URLs, evaluation paths, raw sensor or media content, database identifiers,
filesystem/model/Chroma paths, predictors, artifacts, and secrets. Context construction
requires no database, source recording, embedding model, or vector store.

## CopilotDraft

`CopilotDraft` is a frozen, strict Pydantic contract with additional fields forbidden:

```text
executive_summary
finding_explanations[]
    finding_id
    text
    citation_ids
inspection_considerations[]
    finding_id
    text
    citation_ids
knowledge_gap_statement
```

Limits are deliberately conservative:

| Field | Limit |
|---|---:|
| Executive summary | 700 characters |
| Finding explanation | 500 characters |
| Inspection consideration | 400 characters |
| Knowledge gap | 400 characters |
| Finding explanations | 3 |
| Inspection considerations | 3 |
| Citation IDs per item | 3 |

Every technical finding explanation and inspection consideration requires at least one
citation. The draft has no fields for authoritative condition, status, confidence,
health, risk, severity, failure probability, RUL, identity, model status, source URI,
fault code, or citation metadata.

## MaintenanceSafetyValidator

There is one semantic safety validator. The future orchestration milestone will call the
same `MaintenanceSafetyValidator` after initial generation and after no more than one
repair attempt.

The validator checks:

- Draft structure and bounded content.
- Valid, non-duplicated finding references.
- Known and non-duplicated citations.
- Exact fault-code compatibility.
- Exact or `generic` asset compatibility; `generic` never bypasses fault matching.
- Maintenance-lane citations for inspection considerations.
- Anomaly-to-physical-fault and physical cross-fault contamination.
- Failure-probability, severity, health, risk, RUL, and time-to-failure claims.
- Generated technical numeric claims.
- High-impact or directive actions.
- Non-authoritative inspection wording.
- Model-scope overclaims.
- Generated URLs, Markdown links, HTML, code fences, and script-like markup.

The V1 policy completely prohibits generated directive actions such as shutdown,
continued-operation, restart, isolation, lockout/tagout, de-energization, evacuation,
replacement, disposal, bypass, and alarm-disable instructions. It also prohibits urgency
language and technical numeric claims. Inspection content must remain a cited,
non-authoritative consideration; it is not a recommendation or work instruction.

Rules are intentionally conservative and lexically bounded. Citation metadata
compatibility is not proof of semantic entailment, and the validator does not prove
factual correctness. Future prompt controls and human evaluation remain required.

## Final report and invariant verification

The deterministic assembler copies the authoritative Evidence Package fields and
producing-model snapshots exactly. It adds only a validated narrative, citations actually
used by accepted narrative items, generation provenance, safety outcome, policy versions,
and the fixed disclaimer.

`MaintenanceReport` has only `GENERATED` and `FALLBACK` generation statuses. Its fallback
reasons are:

- `GENERATION_UNAVAILABLE`
- `GENERATION_FAILED`
- `VALIDATION_FAILED`
- `NO_GROUNDED_CONTENT`
- `UNSUPPORTED_REQUEST`

Request disposition is independently represented as `ANSWERED`, `PARTIALLY_ANSWERED`, or
`NOT_SUPPORTED_BY_CURRENT_EVIDENCE`.

Each report occurrence receives a UUID4 and timezone-aware UTC generation time. Its
SHA-256 digest covers canonical report JSON—including the ID and time—but excludes the
digest field itself. The digest is an integrity/reference mechanism, not a signature,
authentication mechanism, or proof of truth.

`verify_maintenance_report` is a small final integrity check, not another semantic safety
validator. It verifies the report digest, evidence and retrieval identities, machine,
condition, status, findings, health/risk, claim support, producing models, and resolved
citations against the original validated inputs.

## Deterministic fallback

A fallback preserves all deterministic analysis fields, confidence and semantics,
models, limitations, claim boundaries, evidence/retrieval identity, provenance, policy
versions, and the disclaimer. It discards rejected generated text, has no inspection
considerations, and has `citations = ()` because no accepted generated technical narrative
used a source.

Its fixed narrative is:

```text
The analysis results are available below. A grounded maintenance explanation could not
be generated for this request.

No additional maintenance interpretation is provided.
```

Integrity failures do not use this fallback. A future provider outage or twice-invalid
draft may use it safely.

## Privacy and logging boundary

Future telemetry may contain report/evidence/retrieval IDs, intent, policy versions,
validation codes, latency, and token counts. Full prompts, retrieved text, generated
drafts, question text, machine names, API keys, and raw source data are forbidden from
default logging.

No runtime output files are written by this foundation.

## Producing-model provenance limitation

Evidence Package V1 currently resolves producing-model identity from the runtime-default
capability for each prediction modality. That remains acceptable only for the immediate
in-process workflow. Exact runtime `ProducingModelContext` propagation must be implemented
before historical reconstruction, persisted Copilot reports, or a public report API.
This milestone deliberately does not modify `Prediction` or Evidence Package semantics.

## Synthetic report example

The following is abbreviated; values are synthetic:

```json
{
  "schema_version": "1",
  "report_id": "00000000-0000-0000-0000-00000000c001",
  "generation_status": "generated",
  "fallback_reason": null,
  "request_disposition": "answered",
  "analysis": {
    "condition": "abnormal",
    "status": "provisional",
    "findings": [
      {
        "finding_id": "F1",
        "modality": "timeseries",
        "code": "bearing_fault",
        "confidence": 0.84,
        "confidence_kind": "raw"
      }
    ],
    "health_score": null,
    "risk_level": null
  },
  "narrative": {
    "executive_summary": "The analysis reported a bearing fault.",
    "finding_explanations": [
      {
        "finding_id": "F1",
        "text": "The cited source provides bearing-related condition context.",
        "citation_ids": ["K1"]
      }
    ],
    "inspection_considerations": [],
    "knowledge_gap_statement": null
  },
  "citations": [
    {
      "citation_id": "K1",
      "title": "Synthetic maintenance reference",
      "publisher": "SentinelAI tests",
      "section": "Condition interpretation"
    }
  ],
  "disclaimer": "This report provides evidence interpretation and source-backed inspection context. It does not authorize equipment shutdown, continued operation, isolation, repair, or return to service."
}
```

## Provider Boundary — Milestone 2

Milestone 2 adds the async, Copilot-specific `MaintenanceGenerator` protocol and one
`OpenAIMaintenanceGenerator` implementation. It uses the OpenAI Responses API with the
exact baseline snapshot `gpt-5.4-mini-2026-03-17`; there is no floating alias, provider
registry, or automatic model fallback. The requested model and response model are both
retained in the generation receipt so a snapshot mismatch is visible.

The adapter uses the official SDK's current Pydantic Structured Outputs path:
`responses.parse(..., text_format=CopilotDraft)`. The SDK derives a strict JSON Schema
from the existing model, marks every object as closed to additional properties, and
requires the four draft fields. Local strict Pydantic validation remains authoritative
for every parsed response and preserves all string and collection limits; there is no
second provider schema, near-JSON recovery, or provider text fallback.

Provider configuration is a frozen per-generator value with these baseline defaults:

| Setting | Default |
|---|---:|
| Model | `gpt-5.4-mini-2026-03-17` |
| Timeout | 30 seconds |
| Maximum output | 1,200 tokens |
| Temperature | 0 |
| Reasoning effort | `none` |
| Transient transport retries | 1 |

Each call is stateless, uses `store=false` and `truncation=disabled`, and supplies no
tools, conversation, or previous response ID. The underlying `AsyncOpenAI` client has
`max_retries=0`; SentinelAI alone permits one retry for connection failures, timeouts,
rate limits, HTTP 408/409, and 5xx responses. Authentication, permission, bad-request,
schema, refusal, incomplete, malformed-output, and safety-validation failures are not
transport-retried. Normalized error categories and messages exclude provider bodies,
prompts, source text, credentials, paths, and headers.

The versioned developer policy keeps Evidence Package facts authoritative and retrieval
closed-book. Deterministic evidence, citation-labeled excerpts, and the optional question
are serialized as stable JSON data. Retrieved content is explicitly untrusted reference
data, and question text cannot become developer instructions. Provider context still
excludes machine identity, evidence/retrieval IDs and digests, source URLs and hashes,
raw sensor/media data, artifact/dataset/evaluation/Chroma paths, API keys, and environment
values.

Explicit refusal, incomplete status, missing output, and invalid structured output are
distinct failures; partial or refusal text never becomes a draft. A direct
`RepairInstruction` can submit the same original context, one previous rejected draft,
and finite validator codes for a future single repair attempt. This milestone provides no
repair loop and does not change deterministic provider-bypass decisions for confidence,
limitations, unsupported requests, or absent grounded content.

The opt-in `uv run python -m scripts.smoke_copilot_provider` command reads
`OPENAI_API_KEY` only at composition time and runs three synthetic, first-attempt cases.
It prints receipt and validation metadata but no prompt or draft by default; `--show-draft`
is explicit. Normal tests remain offline. This smoke is an integration check, not a
promotion benchmark; formal adversarial safety evaluation remains Milestone 4 work.

## Next milestones

LangGraph remains a later, separately reviewed bounded orchestration milestone. No graph,
application service, public API, report persistence, database schema, or report event is
implemented here.
