import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any, cast

from fastapi.sse import ServerSentEvent

from app.config import Settings
from app.deps import AppContext
from app.heatzy.events import EventEmitter
from app.heatzy.service import HeatzyService
from app.routers.events_sse import sse_events


def _context() -> AppContext:
    events = EventEmitter()
    return AppContext(
        settings=Settings(),
        service=HeatzyService(Settings(), events),
        events=events,
    )


def _use_devices(ctx: AppContext, dids: list[str]) -> None:
    ctx.service._session._client = cast(
        Any,
        SimpleNamespace(
            websocket=SimpleNamespace(devices={did: {"did": did} for did in dids})
        ),
    )


def _stream(
    ctx: AppContext, last_event_id: str | None = None
) -> AsyncGenerator[ServerSentEvent]:
    return cast(AsyncGenerator[ServerSentEvent], sse_events(ctx, last_event_id))


async def _next(gen: AsyncGenerator[ServerSentEvent]) -> ServerSentEvent:
    return await asyncio.wait_for(gen.__anext__(), 1)


async def test_sse_sends_sync_sentinel_first() -> None:
    ctx = _context()
    gen = _stream(ctx)

    sentinel = await _next(gen)

    assert sentinel.id == "sync"
    assert sentinel.event is None

    await gen.aclose()


async def test_sse_forwards_device_changed() -> None:
    ctx = _context()
    gen = _stream(ctx)
    await _next(gen)

    pending = asyncio.create_task(gen.__anext__())
    ctx.events.emit("device_changed", "did-1")
    event = await asyncio.wait_for(pending, 1)

    assert event.event == "device_changed@did-1"

    await gen.aclose()


async def test_sse_forwards_service_status() -> None:
    ctx = _context()
    gen = _stream(ctx)
    await _next(gen)

    pending = asyncio.create_task(gen.__anext__())
    ctx.events.emit("service_status", "reconnecting")
    event = await asyncio.wait_for(pending, 1)

    assert event.event == "service_status"

    await gen.aclose()


async def test_sse_resync_on_reconnect() -> None:
    ctx = _context()
    _use_devices(ctx, ["did-1", "did-2"])
    gen = _stream(ctx, "sync")

    events = [await _next(gen) for _ in range(4)]

    assert [event.id for event in events] == ["sync", None, None, None]
    assert [event.event for event in events] == [
        None,
        "service_status",
        "device_changed@did-1",
        "device_changed@did-2",
    ]

    await gen.aclose()


async def test_sse_resync_sends_service_status_without_devices() -> None:
    ctx = _context()
    gen = _stream(ctx, "sync")

    sentinel = await _next(gen)
    status = await _next(gen)

    assert sentinel.id == "sync"
    assert status.event == "service_status"

    await gen.aclose()


async def test_sse_no_resync_on_initial_connection() -> None:
    ctx = _context()
    _use_devices(ctx, ["did-1"])
    gen = _stream(ctx)
    await _next(gen)

    pending = asyncio.create_task(gen.__anext__())
    ctx.events.emit("device_changed", "did-9")
    event = await asyncio.wait_for(pending, 1)

    assert event.event == "device_changed@did-9"

    await gen.aclose()


async def test_sse_no_resync_for_unknown_last_event_id() -> None:
    ctx = _context()
    _use_devices(ctx, ["did-1"])
    gen = _stream(ctx, "other")
    await _next(gen)

    pending = asyncio.create_task(gen.__anext__())
    ctx.events.emit("service_status", "connected")
    event = await asyncio.wait_for(pending, 1)

    assert event.event == "service_status"

    await gen.aclose()


async def test_sse_unregisters_both_listeners_on_close() -> None:
    ctx = _context()
    gen = _stream(ctx)
    await _next(gen)

    await gen.aclose()

    assert ctx.events._listeners == {}
