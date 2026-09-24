import asyncio
import logging
from typing import Any

from aiohttp import ClientSession
from heatzypy import AuthenticationFailed, HeatzyClient, HeatzyException

from app.config import Settings
from app.domain.protocol import parse_bool, parse_mode
from app.heatzy.device import DeviceState
from app.models.credentials import load, mark_disconnected
from app.models.db import session_scope

logger = logging.getLogger(__name__)


class HeatzyService:
    def __init__(self, settings: Settings):
        self.auth_error: str | None = None

        self._region = settings.heatzy_region
        self._use_tls = settings.use_tls

        self._client: HeatzyClient | None = None
        self._listen_task: asyncio.Task[None] | None = None

    @property
    def devices(self) -> list[DeviceState]:
        if self._client is None:
            return []
        return [
            DeviceState(device) for device in self._client.websocket.devices.values()
        ]

    @property
    def is_connected(self) -> bool:
        if self._client is None:
            return False
        return self._client.websocket.is_connected

    async def login(self, username: str, password: str) -> None:
        await self.stop()
        self._client = HeatzyClient(
            username,
            password,
            session=ClientSession(),
            region=self._region,
            use_tls=self._use_tls,
        )

        try:
            self._client.websocket.register_callback(self._callback)
            await self._client.websocket.async_connect(
                auto_subscribe=True, all_devices=True
            )
            self._listen_task = asyncio.create_task(
                self._client.websocket.async_listen()
            )
        except Exception:
            await self.stop()
            raise
        self.auth_error = None

    async def start(self) -> None:
        if self._client is not None:
            return

        with session_scope() as session:
            creds = load(session)
        if creds is None or not creds.connected:
            return
        try:
            await self.login(creds.username, creds.password)
        except AuthenticationFailed as error:
            with session_scope() as session:
                mark_disconnected(session)
            self.auth_error = "Identifiants Heatzy invalides"
            logger.warning("Heatzy authentication failed: %s", error)
        except HeatzyException as error:
            logger.error("Heatzy authentication was interrupted: %s", str(error))

    async def stop(self) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Unexpected error while stopping listen task")
            self._listen_task = None
        if self._client is not None:
            await self._client.async_close()
            self._client = None

    def _callback(self, devices: dict[str, Any]) -> None:
        for device in devices.values():
            dev_alias = device.get("dev_alias")
            attrs = device.get("attrs", {})
            mode = parse_mode(attrs.get("mode"))
            lock = parse_bool(attrs.get("lock_switch"))

            logger.info("Device: %s, mode: %s, lock: %s", dev_alias, mode, lock)
        logger.info("---------------------------------------")
