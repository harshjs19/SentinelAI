from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from edge_simulator.config import SimulatorConfig
from edge_simulator.models import EdgeObservation, MachineRecord, Modality, SubmissionReceipt


class SimulatorError(RuntimeError):
    """Base class for safe, user-facing simulator failures."""


class ApiConnectionError(SimulatorError):
    pass


class ApiTimeoutError(SimulatorError):
    pass


class ApiResponseError(SimulatorError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        category = {
            400: "Request rejected",
            404: "Resource not found",
            409: "Request conflict",
            422: "Request validation failed",
            500: "SentinelAI internal error",
            503: "SentinelAI service unavailable",
        }.get(status_code, "SentinelAI API request failed")
        super().__init__(f"{category} (HTTP {status_code}): {detail}")


class SentinelAIClient:
    """Typed client for SentinelAI's existing public HTTP endpoints."""

    def __init__(
        self,
        config: SimulatorConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.api_base_url,
            timeout=config.httpx_timeout(),
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "SentinelAI-Edge-Simulator/1.0",
            },
        )

    def __enter__(self) -> "SentinelAIClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def new_idempotency_key() -> str:
        return str(uuid4())

    def health(self) -> str:
        document = self._object(self._request("GET", "/health"), "health response")
        api_status = document.get("status")
        if api_status != "ok":
            raise SimulatorError("SentinelAI health endpoint did not report status 'ok'")
        return api_status

    def list_machines(self) -> list[MachineRecord]:
        response = self._request("GET", "/machines")
        document = self._json(response, "machine list")
        if not isinstance(document, list):
            raise SimulatorError("SentinelAI returned an invalid machine list")
        return [self._machine(item) for item in document]

    def get_machine(self, machine_id: str) -> MachineRecord:
        normalized_id = _uuid_string(machine_id, "machine ID")
        document = self._object(
            self._request("GET", f"/machines/{normalized_id}"),
            "machine response",
        )
        return self._machine(document)

    def select_machine(self, machine_id: str | None) -> MachineRecord:
        if machine_id is not None:
            return self.get_machine(machine_id)
        machines = self.list_machines()
        if not machines:
            raise SimulatorError(
                "No machines exist. Create a demo machine through POST /machines, "
                "then pass --machine-id."
            )
        if len(machines) != 1:
            raise SimulatorError(
                f"Found {len(machines)} machines; pass --machine-id to select one explicitly."
            )
        return machines[0]

    def submit_report(
        self,
        machine_id: str,
        observation: EdgeObservation,
        *,
        intent: str,
        question: str | None = None,
        idempotency_key: str | None = None,
    ) -> SubmissionReceipt:
        normalized_id = _uuid_string(machine_id, "machine ID")
        key = idempotency_key or self.new_idempotency_key()
        endpoint = f"/machines/{normalized_id}/maintenance-reports/{observation.modality.value}"
        headers = {"Idempotency-Key": key}

        if observation.modality is Modality.TIMESERIES:
            payload: dict[str, object] = {
                "samples": [sample.to_api_payload() for sample in observation.samples],
                "intent": intent,
            }
            if question is not None:
                payload["question"] = question
            response = self._request("POST", endpoint, headers=headers, json=payload)
        else:
            response = self._submit_media(
                endpoint,
                observation,
                intent=intent,
                question=question,
                headers=headers,
            )

        document = self._object(response, "maintenance report response")
        report_id = document.get("report_id")
        if not isinstance(report_id, str):
            raise SimulatorError("SentinelAI maintenance report response omitted report_id")
        _uuid_string(report_id, "report ID")
        return SubmissionReceipt(
            status_code=response.status_code,
            report_id=report_id,
            replayed=response.headers.get("Idempotent-Replay", "").lower() == "true",
            idempotency_key=key,
            document=document,
        )

    def get_report(self, report_id: str) -> dict[str, object]:
        normalized_id = _uuid_string(report_id, "report ID")
        return self._object(
            self._request("GET", f"/maintenance-reports/{normalized_id}"),
            "maintenance report",
        )

    def get_evidence(self, report_id: str) -> dict[str, object]:
        normalized_id = _uuid_string(report_id, "report ID")
        return self._object(
            self._request("GET", f"/maintenance-reports/{normalized_id}/evidence"),
            "evidence response",
        )

    def get_history(
        self,
        machine_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        normalized_id = _uuid_string(machine_id, "machine ID")
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("History requires limit 1..100 and a non-negative offset")
        document = self._json(
            self._request(
                "GET",
                f"/machines/{normalized_id}/maintenance-reports",
                params={"limit": limit, "offset": offset},
            ),
            "maintenance history",
        )
        if not isinstance(document, list) or not all(isinstance(item, dict) for item in document):
            raise SimulatorError("SentinelAI returned an invalid maintenance history")
        return document

    def _submit_media(
        self,
        endpoint: str,
        observation: EdgeObservation,
        *,
        intent: str,
        question: str | None,
        headers: Mapping[str, str],
    ) -> httpx.Response:
        asset_path = observation.asset_path
        if asset_path is None or observation.content_type is None:
            raise ValueError("Media observation is incomplete")
        form = {"intent": intent}
        if question is not None:
            form["question"] = question
        with Path(asset_path).open("rb") as asset:
            return self._request(
                "POST",
                endpoint,
                headers=headers,
                data=form,
                files={"file": (asset_path.name, asset, observation.content_type)},
            )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, url.lstrip("/"), **kwargs)
        except httpx.TimeoutException as error:
            raise ApiTimeoutError(
                "SentinelAI API request timed out; no automatic retry was attempted."
            ) from error
        except httpx.RequestError as error:
            raise ApiConnectionError(
                f"Cannot reach SentinelAI at {self.config.api_base_url}. "
                "Start the local stack with .\\scripts\\dev.ps1, then retry."
            ) from error
        if not 200 <= response.status_code < 300:
            raise ApiResponseError(response.status_code, self._error_detail(response))
        return response

    @staticmethod
    def _json(response: httpx.Response, description: str) -> object:
        try:
            return response.json()
        except ValueError as error:
            raise SimulatorError(f"SentinelAI returned invalid JSON for {description}") from error

    @classmethod
    def _object(cls, response: httpx.Response, description: str) -> dict[str, object]:
        document = cls._json(response, description)
        if not isinstance(document, dict):
            raise SimulatorError(f"SentinelAI returned an invalid {description}")
        return document

    @classmethod
    def _error_detail(cls, response: httpx.Response) -> str:
        document = cls._json_or_none(response)
        if isinstance(document, dict) and isinstance(document.get("detail"), str):
            return document["detail"]
        return "The API did not provide a public error detail"

    @staticmethod
    def _json_or_none(response: httpx.Response) -> object | None:
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _machine(value: object) -> MachineRecord:
        if not isinstance(value, dict):
            raise SimulatorError("SentinelAI returned an invalid machine record")
        machine_id = value.get("id")
        name = value.get("name")
        asset_type = value.get("asset_type")
        if not all(isinstance(item, str) for item in (machine_id, name, asset_type)):
            raise SimulatorError("SentinelAI returned an incomplete machine record")
        return MachineRecord(_uuid_string(machine_id, "machine ID"), name, asset_type)


def _uuid_string(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as error:
        raise ValueError(f"Invalid {label}: expected a UUID") from error
