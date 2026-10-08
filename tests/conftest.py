import pytest

from app.config import Settings
from app.heatzy import session as session_mod
from app.heatzy.events import EventEmitter
from app.heatzy.service import HeatzyService
from app.heatzy.session import ConnectionSupervisor
from tests.helpers import FakeHeatzypyClient

_SETTINGS = Settings(
    username="user",
    password="pass",
    retry_backoff_base=15,
    retry_backoff_cap=240,
    retry_max_attempts=5,
)


def _settings() -> Settings:
    return Settings(
        username=None,
        password=None,
        retry_backoff_base=15,
        retry_backoff_cap=240,
        retry_max_attempts=5,
    )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeHeatzypyClient:
    client = FakeHeatzypyClient()
    monkeypatch.setattr(session_mod, "HeatzyClient", lambda *a, **kw: client)
    monkeypatch.setattr(session_mod, "ClientSession", lambda *a, **kw: object())
    monkeypatch.setattr(session_mod, "backoff", lambda *a: 0.0)
    return client


@pytest.fixture
def settings() -> Settings:
    return _SETTINGS


@pytest.fixture
def supervisor(fake: FakeHeatzypyClient) -> ConnectionSupervisor:
    return ConnectionSupervisor(_SETTINGS, EventEmitter(), lambda device: None)


@pytest.fixture
def supervisor_without_credentials(
    fake: FakeHeatzypyClient,
) -> ConnectionSupervisor:
    return ConnectionSupervisor(_settings(), EventEmitter(), lambda device: None)


@pytest.fixture
def service(fake: FakeHeatzypyClient) -> HeatzyService:
    return HeatzyService(_SETTINGS, EventEmitter())


@pytest.fixture
def service_without_credentials(fake: FakeHeatzypyClient) -> HeatzyService:
    return HeatzyService(_settings(), EventEmitter())
