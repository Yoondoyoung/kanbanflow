from datetime import date
from urllib.parse import quote, unquote, urlencode, urlsplit

import httpx
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from app.models import Priority, Role, TicketStatus, TicketType
except ModuleNotFoundError as error:
    if error.name != "app":
        raise
    from models import Priority, Role, TicketStatus, TicketType


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


def _path_segment(value: str) -> str:
    return quote(value, safe="")


def _with_query(path: str, **params: object) -> str:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return f"{path}?{query}" if query else path


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
async def create_project(name: str) -> dict[str, object]:
    """Create a project owned by the token's user."""
    return await _tool_request("POST", "/api/v1/projects", {"name": name})


@mcp.tool()
async def list_projects() -> list[dict[str, object]]:
    """List projects available to the token's user."""
    return await _tool_request("GET", "/api/v1/projects")


@mcp.tool()
async def get_project(slug: str) -> dict[str, object]:
    """Get a project available to the token's user."""
    return await _tool_request("GET", f"/api/v1/projects/{_path_segment(slug)}")


@mcp.tool()
async def update_project(slug: str, name: str) -> dict[str, object]:
    """Rename a project. Owner-only."""
    return await _tool_request("PATCH", f"/api/v1/projects/{_path_segment(slug)}", {"name": name})


@mcp.tool()
async def delete_project(slug: str, confirm_slug: str) -> None:
    """Delete a project and its contents. Owner-only; confirmation must match slug."""
    return await _tool_request(
        "DELETE",
        _with_query(f"/api/v1/projects/{_path_segment(slug)}", confirm=confirm_slug),
    )


@mcp.tool()
async def list_project_members(slug: str) -> list[dict[str, object]]:
    """List a project's members."""
    return await _tool_request("GET", f"/api/v1/projects/{_path_segment(slug)}/members")


@mcp.tool()
async def add_project_member(slug: str, email: str, role: Role = Role.MEMBER) -> dict[str, object]:
    """Add a member to a project. Owner-only."""
    return await _tool_request(
        "POST",
        f"/api/v1/projects/{_path_segment(slug)}/members",
        {"email": email, "role": role.value},
    )


@mcp.tool()
async def update_project_member(slug: str, user_id: str, role: Role) -> dict[str, object]:
    """Change a project member's role. Owner-only."""
    return await _tool_request(
        "PATCH",
        f"/api/v1/projects/{_path_segment(slug)}/members/{_path_segment(user_id)}",
        {"role": role.value},
    )


@mcp.tool()
async def remove_project_member(slug: str, user_id: str) -> None:
    """Remove a project member. Owner-only."""
    return await _tool_request(
        "DELETE",
        f"/api/v1/projects/{_path_segment(slug)}/members/{_path_segment(user_id)}",
    )


@mcp.tool()
async def create_ticket(
    slug: str,
    title: str,
    description: str = "",
    type: TicketType = TicketType.TASK,
    priority: Priority = Priority.MEDIUM,
    story_points: int | None = None,
    sprint_id: str | None = None,
    assignee_id: str | None = None,
    due_date: date | None = None,
) -> dict[str, object]:
    """Create a ticket in a project."""
    return await _tool_request(
        "POST",
        "/api/v1/tickets",
        {
            "slug": slug,
            "title": title,
            "description": description,
            "type": type.value,
            "priority": priority.value,
            "story_points": story_points,
            "sprint_id": sprint_id,
            "assignee_id": assignee_id,
            "due_date": due_date.isoformat() if due_date else None,
        },
    )


@mcp.tool()
async def list_tickets(
    slug: str,
    status: TicketStatus | None = None,
    type: TicketType | None = None,
    priority: Priority | None = None,
    sprint_id: str | None = None,
    assignee_id: str | None = None,
    cursor: int | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """List tickets in a project."""
    return await _tool_request(
        "GET",
        _with_query(
            f"/api/v1/projects/{_path_segment(slug)}/tickets",
            status=status.value if status else None,
            type=type.value if type else None,
            priority=priority.value if priority else None,
            sprint_id=sprint_id,
            assignee_id=assignee_id,
            cursor=cursor,
            limit=limit,
        ),
    )


@mcp.tool()
async def get_ticket(ticket_id: str) -> dict[str, object]:
    """Get a ticket available to the token's user."""
    return await _tool_request("GET", f"/api/v1/tickets/{_path_segment(ticket_id)}")


@mcp.tool()
async def update_ticket(ticket_id: str, changes: dict[str, object]) -> dict[str, object]:
    """Update title, description, type, priority, story_points, sprint_id, assignee_id, resolution_notes, or meta; explicit null clears story_points, sprint_id, assignee_id, or resolution_notes."""  # noqa: E501
    return await _tool_request("PATCH", f"/api/v1/tickets/{_path_segment(ticket_id)}", changes)


@mcp.tool()
async def update_ticket_status(
    ticket_id: str,
    status: TicketStatus,
    resolution_notes: str | None = None,
) -> dict[str, object]:
    """Change a ticket's status and optional resolution notes."""
    return await _tool_request(
        "PATCH",
        f"/api/v1/tickets/{_path_segment(ticket_id)}/status",
        {"status": status.value, "resolution_notes": resolution_notes},
    )


@mcp.tool()
async def delete_ticket(ticket_id: str) -> None:
    """Delete a ticket. Owner-only."""
    return await _tool_request("DELETE", f"/api/v1/tickets/{_path_segment(ticket_id)}")


@mcp.tool()
async def list_sprints(slug: str) -> list[dict[str, object]]:
    """List a project's sprints; sprint changes are owner-only."""
    sprints = await _tool_request("GET", f"/api/v1/projects/{_path_segment(slug)}/sprints")
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
        f"/api/v1/projects/{_path_segment(slug)}/sprints",
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
    return await _tool_request(
        "PATCH", f"/api/v1/sprints/{_path_segment(sprint_id)}", {"status": "ACTIVE"}
    )


@mcp.tool()
async def close_sprint(sprint_id: str, next_sprint_id: str) -> dict[str, object]:
    """Close an active sprint and roll work over. Owner-only."""
    return await _tool_request(
        "POST",
        f"/api/v1/sprints/{_path_segment(sprint_id)}/close",
        {"next_sprint_id": next_sprint_id},
    )


@mcp.tool()
async def get_sprint(sprint_id: str) -> dict[str, object]:
    """Get a sprint available to the token's user."""
    return await _tool_request("GET", f"/api/v1/sprints/{_path_segment(sprint_id)}")


@mcp.tool()
async def update_sprint(
    sprint_id: str,
    name: str | None = None,
    goal: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Update a planning sprint. Owner-only."""
    changes = {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in {
            "name": name,
            "goal": goal,
            "start_date": start_date,
            "end_date": end_date,
        }.items()
        if value is not None
    }
    return await _tool_request("PATCH", f"/api/v1/sprints/{_path_segment(sprint_id)}", changes)


@mcp.tool()
async def get_sprint_history(sprint_id: str) -> list[dict[str, object]]:
    """Get a closed sprint's ticket history."""
    return await _tool_request("GET", f"/api/v1/sprints/{_path_segment(sprint_id)}/history")
