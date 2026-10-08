from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.requests import Request

from app.config import Settings
from app.heatzy import HeatzyService
from app.heatzy.events import EventEmitter


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    service: HeatzyService
    events: EventEmitter


def get_context(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


AppContextDep = Annotated[AppContext, Depends(get_context)]


def get_service(ctx: AppContextDep) -> HeatzyService:
    return ctx.service


ServiceDep = Annotated[HeatzyService, Depends(get_service)]
