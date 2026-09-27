import asyncio
from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.deps import AppContextDep

router = APIRouter(tags=["events"])


@router.get("/events", response_class=EventSourceResponse)
async def sse_events(ctx: AppContextDep) -> AsyncIterable[ServerSentEvent]:
    queue: asyncio.Queue[str] = asyncio.Queue()

    async def on_device_changed(did: str) -> None:
        await queue.put(did)

    ctx.events.on("device_changed", on_device_changed)

    try:
        while True:
            did = await queue.get()
            yield ServerSentEvent(event=f"device_changed@{did}", data=did)
    finally:
        ctx.events.off("device_changed", on_device_changed)
