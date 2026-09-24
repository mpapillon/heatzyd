import logging
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlmodel import Session, SQLModel

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("init_db() should be called before using the database")
    return _engine


def session_scope() -> Session:
    """Session pour le code hors-HTTP.

    Usage: ``with session_scope() as session: ...``
    """
    return Session(get_engine())


def init_db(path: str) -> None:
    global _engine

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_pragmas)
    _engine = engine

    import app.models  # noqa: F401 - importe les tables dans SQLModel.metadata

    SQLModel.metadata.create_all(engine)
    logger.info("base %s initialisee", db_path)


def _apply_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
