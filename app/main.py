from fastapi import FastAPI

from app.routers import api_auth

app = FastAPI(title="Kanban Flow")
app.include_router(api_auth.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
