from dataclasses import dataclass


@dataclass(frozen=True)
class HealthScore:
    value: float

    def __post_init__(self):
        if not 0 <= self.value <= 100:
            raise ValueError("Health score must be between 0 and 100")
