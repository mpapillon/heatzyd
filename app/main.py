import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.deps import AppContext
from app.heatzy import HeatzyService
from app.models.db import init_db
from app.routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    init_db(settings.database_path)

    service = HeatzyService(settings=settings)
    await service.start()

    app.state.ctx = AppContext(settings=settings, service=service)
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
    app.include_router(auth.router)
    return app


app = create_app()
