import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.deps import AppContext
from app.heatzy import HeatzyService
from app.heatzy.events import EventEmitter
from app.middlewares import IsConnectedMiddleware
from app.models.db import init_db
from app.routers import auth, devices, events_sse, pages


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    init_db(settings.database_path)

    events = EventEmitter()
    service = HeatzyService(settings=settings, events=events)
    await service.start()

    app.state.ctx = AppContext(settings=settings, service=service, events=events)
    try:
        yield
    finally:
        await service.stop()


def create_app() -> FastAPI:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    app = FastAPI(title="heatzyd", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.add_middleware(IsConnectedMiddleware)
    app.include_router(auth.router)
    app.include_router(devices.router)
    app.include_router(events_sse.router)
    app.include_router(pages.router)
    return app


app = create_app()
