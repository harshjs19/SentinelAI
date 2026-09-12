# Public demo

SentinelAI's public-demo build is a static, read-only view over a reviewed export of genuine
simulation/replay workflow outputs. It performs no inference, retrieval, Decision Engine
execution, report generation, or API writes in the browser. It does not require an
`OPENAI_API_KEY`.

## Build modes

- `cd frontend && npm run build` creates the normal API-backed dashboard.
- `cd frontend && npm run build:demo` creates the static public demo.
- `VITE_PUBLIC_DEMO=true` also enables the static provider for an explicit Vite build.

`frontend/src/api/demo.ts` is the provider boundary. In demo mode, the existing machine,
capability, report, and evidence API modules delegate reads to the validated static snapshot.
Maintenance-report creation is rejected, and the UI disables Run Analysis. In normal mode,
the existing `/api` client and write workflow remain active.

## Snapshot provenance

The snapshot is `frontend/public/demo/snapshot.json`. It was exported from these existing,
read-only API routes:

- `GET /machines`
- `GET /capabilities/models`
- `GET /machines/{machine_id}/maintenance-reports`
- `GET /maintenance-reports/{report_id}`
- `GET /maintenance-reports/{report_id}/evidence`

Use `scripts/export_public_demo.py` against a controlled local SentinelAI deployment. Every
machine must be selected explicitly so an unreviewed database record cannot enter an export
by default:

```shell
uv run python -m scripts.export_public_demo \
  --machine-id <reviewed-machine-uuid> \
  --machine-id <reviewed-machine-uuid>
```

The exporter validates responses through the existing public Pydantic response schemas and
checks report/evidence/machine bindings. It serializes only the response fields already
allowed by those schemas. The API origin is not recorded.

The current reviewed snapshot contains 4 demonstration machines, 10 stored reports, and 10
one-to-one evidence records. All stored reports are single-modality time-series records.
Its condition distribution is 0 normal, 10 abnormal, and 0 indeterminate: the frozen model
classified the repository's deterministic healthy-profile simulator input as abnormal, so the
snapshot preserves that genuine result instead of manufacturing visual balance.
The capability registry separately declares time-series, audio, vision, and thermal modules;
those declarations do not imply multimodal fusion or that every modality appears in the
report snapshot.

`frontend/public/model-evaluations.json` is a compact display index derived from the five
tracked evaluation result files named by the capability registry. Each record retains the
evaluation path and SHA-256 digest of its source file. The dashboard validates one-to-one
model/reference bindings and exposes the verified metric together with its known limitation.

## Scientific boundaries

Classifier confidence is displayed with its stored confidence kind. It is not converted to
failure probability, fault severity, machine health, operational risk, or remaining useful
life. Unsupported claims remain omitted or are described as unavailable from the evidence.
Inspection Considerations remain non-directive. Experimental and rejected model results stay
visible with their lifecycle labels and evaluation limitations.

The Sentinel Core and page geometry are representational. They do not depict live telemetry,
physical topology, a digital twin, or sensor fusion. The CSS fallback preserves this meaning
when WebGL is unavailable, and reduced-motion preferences disable continuous movement.

## Privacy and publication review

Before updating the public snapshot, review the generated files and production build for
credentials, authorization data, provider response IDs, absolute paths, personal data, raw
media, raw sensor rows, model binaries, datasets, vector stores, and embeddings. The snapshot
contains source digests and byte counts, but no raw source or full retrieval chunks.

## Vercel

The root `vercel.json` installs and builds only the frontend public-demo target and serves
`frontend/dist`. Its SPA rewrite sends non-file client routes to `index.html`; Vercel gives
filesystem content precedence, so hashed assets and the two JSON data files remain directly
served. No deployment is performed by repository scripts.

After a reviewed preview deployment, verify `/`, `/machines`, a machine direct URL, `/reports`,
a report direct URL, and `/models`. Confirm the banner reads `PUBLIC DEMO · READ ONLY`, no
`/api` request occurs, and the browser console is clean.
