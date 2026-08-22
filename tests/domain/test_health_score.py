import pytest

from domain.value_objects.health_score import HealthScore


def test_accepts_score_within_range() -> None:
    score = HealthScore(72.5)

    assert score.value == 72.5


@pytest.mark.parametrize("value", [-0.1, 100.1])
def test_rejects_score_outside_range(value: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        HealthScore(value)
