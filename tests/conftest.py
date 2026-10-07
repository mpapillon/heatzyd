from pathlib import Path

import pytest

from app.config import Settings
from app.heatzy import session as session_mod
from app.heatzy.events import EventEmitter
from app.heatzy.service import HeatzyService
from app.heatzy.session import ConnectionSupervisor
from app.models import db
from tests.helpers import FakeHeatzypyClient

_SETTINGS = Settings(
    retry_backoff_base=15,
    retry_backoff_cap=240,
    retry_max_attempts=5,
)


@pytest.fixture(autouse=True)
def _database(tmp_path: Path) -> None:
    db.init_db(str(tmp_path / "test.db"))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeHeatzypyClient:
    client = FakeHeatzypyClient()
    monkeypatch.setattr(session_mod, "HeatzyClient", lambda *a, **kw: client)
    monkeypatch.setattr(session_mod, "ClientSession", lambda *a, **kw: object())
    monkeypatch.setattr(session_mod, "backoff", lambda *a: 0.0)
    return client


@pytest.fixture
def supervisor(fake: FakeHeatzypyClient) -> ConnectionSupervisor:
    return ConnectionSupervisor(_SETTINGS, EventEmitter(), lambda device: None)


@pytest.fixture
def service(fake: FakeHeatzypyClient) -> HeatzyService:
    return HeatzyService(_SETTINGS, EventEmitter())
