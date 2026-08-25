# Insufficient-evidence interpretation

## Scope

This card applies when an Evidence Package contains an `insufficient_evidence` Analysis
or its condition is unavailable.

## What this evidence can mean

No supported prediction was available for Decision Engine V1 to convert into a finding.
The Analysis is indeterminate and contains no model or source provenance because no
prediction contributed to it.

## Common inspection considerations

The result can prompt a review of whether valid input evidence and the intended model
workflow were available. Any further data collection or inspection remains an external
operational choice, not a Retriever decision.

## What this evidence does not establish

Insufficient evidence is neither healthy nor abnormal. It provides no fault-specific
maintenance conclusion, failure probability, severity, health score, or risk level.

## Source basis

SentinelAI-authored semantic card derived from `docs/decision_engine.md` and
`docs/evidence_package.md`.
