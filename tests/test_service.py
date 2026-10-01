import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

import pytest
from aiohttp import ClientError
from heatzypy import AuthenticationFailed, HeatzyClient, HeatzyException
from heatzypy.exception import WebsocketError

from app.config import Settings
from app.domain.capabilities import PILOTE_GEN_1, PILOTE_GEN_4
from app.domain.derog import DerogMode
from app.domain.errors import DerogNotSupported, LockNotSupported, ModeNotSupported
from app.domain.modes import Mode
from app.heatzy import service as service_mod
from app.heatzy.errors import (
    ControlFailed,
    DeviceNotFound,
    DeviceNotSupported,
    NotConnected,
)
from app.heatzy.events import EventEmitter
from app.heatzy.service import HeatzyService
from app.models import credentials, db


class FakeHeatzypyWebsocket:
    """Stand-in for ``heatzypy.websocket.Websocket``."""

    def __init__(self) -> None:
        self.devices: dict[str, Any] = {}
        self.connected = False
        self.connect_error: BaseException | None = None
        self.disconnect_error: BaseException | None = None
        self.control_error: BaseException | None = None
        # Each call to ``async_listen`` pops one action: an exception to raise,
        # or ``None`` to return cleanly. Once empty, it blocks on the gate.
        self.listen_actions: list[BaseException | None] = []
        self.callback: Callable[[dict[str, Any]], None] | None = None
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.connect_calls = 0
        self.disconnect_calls = 0
        self._listen_gate = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self.connected

    def register_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self.callback = callback

    async def async_connect(self, **_kwargs: Any) -> None:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    async def async_listen(self) -> None:
        if self.listen_actions:
            action = self.listen_actions.pop(0)
            if action is not None:
                raise action
            return
        await self._listen_gate.wait()

    async def async_disconnect(self) -> None:
        self.disconnect_calls += 1
        if self.disconnect_error is not None:
            raise self.disconnect_error
        self.connected = False

    async def async_control_device(self, did: str, payload: dict[str, Any]) -> None:
        if self.control_error is not None:
            raise self.control_error
        self.sent.append((did, payload))


class FakeHeatzypyClient:
    """Stand-in for ``heatzypy.HeatzyClient``."""

    def __init__(self) -> None:
        self.websocket = FakeHeatzypyWebsocket()
        self.close_calls = 0

    async def async_close(self) -> None:
        self.close_calls += 1
        self.websocket.connected = False


@pytest.fixture(autouse=True)
def _database(tmp_path: Path) -> None:
    db.init_db(str(tmp_path / "test.db"))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeHeatzypyClient:
    client = FakeHeatzypyClient()
    monkeypatch.setattr(service_mod, "HeatzyClient", lambda *a, **kw: client)
    monkeypatch.setattr(service_mod, "ClientSession", lambda *a, **kw: object())
    monkeypatch.setattr(service_mod, "backoff", lambda *a: 0.0)
    return client


@pytest.fixture
def service(fake: FakeHeatzypyClient) -> HeatzyService:
    return HeatzyService(
        Settings(
            retry_backoff_base=15,
            retry_backoff_cap=240,
            retry_max_attempts=5,
        ),
        EventEmitter(),
    )


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


def _device(
    did: str = "did-1",
    product_key: str = PILOTE_GEN_4[0],
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    device: dict[str, Any] = {"did": did, "product_key": product_key}
    if attrs is not None:
        device["attrs"] = attrs
    return device


def _use(service: HeatzyService, fake: FakeHeatzypyClient) -> None:
    service._client = cast(HeatzyClient, fake)


def _connected(service: HeatzyService, fake: FakeHeatzypyClient) -> None:
    _use(service, fake)
    fake.websocket.connected = True


# properties


def test_no_client_means_disconnected(service: HeatzyService) -> None:
    assert service.devices == []
    assert service.is_connected is False


def test_devices_come_from_the_client_cache(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    fake.websocket.devices = {"did-1": _device()}
    _use(service, fake)

    assert [device.did for device in service.devices] == ["did-1"]


# _connect / _disconnect


async def test_connect_without_client_is_noop(service: HeatzyService) -> None:
    await service._connect()


async def test_disconnect_swallows_client_errors(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    fake.websocket.disconnect_error = ClientError("boom")

    await service._disconnect()


# _reconnect


async def test_reconnect_resets_attempts_on_success(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    service._connection_attempts = 3

    assert await service._reconnect(None) is True
    assert service._connection_attempts == 0
    assert fake.websocket.connected is True
    assert fake.websocket.disconnect_calls == 1


async def test_reconnect_retries_on_transient_error(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    fake.websocket.connect_error = WebsocketError("down")

    assert await service._reconnect(None) is True
    assert service._connection_attempts == 1
    assert service.auth_error is None
    # Disconnected before the attempt and again after the failure.
    assert fake.websocket.disconnect_calls == 2


async def test_reconnect_treats_auth_failure_as_transient(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    _use(service, fake)
    fake.websocket.connect_error = AuthenticationFailed("nope")

    assert await service._reconnect(None) is True
    assert service.auth_error is None
    assert _credentials_connected() is True


async def test_reconnect_gives_up_when_budget_exhausted(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    service._connection_attempts = service._retry_max_attempts

    assert await service._reconnect(None) is False
    assert service._client is None
    assert fake.close_calls == 1
    assert service.auth_error is not None


async def test_reconnect_stops_during_backoff(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    service._stopping = True

    assert await service._reconnect(None) is False
    assert fake.websocket.connect_calls == 0


async def test_reconnect_without_client_returns_false(service: HeatzyService) -> None:
    assert await service._reconnect(None) is False


# _supervise


async def test_supervise_reconnects_on_transient_error(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.listen_actions.append(WebsocketError("closed"))

    task = asyncio.create_task(service._supervise())
    try:
        await _wait_until(lambda: fake.websocket.connect_calls == 1)
        assert service._connection_attempts == 0
    finally:
        await _cancel(task)


async def test_supervise_reconnects_on_normal_return(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.listen_actions.append(None)

    task = asyncio.create_task(service._supervise())
    try:
        await _wait_until(lambda: fake.websocket.connect_calls == 1)
    finally:
        await _cancel(task)


async def test_supervise_treats_listen_auth_failure_as_terminal(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    _connected(service, fake)
    fake.websocket.listen_actions.append(AuthenticationFailed("rejected"))

    await asyncio.wait_for(service._supervise(), 1)

    assert service._client is None
    assert fake.close_calls == 1
    assert service.auth_error is not None
    assert _credentials_connected() is False


async def test_supervise_gives_up_after_budget(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    service._connection_attempts = service._retry_max_attempts
    fake.websocket.listen_actions.append(WebsocketError("closed"))

    await asyncio.wait_for(service._supervise(), 1)

    assert service._client is None
    assert service.auth_error is not None


# auth failure


async def test_handle_auth_failure_closes_client_and_disconnects(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    _use(service, fake)

    await service._handle_auth_failure()

    assert service._client is None
    assert fake.close_calls == 1
    assert service.auth_error == "Identifiants Heatzy invalides"
    assert _credentials_connected() is False


# login / start / stop


async def test_login_connects_and_starts_supervisor(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    await service.login("user", "pass")
    try:
        assert fake.websocket.connect_calls == 1
        assert service.is_connected is True
        assert service._listen_task is not None
        assert service.auth_error is None
    finally:
        await service.stop()


async def test_login_resets_stopping_flag(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    service._stopping = True

    await service.login("user", "pass")
    try:
        assert service._stopping is False
    finally:
        await service.stop()


async def test_login_tears_down_on_connect_failure(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    fake.websocket.connect_error = AuthenticationFailed("bad")

    with pytest.raises(AuthenticationFailed):
        await service.login("user", "pass")

    assert service._client is None
    assert fake.close_calls == 1


async def test_stop_sets_flag_and_closes_client(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    await service.stop()

    assert service._stopping is True
    assert service._client is None
    assert fake.close_calls == 1


async def test_start_without_credentials_is_noop(service: HeatzyService) -> None:
    await service.start()

    assert service._client is None


async def test_start_logs_in_with_saved_credentials(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()

    await service.start()
    try:
        assert service._client is fake
        assert fake.websocket.connect_calls == 1
    finally:
        await service.stop()


async def test_start_marks_disconnected_on_auth_failure(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    fake.websocket.connect_error = AuthenticationFailed("bad")

    await service.start()

    assert service._client is None
    assert service.auth_error is not None
    assert _credentials_connected() is False


async def test_start_is_noop_when_already_started(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    await service.start()

    assert fake.websocket.connect_calls == 0


# teardown helpers


async def test_close_client_without_client_is_noop(service: HeatzyService) -> None:
    await service._close_client()


async def test_teardown_cancels_task_and_closes_client(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    task = asyncio.create_task(asyncio.sleep(10))
    service._listen_task = task

    await service._teardown()

    assert task.cancelled()
    assert service._listen_task is None
    assert service._client is None


async def test_on_listen_task_end_ignores_cancelled_task(
    service: HeatzyService,
) -> None:
    task = asyncio.create_task(asyncio.sleep(10))
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    service._on_listen_task_end(task)


async def test_on_listen_task_end_logs_failure(
    service: HeatzyService, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)

    async def boom() -> None:
        raise RuntimeError("nope")

    task = asyncio.create_task(boom())
    with suppress(RuntimeError):
        await task

    service._on_listen_task_end(task)

    assert any("listen task ended with error" in m for m in caplog.messages)


# send_order / send_lock


async def test_send_order_requires_client(service: HeatzyService) -> None:
    with pytest.raises(NotConnected):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_requires_connection(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    with pytest.raises(NotConnected):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_unsupported_product(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key="unknown")}

    with pytest.raises(DeviceNotSupported):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_unsupported_mode(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key=PILOTE_GEN_1[0])}

    with pytest.raises(ModeNotSupported):
        await service.send_order("did-1", Mode.CONFORT_M1)


async def test_send_order_sends_encoded_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_order("did-1", Mode.ECO)

    assert fake.websocket.sent == [("did-1", {"attrs": {"mode": "eco"}})]


async def test_send_order_wraps_transport_error(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}
    fake.websocket.control_error = HeatzyException("boom")

    with pytest.raises(ControlFailed):
        await service.send_order("did-1", Mode.ECO)


async def test_send_lock_sends_encoded_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_lock("did-1", True)

    assert fake.websocket.sent == [("did-1", {"attrs": {"lock_switch": 1}})]


async def test_send_lock_not_supported(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key=PILOTE_GEN_1[0])}

    with pytest.raises(LockNotSupported):
        await service.send_lock("did-1", True)


# send_derog / cancel_derog


async def test_send_derog_requires_connection(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    with pytest.raises(NotConnected):
        await service.send_derog("did-1", DerogMode.BOOST, 30)


async def test_send_derog_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.send_derog("did-1", DerogMode.BOOST, 30)


async def test_send_derog_unsupported_product(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key=PILOTE_GEN_1[0])}

    with pytest.raises(DerogNotSupported):
        await service.send_derog("did-1", DerogMode.BOOST, 30)


async def test_send_derog_sends_encoded_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_derog("did-1", DerogMode.BOOST, 45)

    assert fake.websocket.sent == [
        ("did-1", {"attrs": {"derog_mode": 2, "derog_time": 45}})
    ]


async def test_cancel_derog_requires_connection(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    with pytest.raises(NotConnected):
        await service.cancel_derog("did-1")


async def test_cancel_derog_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.cancel_derog("did-1")


async def test_cancel_derog_noop_without_active_derog(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(attrs={"derog_mode": 0})}

    await service.cancel_derog("did-1")

    assert fake.websocket.sent == []


async def test_cancel_derog_sends_clear_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {
        "did-1": _device(attrs={"derog_mode": 2, "derog_time": 30})
    }

    await service.cancel_derog("did-1")

    assert fake.websocket.sent == [
        ("did-1", {"attrs": {"derog_mode": 0, "derog_time": 0}})
    ]


# device changed hook


def test_on_device_changed_emits_event(service: HeatzyService) -> None:
    received: list[Any] = []
    service._events.on("device_changed", received.append)

    service._on_device_changed({"did": "did-1"})

    assert received == ["did-1"]


def test_on_device_changed_without_did_is_ignored(service: HeatzyService) -> None:
    received: list[Any] = []
    service._events.on("device_changed", received.append)

    service._on_device_changed({})

    assert received == []


# status


def test_set_status_emits_only_on_change(service: HeatzyService) -> None:
    received: list[str] = []
    service._events.on("service_status", received.append)

    service._set_status("connected")
    service._set_status("connected")
    service._set_status("reconnecting")

    assert received == ["connected", "reconnecting"]


def test_default_status_is_logged_out(service: HeatzyService) -> None:
    assert service.status == "logged_out"


async def test_login_sets_connected_status(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    await service.login("user", "pass")
    try:
        assert service.status == "connected"
    finally:
        await service.stop()


async def test_login_failure_falls_back_to_logged_out(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    fake.websocket.connect_error = AuthenticationFailed("bad")

    with pytest.raises(AuthenticationFailed):
        await service.login("user", "pass")

    assert service.status == "logged_out"


async def test_stop_sets_logged_out(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    await service.login("user", "pass")

    await service.stop()

    assert service.status == "logged_out"


async def test_start_without_credentials_stays_logged_out(
    service: HeatzyService,
) -> None:
    await service.start()

    assert service.status == "logged_out"


async def test_reconnect_marks_reconnecting_on_retry(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.connect_error = WebsocketError("down")

    assert await service._reconnect(None) is True
    assert service.status == "reconnecting"


async def test_reconnect_marks_connected_on_success(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    service.status = "reconnecting"

    assert await service._reconnect(None) is True
    assert service.status == "connected"


async def test_reconnect_marks_logged_out_when_budget_exhausted(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)
    service._connection_attempts = service._retry_max_attempts

    assert await service._reconnect(None) is False
    assert service.status == "logged_out"


async def test_handle_auth_failure_sets_logged_out(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _set_credentials()
    service.status = "connected"
    service._client = cast(HeatzyClient, fake)

    await service._handle_auth_failure()

    assert service.status == "logged_out"
