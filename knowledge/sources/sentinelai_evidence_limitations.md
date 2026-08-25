# Evidence and multimodal limitations

## Scope

This card explains unsupported Evidence Package claims and the current multimodal-fusion
boundary.

## What this evidence can mean

Claim-support flags say which conclusions already exist upstream. Decision Engine V1 does
not derive fault severity, failure probability, health, or operational risk without the
required evidence and context. A single-modality limitation records that only one sensing
modality contributed.

CORA thermal/vibration fusion remains blocked because the dataset lacks timing evidence
needed for reproducible alignment. The Retriever does not resume or approximate that
fusion.

## What this evidence does not establish

Missing claims must not be reconstructed through retrieval. Knowledge chunks cannot add
severity, health, risk, failure likelihood, timing alignment, or a new diagnosis to the
Evidence Package.

## Source basis

SentinelAI-authored semantic card derived from `docs/decision_engine.md`,
`docs/evidence_package.md`, `docs/runtime_architecture.md`, and
`docs/cora_alignment_feasibility.md`.
