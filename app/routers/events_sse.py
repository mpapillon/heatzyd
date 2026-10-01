import asyncio
from collections.abc import AsyncIterable
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.deps import AppContextDep
from app.heatzy.service import Status

_MAX_PENDING = 64
_SYNC_ID = "sync"

router = APIRouter(tags=["events"])


def _device_changed(did: str) -> str:
    return f"device_changed@{did}"


@router.get("/events", response_class=EventSourceResponse)
async def sse_events(
    ctx: AppContextDep, last_event_id: Annotated[str | None, Header()] = None
) -> AsyncIterable[ServerSentEvent]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_MAX_PENDING)

    def _push(event: str) -> None:
        if queue.full():
            with suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        queue.put_nowait(event)

    def _on_device_changed(did: str) -> None:
        _push(_device_changed(did))

    def _on_service_status(_: Status) -> None:
        _push("service_status")

    ctx.events.on("device_changed", _on_device_changed)
    ctx.events.on("service_status", _on_service_status)

    try:
        yield ServerSentEvent(id=_SYNC_ID)
        if last_event_id == _SYNC_ID:
            yield ServerSentEvent(event="service_status")
            for dev in ctx.service.devices:
                yield ServerSentEvent(event=_device_changed(dev.did))
        while True:
            event = await queue.get()
            yield ServerSentEvent(event=event)
    finally:
        ctx.events.off("device_changed", _on_device_changed)
        ctx.events.off("service_status", _on_service_status)
