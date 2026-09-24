from sqlmodel import Field, Session, SQLModel


class HeatzyCreds(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field()
    password: str = Field()
    connected: bool = Field(default=False)


def load(session: Session) -> HeatzyCreds | None:
    return session.get(HeatzyCreds, 1)


def upsert(
    session: Session, username: str, password: str, *, connected: bool = True
) -> HeatzyCreds:
    creds = load(session) or HeatzyCreds(id=1, username=username, password=password)
    creds.username, creds.password, creds.connected = username, password, connected
    session.add(creds)
    session.commit()
    session.refresh(creds)
    return creds


def clear(session: Session) -> None:
    creds = load(session)
    if creds is not None:
        session.delete(creds)
        session.commit()


def mark_disconnected(session: Session) -> None:
    creds = load(session)
    if creds is not None and creds.connected:
        creds.connected = False
        session.add(creds)
        session.commit()
