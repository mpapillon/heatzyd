from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.errors import DerogNotSupported
from app.heatzy.errors import (
    ControlFailed,
    DeviceNotFound,
    DeviceNotSupported,
    NotConnected,
)
from app.routers.devices import (
    device_boost,
    device_derog_delete,
    device_rename,
    device_vacation,
)

RETURNS_ON = datetime(2026, 8, 15)

_ERRORS = [
    pytest.param(NotConnected(), 200, id="not-connected"),
    pytest.param(DeviceNotFound("did-1"), 404, id="not-found"),
    pytest.param(DeviceNotSupported("did-1"), 409, id="device-unsupported"),
    pytest.param(DerogNotSupported(), 400, id="derog-unsupported"),
    pytest.param(ValueError("ends_at must be in the future"), 400, id="bad-duration"),
    pytest.param(ControlFailed("boom"), 502, id="control-failed"),
]

_RENAME_ERRORS = [
    pytest.param(NotConnected(), 200, id="not-connected"),
    pytest.param(DeviceNotFound("did-1"), 404, id="not-found"),
    pytest.param(DeviceNotSupported("did-1"), 409, id="device-unsupported"),
    pytest.param(ControlFailed("boom"), 502, id="control-failed"),
]


class StubService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[Any, ...]] = []

    async def send_boost_derog(self, did: str, minutes: int) -> None:
        self.calls.append(("boost", did, minutes))
        if self.error is not None:
            raise self.error

    async def send_vacation_derog(self, did: str, ends_at: datetime) -> None:
        self.calls.append(("vacation", did, ends_at))
        if self.error is not None:
            raise self.error

    async def cancel_derog(self, did: str) -> None:
        self.calls.append(("cancel", did))
        if self.error is not None:
            raise self.error

    async def rename(self, did: str, alias: str) -> None:
        self.calls.append(("rename", did, alias))
        if self.error is not None:
            raise self.error


def _ctx(service: StubService) -> Any:
    return SimpleNamespace(service=service)


async def test_device_boost_sends_minutes() -> None:
    service = StubService()

    response = await device_boost(_ctx(service), "did-1", 45)

    assert response.status_code == 204
    assert service.calls == [("boost", "did-1", 45)]


async def test_device_vacation_sends_ends_at() -> None:
    service = StubService()

    response = await device_vacation(_ctx(service), "did-1", RETURNS_ON)

    assert response.status_code == 204
    assert service.calls == [("vacation", "did-1", RETURNS_ON)]


@pytest.mark.parametrize(("error", "status"), _ERRORS)
async def test_device_boost_maps_errors(error: Exception, status: int) -> None:
    response = await device_boost(_ctx(StubService(error)), "did-1", 45)

    assert response.status_code == status


@pytest.mark.parametrize(("error", "status"), _ERRORS)
async def test_device_vacation_maps_errors(error: Exception, status: int) -> None:
    response = await device_vacation(_ctx(StubService(error)), "did-1", RETURNS_ON)

    assert response.status_code == status


async def test_device_boost_redirects_to_setup_when_disconnected() -> None:
    response = await device_boost(_ctx(StubService(NotConnected())), "did-1", 45)

    assert response.headers["HX-Redirect"] == "/setup"


async def test_device_vacation_redirects_to_setup_when_disconnected() -> None:
    response = await device_vacation(
        _ctx(StubService(NotConnected())), "did-1", RETURNS_ON
    )

    assert response.headers["HX-Redirect"] == "/setup"


async def test_device_derog_delete_cancels() -> None:
    service = StubService()

    response = await device_derog_delete(_ctx(service), "did-1")

    assert response.status_code == 204
    assert service.calls == [("cancel", "did-1")]


@pytest.mark.parametrize(("error", "status"), _ERRORS)
async def test_device_derog_delete_maps_errors(error: Exception, status: int) -> None:
    response = await device_derog_delete(_ctx(StubService(error)), "did-1")

    assert response.status_code == status


async def test_device_rename_sends_alias() -> None:
    service = StubService()

    response = await device_rename(_ctx(service), "did-1", "Salon")

    assert response.status_code == 204
    assert service.calls == [("rename", "did-1", "Salon")]


async def test_device_rename_trims_alias() -> None:
    service = StubService()

    response = await device_rename(_ctx(service), "did-1", "  Salon  ")

    assert response.status_code == 204
    assert service.calls == [("rename", "did-1", "Salon")]


async def test_device_rename_rejects_blank_alias() -> None:
    service = StubService()

    response = await device_rename(_ctx(service), "did-1", "   ")

    assert response.status_code == 400
    assert service.calls == []


@pytest.mark.parametrize(("error", "status"), _RENAME_ERRORS)
async def test_device_rename_maps_errors(error: Exception, status: int) -> None:
    response = await device_rename(_ctx(StubService(error)), "did-1", "Salon")

    assert response.status_code == status


async def test_device_rename_redirects_to_setup_when_disconnected() -> None:
    response = await device_rename(_ctx(StubService(NotConnected())), "did-1", "Salon")

    assert response.headers["HX-Redirect"] == "/setup"
