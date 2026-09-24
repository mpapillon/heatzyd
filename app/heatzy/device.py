from dataclasses import dataclass
from typing import Any

from app.domain.modes import Mode
from app.domain.protocol import parse_bool, parse_mode


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
    def mode(self) -> Mode | None:
        return parse_mode(self._attrs.get("mode"))

    @property
    def lock(self) -> bool:
        return parse_bool(self._attrs.get("lock_switch"))

    @property
    def timer_switch(self) -> bool:
        return parse_bool(self._attrs.get("timer_switch"))
