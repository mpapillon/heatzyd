from dataclasses import dataclass

from app.domain.capabilities import ProductCapabilities
from app.domain.modes import Mode
from app.heatzy.device import DeviceState


@dataclass(frozen=True, slots=True)
class DeviceCardVM:
    did: str
    alias: str
    mode: Mode | None
    capabilities: ProductCapabilities | None

    @property
    def quick_switch(self) -> Mode | None:
        if self.mode is None or self.mode == Mode.OFFLINE:
            return None
        return Mode.ECO if self.mode != Mode.ECO else Mode.CONFORT

    @property
    def available_modes(self) -> tuple[Mode, ...]:
        return self.capabilities.modes if self.capabilities else ()

    @classmethod
    def from_state(
        cls, device: DeviceState, capabilities: ProductCapabilities | None
    ) -> DeviceCardVM:
        return cls(
            did=device.did,
            alias=device.dev_alias or "Sans nom",
            mode=device.mode,
            capabilities=capabilities,
        )
