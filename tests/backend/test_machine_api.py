from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
import pytest_asyncio

from backend.app.dependencies import get_machine_service
from backend.app.main import app
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


@pytest_asyncio.fixture
async def client(repository: InMemoryMachineRepository) -> AsyncIterator[httpx.AsyncClient]:
    app.dependency_overrides[get_machine_service] = lambda: MachineService(repository)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.pop(get_machine_service, None)


@pytest.mark.asyncio
async def test_creates_machine(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/machines",
        json={"name": "Pump-101", "asset_type": "centrifugal_pump"},
    )

    assert response.status_code == 201
    assert UUID(response.json()["id"])
    assert response.json()["name"] == "Pump-101"
    assert response.json()["asset_type"] == "centrifugal_pump"


@pytest.mark.asyncio
async def test_lists_machines(client: httpx.AsyncClient) -> None:
    first = await client.post("/machines", json={"name": "Pump-101", "asset_type": "pump"})
    second = await client.post("/machines", json={"name": "Motor-12", "asset_type": "motor"})

    response = await client.get("/machines")

    assert response.status_code == 200
    assert response.json() == [second.json(), first.json()]


@pytest.mark.asyncio
async def test_gets_machine(client: httpx.AsyncClient) -> None:
    created = await client.post("/machines", json={"name": "Motor-12", "asset_type": "motor"})

    response = await client.get(f"/machines/{created.json()['id']}")

    assert response.status_code == 200
    assert response.json() == created.json()


@pytest.mark.asyncio
async def test_returns_not_found_for_unknown_machine(client: httpx.AsyncClient) -> None:
    response = await client.get("/machines/84c69b6d-3bd9-4a85-b86c-d9db01ebc321")

    assert response.status_code == 404
    assert response.json() == {"detail": "Machine not found"}
