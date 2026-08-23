from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_session
from backend.app.repositories.sqlalchemy_machine_repository import (
    SQLAlchemyMachineRepository,
)
from backend.app.services.machine_service import MachineService

SessionDependency = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_machine_service(session: SessionDependency) -> MachineService:
    return MachineService(SQLAlchemyMachineRepository(session))
