from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.derog import DerogMode
from app.domain.errors import DerogNotSupported
from app.heatzy.errors import (
    ControlFailed,
    DeviceNotFound,
    DeviceNotSupported,
    NotConnected,
)
from app.routers.devices import device_derog, device_derog_delete


class StubService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[Any, ...]] = []

    async def send_derog(self, did: str, kind: DerogMode, time: int) -> None:
        self.calls.append((did, kind, time))
        if self.error is not None:
            raise self.error

    async def cancel_derog(self, did: str) -> None:
        self.calls.append((did,))
        if self.error is not None:
            raise self.error


def _ctx(service: StubService) -> Any:
    return SimpleNamespace(service=service)


async def test_device_derog_sends_command() -> None:
    service = StubService()

    response = await device_derog(_ctx(service), "did-1", DerogMode.BOOST, 45)

    assert response.status_code == 204
    assert service.calls == [("did-1", DerogMode.BOOST, 45)]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotConnected(), 200),
        (DeviceNotFound("did-1"), 404),
        (DeviceNotSupported("did-1"), 409),
        (DerogNotSupported(), 400),
        (ValueError("bad time"), 400),
        (ControlFailed("boom"), 502),
    ],
)
async def test_device_derog_maps_errors(error: Exception, status: int) -> None:
    response = await device_derog(
        _ctx(StubService(error)), "did-1", DerogMode.BOOST, 45
    )

    assert response.status_code == status


async def test_device_derog_redirects_to_login_when_disconnected() -> None:
    response = await device_derog(
        _ctx(StubService(NotConnected())), "did-1", DerogMode.BOOST, 45
    )

    assert response.headers["HX-Redirect"] == "/login"


async def test_device_derog_delete_cancels() -> None:
    service = StubService()

    response = await device_derog_delete(_ctx(service), "did-1")

    assert response.status_code == 204
    assert service.calls == [("did-1",)]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotConnected(), 200),
        (DeviceNotFound("did-1"), 404),
        (DeviceNotSupported("did-1"), 409),
        (DerogNotSupported(), 400),
        (ValueError("bad"), 400),
        (ControlFailed("boom"), 502),
    ],
)
async def test_device_derog_delete_maps_errors(error: Exception, status: int) -> None:
    response = await device_derog_delete(_ctx(StubService(error)), "did-1")

    assert response.status_code == status
