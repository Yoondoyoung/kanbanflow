import httpx
from mcp.server import MCPServer
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    api_token: str
    base_url: str = "http://localhost:8000"
    timeout: float = 10

    model_config = SettingsConfigDict(env_prefix="KANBANFLOW_", extra="ignore")


mcp = MCPServer("Kanban Flow")


def _error_detail(response: httpx.Response, token: str) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.reason_phrase or "Request failed"
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, str) or not detail.strip():
        return response.reason_phrase or "Request failed"
    return detail.strip().replace(token, "[redacted]")


async def api_request(method: str, path: str, json=None, *, transport=None):
    settings = MCPSettings()
    async with httpx.AsyncClient(
        base_url=f"{settings.base_url.rstrip('/')}/",
        headers={"Authorization": f"Bearer {settings.api_token}"},
        timeout=settings.timeout,
        transport=transport,
    ) as client:
        response = await client.request(method, path.lstrip("/"), json=json)
    if not response.is_success:
        raise ValueError(
            f"Kanban Flow API {response.status_code}: {_error_detail(response, settings.api_token)}"
        )
    return response.json() if response.content else None
