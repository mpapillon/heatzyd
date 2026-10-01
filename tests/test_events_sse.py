import asyncio

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


async def _wait_for_listeners(emitter: EventEmitter, count: int) -> None:
    for _ in range(1000):
        if sum(len(listeners) for listeners in emitter._listeners.values()) >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError("listeners never registered")


async def test_sse_forwards_device_changed() -> None:
    ctx = _context()
    gen = sse_events(ctx)

    first = asyncio.create_task(gen.__anext__())
    await _wait_for_listeners(ctx.events, 2)
    ctx.events.emit("device_changed", "did-1")

    event = await asyncio.wait_for(first, 1)
    assert event.event == "device_changed@did-1"

    await gen.aclose()


async def test_sse_forwards_service_status() -> None:
    ctx = _context()
    gen = sse_events(ctx)

    first = asyncio.create_task(gen.__anext__())
    await _wait_for_listeners(ctx.events, 2)
    ctx.events.emit("service_status", "reconnecting")

    event = await asyncio.wait_for(first, 1)
    assert event.event == "service_status"

    await gen.aclose()


async def test_sse_unregisters_both_listeners_on_close() -> None:
    ctx = _context()
    gen = sse_events(ctx)

    first = asyncio.create_task(gen.__anext__())
    await _wait_for_listeners(ctx.events, 2)
    ctx.events.emit("service_status", "connected")
    await asyncio.wait_for(first, 1)

    await gen.aclose()

    assert ctx.events._listeners == {}
