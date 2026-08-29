from collections.abc import Iterator

import httpx
import pytest

from backend.app.db.session import engine
from backend.app.main import app
from backend.app.readiness import database_is_ready


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readiness_returns_ready_when_database_check_succeeds() -> None:
    app.dependency_overrides[database_is_ready] = lambda: True
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_readiness_fails_safely_when_database_is_unavailable() -> None:
    app.dependency_overrides[database_is_ready] = lambda: False
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    serialized = response.text.lower()
    assert "postgres" not in serialized
    assert "password" not in serialized
    assert "database_url" not in serialized


@pytest.mark.asyncio
async def test_real_readiness_check_uses_only_the_database_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden_modules = (
        "get_timeseries_predictor",
        "get_audio_predictor",
        "get_vision_predictor",
        "get_thermal_predictor",
        "get_knowledge_retriever",
        "get_maintenance_copilot_service",
    )

    def forbidden() -> None:
        raise AssertionError("Readiness executed non-database runtime work")

    import backend.app.dependencies as dependencies

    for name in forbidden_modules:
        monkeypatch.setattr(dependencies, name, forbidden)

    try:
        assert await database_is_ready() is True
    finally:
        await engine.dispose()
