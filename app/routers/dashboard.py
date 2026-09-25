import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.deps import AppContextDep
from app.templating import templates

logger = logging.getLogger(__name__)


router = APIRouter(tags=["dashboard"])

@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, ctx: AppContextDep):
    if not ctx.service.is_connected:
        return RedirectResponse("/login", status_code=303)
    devices = ctx.service.devices
    return templates.TemplateResponse(
        request, "pages/dashboard.html", {"devices": devices}
    )
