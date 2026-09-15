from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app.rendering import render_markdown
from app.routers import api_auth, api_projects, api_tickets, web

app = FastAPI(title="Kanban Flow")
app.include_router(api_auth.router)
app.include_router(api_projects.router)
app.include_router(api_tickets.router)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["markdown"] = render_markdown

app.include_router(web.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
