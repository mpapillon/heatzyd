from datetime import datetime, timedelta
from typing import Any

import pytest
from heatzypy import AuthenticationFailed, HeatzyException
from heatzypy.exception import CommandFailed

from app.domain.capabilities import PILOTE_GEN_1, PILOTE_GEN_4
from app.domain.derog import DerogMode
from app.domain.errors import DerogNotSupported, LockNotSupported, ModeNotSupported
from app.domain.modes import Mode
from app.domain.protocol import ALIAS_MAX_LENGTH
from app.heatzy.errors import (
    ControlFailed,
    DeviceNotFound,
    DeviceNotSupported,
    NotConnected,
)
from app.heatzy.service import HeatzyService
from tests.helpers import FakeHeatzypyClient, _connected, _use


def _device(
    did: str = "did-1",
    product_key: str = PILOTE_GEN_4[0],
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    device: dict[str, Any] = {"did": did, "product_key": product_key}
    if attrs is not None:
        device["attrs"] = attrs
    return device


# properties


def test_no_client_means_disconnected(service: HeatzyService) -> None:
    assert service.devices == []
    assert service.is_connected is False


def test_devices_come_from_the_client_cache(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    fake.websocket.devices = {"did-1": _device()}
    _use(service, fake)

    assert [device.did for device in service.devices] == ["did-1"]


# send_order / send_lock


async def test_send_order_requires_client(service: HeatzyService) -> None:
    with pytest.raises(NotConnected):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_requires_connection(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    with pytest.raises(NotConnected):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_unsupported_product(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key="unknown")}

    with pytest.raises(DeviceNotSupported):
        await service.send_order("did-1", Mode.ECO)


async def test_send_order_unsupported_mode(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key=PILOTE_GEN_1[0])}

    with pytest.raises(ModeNotSupported):
        await service.send_order("did-1", Mode.CONFORT_M1)


async def test_send_order_sends_encoded_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_order("did-1", Mode.ECO)

    assert fake.websocket.sent == [("did-1", {"attrs": {"mode": "eco"}})]


async def test_send_order_wraps_transport_error(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}
    fake.websocket.control_error = HeatzyException("boom")

    with pytest.raises(ControlFailed):
        await service.send_order("did-1", Mode.ECO)


async def test_send_lock_sends_encoded_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_lock("did-1", True)

    assert fake.websocket.sent == [("did-1", {"attrs": {"lock_switch": 1}})]


async def test_send_lock_not_supported(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key=PILOTE_GEN_1[0])}

    with pytest.raises(LockNotSupported):
        await service.send_lock("did-1", True)


# send_derog / cancel_derog


async def test_send_derog_requires_connection(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    with pytest.raises(NotConnected):
        await service.send_derog("did-1", DerogMode.BOOST, 30)


async def test_send_derog_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.send_derog("did-1", DerogMode.BOOST, 30)


async def test_send_derog_unsupported_product(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(product_key=PILOTE_GEN_1[0])}

    with pytest.raises(DerogNotSupported):
        await service.send_derog("did-1", DerogMode.BOOST, 30)


async def test_send_derog_sends_encoded_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_derog("did-1", DerogMode.BOOST, 45)

    assert fake.websocket.sent == [
        ("did-1", {"attrs": {"derog_mode": 2, "derog_time": 45, "mode": "cft"}})
    ]


async def test_send_boost_derog_sends_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    await service.send_boost_derog("did-1", 45)

    assert fake.websocket.sent == [
        ("did-1", {"attrs": {"derog_mode": 2, "derog_time": 45, "mode": "cft"}})
    ]


async def test_send_vacation_derog_derives_days_from_ends_at(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}
    # 5 jours demandés : le delta réel est légèrement < 5 j, donc ceil -> 5
    ends_at = datetime.now() + timedelta(days=5)

    await service.send_vacation_derog("did-1", ends_at)

    assert fake.websocket.sent == [
        ("did-1", {"attrs": {"derog_mode": 1, "derog_time": 5, "mode": "fro"}})
    ]


async def test_send_vacation_derog_rejects_a_past_date(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    with pytest.raises(ValueError, match="future"):
        await service.send_vacation_derog("did-1", datetime.now() - timedelta(days=1))

    assert fake.websocket.sent == []


async def test_cancel_derog_requires_connection(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _use(service, fake)

    with pytest.raises(NotConnected):
        await service.cancel_derog("did-1")


async def test_cancel_derog_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.cancel_derog("did-1")


async def test_cancel_derog_noop_without_active_derog(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device(attrs={"derog_mode": 0})}

    await service.cancel_derog("did-1")

    assert fake.websocket.sent == []


async def test_cancel_derog_sends_clear_payload(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {
        "did-1": _device(attrs={"derog_mode": 2, "derog_time": 30})
    }

    await service.cancel_derog("did-1")

    assert fake.websocket.sent == [
        ("did-1", {"attrs": {"derog_mode": 0, "derog_time": 0}})
    ]


# rename


async def test_rename_requires_client(service: HeatzyService) -> None:
    with pytest.raises(NotConnected):
        await service.rename("did-1", "Salon")


async def test_rename_unknown_device(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)

    with pytest.raises(DeviceNotFound):
        await service.rename("did-1", "Salon")


async def test_rename_updates_cache_and_emits_event(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}
    fake.request_response = {"dev_alias": "Salon"}
    received: list[Any] = []
    service._events.on("device_changed", received.append)

    await service.rename("did-1", "Salon")

    assert fake.requests == [
        ("bindings/did-1", "put", {"json": {"dev_alias": "Salon"}})
    ]
    assert fake.websocket.devices["did-1"]["dev_alias"] == "Salon"
    assert received == ["did-1"]


async def test_rename_wraps_transport_error(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}
    fake.request_error = CommandFailed("boom")

    with pytest.raises(ControlFailed):
        await service.rename("did-1", "Salon")


async def test_rename_rejects_too_long_alias(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    _connected(service, fake)
    fake.websocket.devices = {"did-1": _device()}

    with pytest.raises(ControlFailed):
        await service.rename("did-1", "x" * (ALIAS_MAX_LENGTH + 1))

    assert fake.requests == []


# device changed hook


def test_on_device_changed_emits_event(service: HeatzyService) -> None:
    received: list[Any] = []
    service._events.on("device_changed", received.append)

    service._on_device_changed({"did": "did-1"})

    assert received == ["did-1"]


def test_on_device_changed_without_did_is_ignored(service: HeatzyService) -> None:
    received: list[Any] = []
    service._events.on("device_changed", received.append)

    service._on_device_changed({})

    assert received == []


# status delegation


def test_default_status_is_failed(service: HeatzyService) -> None:
    assert service.status == "failed"


async def test_start_sets_connected_status(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    await service.start()
    try:
        assert service.status == "connected"
    finally:
        await service.stop()


async def test_start_failure_keeps_failed(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    fake.websocket.connect_error = AuthenticationFailed("bad")

    await service.start()

    assert service.status == "failed"


async def test_stop_sets_failed(
    service: HeatzyService, fake: FakeHeatzypyClient
) -> None:
    await service.start()

    await service.stop()

    assert service.status == "failed"


async def test_start_without_credentials_stays_failed(
    service_without_credentials: HeatzyService,
) -> None:
    await service_without_credentials.start()

    assert service_without_credentials.status == "failed"
