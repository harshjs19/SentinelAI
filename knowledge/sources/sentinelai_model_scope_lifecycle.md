# Model scope and lifecycle interpretation

## Scope

This card explains `validated_scope` and model lifecycle status in an Evidence Package.

## What this evidence can mean

`validated_baseline` means the model passed its specifically declared experimental
protocol; it is not deployment certification. `experimental` means the runtime role is
available while material performance or generalization limitations remain. The copied
validated scope states the dataset and split boundary supported by existing evaluation.

## What this evidence does not establish

Retrieved engineering knowledge never expands model scope. A reference about bearings or
motors does not validate a model for every industrial asset, operating state, site, or
failure mode. Lifecycle status alone neither suppresses a supported finding nor turns it
into a production-certified diagnosis.

## Source basis

SentinelAI-authored semantic card derived from `docs/model_capabilities.md` and
`docs/evidence_package.md`. Evaluation details remain in each package's repository-relative
evaluation reference.
