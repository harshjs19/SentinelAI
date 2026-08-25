# Induction-motor rotor-bar reference

## Scope

This card supports the separate SentinelAI `half_broken_rotor_bar` and
`broken_rotor_bar` classifier labels without merging them.

## What this evidence can mean

Peer-reviewed induction-motor research describes broken cage bars as faults that can
produce characteristic components in measured electrical signatures. Diagnostic
performance depends on operating state: load, slip, speed ripple, noise, and other
machine asymmetries can affect the observed components. Published work also treats
partial-bar detection as a harder, distinct measurement problem.

## Common inspection considerations

Corroborate a classifier output with motor-specific current or other approved condition
measurements across suitable load states. Review the motor design and qualified test or
inspection procedure before drawing a physical conclusion.

## What this evidence does not establish

The label does not count damaged bars, prove a physical crack, quantify severity or
remaining life, or distinguish every competing electrical or mechanical influence.

## Source basis

SentinelAI-authored paraphrase of IEEE Transactions on Industry Applications research,
DOI 10.1109/28.952499, with partial-bar scope cross-checked against DOI
10.1109/TIM.2016.2540941. No paper text is redistributed.
