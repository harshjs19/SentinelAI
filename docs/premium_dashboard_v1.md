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
