from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.deps import AppContextDep

router = APIRouter(tags=["events"])


@router.get("/events", response_class=EventSourceResponse)
async def sse_events(ctx: AppContextDep) -> AsyncIterable[ServerSentEvent]:
    async for did in ctx.events.stream("device_changed"):
        yield ServerSentEvent(event=f"device_changed@{did}", data=did)
