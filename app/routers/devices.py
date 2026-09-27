import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from app.deps import AppContextDep
from app.templating import templates

logger = logging.getLogger(__name__)


router = APIRouter(tags=["devices"])


@router.get("/devices/{did}/card", response_class=HTMLResponse)
async def device_card(
    request: Request,
    ctx: AppContextDep,
    did: str,
):
    if not ctx.service.is_connected:
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    device = ctx.service.get_device(did)
    return templates.TemplateResponse(
        request, "partials/device_card.html", {"device": device}
    )
