import json
import logging
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from backend.app.observability import (
    MAX_REQUEST_ID_CHARACTERS,
    REQUEST_ID_HEADER,
    JsonLineFormatter,
    RequestObservabilityMiddleware,
)


def _observed_app(logger: logging.Logger, *, fail: bool = False) -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestObservabilityMiddleware, logger=logger)

    @application.post("/probe")
    async def probe() -> dict[str, str]:
        if fail:
            raise RuntimeError("DATABASE_URL=postgres://user:private-password@database")
        return {"status": "ok"}

    return application


@pytest.mark.asyncio
async def test_generated_request_id_is_returned_and_correlated_in_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("tests.request.generated")
    caplog.set_level(logging.INFO, logger=logger.name)
    transport = httpx.ASGITransport(app=_observed_app(logger))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/probe", content=b"private time-series samples")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert UUID(request_id)
    record = caplog.records[-1]
    assert record.event == "http_request"  # type: ignore[attr-defined]
    assert record.request_id == request_id  # type: ignore[attr-defined]
    assert record.method == "POST"  # type: ignore[attr-defined]
    assert record.path == "/probe"  # type: ignore[attr-defined]
    assert record.status_code == 200  # type: ignore[attr-defined]
    assert record.duration_ms >= 0  # type: ignore[attr-defined]
    assert "private time-series samples" not in caplog.text


@pytest.mark.asyncio
async def test_safe_caller_request_id_is_preserved_but_idempotency_key_is_not_used(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("tests.request.provided")
    caplog.set_level(logging.INFO, logger=logger.name)
    transport = httpx.ASGITransport(app=_observed_app(logger))
    provided = "edge-demo.request-42"
    idempotency_key = "full-idempotency-key-must-not-appear"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/probe",
            headers={
                REQUEST_ID_HEADER: provided,
                "Idempotency-Key": idempotency_key,
                "Authorization": "Bearer private-token",
                "Cookie": "session=private-cookie",
            },
            json={"question": "Should private question contents be logged?"},
        )

    assert response.headers[REQUEST_ID_HEADER] == provided
    assert caplog.records[-1].request_id == provided  # type: ignore[attr-defined]
    assert idempotency_key not in caplog.text
    assert "private-token" not in caplog.text
    assert "private-cookie" not in caplog.text
    assert "private question" not in caplog.text


@pytest.mark.parametrize(
    "unsafe_request_id",
    [
        "contains spaces",
        "contains/slash",
        "x" * (MAX_REQUEST_ID_CHARACTERS + 1),
        "!starts-unsafe",
    ],
)
@pytest.mark.asyncio
async def test_unsafe_request_ids_are_replaced(unsafe_request_id: str) -> None:
    logger = logging.getLogger("tests.request.unsafe")
    transport = httpx.ASGITransport(app=_observed_app(logger))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/probe", headers={REQUEST_ID_HEADER: unsafe_request_id})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != unsafe_request_id
    assert UUID(returned)


@pytest.mark.asyncio
async def test_unhandled_exception_is_safe_for_client_and_logs_only_bounded_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("tests.request.failure")
    caplog.set_level(logging.INFO, logger=logger.name)
    transport = httpx.ASGITransport(
        app=_observed_app(logger, fail=True),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/probe")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    request_id = response.headers[REQUEST_ID_HEADER]
    assert UUID(request_id)
    record = caplog.records[-1]
    assert record.event == "http_request_error"  # type: ignore[attr-defined]
    assert record.request_id == request_id  # type: ignore[attr-defined]
    assert record.exception_type == "RuntimeError"  # type: ignore[attr-defined]
    assert "test_observability.py" in record.exception_location  # type: ignore[attr-defined]
    assert "private-password" not in caplog.text
    assert "database_url" not in caplog.text.lower()


def test_json_line_formatter_emits_only_machine_readable_safe_fields() -> None:
    record = logging.LogRecord(
        name="sentinelai.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ignored human message",
        args=(),
        exc_info=None,
    )
    record.event = "http_request"  # type: ignore[attr-defined]
    record.request_id = "request-1"  # type: ignore[attr-defined]
    record.method = "GET"  # type: ignore[attr-defined]
    record.path = "/health"  # type: ignore[attr-defined]
    record.status_code = 200  # type: ignore[attr-defined]
    record.duration_ms = 1.25  # type: ignore[attr-defined]
    record.idempotency_key = "must-not-serialize"  # type: ignore[attr-defined]

    payload = json.loads(JsonLineFormatter().format(record))

    assert payload == {
        "duration_ms": 1.25,
        "event": "http_request",
        "level": "INFO",
        "method": "GET",
        "path": "/health",
        "request_id": "request-1",
        "status_code": 200,
        "timestamp": payload["timestamp"],
    }
    assert "idempotency_key" not in payload
