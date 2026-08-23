from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.machine import MachineModel
from domain.entities.machine import Machine


class SQLAlchemyMachineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, machine: Machine) -> None:
        self.session.add(self._to_model(machine))
        await self.session.flush()

    async def get_by_id(self, machine_id: UUID) -> Machine | None:
        model = await self.session.get(MachineModel, machine_id)
        return self._to_domain(model) if model is not None else None

    async def list_all(self) -> list[Machine]:
        result = await self.session.scalars(
            select(MachineModel).order_by(MachineModel.name, MachineModel.id)
        )
        return [self._to_domain(model) for model in result]

    @staticmethod
    def _to_model(machine: Machine) -> MachineModel:
        return MachineModel(
            id=machine.id,
            name=machine.name,
            asset_type=machine.asset_type,
        )

    @staticmethod
    def _to_domain(model: MachineModel) -> Machine:
        return Machine(
            id=model.id,
            name=model.name,
            asset_type=model.asset_type,
        )
