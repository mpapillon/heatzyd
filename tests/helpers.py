import asyncio
from collections.abc import Callable
from typing import Any, cast

from heatzypy import HeatzyClient

from app.heatzy.service import HeatzyService
from app.heatzy.session import ConnectionSupervisor


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
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.request_error: BaseException | None = None
        self.request_response: dict[str, Any] = {}

    async def async_request(
        self, path: str, method: str = "get", **kwargs: Any
    ) -> dict[str, Any]:
        self.requests.append((path, method, kwargs))
        if self.request_error is not None:
            raise self.request_error
        return self.request_response

    async def async_close(self) -> None:
        self.close_calls += 1
        self.websocket.connected = False


def _use(
    target: HeatzyService | ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    """Injecte le fake comme client du superviseur de ``target``."""
    supervisor = target._session if isinstance(target, HeatzyService) else target
    supervisor._client = cast(HeatzyClient, fake)


def _connected(
    target: HeatzyService | ConnectionSupervisor, fake: FakeHeatzypyClient
) -> None:
    """Injecte le fake et marque la websocket comme connectée."""
    _use(target, fake)
    fake.websocket.connected = True
