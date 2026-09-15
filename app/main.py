from fastapi import FastAPI

from app.routers import api_auth, api_projects

app = FastAPI(title="Kanban Flow")
app.include_router(api_auth.router)
app.include_router(api_projects.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
