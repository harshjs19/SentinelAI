# Evidence Package V1

## Purpose and boundary

Evidence Package V1 is SentinelAI's immutable, deterministic bridge from an existing
`Machine`, an already-produced `Analysis`, source provenance, and the exact producing
model context captured during inference to a small serializable evidence snapshot. It
records:

- what SentinelAI observed;
- which runtime model produced each prediction;
- what Decision Engine V1 concluded;
- the model's declared scientific scope and lifecycle status;
- which claims are supported or explicitly unavailable.

The flow is:

```text
input evidence -> predictor -> InferenceOrchestrator
    -> InferenceResult(Prediction, ProducingModelContext)
    -> Decision Engine(Prediction) -> Analysis
    -> EvidencePackageService(Analysis, ProducingModelContext) -> EvidencePackage
    -> KnowledgeRetriever -> RetrievalBundle -> MaintenanceCopilotService
```

The internal `MaintenanceWorkflowService` now owns this construction sequence. Its caller
cannot submit a Prediction, Analysis, EvidencePackage, RetrievalBundle, source hash, or
model-provenance claim. The workflow resolves the authoritative Machine, derives source
provenance from the same input passed to inference, and supplies the exact context from
`InferenceResult`.

`EvidencePackageService` consumes an existing domain `Machine`, `Analysis`, source
provenance, and explicit `ProducingModelContext` snapshots. It does not run inference,
rediscover a model from current configuration, call `DecisionEngine`, query a database,
read an evaluation file, retrieve documents, invoke an LLM, or generate maintenance
advice. There is no public Evidence Package endpoint, EventBus event, or subscriber in
this construction service. A separate internal persistence layer stores the complete
validated package only as part of an atomic completed workflow; it does not change this
construction boundary.

## Immutable schema

The serialization contract uses `schema_version = "1"`. Frozen dataclasses and tuples
hold the in-memory snapshot. An explicit frozen Pydantic schema controls the public JSON
shape.

`EvidencePackage` contains:

- `schema_version`, deterministic `package_id`, full `package_digest_sha256`, and
  `created_at` copied from `Analysis.created_at`;
- `machine`: `machine_id`, `name`, and `asset_type` only;
- `analysis`: analysis and machine IDs, predictions, findings, condition, status,
  health score, risk level, limitations, creation time, and the existing deterministic
  `top_findings` ordering;
- `sources`: modality, source kind, SHA-256, canonical/input byte size, and descriptive
  content type;
- `models`: an immutable copy of exact execution-time producing-model metadata;
- `claim_support`: explicit availability boundaries for condition, failure probability,
  fault severity, health score, and operational risk.

No ORM object is retained. Prediction and Finding confidences and
`Finding.confidence_kind` are copied without calibration, rewriting, or rounding.
`Analysis.limitations` is preserved exactly.

## Deterministic construction and identity

The same machine snapshot, Analysis, source provenance, model provenance, and schema
version always produce the same identity. Package creation does not call `uuid4()` or
`datetime.now()`.

The core payload contains every serialized package field except `package_id` and
`package_digest_sha256`. Its canonical bytes are hashed with SHA-256:

```text
package_digest_sha256 = SHA-256(canonical_json_bytes(core_payload))
package_id = "evp1_" + first 32 hexadecimal characters of package_digest_sha256
```

Thirty-two digest characters provide a 128-bit identifier prefix; the complete
256-bit digest remains in the package. Verification recomputes the core digest, compares
the full digest, and verifies the derived ID. A changed core field with the old identity
fails verification.

The digest supports deterministic identity, integrity checking, and future audit
linkage. It is not a digital signature, authentication, non-repudiation, or proof that a
prediction is objectively true.

## SentinelAI V1 canonical JSON

`canonical_json_bytes` is deliberately not described as RFC 8785/JCS. Its frozen V1
rules are:

- UTF-8 encoding and compact separators;
- object keys sorted lexicographically;
- list/tuple order preserved;
- object keys must be strings;
- finite JSON numbers only; NaN and positive/negative Infinity are rejected;
- `Enum` values serialize through `.value` and UUIDs as strings;
- timezone-aware datetimes normalize to UTC as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`;
- naive datetimes and unsupported Python objects are rejected;
- domain/evidence dataclasses use explicit field serializers rather than `repr()` or an
  unrestricted `__dict__` conversion.

## Source provenance and privacy

Within the server-owned workflow, `SourceProvenance` has two source kinds:

- `file`: Audio, Vision, and Thermal helpers hash the exact uploaded bytes before those
  bytes are discarded from the package;
- `structured`: Time-Series inputs are canonically serialized, then the exact canonical
  bytes are hashed.

Structured object insertion order therefore does not affect the hash, while sample-list
order does. `size_bytes` is the exact uploaded size for file evidence and the canonical
JSON byte length for structured evidence. `content_type` is descriptive provenance, not
a security guarantee. Client filenames are omitted.

Evidence Package serialization contains no raw samples, media bytes, base64, temporary
paths, model paths, dataset paths, or source filenames. A typical single-modality
package is a few KB rather than MB.

## Model provenance and confidence semantics

The concrete predictor binding is resolved before inference. `InferenceOrchestrator`
returns an immutable `InferenceResult` containing the `Prediction` and its bound
`ProducingModelContext`. The context snapshots model ID, modality, lifecycle status,
whether it was the runtime default at execution, validated scope, evaluation reference,
and confidence semantics. It contains no predictor, estimator, artifact, path, raw input,
or credential.

`EvidencePackageService` requires the captured contexts for every evidence-bearing
Prediction and copies them into `ModelProvenance`. It never asks which model is the
current default. Missing exact context fails closed; duplicate, wrong, missing, or extra
modalities are rejected. An insufficient-evidence Analysis with no Predictions correctly
uses empty source and model provenance.

`runtime_default` in serialized model provenance is the snapshotted
`runtime_default_at_execution` fact. It is historical configuration metadata, not a way
to rediscover producing identity and not a claim of superiority or maturity. A producing
model and the model configured as the default at some later time are distinct concepts.

| Model | Modality | Lifecycle | Runtime default | Confidence semantics |
| --- | --- | --- | ---: | --- |
| `timeseries_utk_v1` | Time-Series | `validated_baseline` | yes | `raw_selected_class_predict_proba` |
| `audio_mimii_v1` | Audio | `experimental` | yes | `bounded_empirical_anomaly_evidence_from_normal_calibration` |
| `audio_mimii_ast_v2` | Audio | `rejected_experiment` | no | `bounded_empirical_anomaly_evidence_from_normal_calibration` |
| `vision_visa_pcb1_v1` | Vision | `experimental` | yes | `bounded_empirical_visual_anomaly_evidence_from_normal_calibration` |
| `thermal_cora_v1` | Thermal | `experimental` | yes | `raw_selected_class_predict_proba` |

`validated_scope` remains part of every provenance snapshot, and
`evaluation_reference` must be a repository-relative `evaluation/*.json` path. Package
generation records that reference without opening or parsing it. Metrics are not copied
into each package.

Raw selected-class `predict_proba` output is not called calibrated probability. None of
the current confidence values is a validated probability of machine failure.

## Claim support

Current V1 rules are deterministic:

- `condition_available` is false only for an `INSUFFICIENT_EVIDENCE` Analysis;
- `failure_probability_available` is always false;
- `fault_severity_available` is always false, including labels such as
  `gear_wear_75`;
- `health_score_available` is true only when the Analysis already contains a health
  score;
- `operational_risk_available` is true only when the Analysis already contains a risk
  level.

The service never derives health, risk, severity, or failure probability. An
insufficient-evidence Analysis is represented with empty predictions, findings, source
provenance, and model provenance.

## Provenance invariants

- Machine and Analysis machine IDs must match.
- Prediction modalities must be unique.
- Every Prediction modality must have exactly one explicit producing-model context.
- Producing-model context and Prediction modalities must match exactly; missing, duplicate,
  wrong, and extra contexts fail construction.
- Source and model modalities must exactly match the Analysis prediction modalities.
- Source and model provenance cannot contain duplicate modalities.
- Time-Series sources must be `structured`; Audio, Vision, and Thermal sources must be
  `file`.
- New provenance collections are sorted by stable modality/model keys. Existing
  Analysis prediction/finding order is preserved.
- Package and Analysis timestamps must be timezone-aware UTC and identical.

## Synthetic JSON example

```json
{
  "schema_version": "1",
  "package_id": "evp1_fd60a29ac823915f6e98e14e3981c11c",
  "package_digest_sha256": "fd60a29ac823915f6e98e14e3981c11cad826556c67a5f0f4e588ca20daeb74e",
  "created_at": "2026-08-25T08:30:00.123456Z",
  "machine": {
    "machine_id": "00000000-0000-0000-0000-000000000101",
    "name": "Synthetic pump",
    "asset_type": "pump"
  },
  "analysis": {
    "analysis_id": "00000000-0000-0000-0000-000000000201",
    "machine_id": "00000000-0000-0000-0000-000000000101",
    "predictions": [
      {"modality": "timeseries", "label": "bearing_fault", "confidence": 0.91}
    ],
    "findings": [
      {
        "modality": "timeseries",
        "code": "bearing_fault",
        "condition": "abnormal",
        "confidence": 0.91,
        "confidence_kind": "raw"
      }
    ],
    "condition": "abnormal",
    "status": "provisional",
    "health_score": null,
    "risk_level": null,
    "limitations": [
      "uncalibrated_confidence",
      "fault_severity_unavailable",
      "risk_context_unavailable",
      "single_modality_evidence"
    ],
    "created_at": "2026-08-25T08:30:00.123456Z",
    "top_findings": [
      {
        "modality": "timeseries",
        "code": "bearing_fault",
        "condition": "abnormal",
        "confidence": 0.91,
        "confidence_kind": "raw"
      }
    ]
  },
  "sources": [
    {
      "modality": "timeseries",
      "source_kind": "structured",
      "sha256": "2af763b6a2599ba5e5fc32e8cb18a9e2c276ace8eb97116a8e813803d44617d6",
      "size_bytes": 37,
      "content_type": "application/json"
    }
  ],
  "models": [
    {
      "model_id": "timeseries_utk_v1",
      "modality": "timeseries",
      "status": "validated_baseline",
      "runtime_default": true,
      "validated_scope": "UTK blocked chronological within-recording multiclass evaluation",
      "evaluation_reference": "evaluation/timeseries_baseline_results.json",
      "confidence_semantics": "raw_selected_class_predict_proba"
    }
  ],
  "claim_support": {
    "condition_available": true,
    "failure_probability_available": false,
    "fault_severity_available": false,
    "health_score_available": false,
    "operational_risk_available": false
  }
}
```

## Current limitations and future use

V1 does not include model artifact hashes, training-run or registry identities, binary
signatures, or external audit guarantees. Durable maintenance workflow storage retains
the exact package JSON and re-runs the existing digest verifier on historical reads. The
static predictor/model binding is explicit and tested, but no artifact registry
independently attests that
binding. Those capabilities belong to later MLOps milestones. V1 also
does not make model claims broader than each capability's `validated_scope`.

CORA frame-level multimodal fusion remains deferred because v2.1 lacks sufficient
timing evidence for reproducible thermal/vibration alignment. Evidence Package V1 does
not alter that scientific decision.

The current Retriever consumes the package without model objects, ORM objects, raw
sensor/media payloads, sklearn, or torch. The request-local server workflow can continue
through retrieval and report generation. After the entire result verifies, a separate
durable layer can atomically store the package JSON and digest with the other three
artifacts. Historical reconstruction does not consult current model defaults. See
[Maintenance workflow persistence](maintenance_workflow_persistence.md).
