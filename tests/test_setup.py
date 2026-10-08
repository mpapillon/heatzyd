from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.testclient import TestClient

from app.config import Settings
from app.deps import AppContext
from app.heatzy.events import EventEmitter
from app.middlewares import IsConnectedMiddleware
from app.routers import pages, service


def _context(status: str, *, creds: bool = True) -> AppContext:
    settings = Settings(
        username="user" if creds else None,
        password="pass" if creds else None,
    )
    return AppContext(
        settings=settings,
        service=SimpleNamespace(status=status),  # type: ignore[arg-type]
        events=EventEmitter(),
    )


def _app(ctx: AppContext, *, middleware: bool = False) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    if middleware:
        app.add_middleware(IsConnectedMiddleware)
    app.include_router(pages.router)
    app.include_router(service.router)

    @app.get("/ping")
    def ping() -> str:
        return "pong"

    app.state.ctx = ctx
    return app


def _client(ctx: AppContext, *, middleware: bool = False) -> TestClient:
    return TestClient(_app(ctx, middleware=middleware), follow_redirects=False)


# IsConnectedMiddleware


def test_middleware_redirects_failed_to_setup() -> None:
    response = _client(_context("failed"), middleware=True).get("/")

    assert response.status_code == 303
    assert response.headers["location"] == "/setup"


def test_middleware_redirects_lost_connection_to_setup() -> None:
    response = _client(_context("lost_connection"), middleware=True).get("/")

    assert response.status_code == 303
    assert response.headers["location"] == "/setup"


def test_middleware_redirects_htmx_via_header() -> None:
    response = _client(_context("failed"), middleware=True).get(
        "/", headers={"hx-request": "true"}
    )

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/setup"


def test_middleware_leaves_reconnecting_through() -> None:
    response = _client(_context("reconnecting"), middleware=True).get("/ping")

    assert response.status_code == 200
    assert "pong" in response.text


def test_middleware_leaves_connected_through() -> None:
    response = _client(_context("connected"), middleware=True).get("/ping")

    assert response.status_code == 200
    assert "pong" in response.text


def test_middleware_whitelists_setup() -> None:
    response = _client(_context("failed"), middleware=True).get("/setup")

    assert response.status_code == 200


def test_middleware_whitelists_static() -> None:
    response = _client(_context("failed"), middleware=True).get("/static/app.css")

    assert response.status_code == 200


# setup page variants


def test_setup_variant_missing_credentials() -> None:
    response = _client(_context("failed", creds=False)).get("/setup")

    assert response.status_code == 200
    assert "Configuration requise" in response.text


def test_setup_variant_connection_failed() -> None:
    response = _client(_context("failed")).get("/setup")

    assert response.status_code == 200
    assert "Connexion à Heatzy impossible" in response.text


def test_setup_variant_lost_connection() -> None:
    response = _client(_context("lost_connection")).get("/setup")

    assert response.status_code == 200
    assert "Connexion perdue avec les serveurs Heatzy" in response.text


def test_setup_page_has_no_sse_stream() -> None:
    response = _client(_context("failed")).get("/setup")

    assert "hx-sse:connect" not in response.text


# service banner


def test_banner_redirects_failed_to_setup() -> None:
    response = _client(_context("failed")).get("/service/banner")

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/setup"


def test_banner_redirects_lost_connection_to_setup() -> None:
    response = _client(_context("lost_connection")).get("/service/banner")

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/setup"


def test_banner_shown_while_reconnecting() -> None:
    response = _client(_context("reconnecting")).get("/service/banner")

    assert response.status_code == 200
    assert "Connexion perdue" in response.text
    assert "d-none" not in response.text


def test_banner_hidden_when_connected() -> None:
    response = _client(_context("connected")).get("/service/banner")

    assert response.status_code == 200
    assert "d-none" in response.text
