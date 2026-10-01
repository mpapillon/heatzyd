from typing import Any

from app.domain.derog import DerogMode
from app.domain.modes import Mode
from app.heatzy.device import DeviceState, Group

_REMARK = "range=4|isdelete=1|gid=0|groupname=|grouprange=4"


def _device(**overrides: Any) -> DeviceState:
    raw: dict[str, Any] = {
        "did": "did-1",
        "dev_alias": "Salon",
        "product_name": "Pilote",
        "product_key": "key",
        "mac": "AA:BB:CC",
        "is_online": 1,
        "remark": _REMARK,
        "attrs": {"mode": "eco", "lock_switch": 1, "derog_mode": 2, "derog_time": 30},
    }
    raw.update(overrides)
    return DeviceState(raw)


# remark-driven properties


def test_range_from_remark() -> None:
    assert _device().range == 4


def test_range_missing_remark_defaults_to_zero() -> None:
    assert _device(remark="").range == 0


def test_group_from_remark() -> None:
    assert _device().group == Group(id=0, name="", range=4)


def test_group_with_actual_values() -> None:
    device = _device(remark="range=4|gid=7|groupname=Étage|grouprange=3")

    assert device.group == Group(id=7, name="Étage", range=3)


# identity / metadata


def test_basic_metadata() -> None:
    device = _device()

    assert device.did == "did-1"
    assert device.dev_alias == "Salon"
    assert device.product_name == "Pilote"
    assert device.product_key == "key"
    assert device.mac == "AA:BB:CC"


def test_metadata_defaults_when_missing() -> None:
    device = DeviceState({})

    assert device.did == ""
    assert device.dev_alias == ""
    assert device.product_name == ""
    assert device.product_key == ""
    assert device.mac == ""


# online / mode


def test_online_device_reports_attrs_mode() -> None:
    assert _device().is_online is True
    assert _device().mode is Mode.ECO


def test_offline_device_reports_offline_mode() -> None:
    assert _device(is_online=0).is_online is False
    assert _device(is_online=0).mode is Mode.OFFLINE


# lock / derogation


def test_lock_flag() -> None:
    assert _device().lock is True
    assert _device(attrs={"lock_switch": 0}).lock is False


def test_derogation_state() -> None:
    device = _device()

    assert device.derog_mode is DerogMode.BOOST
    assert device.derog_time == 30


def test_derogation_defaults_when_absent() -> None:
    device = _device(attrs={})

    assert device.derog_mode is DerogMode.NONE
    assert device.derog_time == 0
