import asyncio
import logging
from datetime import datetime
from typing import Any, Literal

from aiohttp import ClientError, ClientSession
from heatzypy import (
    AuthenticationFailed,
    HeatzyClient,
    HeatzyException,
)
from heatzypy.exception import (
    HttpRequestFailed,
    RetrieveFailed,
    TimeoutExceededError,
    WebsocketError,
)

from app.config import Settings
from app.domain import derog
from app.domain.capabilities import ProductCapabilities, capabilities_for
from app.domain.control import backoff
from app.domain.derog import DerogMode
from app.domain.modes import Mode
from app.domain.protocol import (
    ALIAS_MAX_LENGTH,
    encode_derog,
    encode_lock,
    encode_order,
)
from app.heatzy.device import DeviceState
from app.heatzy.errors import (
    ControlFailed,
    DeviceNotFound,
    DeviceNotSupported,
    NotConnected,
)
from app.heatzy.events import EventEmitter
from app.models import credentials, db

logger = logging.getLogger(__name__)


_TRANSIENT_ERRORS = (
    WebsocketError,
    ClientError,
    ConnectionResetError,
    RetrieveFailed,
    HttpRequestFailed,
    TimeoutExceededError,
)

_RECONNECT_ERRORS = (*_TRANSIENT_ERRORS, AuthenticationFailed)

type Status = Literal["logged_out", "connecting", "connected", "reconnecting"]


class HeatzyService:
    def __init__(self, settings: Settings, events: EventEmitter):
        self.auth_error: str | None = None
        self.status: Status = "logged_out"

        self._events = events
        self._region = settings.heatzy_region
        self._use_tls = settings.use_tls
        self._tz = settings.tz
        self._retry_backoff_base = settings.retry_backoff_base
        self._retry_backoff_cap = settings.retry_backoff_cap
        self._retry_max_attempts = settings.retry_max_attempts

        self._connection_attempts = 0
        self._stopping = False
        self._client: HeatzyClient | None = None
        self._listen_task: asyncio.Task[None] | None = None

    @property
    def devices(self) -> list[DeviceState]:
        if self._client is None:
            return []
        return sorted(
            [DeviceState(device) for device in self._client.websocket.devices.values()],
            key=lambda device: device.range,
        )

    @property
    def is_connected(self) -> bool:
        if self._client is None:
            return False
        return self._client.websocket.is_connected

    async def login(self, username: str, password: str) -> None:
        await self._teardown()
        self._stopping = False
        self._set_status("connecting")

        self._client = HeatzyClient(
            username,
            password,
            session=ClientSession(),
            region=self._region,
            use_tls=self._use_tls,
        )

        try:
            self._client.websocket.register_callback(self._on_device_changed)
            await self._connect()
            self._set_status("connected")
            self._listen_task = asyncio.create_task(self._supervise())
            self._listen_task.add_done_callback(self._on_listen_task_end)
        except Exception:
            await self._teardown()
            self._set_status("logged_out")
            raise
        self.auth_error = None

    async def start(self) -> None:
        if self._client is not None:
            logger.warning("already started")
            return

        with db.session_scope() as session:
            creds = credentials.load(session)
        if creds is None or not creds.connected:
            return
        try:
            await self.login(creds.username, creds.password)
        except AuthenticationFailed as error:
            await self._handle_auth_failure()
            logger.warning("Heatzy authentication failed: %s", error)
        except HeatzyException as error:
            logger.error("Heatzy authentication was interrupted: %s", str(error))

    async def stop(self) -> None:
        self._stopping = True
        self._set_status("logged_out")
        await self._teardown()

    async def _teardown(self) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("unexpected error while stopping listen task")
            self._listen_task = None
        await self._close_client()

    async def _close_client(self) -> None:
        if self._client is not None:
            await self._client.async_close()
            self._client = None

    def get_device(self, did: str) -> DeviceState | None:
        for device in self.devices:
            if device.did == did:
                return device
        return None

    async def rename(self, did: str, alias: str) -> None:
        if self._client is None:
            raise NotConnected
        if (device := self.get_device(did)) is None:
            raise DeviceNotFound(did)
        if len(alias) > ALIAS_MAX_LENGTH:
            raise ControlFailed(f"alias is too long (max: {ALIAS_MAX_LENGTH})")
        try:
            response = await self._client.async_request(
                f"bindings/{did}",
                "put",
                json={"dev_alias": alias},
            )
        except (HeatzyException, ClientError) as error:
            raise ControlFailed(str(error)) from error
        device.raw_device["dev_alias"] = response.get("dev_alias", alias)
        self._events.emit("device_changed", did)

    async def send_order(self, did: str, mode: Mode) -> None:
        await self._send_command(
            did, encode_order(self._capabilities_or_raise(did), mode)
        )

    async def send_lock(self, did: str, lock: bool) -> None:
        await self._send_command(
            did, encode_lock(self._capabilities_or_raise(did), lock)
        )

    async def send_boost_derog(self, did: str, time: int) -> None:
        await self._send_command(
            did, encode_derog(self._capabilities_or_raise(did), DerogMode.BOOST, time)
        )

    async def send_vacation_derog(self, did: str, ends_at: datetime) -> None:
        tz = self._tz
        await self._send_command(
            did,
            encode_derog(
                self._capabilities_or_raise(did),
                DerogMode.VACATIONS,
                derog.days_until(ends_at, now=datetime.now(tz), tz=tz),
            ),
        )

    async def send_derog(self, did: str, kind: DerogMode, time: int) -> None:
        await self._send_command(
            did, encode_derog(self._capabilities_or_raise(did), kind, time)
        )

    async def cancel_derog(self, did: str) -> None:
        cap = self._capabilities_or_raise(did)
        device = self.get_device(did)
        if device is not None and device.derog_mode == DerogMode.NONE:
            return
        await self._send_command(did, encode_derog(cap, DerogMode.NONE))

    def _on_device_changed(self, device: dict[str, Any]) -> None:
        did = device.get("did")
        if did is None:
            return
        self._events.emit("device_changed", did)

    def _capabilities_or_raise(self, did: str) -> ProductCapabilities:
        if self._client is None or not self.is_connected:
            raise NotConnected
        device = self.get_device(did)
        if device is None:
            raise DeviceNotFound(did)
        if (capabilities := capabilities_for(device.product_key)) is None:
            raise DeviceNotSupported(did)
        return capabilities

    async def _send_command(self, did: str, payload: dict[str, Any]) -> None:
        if self._client is None or not self.is_connected:
            raise NotConnected
        try:
            await self._client.websocket.async_control_device(did, payload)
        except (HeatzyException, ClientError) as error:
            raise ControlFailed(str(error)) from error

    def _on_listen_task_end(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        if (exc := task.exception()) is not None:
            logger.error("listen task ended with error: %s", exc)

    async def _handle_auth_failure(self) -> None:
        self._set_status("logged_out")
        await self._close_client()
        self.auth_error = "Identifiants Heatzy invalides"
        with db.session_scope() as session:
            credentials.mark_disconnected(session)

    async def _connect(self) -> None:
        if self._client is None:
            return
        await self._client.websocket.async_connect(
            auto_subscribe=True, all_devices=False
        )

    async def _disconnect(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.websocket.async_disconnect()
        except Exception as exc:
            logger.debug("websocket disconnect failed: %s", exc)

    async def _supervise(self) -> None:
        while not self._stopping and self._client is not None:
            try:
                await self._client.websocket.async_listen()
            except AuthenticationFailed as exc:
                await self._handle_auth_failure()
                logger.warning("authentication failed during listen: %s", exc)
                return
            except _TRANSIENT_ERRORS as error:
                if not await self._reconnect(error):
                    return
            else:
                if not await self._reconnect(None):
                    return

    async def _reconnect(self, error: Exception | None) -> bool:
        self._connection_attempts += 1
        if self._connection_attempts > self._retry_max_attempts:
            logger.error("giving up on websocket: %s", error)
            self.auth_error = "La connexion aux serveurs Heatzy a été perdue."
            self._set_status("logged_out")
            await self._close_client()
            return False

        self._set_status("reconnecting")

        delay = backoff(
            self._connection_attempts,
            self._retry_backoff_base,
            self._retry_backoff_cap,
        )

        logger.info(
            "reconnecting in %s s (attempt %s)", delay, self._connection_attempts
        )

        await asyncio.sleep(delay)

        if self._stopping:
            return False
        if self._client is None:
            logger.error("client not initialized")
            return False

        await self._disconnect()

        try:
            await self._connect()
        except _RECONNECT_ERRORS as exc:
            logger.warning("reconnect failed, will retry: %s", exc)
            await self._disconnect()
            return True

        self._connection_attempts = 0
        self._set_status("connected")
        return True

    def _set_status(self, status: Status) -> None:
        if status == self.status:
            return
        self.status = status
        self._events.emit("service_status", status)
