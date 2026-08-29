import json
import logging
import re
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.config import Settings

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_CHARACTERS = 64
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_SAFE_LOG_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "exception_type",
    "exception_location",
    "environment",
    "version",
)


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
        }
        for field in _SAFE_LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class ReadableFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", record.getMessage())
        details = [
            f"{field}={getattr(record, field)}"
            for field in _SAFE_LOG_FIELDS
            if getattr(record, field, None) is not None
        ]
        suffix = f" {' '.join(details)}" if details else ""
        return f"{record.levelname} event={event}{suffix}"


def configure_application_logging(settings: Settings) -> None:
    logger = logging.getLogger("sentinelai")
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonLineFormatter() if settings.log_format == "json" else ReadableFormatter()
    )
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    logger.propagate = False


def log_startup(settings: Settings, version: str) -> None:
    logging.getLogger("sentinelai.startup").info(
        "SentinelAI API started",
        extra={
            "event": "api_started",
            "environment": settings.app_env,
            "version": version,
        },
    )


class RequestObservabilityMiddleware:
    """Add a bounded request ID and privacy-safe request completion log."""

    def __init__(self, app: ASGIApp, logger: logging.Logger | None = None) -> None:
        self._app = app
        self._logger = logger or logging.getLogger("sentinelai.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _request_id(scope)
        method = str(scope.get("method", "UNKNOWN"))[:16]
        path = str(scope.get("path", "/"))[:512]
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        except Exception as error:
            duration_ms = _duration_ms(started)
            self._logger.error(
                "HTTP request failed",
                extra={
                    "event": "http_request_error",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "exception_type": type(error).__name__,
                    "exception_location": _exception_location(error),
                },
            )
            if response_started:
                raise
            response = PlainTextResponse(
                "Internal Server Error",
                status_code=500,
                headers={REQUEST_ID_HEADER: request_id},
            )
            await response(scope, receive, send)
            return

        self._logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": _duration_ms(started),
            },
        )


def _request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", ()):
        if name.lower() != b"x-request-id":
            continue
        try:
            candidate = value.decode("ascii")
        except UnicodeDecodeError:
            break
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        break
    return str(uuid4())


def _duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _exception_location(error: Exception) -> str:
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "unavailable"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
