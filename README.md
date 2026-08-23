
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
