import logging
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from app.deps import AppContextDep
from app.domain.capabilities import capabilities_for
from app.domain.derog import DerogMode
from app.domain.errors import DerogNotSupported, LockNotSupported, ModeNotSupported
from app.domain.modes import Mode
from app.heatzy.errors import (
    ControlFailed,
    DeviceNotFound,
    DeviceNotSupported,
    NotConnected,
)
from app.templating import templates
from app.viewmodels import DeviceVM

logger = logging.getLogger(__name__)


router = APIRouter(tags=["devices"])


@router.get("/devices/{did}/card", response_class=HTMLResponse)
async def device_card(
    request: Request,
    ctx: AppContextDep,
    did: str,
):
    device = ctx.service.get_device(did)
    if device is None:
        return Response(status_code=404)

    cap = capabilities_for(device.product_key)
    return templates.TemplateResponse(
        request,
        "partials/device_card.html",
        {"device": DeviceVM.from_state(device, cap)},
    )


@router.get("/devices/{did}/live", response_class=HTMLResponse)
async def device_live(
    request: Request,
    ctx: AppContextDep,
    did: str,
):
    device = ctx.service.get_device(did)
    if device is None:
        return Response(status_code=404)

    cap = capabilities_for(device.product_key)
    return templates.TemplateResponse(
        request,
        "partials/device_live.html",
        {"device": DeviceVM.from_state(device, cap)},
    )


@router.post("/devices/{did}/order")
async def device_order(
    ctx: AppContextDep,
    did: str,
    mode: Annotated[Mode, Form()],
):
    try:
        await ctx.service.send_order(did, mode)
    except NotConnected:
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    except DeviceNotFound:
        return Response(status_code=404)
    except DeviceNotSupported:
        return Response(status_code=409)
    except ModeNotSupported:
        return Response(status_code=400)
    except ControlFailed:
        return Response(status_code=502)

    return Response(status_code=204)


@router.put("/devices/{did}/lock")
async def device_lock(ctx: AppContextDep, did: str, lock: Annotated[bool, Form()]):
    try:
        await ctx.service.send_lock(did, lock)
    except NotConnected:
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    except DeviceNotFound:
        return Response(status_code=404)
    except DeviceNotSupported:
        return Response(status_code=409)
    except LockNotSupported:
        return Response(status_code=400)
    except ControlFailed:
        return Response(status_code=502)

    return Response(status_code=204)


@router.post("/devices/{did}/derog")
async def device_derog(
    ctx: AppContextDep,
    did: str,
    derog_mode: Annotated[DerogMode, Form()],
    derog_time: Annotated[int, Form(ge=1, le=255)],
):
    try:
        await ctx.service.send_derog(did, derog_mode, derog_time)
    except NotConnected:
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    except DeviceNotFound:
        return Response(status_code=404)
    except DeviceNotSupported:
        return Response(status_code=409)
    except DerogNotSupported, ValueError:
        return Response(status_code=400)
    except ControlFailed:
        return Response(status_code=502)

    return Response(status_code=204)


@router.delete("/devices/{did}/derog")
async def device_derog_delete(ctx: AppContextDep, did: str):
    try:
        await ctx.service.cancel_derog(did)
    except NotConnected:
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    except DeviceNotFound:
        return Response(status_code=404)
    except DeviceNotSupported:
        return Response(status_code=409)
    except DerogNotSupported, ValueError:
        return Response(status_code=400)
    except ControlFailed:
        return Response(status_code=502)

    return Response(status_code=204)


@router.patch("/devices/{did}/rename")
async def device_rename(ctx: AppContextDep, did: str, name: Annotated[str, Form()]):
    try:
        await ctx.service.rename(did, name)
    except NotConnected:
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    except DeviceNotFound:
        return Response(status_code=404)
    except DeviceNotSupported:
        return Response(status_code=409)
    except ControlFailed:
        return Response(status_code=502)

    return Response(status_code=204)
