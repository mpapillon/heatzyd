from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.deps import AppContext

_EXEMPT_PREFIXES = ("/login", "/logout", "/static", "/events")


class IsConnectedMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        ctx: AppContext = request.app.state.ctx
        path = request.url.path
        if not ctx.service.is_connected and not path.startswith(_EXEMPT_PREFIXES):
            if request.headers.get("hx-request") == "true":
                return Response(status_code=200, headers={"HX-Redirect": "/login"})
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)
