import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from heatzypy import AuthenticationFailed, HeatzyException

from app.deps import AppContextDep, SessionDep
from app.models import credentials
from app.templating import templates

logger = logging.getLogger(__name__)


router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, ctx: AppContextDep):
    if ctx.service.is_connected:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "pages/login.html", {"username": "", "error": ctx.service.auth_error}
    )


@router.post("/login")
async def login(
    request: Request,
    ctx: AppContextDep,
    session: SessionDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    try:
        await ctx.service.login(username, password)
    except AuthenticationFailed:
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {"error": "Identifiants Heatzy invalides", "username": username},
            status_code=401,
        )
    except HeatzyException as err:
        logger.error(err)
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {"error": "Serveur Heatzy indisponible", "username": username},
            status_code=502,
        )

    try:
        credentials.upsert(session, username, password)
    except Exception:
        logger.exception("Failed to upsert credentials")
        await ctx.service.stop()
        raise
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(ctx: AppContextDep, session: SessionDep):
    await ctx.service.stop()
    credentials.clear(session)
    ctx.service.auth_error = None
    return RedirectResponse("/login", status_code=303)
