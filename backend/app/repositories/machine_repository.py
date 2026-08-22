from typing import Protocol
from uuid import UUID

from domain.entities.machine import Machine


class MachineRepository(Protocol):
    async def add(self, machine: Machine) -> None: ...

    async def get_by_id(self, machine_id: UUID) -> Machine | None: ...

    async def list_all(self) -> list[Machine]: ...
