import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

import pytest
from aiohttp import ClientError
from heatzypy import AuthenticationFailed
from heatzypy.exception import WebsocketError

from app.heatzy.session import ConnectionSupervisor
from app.models import credentials, db
from tests.helpers import FakeHeatzypyClient, _connected, _use


async def _wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0)


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _set_credentials(username: str = "user", password: str = "pass") -> None:
    with db.session_scope() as session:
        credentials.upsert(session, username, password)


def _credentials_connected() -> bool:
    with db.session_scope() as session:
        creds = credentials.load(session)
        return creds.connected if creds is not None else False


# _connect / _disconnect


async def test_connect_without_client_is_noop(
    supervisor: ConnectionSupervisor,
) -> None:
    await supervisor._connect()


async def test_disconnect_swallows_client_errors(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    fake.websocket.disconnect_error = ClientError("boom")

    await supervisor._disconnect()


# _reconnect


async def test_reconnect_resets_attempts_on_success(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    supervisor._connection_attempts = 3

    assert await supervisor._reconnect(None) is True
    assert supervisor._connection_attempts == 0
    assert fake.websocket.connected is True
    assert fake.websocket.disconnect_calls == 1


async def test_reconnect_retries_on_transient_error(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    fake.websocket.connect_error = WebsocketError("down")

    assert await supervisor._reconnect(None) is True
    assert supervisor._connection_attempts == 1
    assert supervisor.auth_error is None
    # Disconnected before the attempt and again after the failure.
    assert fake.websocket.disconnect_calls == 2


async def test_reconnect_treats_auth_failure_as_transient(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    _use(supervisor, fake)
    fake.websocket.connect_error = AuthenticationFailed("nope")

    assert await supervisor._reconnect(None) is True
    assert supervisor.auth_error is None
    assert _credentials_connected() is True


async def test_reconnect_gives_up_when_budget_exhausted(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    supervisor._connection_attempts = supervisor._retry_max_attempts

    assert await supervisor._reconnect(None) is False
    assert supervisor._client is None
    assert fake.close_calls == 1
    assert supervisor.auth_error is not None


async def test_reconnect_stops_during_backoff(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    supervisor._stopping = True

    assert await supervisor._reconnect(None) is False
    assert fake.websocket.connect_calls == 0


async def test_reconnect_without_client_returns_false(
    supervisor: ConnectionSupervisor,
) -> None:
    assert await supervisor._reconnect(None) is False


# _supervise


async def test_supervise_reconnects_on_transient_error(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _connected(supervisor, fake)
    fake.websocket.listen_actions.append(WebsocketError("closed"))

    task = asyncio.create_task(supervisor._supervise())
    try:
        await _wait_until(lambda: fake.websocket.connect_calls == 1)
        assert supervisor._connection_attempts == 0
    finally:
        await _cancel(task)


async def test_supervise_reconnects_on_normal_return(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _connected(supervisor, fake)
    fake.websocket.listen_actions.append(None)

    task = asyncio.create_task(supervisor._supervise())
    try:
        await _wait_until(lambda: fake.websocket.connect_calls == 1)
    finally:
        await _cancel(task)


async def test_supervise_treats_listen_auth_failure_as_terminal(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    _connected(supervisor, fake)
    fake.websocket.listen_actions.append(AuthenticationFailed("rejected"))

    await asyncio.wait_for(supervisor._supervise(), 1)

    assert supervisor._client is None
    assert fake.close_calls == 1
    assert supervisor.auth_error is not None
    assert _credentials_connected() is False


async def test_supervise_gives_up_after_budget(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _connected(supervisor, fake)
    supervisor._connection_attempts = supervisor._retry_max_attempts
    fake.websocket.listen_actions.append(WebsocketError("closed"))

    await asyncio.wait_for(supervisor._supervise(), 1)

    assert supervisor._client is None
    assert supervisor.auth_error is not None


# auth failure


async def test_handle_auth_failure_closes_client_and_disconnects(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    _use(supervisor, fake)

    await supervisor._handle_auth_failure()

    assert supervisor._client is None
    assert fake.close_calls == 1
    assert supervisor.auth_error == "Identifiants Heatzy invalides"
    assert _credentials_connected() is False


# login / start / stop


async def test_login_connects_and_starts_supervisor(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    await supervisor.login("user", "pass")
    try:
        assert fake.websocket.connect_calls == 1
        assert supervisor.is_connected is True
        assert supervisor._listen_task is not None
        assert supervisor.auth_error is None
    finally:
        await supervisor.stop()


async def test_login_resets_stopping_flag(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    supervisor._stopping = True

    await supervisor.login("user", "pass")
    try:
        assert supervisor._stopping is False
    finally:
        await supervisor.stop()


async def test_login_tears_down_on_connect_failure(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    fake.websocket.connect_error = AuthenticationFailed("bad")

    with pytest.raises(AuthenticationFailed):
        await supervisor.login("user", "pass")

    assert supervisor._client is None
    assert fake.close_calls == 1


async def test_stop_sets_flag_and_closes_client(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)

    await supervisor.stop()

    assert supervisor._stopping is True
    assert supervisor._client is None
    assert fake.close_calls == 1


async def test_start_without_credentials_is_noop(
    supervisor: ConnectionSupervisor,
) -> None:
    await supervisor.start()

    assert supervisor._client is None


async def test_start_logs_in_with_saved_credentials(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()

    await supervisor.start()
    try:
        assert supervisor._client is fake
        assert fake.websocket.connect_calls == 1
    finally:
        await supervisor.stop()


async def test_start_marks_disconnected_on_auth_failure(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    fake.websocket.connect_error = AuthenticationFailed("bad")

    await supervisor.start()

    assert supervisor._client is None
    assert supervisor.auth_error is not None
    assert _credentials_connected() is False


async def test_start_is_noop_when_already_started(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)

    await supervisor.start()

    assert fake.websocket.connect_calls == 0


# teardown helpers


async def test_close_client_without_client_is_noop(
    supervisor: ConnectionSupervisor,
) -> None:
    await supervisor._close_client()


async def test_teardown_cancels_task_and_closes_client(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    task = asyncio.create_task(asyncio.sleep(10))
    supervisor._listen_task = task

    await supervisor._teardown()

    assert task.cancelled()
    assert supervisor._listen_task is None
    assert supervisor._client is None


async def test_on_listen_task_end_ignores_cancelled_task(
    supervisor: ConnectionSupervisor,
) -> None:
    task = asyncio.create_task(asyncio.sleep(10))
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    supervisor._on_listen_task_end(task)


async def test_on_listen_task_end_logs_failure(
    supervisor: ConnectionSupervisor, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)

    async def boom() -> None:
        raise RuntimeError("nope")

    task = asyncio.create_task(boom())
    with suppress(RuntimeError):
        await task

    supervisor._on_listen_task_end(task)

    assert any("listen task ended with error" in m for m in caplog.messages)


# status


def test_set_status_emits_only_on_change(
    supervisor: ConnectionSupervisor,
) -> None:
    received: list[str] = []
    supervisor._events.on("service_status", received.append)

    supervisor._set_status("connected")
    supervisor._set_status("connected")
    supervisor._set_status("reconnecting")

    assert received == ["connected", "reconnecting"]


async def test_reconnect_marks_reconnecting_on_retry(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _connected(supervisor, fake)
    fake.websocket.connect_error = WebsocketError("down")

    assert await supervisor._reconnect(None) is True
    assert supervisor.status == "reconnecting"


async def test_reconnect_marks_connected_on_success(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    supervisor.status = "reconnecting"

    assert await supervisor._reconnect(None) is True
    assert supervisor.status == "connected"


async def test_reconnect_marks_logged_out_when_budget_exhausted(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _use(supervisor, fake)
    supervisor._connection_attempts = supervisor._retry_max_attempts

    assert await supervisor._reconnect(None) is False
    assert supervisor.status == "logged_out"


async def test_handle_auth_failure_sets_logged_out(
    supervisor: ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    supervisor.status = "connected"
    _use(supervisor, fake)

    await supervisor._handle_auth_failure()

    assert supervisor.status == "logged_out"
