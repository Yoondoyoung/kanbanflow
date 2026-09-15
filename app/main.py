from fastapi import FastAPI

app = FastAPI(title="Kanban Flow")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
