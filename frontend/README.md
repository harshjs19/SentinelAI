# SentinelAI dashboard

The dashboard is an internal/demo React application over SentinelAI's existing REST API.
It never performs inference, Decision Engine logic, retrieval, report generation, or
historical provenance reconstruction in the browser.

## Local development

Start the backend on `127.0.0.1:8000`, then:

```shell
npm install
npm run dev
```

Vite proxies `/api` to the local backend. To use an explicitly deployed API instead,
set `VITE_API_BASE_URL` to its public base URL. Frontend environment variables must not
contain database or provider credentials.

## Public demonstration build

```shell
npm run build:demo
```

Demo mode is read-only and loads the versioned records in `public/demo/snapshot.json`.
Those records were exported from genuine SentinelAI simulation/replay workflow outputs;
the browser performs no API writes or inference. Model evaluation summaries are derived
from the tracked evaluation artifacts and retain each source path and SHA-256 digest.
The ordinary `npm run build` command remains API-backed.

## Quality commands

```shell
npm run lint
npm run typecheck
npm run test
npm run build
```

The Three.js Sentinel Core is lazy-loaded and decorative. A CSS fallback is used when
WebGL is unavailable, and reduced-motion preferences disable continuous movement.
