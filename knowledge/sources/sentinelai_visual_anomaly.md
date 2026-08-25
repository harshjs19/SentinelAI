# Visual anomaly interpretation

## Scope

This card interprets the SentinelAI `visual_anomaly` code using the project's Vision V1
semantics.

## What this evidence can mean

The Vision model found visual anomaly evidence relative to its normal-only VisA PCB1
reference. It flags appearance that differs from learned normal examples within that
camera and dataset scope.

## Common inspection considerations

Check image quality, viewpoint, illumination, occlusion, and repeatability. A qualified
visual inspection or another sensing modality may be used for corroboration when the
application calls for it.

## What this evidence does not establish

It does not name a physical defect or imply bearing, coupling, gear, rotor, or thermal
damage. Its confidence is not failure probability, severity, health, risk, or urgency.
The runtime Vision V1 model is experimental and has limited anomaly recall at its
conservative threshold.

## Source basis

SentinelAI-authored summary derived from `docs/vision_baseline.md`,
`docs/model_capabilities.md`, `docs/decision_engine.md`, and
`docs/evidence_package.md`.
