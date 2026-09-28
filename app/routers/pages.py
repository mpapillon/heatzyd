import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.deps import AppContextDep
from app.domain.capabilities import capabilities_for
from app.templating import templates
from app.viewmodels import DeviceVM

logger = logging.getLogger(__name__)


router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request, ctx: AppContextDep):
    devices = [
        DeviceVM.from_state(device, capabilities_for(device.product_key))
        for device in ctx.service.devices
    ]
    return templates.TemplateResponse(
        request, "pages/dashboard.html", {"devices": devices}
    )


@router.get("/devices/{did}", response_class=HTMLResponse)
def device_page(request: Request, ctx: AppContextDep, did: str):
    device = ctx.service.get_device(did)
    if not device:
        return templates.TemplateResponse(
            request, "pages/device-not-found.html", {}, status_code=404
        )
    device_vm = DeviceVM.from_state(device, capabilities_for(device.product_key))
    return templates.TemplateResponse(
        request, "pages/device_detail.html", {"device": device_vm}
    )
