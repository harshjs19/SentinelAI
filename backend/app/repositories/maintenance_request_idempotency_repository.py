from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from domain.enums.modality import Modality


class MaintenanceRequestStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"


class ClaimDisposition(StrEnum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class MaintenanceRequestIdentity:
    idempotency_key_digest: str
    request_digest: str
    machine_id: UUID
    modality: Modality


@dataclass(frozen=True)
class MaintenanceRequestClaim:
    disposition: ClaimDisposition
    claim_token: UUID | None = None
    report_id: UUID | None = None


class MaintenanceRequestIdempotencyRepository(Protocol):
    async def claim(
        self,
        identity: MaintenanceRequestIdentity,
        *,
        claim_token: UUID,
        now: datetime,
        lease_expires_at: datetime,
    ) -> MaintenanceRequestClaim: ...

    async def release(
        self,
        identity: MaintenanceRequestIdentity,
        claim_token: UUID,
    ) -> bool: ...

    async def complete(
        self,
        identity: MaintenanceRequestIdentity,
        claim_token: UUID,
        report_id: UUID,
        *,
        completed_at: datetime,
    ) -> bool: ...
