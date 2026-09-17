from datetime import date
from urllib.parse import unquote, urlsplit

import httpx
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    api_token: str
    base_url: str = "http://localhost:8000"
    timeout: float = 10

    model_config = SettingsConfigDict(env_prefix="KANBANFLOW_", extra="ignore")


mcp = MCPServer("Kanban Flow")


def _api_path(path: str) -> str:
    try:
        parsed = urlsplit(path)
    except ValueError:
        raise ValueError("Kanban Flow API request path must be a relative /api/v1/ path") from None
    decoded_path = parsed.path
    for _ in range(4):
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or "\\" in decoded_path
            or "//" in decoded_path
            or not decoded_path.startswith("/api/v1/")
            or any(part in {".", ".."} for part in decoded_path.split("/"))
        ):
            raise ValueError("Kanban Flow API request path must be a relative /api/v1/ path")
        next_path = unquote(decoded_path)
        if next_path == decoded_path:
            return path.lstrip("/")
        decoded_path = next_path
    raise ValueError("Kanban Flow API request path must be a relative /api/v1/ path")


def _status_detail(status: int) -> str:
    return {
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        422: "Validation failed",
    }.get(status, "Request failed")


async def api_request(method: str, path: str, json=None, *, transport=None):
    path = _api_path(path)
    settings = MCPSettings()
    async with httpx.AsyncClient(
        base_url=f"{settings.base_url.rstrip('/')}/",
        headers={"Authorization": f"Bearer {settings.api_token}"},
        timeout=settings.timeout,
        transport=transport,
    ) as client:
        response = await client.request(method, path, json=json)
    if not response.is_success:
        raise ValueError(
            f"Kanban Flow API {response.status_code}: {_status_detail(response.status_code)}"
        )
    return response.json() if response.content else None


async def _tool_request(method: str, path: str, json=None):
    try:
        return await api_request(method, path, json)
    except ValueError as error:
        return CallToolResult(
            content=[TextContent(type="text", text=str(error))],
            isError=True,
        )


@mcp.tool()
async def list_sprints(slug: str) -> list[dict[str, object]]:
    """List a project's sprints; sprint changes are owner-only."""
    sprints = await _tool_request("GET", f"/api/v1/projects/{slug}/sprints")
    if isinstance(sprints, CallToolResult):
        return sprints
    fields = (
        "id",
        "name",
        "status",
        "start_date",
        "end_date",
        "goal",
        "committed_points",
        "completed_points",
    )
    return [{field: sprint[field] for field in fields} for sprint in sprints]


@mcp.tool()
async def create_sprint(
    slug: str, name: str, goal: str, start_date: date, end_date: date
) -> dict[str, object]:
    """Create a planning sprint. Owner-only."""
    return await _tool_request(
        "POST",
        f"/api/v1/projects/{slug}/sprints",
        {
            "name": name,
            "goal": goal,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )


@mcp.tool()
async def start_sprint(sprint_id: str) -> dict[str, object]:
    """Start a planning sprint. Owner-only."""
    return await _tool_request("PATCH", f"/api/v1/sprints/{sprint_id}", {"status": "ACTIVE"})


@mcp.tool()
async def close_sprint(sprint_id: str, next_sprint_id: str) -> dict[str, object]:
    """Close an active sprint and roll work over. Owner-only."""
    return await _tool_request(
        "POST", f"/api/v1/sprints/{sprint_id}/close", {"next_sprint_id": next_sprint_id}
    )
