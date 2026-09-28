from dataclasses import dataclass
from typing import Any

from app.domain.modes import Mode
from app.domain.protocol import extract_mode, parse_int_flag


@dataclass(frozen=True, slots=True)
class DeviceState:
    raw_device: dict[str, Any]

    @property
    def _attrs(self) -> dict[str, Any]:
        return self.raw_device.get("attrs", {})

    @property
    def did(self) -> str:
        return self.raw_device.get("did", "")

    @property
    def dev_alias(self) -> str:
        return self.raw_device.get("dev_alias", "")

    @property
    def product_name(self) -> str:
        return self.raw_device.get("product_name", "")

    @property
    def mac(self) -> str:
        return self.raw_device.get("mac", "")

    @property
    def product_key(self) -> str:
        return self.raw_device.get("product_key", "")

    @property
    def is_online(self) -> bool:
        return parse_int_flag(self.raw_device.get("is_online"))

    @property
    def mode(self) -> Mode | None:
        if not self.is_online:
            return Mode.OFFLINE
        return extract_mode(self._attrs)

    @property
    def lock(self) -> bool:
        return parse_int_flag(self._attrs.get("lock_switch"))

    @property
    def timer_switch(self) -> bool:
        return parse_int_flag(self._attrs.get("timer_switch"))
