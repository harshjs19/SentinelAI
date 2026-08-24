import pytest

from backend.app.errors import model_unavailable_error


@pytest.mark.parametrize("model_name", ["Time-series", "Audio", "Vision", "Thermal"])
def test_model_unavailable_error_is_a_safe_service_unavailable_response(
    model_name: str,
) -> None:
    error = model_unavailable_error(model_name)

    assert error.status_code == 503
    assert error.detail == f"{model_name} model is not available"
