import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.deps import AppContextDep
from app.domain.capabilities import capabilities_for
from app.templating import templates
from app.viewmodels import DeviceCardVM

logger = logging.getLogger(__name__)


router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, ctx: AppContextDep):
    devices = [
        DeviceCardVM.from_state(device, capabilities_for(device.product_key))
        for device in ctx.service.devices
    ]
    return templates.TemplateResponse(
        request, "pages/dashboard.html", {"devices": devices}
    )
