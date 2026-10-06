from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.capabilities import ProductCapabilities
from app.domain.derog import DerogMode, derogation_bounds
from app.domain.modes import Mode
from app.heatzy.device import DeviceState


@dataclass(frozen=True, slots=True)
class DeviceVM:
    did: str
    alias: str
    capabilities: ProductCapabilities | None
    is_online: bool
    lock: bool
    mode: Mode | None
    derog_mode: DerogMode
    derog_time: int
    model: str
    serial: str

    _tz: ZoneInfo | None = field(default=None, repr=False, compare=False)

    @property
    def quick_switch(self) -> Mode | None:
        if self.mode is None or self.mode == Mode.OFFLINE:
            return None
        return Mode.ECO if self.mode != Mode.ECO else Mode.CONFORT

    @property
    def available_modes(self) -> tuple[Mode, ...]:
        return self.capabilities.modes if self.capabilities else ()

    @property
    def dashboard_modes(self) -> tuple[Mode, ...]:
        return tuple(m for m in self.available_modes if m != Mode.OFF)

    @property
    def has_vacations(self) -> bool:
        return self.derog_mode == DerogMode.VACATIONS

    @property
    def vacation_ends_at(self) -> str | None:
        if not self.has_vacations:
            return None
        ends_at = datetime.now(self._tz) + timedelta(days=self.derog_time)
        return ends_at.date().isoformat()

    @property
    def vacation_min(self) -> str:
        min_date, _ = derogation_bounds(self._tz)
        return min_date.isoformat()

    @property
    def vacation_max(self) -> str:
        _, max_date = derogation_bounds(self._tz)
        return max_date.isoformat()

    @classmethod
    def from_state(
        cls,
        device: DeviceState,
        capabilities: ProductCapabilities | None,
        tz: ZoneInfo | None,
    ) -> DeviceVM:
        return cls(
            did=device.did,
            alias=device.dev_alias or "Sans nom",
            capabilities=capabilities,
            is_online=device.is_online,
            lock=device.lock,
            mode=device.mode,
            derog_mode=device.derog_mode,
            derog_time=device.derog_time,
            model=device.product_name,
            serial=device.mac,
            _tz=tz,
        )
