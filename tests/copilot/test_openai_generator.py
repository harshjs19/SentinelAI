import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)
from openai.lib._parsing._responses import type_to_text_format_param

from modules.copilot.contracts import (
    CopilotDraft,
    CopilotIntent,
    DraftFindingExplanation,
    SafetyViolationCode,
)
from modules.copilot.generator import (
    GenerationFailureCode,
    MaintenanceGenerationError,
    RepairInstruction,
)
from modules.copilot.openai_generator import (
    DEFAULT_OPENAI_MODEL,
    OpenAIMaintenanceGenerator,
    OpenAIMaintenanceGeneratorConfig,
)
from modules.copilot.policy import decide_request_policy
from modules.copilot.prompt import COPILOT_DEVELOPER_POLICY
from modules.copilot.validation import MaintenanceSafetyValidator
from tests.copilot.support import make_prepared


class FakeResponses:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, *outcomes: object) -> None:
        self.responses = FakeResponses(list(outcomes))


async def _no_sleep(_: float) -> None:
    return None


def _draft() -> CopilotDraft:
    return CopilotDraft(
        executive_summary="The analysis reported a bearing fault.",
        finding_explanations=(
            DraftFindingExplanation(
                finding_id="F1",
                text="The cited source provides bearing-related condition context.",
                citation_ids=("K1",),
            ),
        ),
    )


def _response(
    parsed: object = None,
    *,
    status: str = "completed",
    model: str = DEFAULT_OPENAI_MODEL,
    output: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_test_123",
        model=model,
        status=status,
        incomplete_details=(
            SimpleNamespace(reason="max_output_tokens") if status == "incomplete" else None
        ),
        output=[] if output is None else output,
        output_parsed=_draft() if parsed is None else parsed,
        usage=SimpleNamespace(input_tokens=321, output_tokens=87),
    )


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _status_error(
    error_type: type[APIStatusError],
    status: int,
) -> APIStatusError:
    response = httpx2.Response(status, request=_request())
    return error_type(
        "sensitive provider body sk-test-secret-marker",
        response=response,
        body={"message": "private source https://example.invalid"},
    )


@pytest.mark.asyncio
async def test_valid_generation_records_receipt_and_submits_frozen_request() -> None:
    prepared = make_prepared(question="What does this supplied finding mean?")
    client = FakeClient(_response())
    generator = OpenAIMaintenanceGenerator(client=client, sleep=_no_sleep)

    result = await generator.generate(prepared.context)

    assert result.draft == _draft()
    assert result.provider == "openai"
    assert result.requested_model == DEFAULT_OPENAI_MODEL
    assert result.response_model == DEFAULT_OPENAI_MODEL
    assert result.model_snapshot == DEFAULT_OPENAI_MODEL
    assert result.response_id == "resp_test_123"
    assert result.input_tokens == 321
    assert result.output_tokens == 87
    assert result.latency_ms >= 0
    assert result.repair_attempted is False
    provenance = result.to_generation_provenance(
        temperature=generator.config.temperature,
        reasoning_effort=generator.config.reasoning_effort,
    )
    assert provenance.model == DEFAULT_OPENAI_MODEL
    assert provenance.model_snapshot == DEFAULT_OPENAI_MODEL
    assert provenance.response_id == "resp_test_123"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.4-mini-2026-03-17"
    assert call["instructions"] == COPILOT_DEVELOPER_POLICY
    assert call["text_format"] is CopilotDraft
    assert call["max_output_tokens"] == 1200
    assert call["temperature"] == 0.0
    assert call["reasoning"] == {"effort": "none"}
    assert call["store"] is False
    assert call["truncation"] == "disabled"
    assert "tools" not in call
    assert "tool_choice" not in call
    assert "previous_response_id" not in call
    assert "conversation" not in call


def test_sdk_generated_schema_is_strict_exact_copilot_draft_contract() -> None:
    text_format = type_to_text_format_param(CopilotDraft)
    schema = text_format["schema"]

    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "executive_summary",
        "finding_explanations",
        "inspection_considerations",
        "knowledge_gap_statement",
    }
    assert schema["properties"]["executive_summary"]["maxLength"] == 700
    assert schema["properties"]["finding_explanations"]["maxItems"] == 3
    assert schema["properties"]["inspection_considerations"]["maxItems"] == 3
    assert all(
        definition["additionalProperties"] is False for definition in schema["$defs"].values()
    )
    forbidden = {"condition", "risk", "health", "severity", "model_id", "source_uri"}
    assert forbidden.isdisjoint(schema["properties"])


@pytest.mark.parametrize(
    "invalid",
    [
        {
            "executive_summary": "Summary",
            "finding_explanations": [],
            "inspection_considerations": [],
            "knowledge_gap_statement": None,
            "condition": "abnormal",
        },
        {
            "executive_summary": "Summary",
            "finding_explanations": [{"finding_id": "F1", "text": "text", "citation_ids": ["K1"]}],
            "inspection_considerations": [
                {"finding_id": "F1", "text": "text", "citation_ids": ["K1"]}
            ]
            * 4,
            "knowledge_gap_statement": None,
        },
        {
            "executive_summary": "x" * 701,
            "finding_explanations": [],
            "inspection_considerations": [],
            "knowledge_gap_statement": None,
        },
        {
            "executive_summary": 12,
            "finding_explanations": [],
            "inspection_considerations": [],
            "knowledge_gap_statement": None,
        },
    ],
    ids=["additional-property", "too-many-considerations", "overlong", "pydantic-invalid"],
)
@pytest.mark.asyncio
async def test_invalid_structured_draft_is_malformed_without_retry(invalid: object) -> None:
    client = FakeClient(_response(invalid))
    generator = OpenAIMaintenanceGenerator(client=client, sleep=_no_sleep)

    with pytest.raises(MaintenanceGenerationError) as raised:
        await generator.generate(make_prepared().context)

    assert raised.value.code is GenerationFailureCode.MALFORMED_OUTPUT
    assert len(client.responses.calls) == 1


@pytest.mark.asyncio
async def test_sdk_parse_failure_is_malformed_without_retry() -> None:
    error = json.JSONDecodeError("secret malformed output", "private draft", 0)
    client = FakeClient(error)
    generator = OpenAIMaintenanceGenerator(client=client, sleep=_no_sleep)

    with pytest.raises(MaintenanceGenerationError) as raised:
        await generator.generate(make_prepared().context)

    assert raised.value.code is GenerationFailureCode.MALFORMED_OUTPUT
    assert len(client.responses.calls) == 1
    assert "private draft" not in str(raised.value)


@pytest.mark.asyncio
async def test_missing_structured_output_is_malformed() -> None:
    response = _response()
    response.output_parsed = None
    client = FakeClient(response)

    with pytest.raises(MaintenanceGenerationError) as raised:
        await OpenAIMaintenanceGenerator(client=client).generate(make_prepared().context)

    assert raised.value.code is GenerationFailureCode.MALFORMED_OUTPUT
    assert len(client.responses.calls) == 1


@pytest.mark.asyncio
async def test_oversized_provider_context_fails_before_any_provider_call() -> None:
    prepared = make_prepared()
    context = replace(
        prepared.context,
        citations=(replace(prepared.context.citations[0], text="x" * 1201),),
    )
    client = FakeClient(_response())

    with pytest.raises(MaintenanceGenerationError) as raised:
        await OpenAIMaintenanceGenerator(client=client).generate(context)

    assert raised.value.code is GenerationFailureCode.CONFIGURATION
    assert client.responses.calls == []


@pytest.mark.asyncio
async def test_explicit_refusal_is_separate_and_not_returned_as_a_draft() -> None:
    refusal = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="refusal", refusal="private refusal text")],
    )
    client = FakeClient(_response(output=[refusal]))

    with pytest.raises(MaintenanceGenerationError) as raised:
        await OpenAIMaintenanceGenerator(client=client).generate(make_prepared().context)

    assert raised.value.code is GenerationFailureCode.REFUSED
    assert "private refusal text" not in str(raised.value)
    assert len(client.responses.calls) == 1


@pytest.mark.asyncio
async def test_incomplete_response_is_separate_and_partial_output_is_discarded() -> None:
    client = FakeClient(_response(status="incomplete"))

    with pytest.raises(MaintenanceGenerationError) as raised:
        await OpenAIMaintenanceGenerator(client=client).generate(make_prepared().context)

    assert raised.value.code is GenerationFailureCode.INCOMPLETE
    assert len(client.responses.calls) == 1


@pytest.mark.asyncio
async def test_response_model_mismatch_is_recorded_without_being_silently_rewritten() -> None:
    client = FakeClient(_response(model="gpt-5.4-mini"))

    result = await OpenAIMaintenanceGenerator(client=client).generate(make_prepared().context)

    assert result.requested_model == DEFAULT_OPENAI_MODEL
    assert result.response_model == "gpt-5.4-mini"
    assert result.model_snapshot is None


@pytest.mark.parametrize(
    "factory",
    [
        lambda: APIConnectionError(message="private connection body", request=_request()),
        lambda: APITimeoutError(_request()),
        lambda: _status_error(RateLimitError, 429),
        lambda: _status_error(APIStatusError, 503),
        lambda: _status_error(APIStatusError, 408),
        lambda: _status_error(APIStatusError, 409),
    ],
    ids=["connection", "timeout", "rate-limit", "server", "request-timeout", "conflict"],
)
@pytest.mark.asyncio
async def test_transient_failures_receive_exactly_one_application_retry(
    factory: Callable[[], BaseException],
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    client = FakeClient(factory(), factory())
    generator = OpenAIMaintenanceGenerator(client=client, sleep=record_sleep)

    with pytest.raises(MaintenanceGenerationError) as raised:
        await generator.generate(make_prepared().context)

    assert raised.value.code is GenerationFailureCode.TRANSIENT
    assert len(client.responses.calls) == 2
    assert delays == [0.25]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (_status_error(AuthenticationError, 401), GenerationFailureCode.AUTHENTICATION),
        (_status_error(PermissionDeniedError, 403), GenerationFailureCode.AUTHENTICATION),
        (_status_error(BadRequestError, 400), GenerationFailureCode.PROVIDER_ERROR),
        (_status_error(APIStatusError, 422), GenerationFailureCode.PROVIDER_ERROR),
    ],
    ids=["authentication", "permission", "bad-request", "unprocessable"],
)
@pytest.mark.asyncio
async def test_non_transient_provider_errors_are_safe_and_not_retried(
    error: BaseException,
    code: GenerationFailureCode,
) -> None:
    client = FakeClient(error)
    generator = OpenAIMaintenanceGenerator(client=client, sleep=_no_sleep)

    with pytest.raises(MaintenanceGenerationError) as raised:
        await generator.generate(make_prepared().context)

    assert raised.value.code is code
    assert len(client.responses.calls) == 1
    message = str(raised.value)
    assert "sk-test-secret-marker" not in message
    assert "https://example.invalid" not in message
    assert "private source" not in message


def test_client_construction_disables_sdk_retries_and_sets_explicit_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    client = FakeClient(_response())

    def fake_openai(**kwargs: object) -> FakeClient:
        captured.update(kwargs)
        return client

    monkeypatch.setattr("modules.copilot.openai_generator.AsyncOpenAI", fake_openai)

    OpenAIMaintenanceGenerator(api_key="synthetic-test-key")

    assert captured == {
        "api_key": "synthetic-test-key",
        "max_retries": 0,
        "timeout": 30.0,
    }


def test_missing_api_key_is_normalized_configuration_failure() -> None:
    with pytest.raises(MaintenanceGenerationError) as raised:
        OpenAIMaintenanceGenerator(api_key="  ")

    assert raised.value.code is GenerationFailureCode.CONFIGURATION
    assert "key" not in str(raised.value).lower()


def test_provider_config_is_frozen_and_has_exact_baseline_defaults() -> None:
    config = OpenAIMaintenanceGeneratorConfig()

    assert config == OpenAIMaintenanceGeneratorConfig(
        model="gpt-5.4-mini-2026-03-17",
        timeout_seconds=30.0,
        max_output_tokens=1200,
        temperature=0.0,
        reasoning_effort="none",
        transport_retry_count=1,
    )
    with pytest.raises(FrozenInstanceError):
        config.model = "gpt-5.4-mini"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_repair_mode_is_single_direct_generation_and_marks_receipt() -> None:
    prepared = make_prepared()
    repair = RepairInstruction(_draft(), (SafetyViolationCode.HIGH_IMPACT_ACTION,))
    client = FakeClient(_response())
    generator = OpenAIMaintenanceGenerator(client=client, sleep=_no_sleep)

    result = await generator.generate(prepared.context, repair)

    assert result.repair_attempted is True
    assert len(client.responses.calls) == 1
    payload = json.loads(client.responses.calls[0]["input"])
    assert payload["repair"]["violation_codes"] == ["high_impact_action"]


@pytest.mark.asyncio
async def test_generated_draft_composes_directly_with_existing_validator() -> None:
    prepared = make_prepared()
    generator = OpenAIMaintenanceGenerator(client=FakeClient(_response()))

    result = await generator.generate(prepared.context)
    validation = MaintenanceSafetyValidator().validate(result.draft, prepared)

    assert validation.valid is True
    assert validation.violations == ()


@pytest.mark.parametrize(
    "prepared_factory",
    [
        lambda: make_prepared(intent=CopilotIntent.EXPLAIN_CONFIDENCE),
        lambda: make_prepared(intent=CopilotIntent.EXPLAIN_LIMITATIONS),
        lambda: make_prepared(question="Should I shut down the machine?"),
        lambda: make_prepared(specs=()),
    ],
    ids=["confidence", "limitations", "high-impact", "no-grounded-content"],
)
@pytest.mark.asyncio
async def test_deterministic_policy_bypasses_provider(
    prepared_factory: Callable[[], object],
) -> None:
    prepared = prepared_factory()
    client = FakeClient(_response())
    generator = OpenAIMaintenanceGenerator(client=client)

    decision = decide_request_policy(prepared)  # type: ignore[arg-type]
    if decision.provider_required:
        await generator.generate(prepared.context)  # type: ignore[union-attr]

    assert decision.provider_required is False
    assert client.responses.calls == []
