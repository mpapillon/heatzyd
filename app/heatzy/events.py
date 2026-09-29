import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

type Handler = Callable[[Any], Awaitable[None] | None]

logger = logging.getLogger(__name__)

_MAX_PENDING = 64
_SLOW = object()


class EventEmitter:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Handler]] = defaultdict(list)
        self._pending: set[asyncio.Task] = set()

    def on(self, event: str, callback: Handler) -> Handler:
        self._listeners[event].append(callback)
        return callback

    def off(self, event: str, callback: Handler) -> None:
        if callback in self._listeners.get(event, []):
            self._listeners[event].remove(callback)
            if not self._listeners[event]:
                del self._listeners[event]

    def emit(self, event: str, payload: Any) -> None:
        for callback in list(self._listeners.get(event, [])):
            try:
                res = callback(payload)
            except Exception:
                logger.exception("Error in event listener: %s", event)
                continue
            if inspect.isawaitable(res):
                self._spawn(res, event)

    def _spawn(self, awaitable: Awaitable[None], event: str) -> None:
        task = asyncio.ensure_future(awaitable)
        self._pending.add(task)

        def _done(t: asyncio.Task) -> None:
            self._pending.discard(t)
            if t.cancelled():
                return
            if (exc := t.exception()) is not None:
                logger.error("Error in event listener: %s", event, exc_info=exc)

        task.add_done_callback(_done)

    async def stream(self, event: str):
        queue: asyncio.Queue[Any] = asyncio.Queue(_MAX_PENDING)

        def _push(payload: Any) -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(_SLOW)
                return
            queue.put_nowait(payload)

        self.on(event, _push)

        try:
            while True:
                payload = await queue.get()
                if payload is _SLOW:
                    logger.warning("slow consumer on event %r", event)
                    return
                yield payload
        finally:
            self.off(event, _push)

    async def shutdown(self) -> None:
        for task in list(self._pending):
            task.cancel()
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
