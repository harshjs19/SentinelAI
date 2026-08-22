from uuid import uuid4

import pytest

from domain.entities.machine import Machine


def test_creates_machine() -> None:
    machine_id = uuid4()

    machine = Machine(
        id=machine_id,
        name="Pump-101",
        asset_type="centrifugal_pump",
    )

    assert machine.id == machine_id
    assert machine.name == "Pump-101"
    assert machine.asset_type == "centrifugal_pump"


def test_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="Machine name cannot be empty"):
        Machine(
            id=uuid4(),
            name="",
            asset_type="pump",
        )


def test_rejects_empty_asset_type() -> None:
    with pytest.raises(ValueError, match="Machine asset type cannot be empty"):
        Machine(
            id=uuid4(),
            name="Pump-101",
            asset_type="   ",
        )
