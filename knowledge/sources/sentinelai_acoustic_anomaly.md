# Acoustic anomaly interpretation

## Scope

This card interprets the SentinelAI `acoustic_anomaly` code using the project's declared
Audio V1 semantics.

## What this evidence can mean

The Audio model found an input whose anomaly score differs from its normal calibration
reference. It is evidence of acoustic novelty within the model and dataset scope, not a
named mechanical fault.

## Common inspection considerations

Confirm input quality and operating context, compare repeat observations, and seek
qualified corroboration from other measurements or inspection when appropriate.

## What this evidence does not establish

It does not identify a bearing, coupling, gear, rotor, or other physical fault. Its
confidence is not failure probability, severity, health, risk, or urgency. The runtime
Audio V1 baseline is experimental and performed near chance under its held-out domain
shift evaluation.

## Source basis

SentinelAI-authored summary derived from `docs/audio_baseline.md`,
`docs/model_capabilities.md`, `docs/decision_engine.md`, and
`docs/evidence_package.md`.
