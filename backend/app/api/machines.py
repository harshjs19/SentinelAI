from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_machine_service
from backend.app.schemas.machine import MachineCreate, MachineResponse
from backend.app.services.machine_service import MachineService

router = APIRouter(prefix="/machines", tags=["machines"])
MachineServiceDependency = Annotated[MachineService, Depends(get_machine_service)]


@router.post("", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
async def create_machine(
    machine_create: MachineCreate,
    service: MachineServiceDependency,
) -> MachineResponse:
    machine = await service.create_machine(machine_create.name, machine_create.asset_type)
    return MachineResponse.model_validate(machine, from_attributes=True)


@router.get("", response_model=list[MachineResponse])
async def list_machines(service: MachineServiceDependency) -> list[MachineResponse]:
    machines = await service.list_machines()
    return [MachineResponse.model_validate(machine, from_attributes=True) for machine in machines]


@router.get("/{machine_id}", response_model=MachineResponse)
async def get_machine(
    machine_id: UUID,
    service: MachineServiceDependency,
) -> MachineResponse:
    machine = await service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    return MachineResponse.model_validate(machine, from_attributes=True)
