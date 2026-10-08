from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from app.deps import AppContextDep
from app.templating import templates

router = APIRouter(tags=["service"])


@router.get("/service/banner", response_class=HTMLResponse)
async def service_banner(
    request: Request,
    ctx: AppContextDep,
):
    if ctx.service.status in ("failed", "lost_connection"):
        return Response(status_code=200, headers={"HX-Redirect": "/setup"})

    return templates.TemplateResponse(
        request,
        "partials/service_banner.html",
        {"show_banner": ctx.service.status == "reconnecting"},
    )
