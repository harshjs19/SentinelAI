from uuid import UUID, uuid4

import pytest

from backend.app.services.machine_service import MachineService
from domain.entities.machine import Machine


class InMemoryMachineRepository:
    def __init__(self) -> None:
        self.machines: dict[UUID, Machine] = {}

    async def add(self, machine: Machine) -> None:
        self.machines[machine.id] = machine

    async def get_by_id(self, machine_id: UUID) -> Machine | None:
        return self.machines.get(machine_id)

    async def list_all(self) -> list[Machine]:
        return sorted(self.machines.values(), key=lambda machine: (machine.name, machine.id))


@pytest.fixture
def repository() -> InMemoryMachineRepository:
    return InMemoryMachineRepository()


@pytest.fixture
def service(repository: InMemoryMachineRepository) -> MachineService:
    return MachineService(repository)


@pytest.mark.asyncio
async def test_creates_machine(
    service: MachineService,
    repository: InMemoryMachineRepository,
) -> None:
    machine = await service.create_machine(
        name="Pump-101",
        asset_type="centrifugal_pump",
    )

    assert machine.name == "Pump-101"
    assert machine.asset_type == "centrifugal_pump"
    assert repository.machines[machine.id] == machine


@pytest.mark.asyncio
async def test_normalizes_machine_fields(service: MachineService) -> None:
    machine = await service.create_machine(
        name="  Pump-101  ",
        asset_type="  centrifugal_pump  ",
    )

    assert machine.name == "Pump-101"
    assert machine.asset_type == "centrifugal_pump"


@pytest.mark.asyncio
async def test_gets_machine(
    service: MachineService,
) -> None:
    created = await service.create_machine(
        name="Motor-12",
        asset_type="motor",
    )

    machine = await service.get_machine(created.id)

    assert machine == created


@pytest.mark.asyncio
async def test_returns_none_for_unknown_machine(
    service: MachineService,
) -> None:
    machine = await service.get_machine(uuid4())

    assert machine is None


@pytest.mark.asyncio
async def test_lists_machines(service: MachineService) -> None:
    first = await service.create_machine("Pump-101", "pump")
    second = await service.create_machine("Motor-12", "motor")

    machines = await service.list_machines()

    assert machines == [second, first]
