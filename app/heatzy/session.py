import asyncio
import logging
from collections.abc import Callable
from typing import Any, Literal

from aiohttp import ClientError, ClientSession
from heatzypy import (
    AuthenticationFailed,
    HeatzyClient,
)
from heatzypy.exception import (
    HeatzyException,
    HttpRequestFailed,
    RetrieveFailed,
    TimeoutExceededError,
    WebsocketError,
)

from app.config import Settings
from app.domain.control import backoff
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


class ConnectionSupervisor:
    def __init__(
        self,
        settings: Settings,
        events: EventEmitter,
        on_device_changed: Callable[[dict[str, Any]], None],
    ) -> None:
        self.auth_error: str | None = None
        self.status: Status = "logged_out"

        self._events = events
        self._on_device_changed = on_device_changed

        self._region = settings.heatzy_region
        self._use_tls = settings.use_tls
        self._retry_backoff_base = settings.retry_backoff_base
        self._retry_backoff_cap = settings.retry_backoff_cap
        self._retry_max_attempts = settings.retry_max_attempts

        self._connection_attempts = 0
        self._stopping = False
        self._client: HeatzyClient | None = None
        self._listen_task: asyncio.Task[None] | None = None

    @property
    def client(self) -> HeatzyClient | None:
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.websocket.is_connected

    # Lifecycle

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

    # Supervision

    async def _connect(self) -> None:
        if self._client is None:
            return
        await self._client.websocket.async_connect(
            auto_subscribe=True, all_devices=False
        )

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

    async def _handle_auth_failure(self) -> None:
        self._set_status("logged_out")
        await self._close_client()
        self.auth_error = "Identifiants Heatzy invalides"
        with db.session_scope() as session:
            credentials.mark_disconnected(session)

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

    async def _disconnect(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.websocket.async_disconnect()
        except Exception as exc:
            logger.debug("websocket disconnect failed: %s", exc)

    def _on_listen_task_end(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        if (exc := task.exception()) is not None:
            logger.error("listen task ended with error: %s", exc)

    def _set_status(self, status: Status) -> None:
        if status == self.status:
            return
        self.status = status
        self._events.emit("service_status", status)
