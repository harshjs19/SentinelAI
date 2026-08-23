# Decision Engine V1

Decision Engine V1 converts supported model predictions into provisional diagnostic
findings. It preserves a strict separation between four different concepts:

- model confidence describes a bounded, model-reported confidence or evidence value;
- fault severity describes the physical extent of a fault;
- machine health summarizes evidence about overall asset condition;
- operational risk combines failure likelihood with consequence or asset criticality.

Its raw interpretation is modality-specific. The time-series classifier reports
selected-class `predict_proba`; Audio ASD and Vision anomaly detection report bounded
empirical evidence derived from their own normal calibration scores. None is a severity
measurement, health score, probability of failure, or risk level, and the three raw
values are not assumed to be calibrated or directly comparable.

## V1 behavior

A supported prediction becomes a `Finding` with the original confidence marked as
`raw`. One or more supported predictions produce a `provisional` analysis. No
predictions produce an `insufficient_evidence` analysis with an `indeterminate`
condition.

The overall condition is `abnormal` if any finding is abnormal, `normal` if every
finding is normal, and otherwise `indeterminate`. Classifier labels determine the
diagnostic condition; confidence thresholds are not used.

Health score and risk level are always `null` in V1. The available dataset does not
measure fault severity or support a defensible health model. SentinelAI also lacks a
calibrated failure likelihood and asset consequence context, so operational risk cannot
be assigned.

Analyses identify applicable limitations in deterministic order:

- `uncalibrated_confidence` for raw model confidence or evidence;
- `fault_severity_unavailable` when an abnormal finding exists;
- `risk_context_unavailable` when evidence exists;
- `single_modality_evidence` when exactly one modality contributes.

Zero-evidence analyses do not claim limitations that imply a prediction existed.

## Time-series finding mapping

| Model label | Canonical code | Condition |
| --- | --- | --- |
| `healthy` | `healthy` | `normal` |
| `bearing_fault` | `bearing_fault` | `abnormal` |
| `coupling_fault` | `coupling_fault` | `abnormal` |
| `bent_shaft` | `bent_shaft` | `abnormal` |
| `eccentric_rotor` | `eccentric_rotor` | `abnormal` |
| `imbalance` | `imbalance` | `abnormal` |

Audio maps `healthy` to a normal `healthy` finding and `acoustic_anomaly` to an
abnormal `acoustic_anomaly` finding. It does not infer a bearing fault or another
physical fault type from anomalous sound alone.

Vision maps `healthy` to a normal `healthy` finding and `visual_anomaly` to an abnormal
`visual_anomaly` finding. It does not infer a physical fault or defect class from an
anomalous image alone.

Unknown labels and unsupported modalities fail explicitly. Multiple predictions from
the same modality are rejected because V1 has no aggregation policy and must not
double-count evidence.

## Future evidence path

Later versions may add measured confidence calibration, additional modalities,
severity evidence, asset criticality, and evidence-fusion rules. Health and risk can be
introduced only after those inputs support defensible calculations. V1 does not add
placeholder calibration, fusion weights, severity tables, or health and risk formulas.
