import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal, Protocol

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from pydantic import ValidationError

from modules.copilot.context import CopilotGenerationContext
from modules.copilot.contracts import CopilotDraft
from modules.copilot.generator import (
    GeneratedDraftResult,
    GenerationFailureCode,
    MaintenanceGenerationError,
    RepairInstruction,
)
from modules.copilot.prompt import COPILOT_DEVELOPER_POLICY, serialize_provider_context

OPENAI_PROVIDER = "openai"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini-2026-03-17"
_RETRY_DELAY_SECONDS = 0.25
_SNAPSHOT_PATTERN = re.compile(r"-\d{4}-\d{2}-\d{2}$")


class _ResponsesAPI(Protocol):
    async def parse(self, **kwargs: Any) -> Any: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesAPI


@dataclass(frozen=True)
class OpenAIMaintenanceGeneratorConfig:
    model: str = DEFAULT_OPENAI_MODEL
    timeout_seconds: float = 30.0
    max_output_tokens: int = 1200
    temperature: float = 0.0
    reasoning_effort: Literal["none"] = "none"
    transport_retry_count: Literal[0, 1] = 1

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("OpenAI model cannot be empty")
        if isinstance(self.timeout_seconds, bool) or not 0 < self.timeout_seconds <= 60:
            raise ValueError("OpenAI timeout must be between 0 and 60 seconds")
        if isinstance(self.max_output_tokens, bool) or self.max_output_tokens <= 0:
            raise ValueError("OpenAI max output tokens must be positive")
        if isinstance(self.temperature, bool) or self.temperature != 0:
            raise ValueError("Maintenance Copilot temperature is frozen at zero")
        if self.reasoning_effort != "none":
            raise ValueError("Maintenance Copilot reasoning effort is frozen at none")
        if isinstance(self.transport_retry_count, bool) or self.transport_retry_count not in (0, 1):
            raise ValueError("Maintenance Copilot permits at most one transport retry")


class OpenAIMaintenanceGenerator:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: _OpenAIClient | None = None,
        config: OpenAIMaintenanceGeneratorConfig | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if client is not None and api_key is not None:
            raise MaintenanceGenerationError(GenerationFailureCode.CONFIGURATION)
        self.config = config or OpenAIMaintenanceGeneratorConfig()
        self._sleep = sleep
        if client is not None:
            self._client = client
            return
        if api_key is None or not api_key.strip():
            raise MaintenanceGenerationError(GenerationFailureCode.CONFIGURATION)
        try:
            self._client = AsyncOpenAI(
                api_key=api_key,
                max_retries=0,
                timeout=self.config.timeout_seconds,
            )
        except (OpenAIError, TypeError, ValueError):
            raise MaintenanceGenerationError(GenerationFailureCode.CONFIGURATION) from None

    async def generate(
        self,
        context: CopilotGenerationContext,
        repair: RepairInstruction | None = None,
    ) -> GeneratedDraftResult:
        try:
            input_payload = serialize_provider_context(context, repair)
        except (TypeError, ValueError):
            raise MaintenanceGenerationError(GenerationFailureCode.CONFIGURATION) from None
        started = perf_counter()
        attempts = self.config.transport_retry_count + 1
        for attempt in range(attempts):
            try:
                response = await self._client.responses.parse(
                    model=self.config.model,
                    instructions=COPILOT_DEVELOPER_POLICY,
                    input=input_payload,
                    text_format=CopilotDraft,
                    max_output_tokens=self.config.max_output_tokens,
                    temperature=self.config.temperature,
                    reasoning={"effort": self.config.reasoning_effort},
                    store=False,
                    truncation="disabled",
                )
                return self._result(response, started=started, repair=repair)
            except (ValidationError, json.JSONDecodeError):
                raise MaintenanceGenerationError(GenerationFailureCode.MALFORMED_OUTPUT) from None
            except OpenAIError as error:
                code = _classify_openai_error(error)
                if code is GenerationFailureCode.TRANSIENT and attempt + 1 < attempts:
                    await self._sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise MaintenanceGenerationError(code) from None
        raise AssertionError("Generation attempt loop exhausted unexpectedly")

    def _result(
        self,
        response: Any,
        *,
        started: float,
        repair: RepairInstruction | None,
    ) -> GeneratedDraftResult:
        if _has_refusal(response):
            raise MaintenanceGenerationError(GenerationFailureCode.REFUSED)
        status = getattr(response, "status", None)
        if status == "incomplete":
            raise MaintenanceGenerationError(GenerationFailureCode.INCOMPLETE)
        if status != "completed":
            raise MaintenanceGenerationError(GenerationFailureCode.PROVIDER_ERROR)

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise MaintenanceGenerationError(GenerationFailureCode.MALFORMED_OUTPUT)
        try:
            draft = CopilotDraft.model_validate(parsed)
        except (ValidationError, TypeError, ValueError):
            raise MaintenanceGenerationError(GenerationFailureCode.MALFORMED_OUTPUT) from None

        usage = getattr(response, "usage", None)
        response_model = _optional_nonempty_string(getattr(response, "model", None))
        return GeneratedDraftResult(
            draft=draft,
            provider=OPENAI_PROVIDER,
            requested_model=self.config.model,
            response_model=response_model,
            model_snapshot=(
                response_model
                if response_model is not None and _SNAPSHOT_PATTERN.search(response_model)
                else None
            ),
            response_id=_optional_nonempty_string(getattr(response, "id", None)),
            input_tokens=_optional_nonnegative_int(getattr(usage, "input_tokens", None)),
            output_tokens=_optional_nonnegative_int(getattr(usage, "output_tokens", None)),
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            repair_attempted=repair is not None,
        )


def _classify_openai_error(error: OpenAIError) -> GenerationFailureCode:
    if isinstance(error, AuthenticationError):
        return GenerationFailureCode.AUTHENTICATION
    if isinstance(error, PermissionDeniedError):
        return GenerationFailureCode.AUTHENTICATION
    if isinstance(error, BadRequestError | UnprocessableEntityError):
        return GenerationFailureCode.PROVIDER_ERROR

    if isinstance(error, APITimeoutError | APIConnectionError | RateLimitError):
        return GenerationFailureCode.TRANSIENT
        return GenerationFailureCode.TRANSIENT
    if isinstance(error, APIStatusError):
        if error.status_code in (408, 409) or error.status_code >= 500:
            return GenerationFailureCode.TRANSIENT
        if error.status_code in (401, 403):
            return GenerationFailureCode.AUTHENTICATION
        return GenerationFailureCode.PROVIDER_ERROR
    return GenerationFailureCode.PROVIDER_ERROR


def _has_refusal(response: Any) -> bool:
    for output in getattr(response, "output", ()) or ():
        for content in getattr(output, "content", ()) or ():
            if getattr(content, "type", None) == "refusal":
                return True
    return False


def _optional_nonempty_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
