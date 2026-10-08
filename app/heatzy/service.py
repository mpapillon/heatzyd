from datetime import datetime
from typing import Any

from aiohttp import ClientError
from heatzypy import HeatzyException

from app.config import Settings
from app.domain import derog
from app.domain.capabilities import ProductCapabilities, capabilities_for
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
from app.heatzy.session import ConnectionSupervisor, Status


class HeatzyService:
    def __init__(self, settings: Settings, events: EventEmitter):
        self._events = events
        self._tz = settings.tz
        self._session = ConnectionSupervisor(settings, events, self._on_device_changed)

    @property
    def status(self) -> Status:
        return self._session.status

    @property
    def is_connected(self) -> bool:
        return self._session.is_connected

    async def start(self) -> None:
        await self._session.start()

    async def stop(self) -> None:
        await self._session.stop()

    @property
    def devices(self) -> list[DeviceState]:
        if (client := self._session.client) is None:
            return []
        return sorted(
            [DeviceState(device) for device in client.websocket.devices.values()],
            key=lambda device: device.range,
        )

    def get_device(self, did: str) -> DeviceState | None:
        for device in self.devices:
            if device.did == did:
                return device
        return None

    async def rename(self, did: str, alias: str) -> None:
        if (client := self._session.client) is None:
            raise NotConnected
        if (device := self.get_device(did)) is None:
            raise DeviceNotFound(did)
        if len(alias) > ALIAS_MAX_LENGTH:
            raise ControlFailed(f"alias is too long (max: {ALIAS_MAX_LENGTH})")
        try:
            response = await client.async_request(
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
        if not self.is_connected:
            raise NotConnected
        device = self.get_device(did)
        if device is None:
            raise DeviceNotFound(did)
        if (capabilities := capabilities_for(device.product_key)) is None:
            raise DeviceNotSupported(did)
        return capabilities

    async def _send_command(self, did: str, payload: dict[str, Any]) -> None:
        if (client := self._session.client) is None or not self.is_connected:
            raise NotConnected
        try:
            await client.websocket.async_control_device(did, payload)
        except (HeatzyException, ClientError) as error:
            raise ControlFailed(str(error)) from error
