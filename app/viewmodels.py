from dataclasses import dataclass

from app.domain.modes import Mode
from app.heatzy.device import DeviceState


@dataclass(frozen=True, slots=True)
class DeviceCardVM:
    did: str
    alias: str
    mode: Mode | None

    @property
    def quick_switch(self) -> Mode | None:
        if self.mode is None or self.mode == Mode.OFFLINE:
            return None
        return Mode.ECO if self.mode != Mode.ECO else Mode.CONFORT

    @classmethod
    def from_state(cls, device: DeviceState) -> "DeviceCardVM":
        return cls(
            did=device.did,
            alias=device.dev_alias or "Sans nom",
            mode=device.mode,
        )
