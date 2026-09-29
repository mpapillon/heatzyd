import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from app.heatzy.events import _MAX_PENDING, EventEmitter


async def _wait_for_listeners(
    emitter: EventEmitter, event: str, count: int = 1
) -> None:
    for _ in range(1000):
        if len(emitter._listeners.get(event, [])) >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"listener for {event!r} never registered")


async def _collect(gen: AsyncGenerator[Any], count: int) -> list[Any]:
    out: list[Any] = []
    try:
        async for payload in gen:
            out.append(payload)
            if len(out) >= count:
                break
    finally:
        await gen.aclose()
    return out


# Sync listeners


def test_emit_calls_all_listeners() -> None:
    emitter = EventEmitter()
    calls: list[tuple[str, Any]] = []
    emitter.on("e", lambda payload: calls.append(("a", payload)))
    emitter.on("e", lambda payload: calls.append(("b", payload)))
    emitter.on("e", lambda payload: calls.append(("c", payload)))

    emitter.emit("e", 1)

    assert calls == [("a", 1), ("b", 1), ("c", 1)]


def test_emit_without_listeners_is_noop() -> None:
    EventEmitter().emit("e", 1)


def test_emit_supports_mapping_payload() -> None:
    emitter = EventEmitter()
    received: list[Any] = []
    emitter.on("e", received.append)
    payload = {"did": "x", "attrs": {"mode": "cft"}}

    emitter.emit("e", payload)

    assert received == [payload]


def test_off_stops_listener() -> None:
    emitter = EventEmitter()
    calls: list[Any] = []

    handler = emitter.on("e", lambda payload: calls.append(payload))
    emitter.off("e", handler)

    emitter.emit("e", 1)

    assert calls == []


def test_off_unknown_callback_is_noop() -> None:
    emitter = EventEmitter()
    emitter.on("e", lambda payload: None)

    emitter.off("e", lambda payload: None)


def test_off_unknown_event_is_noop() -> None:
    EventEmitter().off("missing", lambda payload: None)


def test_off_removes_empty_event_key() -> None:
    emitter = EventEmitter()

    def handler(payload: Any) -> None: ...

    emitter.on("e", handler)
    emitter.off("e", handler)

    assert "e" not in emitter._listeners


def test_emit_isolates_listener_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    emitter = EventEmitter()
    called: list[Any] = []

    def boom(payload: Any) -> None:
        raise ValueError("boom")

    emitter.on("e", boom)
    emitter.on("e", called.append)

    emitter.emit("e", 1)

    assert called == [1]
    assert any("Error in event listener" in m for m in caplog.messages)


# Async listeners


async def test_on_accepts_async_listener() -> None:
    emitter = EventEmitter()

    async def handler(payload: Any) -> None: ...

    emitter.on("e", handler)


async def test_emit_runs_async_listener() -> None:
    emitter = EventEmitter()
    seen = asyncio.Event()
    received: list[Any] = []

    async def handler(payload: Any) -> None:
        received.append(payload)
        seen.set()

    emitter.on("e", handler)

    emitter.emit("e", "did-1")
    await asyncio.wait_for(seen.wait(), 1)

    assert received == ["did-1"]


async def test_emit_runs_sync_and_async_listeners() -> None:
    emitter = EventEmitter()
    sync_calls: list[Any] = []
    async_calls: list[Any] = []
    seen = asyncio.Event()

    async def handler(payload: Any) -> None:
        async_calls.append(payload)
        seen.set()

    emitter.on("e", sync_calls.append)
    emitter.on("e", handler)

    emitter.emit("e", 42)
    await asyncio.wait_for(seen.wait(), 1)

    assert sync_calls == [42]
    assert async_calls == [42]


async def test_pending_cleared_after_async_listener() -> None:
    emitter = EventEmitter()

    async def handler(payload: Any) -> None:
        await asyncio.sleep(0)

    emitter.on("e", handler)

    emitter.emit("e", 1)
    assert len(emitter._pending) == 1

    await asyncio.gather(*emitter._pending, return_exceptions=True)
    await asyncio.sleep(0)

    assert emitter._pending == set()


async def test_async_listener_exception_is_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    emitter = EventEmitter()

    async def boom(payload: Any) -> None:
        raise ValueError("boom")

    emitter.on("e", boom)

    emitter.emit("e", 1)
    await asyncio.gather(*emitter._pending, return_exceptions=True)
    await asyncio.sleep(0)

    assert emitter._pending == set()
    assert any("Error in event listener" in m for m in caplog.messages)


# Stream


async def test_stream_yields_emitted_payloads() -> None:
    emitter = EventEmitter()
    task = asyncio.create_task(_collect(emitter.stream("e"), 2))
    await _wait_for_listeners(emitter, "e")

    emitter.emit("e", "a")
    emitter.emit("e", "b")

    assert await asyncio.wait_for(task, 1) == ["a", "b"]


async def test_stream_preserves_order() -> None:
    emitter = EventEmitter()
    task = asyncio.create_task(_collect(emitter.stream("e"), 3))
    await _wait_for_listeners(emitter, "e")

    for payload in ("a", "b", "c"):
        emitter.emit("e", payload)

    assert await asyncio.wait_for(task, 1) == ["a", "b", "c"]


async def test_stream_supports_multiple_consumers() -> None:
    emitter = EventEmitter()
    first = asyncio.create_task(_collect(emitter.stream("e"), 1))
    second = asyncio.create_task(_collect(emitter.stream("e"), 1))
    await _wait_for_listeners(emitter, "e", count=2)

    emitter.emit("e", "a")

    assert await asyncio.wait_for(first, 1) == ["a"]
    assert await asyncio.wait_for(second, 1) == ["a"]


async def test_stream_removes_listener_on_aclose() -> None:
    emitter = EventEmitter()
    gen = emitter.stream("e")
    task = asyncio.create_task(gen.__anext__())
    await _wait_for_listeners(emitter, "e")

    emitter.emit("e", "a")
    assert await asyncio.wait_for(task, 1) == "a"

    await gen.aclose()

    assert "e" not in emitter._listeners


async def test_stream_slow_consumer_terminates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    emitter = EventEmitter()
    gen = emitter.stream("e")
    first = asyncio.create_task(gen.__anext__())
    await _wait_for_listeners(emitter, "e")

    emitted = _MAX_PENDING + 5
    for index in range(emitted):
        emitter.emit("e", index)

    received = [await asyncio.wait_for(first, 1)]
    while True:
        try:
            received.append(await asyncio.wait_for(gen.__anext__(), 1))
        except StopAsyncIteration:
            break

    assert len(received) < emitted
    assert any("slow consumer" in m for m in caplog.messages)
