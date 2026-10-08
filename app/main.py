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
from app.routers import devices, events_sse, pages, service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    events = EventEmitter()
    service = HeatzyService(settings=settings, events=events)
    await service.start()

    app.state.ctx = AppContext(settings=settings, service=service, events=events)
    try:
        yield
    finally:
        await service.stop()
        await events.shutdown()


def create_app() -> FastAPI:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    app = FastAPI(title="heatzyd", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.add_middleware(IsConnectedMiddleware)
    app.include_router(devices.router)
    app.include_router(events_sse.router)
    app.include_router(pages.router)
    app.include_router(service.router)
    return app


app = create_app()
