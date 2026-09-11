# Model capabilities and lifecycle

`GET /capabilities/models` reports SentinelAI's static model declarations. It describes
the experimental maturity and intended runtime selection of each model; it does not
load artifacts, test their local availability, or provide runtime health.

`runtime_default` is current-configuration metadata. It answers which declared model is
selected for new runtime inference, not which model produced arbitrary existing evidence.
The concrete predictor exposes its exact model ID at runtime; composition verifies that
ID against the configured default and snapshots a `ProducingModelContext` before the
prediction travels forward. Evidence packaging consumes that snapshot and never performs
a later current-default lookup.

Consequently:

```text
runtime_default (configuration now) != producing_model (execution fact for this evidence)
```

The rejected `audio_mimii_ast_v2` declaration remains visible scientific evidence but
cannot bind as the current Audio runtime default or be mislabeled as `audio_mimii_v1`.
No response field or meaning of `GET /capabilities/models` changes in this milestone.

Lifecycle statuses mean:

- `validated_baseline`: validated against the specifically declared experimental
  protocol. This is not deployment certification or evidence of general applicability.
- `experimental`: available for its declared runtime role, but the evidence has
  material performance or generalization limitations.
- `rejected_experiment`: retained as a scientific record after failing its declared
  promotion criterion and not selected for runtime use.

The additive `confidence_semantics` capability field freezes what each current
`Prediction.confidence` represents:

| Model ID | Confidence semantics | Meaning |
| --- | --- | --- |
| `timeseries_utk_v1` | `raw_selected_class_predict_proba` | Raw selected-class classifier `predict_proba`; not calibrated machine-failure probability. |
| `audio_mimii_v1` | `bounded_empirical_anomaly_evidence_from_normal_calibration` | Bounded anomaly evidence positioned against normal calibration scores. |
| `audio_mimii_ast_v2` | `bounded_empirical_anomaly_evidence_from_normal_calibration` | The same score construction as Audio V1, retained for the rejected experiment. |
| `vision_visa_pcb1_v1` | `bounded_empirical_visual_anomaly_evidence_from_normal_calibration` | Bounded visual-anomaly evidence positioned against normal calibration scores. |
| `thermal_cora_v1` | `raw_selected_class_predict_proba` | Raw selected-class classifier `predict_proba`; not calibrated machine-failure probability. |

None of these values is a validated probability of machine failure.

| Model ID | Modality | Status | Runtime default | Evidence and limitations |
| --- | --- | --- | ---: | --- |
| `timeseries_utk_v1` | Time-Series | `validated_baseline` | yes | UTK blocked chronological within-recording test macro F1 was 0.9418. Each fault class has only one recording, so this is not unseen-machine or unseen-session validation. |
| `audio_mimii_v1` | Audio | `experimental` | yes | MIMII DG held-out Section 02 ROC AUC was 0.5213. This near-chance domain-shift result makes the runtime baseline experimental. |
| `audio_mimii_ast_v2` | Audio | `rejected_experiment` | no | The frozen-AST Section 01 promotion score was 0.5158 versus 0.5802 for V1, so the predeclared promotion criterion failed. |
| `vision_visa_pcb1_v1` | Vision | `experimental` | yes | The VisA PCB1 runtime patch nearest-neighbor model reached image ROC AUC 0.8964 and pixel ROC AUC 0.9834, but its conservative threshold recalled only 0.08 of test anomalies and evidence is limited to this dataset/camera scope. |
| `thermal_cora_v1` | Thermal | `experimental` | yes | On the held-out F60 speed, frame macro F1 was 0.1291 and experiment-level accuracy was 1/9. This is a severe operating-speed generalization failure on the same test bench. |

Detailed metrics, protocols, and artifact metadata remain in the referenced files under
`evaluation/`; the application declaration deliberately does not duplicate them.
