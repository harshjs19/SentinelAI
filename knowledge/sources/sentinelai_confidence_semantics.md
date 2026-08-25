# Model confidence interpretation

## Scope

This card explains the confidence semantics copied into an Evidence Package.

## What this evidence can mean

Time-Series and Thermal currently expose raw selected-class classifier `predict_proba`.
Audio and Vision expose bounded empirical anomaly evidence relative to their own normal
calibration scores. These values have different constructions and are not assumed to be
comparable across modalities. A Finding records whether confidence is raw or calibrated;
current findings are raw.

## What this evidence does not establish

No current confidence value is a validated probability that the machine will fail. It
does not measure physical fault severity, overall health, operational risk, urgency, or
remaining useful life. A value such as 0.85 must not be restated as an 85% chance of
failure.

## Source basis

SentinelAI-authored semantic card derived from `docs/model_capabilities.md`,
`docs/decision_engine.md`, and `docs/evidence_package.md`.
