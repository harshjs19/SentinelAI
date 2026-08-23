from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.machine import MachineModel
from backend.app.repositories.sqlalchemy_machine_repository import (
    SQLAlchemyMachineRepository,
)
from domain.entities.machine import Machine


@pytest.fixture
def session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.get = AsyncMock()
    session.scalars = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_adds_domain_machine_as_model(session: MagicMock) -> None:
    machine = Machine(id=uuid4(), name="Pump-101", asset_type="pump")
    repository = SQLAlchemyMachineRepository(session)

    await repository.add(machine)

    model = session.add.call_args.args[0]
    assert isinstance(model, MachineModel)
    assert (model.id, model.name, model.asset_type) == (
        machine.id,
        machine.name,
        machine.asset_type,
    )
    session.flush.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_maps_model_to_domain_machine(session: MagicMock) -> None:
    machine_id = uuid4()
    session.get.return_value = MachineModel(
        id=machine_id,
        name="Motor-12",
        asset_type="motor",
    )
    repository = SQLAlchemyMachineRepository(session)

    machine = await repository.get_by_id(machine_id)

    assert machine == Machine(id=machine_id, name="Motor-12", asset_type="motor")


@pytest.mark.asyncio
async def test_lists_mapped_machines(session: MagicMock) -> None:
    machine_id = uuid4()
    session.scalars.return_value = [
        MachineModel(id=machine_id, name="Motor-12", asset_type="motor")
    ]
    repository = SQLAlchemyMachineRepository(session)

    machines = await repository.list_all()

    assert machines == [Machine(id=machine_id, name="Motor-12", asset_type="motor")]
