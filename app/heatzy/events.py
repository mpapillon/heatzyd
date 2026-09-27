import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable

logger = logging.getLogger(__name__)


class EventEmitter:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, callback: Callable) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable) -> None:
        if callback in self._listeners.get(event, []):
            self._listeners[event].remove(callback)

    async def emit(self, event: str, *args, **kwargs) -> None:
        for callback in list(self._listeners.get(event, [])):
            result = callback(*args, **kwargs)
            if asyncio.iscoroutine(result):
                await result
