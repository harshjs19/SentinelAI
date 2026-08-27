import hashlib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.repositories.maintenance_request_idempotency_repository import (
    ClaimDisposition,
    MaintenanceRequestIdentity,
)
from backend.app.repositories.sqlalchemy_maintenance_request_idempotency_repository import (
    SQLAlchemyMaintenanceRequestIdempotencyRepository,
)
from backend.app.services.maintenance_workflow_service import (
    AudioMaintenanceRequest,
    MaintenanceWorkflowRequest,
    ThermalMaintenanceRequest,
    TimeseriesMaintenanceRequest,
    VisionMaintenanceRequest,
    maintenance_request_source_provenance,
)
from domain.enums.modality import Modality
from modules.copilot.contracts import normalize_question
from shared.evidence.canonical import canonical_json_bytes

IDEMPOTENCY_FINGERPRINT_VERSION = "maintenance_request_v1"
MAX_IDEMPOTENCY_KEY_CHARACTERS = 200
DEFAULT_IDEMPOTENCY_LEASE = timedelta(minutes=5)


class InvalidIdempotencyKeyError(ValueError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


class IdempotencyInProgressError(RuntimeError):
    pass


class IdempotencyClaimLostError(RuntimeError):
    pass


class ReservationDisposition(StrEnum):
    CLAIMED = "claimed"
    REPLAY = "replay"


@dataclass(frozen=True)
class MaintenanceRequestReservation:
    disposition: ReservationDisposition
    identity: MaintenanceRequestIdentity
    claim_token: UUID | None = None
    report_id: UUID | None = None


class MaintenanceRequestIdempotencyService:
    def __init__(
        self,
        *,
        reservation_session_factory: async_sessionmaker[AsyncSession],
        completion_repository: SQLAlchemyMaintenanceRequestIdempotencyRepository,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], UUID] = uuid4,
        lease_duration: timedelta = DEFAULT_IDEMPOTENCY_LEASE,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("Idempotency lease duration must be positive")
        self._reservation_session_factory = reservation_session_factory
        self._completion_repository = completion_repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory
        self._lease_duration = lease_duration

    async def reserve(
        self,
        raw_key: str,
        request: MaintenanceWorkflowRequest,
    ) -> MaintenanceRequestReservation:
        identity = maintenance_request_identity(raw_key, request)
        now = self._utc_now()
        claim_token = self._token_factory()
        async with self._reservation_session_factory.begin() as session:
            repository = SQLAlchemyMaintenanceRequestIdempotencyRepository(session)
            claim = await repository.claim(
                identity,
                claim_token=claim_token,
                now=now,
                lease_expires_at=now + self._lease_duration,
            )
        if claim.disposition is ClaimDisposition.CONFLICT:
            raise IdempotencyConflictError(
                "Idempotency-Key is already bound to a different request"
            )
        if claim.disposition is ClaimDisposition.IN_PROGRESS:
            raise IdempotencyInProgressError(
                "An identical maintenance request is already processing"
            )
        if claim.disposition is ClaimDisposition.COMPLETED:
            if claim.report_id is None:
                raise IdempotencyClaimLostError("Completed idempotency reservation has no report")
            return MaintenanceRequestReservation(
                disposition=ReservationDisposition.REPLAY,
                identity=identity,
                report_id=claim.report_id,
            )
        if claim.claim_token is None:
            raise IdempotencyClaimLostError(
                "Claimed idempotency reservation has no ownership token"
            )
        return MaintenanceRequestReservation(
            disposition=ReservationDisposition.CLAIMED,
            identity=identity,
            claim_token=claim.claim_token,
        )

    async def release(self, reservation: MaintenanceRequestReservation) -> None:
        if reservation.claim_token is None:
            return
        async with self._reservation_session_factory.begin() as session:
            repository = SQLAlchemyMaintenanceRequestIdempotencyRepository(session)
            await repository.release(reservation.identity, reservation.claim_token)

    async def complete(
        self,
        reservation: MaintenanceRequestReservation,
        report_id: UUID,
    ) -> None:
        if reservation.claim_token is None:
            raise IdempotencyClaimLostError(
                "Idempotency completion requires an active ownership token"
            )
        completed = await self._completion_repository.complete(
            reservation.identity,
            reservation.claim_token,
            report_id,
            completed_at=self._utc_now(),
        )
        if not completed:
            raise IdempotencyClaimLostError("Idempotency claim is no longer active")

    def _utc_now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError("Idempotency clock must return timezone-aware UTC")
        return now


def maintenance_request_identity(
    raw_key: str,
    request: MaintenanceWorkflowRequest,
) -> MaintenanceRequestIdentity:
    validate_idempotency_key(raw_key)
    modality = _request_modality(request)
    source = maintenance_request_source_provenance(request)
    request_payload = {
        "version": IDEMPOTENCY_FINGERPRINT_VERSION,
        "machine_id": request.machine_id,
        "modality": modality,
        "intent": request.intent,
        "question": normalize_question(request.question),
        "source": {
            "kind": source.source_kind,
            "sha256": source.sha256,
            "size_bytes": source.size_bytes,
            "content_type": source.content_type,
        },
    }
    return MaintenanceRequestIdentity(
        idempotency_key_digest=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        request_digest=hashlib.sha256(canonical_json_bytes(request_payload)).hexdigest(),
        machine_id=request.machine_id,
        modality=modality,
    )


def validate_idempotency_key(raw_key: str) -> None:
    if not isinstance(raw_key, str):
        raise InvalidIdempotencyKeyError("Idempotency-Key must be text")
    if not raw_key.strip():
        raise InvalidIdempotencyKeyError("Idempotency-Key cannot be blank")
    if len(raw_key) > MAX_IDEMPOTENCY_KEY_CHARACTERS:
        raise InvalidIdempotencyKeyError(
            f"Idempotency-Key cannot exceed {MAX_IDEMPOTENCY_KEY_CHARACTERS} characters"
        )
    if any(unicodedata.category(character).startswith("C") for character in raw_key):
        raise InvalidIdempotencyKeyError("Idempotency-Key cannot contain control characters")


def _request_modality(request: MaintenanceWorkflowRequest) -> Modality:
    if isinstance(request, TimeseriesMaintenanceRequest):
        return Modality.TIMESERIES
    if isinstance(request, AudioMaintenanceRequest):
        return Modality.AUDIO
    if isinstance(request, VisionMaintenanceRequest):
        return Modality.VISION
    if isinstance(request, ThermalMaintenanceRequest):
        return Modality.THERMAL
    raise TypeError("Unsupported maintenance workflow request type")
