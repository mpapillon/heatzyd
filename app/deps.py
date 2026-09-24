from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.requests import Request
from sqlmodel import Session

from app.config import Settings
from app.heatzy import HeatzyService
from app.models.db import get_engine


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    service: HeatzyService


def get_context(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


AppContextDep = Annotated[AppContext, Depends(get_context)]


def get_service(ctx: AppContextDep) -> HeatzyService:
    return ctx.service


ServiceDep = Annotated[HeatzyService, Depends(get_service)]
