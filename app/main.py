from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import SESSION_COOKIE
from app.config import settings
from app.rendering import render_markdown
from app.routers import api_auth, api_projects, api_sprints, api_tickets, web, web_sprints

app = FastAPI(title="Kanban Flow")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(api_auth.router)
app.include_router(api_projects.router)
app.include_router(api_sprints.router)
app.include_router(api_tickets.router)

UNSAFE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


@app.middleware("http")
async def block_foreign_origin_cookie_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method in UNSAFE_METHODS
        and request.url.path.startswith("/api/v1/")
        and SESSION_COOKIE in request.cookies
        and origin
        and origin not in settings.allowed_origins
    ):
        return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
    return await call_next(request)


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["markdown"] = render_markdown

app.include_router(web.router)
app.include_router(web_sprints.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
