from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import SESSION_COOKIE
from app.config import settings
from app.rendering import render_markdown
from app.routers import (
    api_auth,
    api_projects,
    api_sprints,
    api_tickets,
    api_tokens,
    github_webhook,
    web,
    web_sprints,
)
from app.security import enforce_auth_rate_limit

app = FastAPI(title="Kanban Flow")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(api_auth.router)
app.include_router(api_tokens.router)
app.include_router(api_projects.router)
app.include_router(api_sprints.router)
app.include_router(api_tickets.router)
app.include_router(github_webhook.router)

UNSAFE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
AUTH_ACTIONS = {
    "/login": "login",
    "/register": "register",
    "/api/v1/auth/login": "login",
    "/api/v1/auth/register": "register",
}


def _set_security_headers(response: Response) -> Response:
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    return _set_security_headers(await call_next(request))


@app.middleware("http")
async def limit_auth_requests(request: Request, call_next):
    action = AUTH_ACTIONS.get(request.url.path)
    if request.method == "POST" and action:
        try:
            enforce_auth_rate_limit(request, action)
        except HTTPException as exc:
            return _set_security_headers(
                JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
                )
            )
    return await call_next(request)


@app.middleware("http")
async def block_foreign_origin_cookie_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method in UNSAFE_METHODS
        and request.url.path.startswith("/api/v1/")
        and SESSION_COOKIE in request.cookies
        and "authorization" not in request.headers
        and origin
        and origin not in settings.allowed_origins
    ):
        return _set_security_headers(
            JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
        )
    return await call_next(request)


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["markdown"] = render_markdown

app.include_router(web.router)
app.include_router(web_sprints.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
