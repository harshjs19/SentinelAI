from backend.app.db.models.machine import MachineModel


def test_machine_table_definition() -> None:
    table = MachineModel.__table__

    assert table.name == "machines"
    assert set(table.columns.keys()) == {"id", "name", "asset_type"}
    assert table.primary_key.columns.keys() == ["id"]
    assert table.c.name.nullable is False
    assert table.c.asset_type.nullable is False
