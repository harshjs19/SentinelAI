from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Machine:
    id: UUID
    name: str
    asset_type: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Machine name cannot be empty")

        if not self.asset_type.strip():
            raise ValueError("Machine asset type cannot be empty")
