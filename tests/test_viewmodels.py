from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.derog import DerogMode
from app.domain.modes import Mode
from app.heatzy.device import DeviceState
from app.viewmodels import DeviceVM

PARIS = ZoneInfo("Europe/Paris")
TOKYO = ZoneInfo("Asia/Tokyo")


def _vm(**overrides: Any) -> DeviceVM:
    values: dict[str, Any] = {
        "did": "did-1",
        "alias": "Salon",
        "capabilities": None,
        "is_online": True,
        "lock": False,
        "mode": Mode.ECO,
        "derog_mode": DerogMode.NONE,
        "derog_time": 0,
        "model": "Pilote",
        "serial": "AA:BB:CC",
        "_tz": PARIS,
    }
    values.update(overrides)
    return DeviceVM(**values)


def _device(**overrides: Any) -> DeviceState:
    raw: dict[str, Any] = {
        "did": "did-1",
        "dev_alias": "Salon",
        "product_name": "Pilote",
        "product_key": "key",
        "mac": "AA:BB:CC",
        "is_online": 1,
        "attrs": {"mode": "eco", "derog_mode": 1, "derog_time": 5},
    }
    raw.update(overrides)
    return DeviceState(raw)


# vacation_ends_at


def test_vacation_ends_at_is_none_without_derogation() -> None:
    for mode in (DerogMode.NONE, DerogMode.BOOST, DerogMode.PRESENCE):
        assert _vm(derog_mode=mode, derog_time=5).vacation_ends_at is None


def test_vacation_ends_at_adds_derog_days() -> None:
    vm = _vm(derog_mode=DerogMode.VACATIONS, derog_time=5)

    expected = (datetime.now(PARIS).date() + timedelta(days=5)).isoformat()

    assert vm.vacation_ends_at == expected


# vacation bounds


def test_vacation_min_is_tomorrow() -> None:
    vm = _vm()

    expected = (datetime.now(PARIS).date() + timedelta(days=1)).isoformat()

    assert vm.vacation_min == expected


def test_vacation_max_is_255_days() -> None:
    vm = _vm()

    expected = (datetime.now(PARIS).date() + timedelta(days=255)).isoformat()

    assert vm.vacation_max == expected


def test_bounds_follow_the_device_timezone() -> None:
    vm = _vm(_tz=TOKYO)

    expected = (datetime.now(TOKYO).date() + timedelta(days=1)).isoformat()

    assert vm.vacation_min == expected


# _tz is private


def test_tz_is_absent_from_repr() -> None:
    assert "_tz" not in repr(_vm())
    assert "Paris" not in repr(_vm())


def test_tz_does_not_participate_in_equality() -> None:
    assert _vm(_tz=PARIS) == _vm(_tz=TOKYO)


# from_state


def test_from_state_carries_derogation_and_timezone() -> None:
    vm = DeviceVM.from_state(_device(), None, PARIS)

    assert vm.derog_mode is DerogMode.VACATIONS
    assert vm.derog_time == 5
    assert vm.has_vacations
    expected = (datetime.now(PARIS).date() + timedelta(days=1)).isoformat()
    assert vm.vacation_min == expected


def test_from_state_falls_back_to_mac() -> None:
    vm = DeviceVM.from_state(_device(dev_alias=""), None, PARIS)

    assert vm.alias == "AA:BB:CC"
