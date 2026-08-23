# Decision Engine V1

Decision Engine V1 converts supported model predictions into provisional diagnostic
findings. It preserves a strict separation between four different concepts:

- classifier confidence describes the model's probability for its predicted class;
- fault severity describes the physical extent of a fault;
- machine health summarizes evidence about overall asset condition;
- operational risk combines failure likelihood with consequence or asset criticality.

SentinelAI currently has only the first kind of evidence. A high classifier confidence
is not a severity measurement, health score, probability of failure, or risk level.

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

- `uncalibrated_confidence` for raw classifier output;
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

Unknown labels and unsupported modalities fail explicitly. Multiple predictions from
the same modality are rejected because V1 has no aggregation policy and must not
double-count evidence.

## Future evidence path

Later versions may add measured confidence calibration, additional modalities,
severity evidence, asset criticality, and evidence-fusion rules. Health and risk can be
introduced only after those inputs support defensible calculations. V1 does not add
placeholder calibration, fusion weights, severity tables, or health and risk formulas.
