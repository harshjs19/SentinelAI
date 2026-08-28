
# SentinelAI

SentinelAI is a multimodal predictive maintenance platform that combines machine learning models, sensor data analysis, knowledge retrieval, and AI-assisted maintenance reasoning.

The system is designed to analyze industrial equipment health using multiple sources of information such as visual inspection, audio signals, thermal data, and time-series sensor measurements.

## Overview

SentinelAI follows a layered architecture:

- AI models perform modality-specific analysis.
- A decision layer combines predictions and evaluates equipment health.
- A retrieval layer provides supporting technical knowledge.
- An AI maintenance assistant generates grounded explanations and recommendations.

## Architecture

High-level flow:

## Local database

Start PostgreSQL and Redis, then apply the database migrations:

```shell
docker compose up -d
uv run alembic upgrade head
```

The default values in `.env.example` match the local PostgreSQL service in
`docker-compose.yml`.

## Time-series baseline

Dataset setup, training, evaluation, and inference commands are documented in
[docs/timeseries_baseline.md](docs/timeseries_baseline.md).

## Decision Engine

Decision Engine V1 semantics and evidence limitations are documented in
[docs/decision_engine.md](docs/decision_engine.md).

## Audio baseline

MIMII DG bearing-subset setup, evaluation, confidence semantics, and runtime APIs are
documented in [docs/audio_baseline.md](docs/audio_baseline.md).

The frozen-AST Audio Intelligence V2 representation experiment and promotion protocol
are documented in [docs/audio_v2.md](docs/audio_v2.md).

## Vision baseline

The normal-only VisA PCB1 detector, offline localization evaluation, confidence
semantics, and runtime APIs are documented in
[docs/vision_baseline.md](docs/vision_baseline.md).

## Thermal baseline

The CORA speed-held-out thermal condition classifier, dataset preparation, evaluation,
confidence semantics, and runtime APIs are documented in
[docs/thermal_baseline.md](docs/thermal_baseline.md).

## Model and runtime contracts

Current model lifecycle declarations and their scientific evidence are documented in
[docs/model_capabilities.md](docs/model_capabilities.md). The in-process EventBus and
multi-worker deployment boundaries are documented in
[docs/runtime_architecture.md](docs/runtime_architecture.md).

The deterministic internal contract between Analysis and future retrieval/reporting
consumers is documented in [docs/evidence_package.md](docs/evidence_package.md).

The curated [Knowledge Base source audit](docs/knowledge_sources.md) and deterministic
[Retriever V1 contract](docs/retriever.md) describe source-attributed retrieval. A
[Maintenance Copilot](docs/maintenance_copilot.md) defines closed-book contracts,
deterministic validation, safe fallback, and an explicitly constructed OpenAI Responses
structured-output provider boundary. Bounded internal LangGraph orchestration now connects
generation, validation, one repair, and deterministic report assembly. The frozen
[Copilot adversarial evaluation](docs/copilot_evaluation.md) preserves an offline routing
defect and the successful single deterministic hardening rerun. Paid live evaluation and
human review remain pending. The bounded
[maintenance report API](docs/maintenance_report_api.md) is internal/demo only and must not
be publicly exposed without authorization.

## Premium dashboard

The React/Vite dashboard is in [`frontend/`](frontend/). Local setup, its verified demo
flow, scientific boundaries, and browser fallbacks are documented in
[`docs/premium_dashboard_v1.md`](docs/premium_dashboard_v1.md).
