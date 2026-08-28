# Premium Dashboard V1

SentinelAI's dashboard is an internal/demo interface for existing authoritative machine,
model-capability, maintenance-report, and historical-evidence APIs. It is usable with the
deterministic Maintenance Copilot path and does not require `OPENAI_API_KEY`.

## Scientific boundary

Each analysis request carries exactly one source modality: time-series, audio, vision, or
thermal. The four nodes around the decorative Sentinel Core describe available modules;
they do not represent multimodal fusion, live sensors, or a physical digital twin.

The interface does not derive failure probability, severity, health, operational risk,
remaining useful life, evidence packages, retrieval bundles, or producing-model identity.
Unsupported quantities remain visibly not determined or not estimated. Finding confidence
is labelled model confidence, including the explicit statement that raw confidence is not
failure probability. Inspection Considerations reproduce bounded server text and are not
renamed as actions or recommendations.

Historical report lineage is read from:

```text
GET /maintenance-reports/{report_id}/evidence
```

The safe response drives the Source → Analysis → Evidence Package → Retrieval Bundle →
Maintenance Report chain. The browser receives no raw source, retrieval chunks, or local
paths.

## Demo flow

1. Open Overview and identify the available-module Sentinel Core.
2. Inspect real machine and model counts and their explicitly sourced charts.
3. Open Machines and select a persisted machine.
4. Choose Run Analysis and one modality only.
5. Provide raw input, intent, and an optional bounded question.
6. Submit the exact maintenance-report API request.
7. Review the authoritative condition and findings.
8. Explain the raw model-confidence boundary.
9. Review unavailable claims and other scientific limitations.
10. Inspect exact stored producing-model provenance.
11. Follow the verified Evidence Chain and Evidence Package bindings.
12. Read the non-directive Inspection Considerations.
13. Expand a citation and note the human-review disclaimer.
14. Open machine history and reopen the stored report without recomputation.
15. Open Model Capabilities and compare validated, experimental, and rejected results.

## Client behavior

A new semantic submission receives a fresh in-memory idempotency key. Only an exact retry
after transport uncertainty reuses it. Uploaded media remains a browser `File`, is sent
directly as multipart form data, is never base64 encoded, and is not stored in browser
persistence. Image previews use short-lived object URLs.

No WebSocket, polling loop, paid service, Raspberry Pi, new backend subsystem, or database
migration is required by this dashboard.

## Premium Visual Refinement V2

V2 preserves every V1 route, API contract, report structure, and scientific boundary. A
shared motion vocabulary uses fast (160 ms), standard (260 ms), enter (380 ms), and
cinematic (680 ms) timings with one restrained easing curve. Page entry, disclosure,
navigation, evidence, and drawer movement all use that vocabulary. Reduced-motion mode
removes continuous orbit, particle, parallax, and signal movement while retaining content.

The interface uses the locally packaged Manrope variable font for UI and display text and
system monospace only for technical identifiers. Four consistent glass elevations define
navigation, cards, intelligence panels, and the analysis drawer. Directional highlights,
quiet ambient depth, and selected pointer spotlights reinforce hierarchy without adding
telemetry or data-like decoration.

The procedural Sentinel Core now layers a nucleus, translucent shell, lattice, orbital
geometry, bounded particles, module nodes, and subtle architecture pulses. Pointer and
scroll response are deliberately small, use frame-local refs rather than React state, and
return toward a neutral camera. Tablet rendering reduces particle density; reduced-motion
uses demand rendering. No GLTF, texture, video, post-processing pipeline, or downloaded
visual asset is used. WebGL failure retains an intentional CSS core/orbit/node composition.

Evidence Chain motion runs once as stored lineage enters view, then becomes a stable
technical diagram. Focus and hover progressively disclose stored identifiers and digests.
All effects remain decorative: they do not describe live data, sensor synchronization,
multimodal fusion, or a physical digital twin.

## Signature Experience V3

V3 establishes a SentinelAI-specific visual language around `SIGNALS -> INTELLIGENCE ->
EVIDENCE -> DECISION SUPPORT`. Large editorial headings, numbered chapters, technical
coordinates, orbital fields, lineage planes, and restrained ambient depth distinguish the
product without changing any route, API contract, data interpretation, or scientific
boundary. Manrope remains locally packaged; no network font or new frontend dependency is
required.

Overview is the only full WebGL surface. Its Sentinel Core represents independent analysis
modules and explicitly does not imply multimodal fusion, live telemetry, synchronized
sensors, or a physical digital twin. Machines uses a persisted-asset field, Machine Detail
uses a single-asset intelligence halo, History uses a stored-artifact corridor, Model
Capabilities uses a lifecycle constellation, and Run Analysis uses a lightweight selected-
modality chamber. These page-specific scenes are CSS/SVG architecture, not measurements or
generated operational data.

The Maintenance Report is arranged as an evidence brief: executive summary, bounded model
output, unavailable scientific claims, stored lineage, evidence and producing-model
identity, non-directive Inspection Considerations, citations, and binding limitations. The
Evidence Chain performs one lineage traversal when it enters view and then rests as a stable
diagram. Every node is populated from the authoritative historical evidence endpoint; the
client does not rebuild provenance from current defaults.

Reduced-motion mode removes traversal and continuous visual movement and clears stagger
delays so content is immediately visible. Tablet layouts preserve the information hierarchy,
long identifiers wrap inside their own surfaces, and the deliberate CSS Sentinel Core
fallback remains available when WebGL is missing. Decorative scenes stay pointer-light and
state-free; the lazy-loaded Overview scene remains isolated from the other route bundles.
