# Local container deployment

This deployment is for a developer workstation or controlled demonstration. It is not
approved for public-Internet exposure. SentinelAI currently has no authentication,
authorization, TLS termination, rate limiting, device identity, fleet enrollment,
external secret manager, or multi-instance event delivery.

## Runtime shape

`compose.deploy.yml` runs the smallest useful topology:

```text
browser / edge simulator
        |
        | http://127.0.0.1:<frontend-port>
        v
unprivileged Nginx frontend -- /api/* --> single-worker FastAPI
                                                |
                                                v
                                       internal PostgreSQL 16
```

A one-shot `migrate` container applies committed Alembic migrations after PostgreSQL is
healthy. FastAPI starts only after migration succeeds. PostgreSQL is stored in the named
volume `sentinelai_deploy_postgres_data`; neither PostgreSQL nor FastAPI is published on
the host. Redis is omitted because the current application does not use it for events,
inference, persistence, retrieval, or reports.

The API uses one Uvicorn worker. The existing `EventBus` is process-local, so multiple
workers would create separate delivery domains. There is no reload process in this
deployment. Graceful container stops are handled by Uvicorn, Nginx, and PostgreSQL.

## Image-buildable versus inference-ready

Both images build from a clean clone. The API can start, serve health/readiness,
capabilities, machines, and persisted history without an OpenAI API key. A clean clone
is not full-inference-ready because model binaries and generated retrieval indexes are
intentionally ignored by Git and excluded from image build contexts.

The locked Python environment selects the official CPU-only PyTorch index for `torch`
and `torchvision`. The current container has no GPU runtime requirement; this prevents
unused CUDA libraries from entering the API image while preserving the pinned package
versions and existing CPU inference behavior.

The deployment mounts these local directories:

- read-only `models/`, containing the configured time-series, audio, vision, and thermal Joblib
  artifacts and the local AST/ResNet encoder directories required by those lanes;
- writable `knowledge/chroma/`, containing the generated Chroma collection, because the
  embedded Chroma client opens its SQLite persistence in write mode even for queries;
- read-only `knowledge/embeddings/`, containing the pinned local embedding model snapshot.

The tracked `knowledge/sources/manifest.json` and curated sources are built into the API
image, but they are not a substitute for the generated Chroma collection and embedding
snapshot. An absent model continues to produce the API's explicit availability failure;
the deployment never downloads or fabricates a model. An absent retrieval asset means a
maintenance workflow cannot complete retrieval. Set the three directory variables in
`.env.deploy` when the assets live outside the repository. Host paths must be usable by
Docker Desktop and must correspond to the producing artifact metadata.

Artifact directories are external deployment inputs, not baked secrets. Model and
retrieval preparation remains the responsibility of the existing documented offline
workflows. Do not commit the generated assets. Back up the Chroma directory before a
deployment that matters; its writable mount is a runtime compatibility requirement, not
permission for the API to rebuild the knowledge corpus.

## Start and verify

From the repository root in PowerShell:

```powershell
Copy-Item .env.deploy.example .env.deploy
```

Set a unique local `SENTINELAI_POSTGRES_PASSWORD` in `.env.deploy`. Do not reuse the
example development password or commit this file. Then run:

```powershell
docker compose --env-file .env.deploy -f compose.deploy.yml up --build -d
docker compose --env-file .env.deploy -f compose.deploy.yml ps
.\scripts\smoke_deployment.ps1
```

The dashboard is available at `http://127.0.0.1:8080` by default. The smoke script sends
all API checks through Nginx `/api`; it verifies liveness, database readiness, machine
listing, capabilities, and response request IDs. It does not run inference.

To use the existing external edge simulator through the same deployment boundary:

```powershell
$env:SENTINELAI_API_BASE_URL = "http://127.0.0.1:8080/api"
uv run python -m edge_simulator health
uv run python -m edge_simulator demo --machine-id <uuid>
```

The simulator remains an HTTP-only client. Full demo execution requires the applicable
model and retrieval assets described above. No `OPENAI_API_KEY` is required: requests
that need an unavailable generation provider retain the existing deterministic safe
fallback behavior.

## Health, logs, and diagnostics

- `GET /health` is process liveness and deliberately performs no dependency work.
- `GET /ready` executes only `SELECT 1` against PostgreSQL. It returns a safe 503 body
  when the database is unavailable and does not load models, retrieval, or providers.
- Container health checks use PostgreSQL readiness, FastAPI `/health`, and Nginx
  `/healthz`.
- Every API response has `X-Request-ID`. A bounded safe caller value is preserved;
  otherwise the API generates a UUID.
- Deployment request logs are JSON lines with timestamp, level, event, request ID,
  method, path, status, and duration. They deliberately exclude request/response bodies,
  media, sensor samples, questions, idempotency keys, authorization/cookies, environment
  variables, database URLs, and provider credentials.
- Unhandled exceptions return a generic 500 response and log only the exception type
  and bounded code location. They do not serialize the exception message.

Useful diagnostics:

```powershell
docker compose --env-file .env.deploy -f compose.deploy.yml ps
docker compose --env-file .env.deploy -f compose.deploy.yml logs migrate
docker compose --env-file .env.deploy -f compose.deploy.yml logs --tail 100 api frontend postgres
```

The migration container should exit with code 0. If it fails, the API remains gated and
does not start. If `/health` succeeds but `/ready` returns 503, inspect PostgreSQL health
and API logs without printing `.env.deploy`.

## Restart, persistence, and shutdown

Restarting the API does not remove report data or idempotency records because both are
in PostgreSQL:

```powershell
docker compose --env-file .env.deploy -f compose.deploy.yml restart api frontend
```

To stop the deployment while preserving its named database volume:

```powershell
docker compose --env-file .env.deploy -f compose.deploy.yml down
```

Do not add `--volumes` unless deletion is deliberate and a backup exists. The named
volume is local Docker state, not a backup. For material demo data, use normal PostgreSQL
backup/restore procedures and test restoration before relying on them.

Local development remains separate and unchanged:

```powershell
.\scripts\dev.ps1
```

That workflow keeps Vite hot reload and the development Compose services. The deployment
Compose file does not replace it.

## Security boundary

Only the frontend binds to the loopback interface. This reduces accidental LAN exposure
but is not an access-control system. Nginx adds basic content-type, referrer, and frame
headers and serves the existing WebGL fallback unchanged. No frontend secret is used or
baked into the bundle. Do not bind the frontend to a public interface or place this stack
on the Internet until authentication/authorization, TLS, rate limiting, upload controls,
secret management, network policy, dependency/image scanning policy, backups, and
multi-process workflow/event semantics have been designed and reviewed.
