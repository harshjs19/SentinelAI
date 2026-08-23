from uuid import uuid4

import pytest

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced


def prediction_event() -> PredictionProduced:
    return PredictionProduced(
        machine_id=uuid4(),
        prediction=Prediction(
            modality=Modality.TIMESERIES,
            label="bearing_fault",
            confidence=0.91,
        ),
    )


@pytest.mark.asyncio
async def test_handler_receives_prediction_event() -> None:
    bus = EventBus()
    received: list[PredictionProduced] = []

    async def handler(event: PredictionProduced) -> None:
        received.append(event)

    bus.subscribe(PredictionProduced, handler)
    event = prediction_event()

    await bus.publish(event)

    assert received == [event]


@pytest.mark.asyncio
async def test_handlers_run_in_registration_order() -> None:
    bus = EventBus()
    calls: list[str] = []

    async def first(event: PredictionProduced) -> None:
        calls.append("first")

    async def second(event: PredictionProduced) -> None:
        calls.append("second")

    bus.subscribe(PredictionProduced, first)
    bus.subscribe(PredictionProduced, second)

    await bus.publish(prediction_event())

    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_publishing_without_subscribers_succeeds() -> None:
    await EventBus().publish(prediction_event())


@pytest.mark.asyncio
async def test_handler_failure_propagates() -> None:
    bus = EventBus()

    async def failing_handler(event: PredictionProduced) -> None:
        raise RuntimeError("consumer failed")

    bus.subscribe(PredictionProduced, failing_handler)

    with pytest.raises(RuntimeError, match="consumer failed"):
        await bus.publish(prediction_event())
