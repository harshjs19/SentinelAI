from uuid import UUID, uuid4

from backend.app.repositories.machine_repository import MachineRepository
from domain.entities.machine import Machine


class MachineService:
    def __init__(self, repository: MachineRepository) -> None:
        self.repository = repository

    async def create_machine(self, name: str, asset_type: str) -> Machine:
        machine = Machine(
            id=uuid4(),
            name=name.strip(),
            asset_type=asset_type.strip(),
        )

        await self.repository.add(machine)

        return machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        return await self.repository.get_by_id(machine_id)

    async def list_machines(self) -> list[Machine]:
        return await self.repository.list_all()
