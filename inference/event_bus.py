from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

EventT = TypeVar("EventT")
EventHandler = Callable[[EventT], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[object], list[EventHandler[object]]] = {}

    def subscribe(self, event_type: type[EventT], handler: EventHandler[EventT]) -> None:
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(cast(EventHandler[object], handler))

    async def publish(self, event: object) -> None:
        for handler in self._handlers.get(type(event), ()):
            await handler(event)
