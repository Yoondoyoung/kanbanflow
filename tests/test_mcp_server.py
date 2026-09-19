import subprocess
from datetime import date

import httpx
import pytest
from mcp.client import Client

from app import mcp_server
from app.mcp_server import MCPSettings, api_request, mcp


def test_mcp_server_loads_from_documented_cli_command():
    result = subprocess.run(
        ["mcp", "run", "app/mcp_server.py:mcp", "--transport", "stdio"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.anyio
async def test_api_request_joins_base_url_and_sends_bearer_token(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_BASE_URL", "https://kanban.example/base/")
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")
    seen = {}

    async def handler(request):
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={"items": []})

    result = await api_request(
        "GET",
        "/api/v1/projects/demo/sprints",
        transport=httpx.MockTransport(handler),
    )

    assert seen == {
        "url": "https://kanban.example/base/api/v1/projects/demo/sprints",
        "authorization": "Bearer test-token",
    }
    assert result == {"items": []}


@pytest.mark.anyio
async def test_api_request_uses_ten_second_timeout(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    async def handler(request):
        assert request.extensions["timeout"] == {
            "connect": 10.0,
            "read": 10.0,
            "write": 10.0,
            "pool": 10.0,
        }
        return httpx.Response(204)

    assert (
        await api_request(
            "DELETE", "/api/v1/tokens/token-1", transport=httpx.MockTransport(handler)
        )
        is None
    )


@pytest.mark.anyio
async def test_api_request_raises_concise_api_error_without_token(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    async def handler(request):
        return httpx.Response(
            403,
            headers={"X-Upstream-Error": "Bearer test-token"},
            json={"detail": f"Bearer test-token {'x' * 8192}"},
        )

    with pytest.raises(ValueError, match="Kanban Flow API 403: Forbidden") as error:
        await api_request(
            "POST", "/api/v1/projects/demo/sprints", transport=httpx.MockTransport(handler)
        )

    assert "test-token" not in str(error.value)
    assert len(str(error.value)) < 100


@pytest.mark.anyio
async def test_api_request_handles_non_json_api_errors(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    async def handler(request):
        return httpx.Response(502, content=b"upstream response was not JSON")

    with pytest.raises(ValueError, match="Kanban Flow API 502: Request failed"):
        await api_request("GET", "/api/v1/projects", transport=httpx.MockTransport(handler))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "https://attacker.example/api/v1/projects",
        "//attacker.example/api/v1/projects",
        "https://token@attacker.example/api/v1/projects",
        "/api/v1/../tokens",
        "/api/v1\\projects",
        "/api/v1/%252e%252e/tokens",
        "/api/v1/%25252e%25252e/tokens",
        "/api/v1/%255cprojects",
        "/api/v1/%25255cprojects",
        "/projects",
    ],
)
async def test_api_request_rejects_unsafe_paths_before_sending_token(monkeypatch, path):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(
        ValueError, match="Kanban Flow API request path must be a relative /api/v1/ path"
    ) as error:
        await api_request("GET", path, transport=httpx.MockTransport(handler))

    assert seen == []
    assert "test-token" not in str(error.value)


@pytest.mark.anyio
async def test_api_request_preserves_harmless_query_values(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")
    seen = {}

    async def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"items": []})

    result = await api_request(
        "GET",
        "/api/v1/projects?next=https://example.test/%5C&filter=a%2Fb",
        transport=httpx.MockTransport(handler),
    )

    assert (
        seen["url"]
        == "http://localhost:8000/api/v1/projects?next=https://example.test/%5C&filter=a%2Fb"
    )
    assert result == {"items": []}


@pytest.mark.anyio
async def test_encoded_segments_stay_on_api_host_and_reject_backslashes(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_BASE_URL", "https://kanban.example/base/")
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    result = await api_request(
        "GET",
        f"/api/v1/projects/{mcp_server._path_segment('café')}/sprints",
        transport=httpx.MockTransport(handler),
    )

    assert result == {"items": []}
    assert str(seen[0].url) == "https://kanban.example/base/api/v1/projects/caf%C3%A9/sprints"
    assert seen[0].headers["authorization"] == "Bearer test-token"

    backslash = "\\"
    seen.clear()
    with pytest.raises(
        ValueError, match="Kanban Flow API request path must be a relative /api/v1/ path"
    ):
        await api_request(
            "GET",
            f"/api/v1/projects/{mcp_server._path_segment(backslash)}/sprints",
            transport=httpx.MockTransport(handler),
        )

    assert seen == []


def test_mcp_settings_defaults_and_server_are_importable(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    settings = MCPSettings()

    assert settings.base_url == "http://localhost:8000"
    assert settings.timeout == 10
    assert mcp is not None


@pytest.mark.anyio
async def test_create_project_delegates_to_the_api(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        return {"id": "project-1", "name": "MCP Check", "slug": "mcp-check"}

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        result = await client.call_tool("create_project", {"name": "MCP Check"})

    assert calls == [("POST", "/api/v1/projects", {"name": "MCP Check"})]
    assert result.structured_content["slug"] == "mcp-check"


@pytest.mark.anyio
async def test_project_tools_delegate_to_the_api(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        return {"slug": "mcp-check"}

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        for name, arguments in (
            ("list_projects", {}),
            ("get_project", {"slug": "mcp-check"}),
            ("update_project", {"slug": "mcp-check", "name": "Renamed"}),
            (
                "delete_project",
                {"slug": "mcp-check", "confirm_slug": "mcp-check"},
            ),
        ):
            assert name in tools
            await client.call_tool(name, arguments)

    assert calls == [
        ("GET", "/api/v1/projects", None),
        ("GET", "/api/v1/projects/mcp-check", None),
        ("PATCH", "/api/v1/projects/mcp-check", {"name": "Renamed"}),
        ("DELETE", "/api/v1/projects/mcp-check?confirm=mcp-check", None),
    ]


@pytest.mark.anyio
async def test_ticket_tools_delegate_to_the_api(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        return {} if method != "DELETE" else None

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        await mcp_server.create_ticket(
            "mcp-check",
            "MCP ticket",
            due_date=date(2026, 9, 30),
        )
        await client.call_tool(
            "list_tickets", {"slug": "mcp-check", "status": "BACKLOG", "limit": 10}
        )
        await client.call_tool("get_ticket", {"ticket_id": "ticket-1"})
        await client.call_tool(
            "update_ticket", {"ticket_id": "ticket-1", "changes": {"title": "Renamed"}}
        )
        await client.call_tool(
            "update_ticket_status",
            {"ticket_id": "ticket-1", "status": "IN_PROGRESS"},
        )
        await client.call_tool("delete_ticket", {"ticket_id": "ticket-1"})

    assert calls == [
        (
            "POST",
            "/api/v1/tickets",
            {
                "slug": "mcp-check",
                "title": "MCP ticket",
                "description": "",
                "type": "TASK",
                "priority": "MEDIUM",
                "story_points": None,
                "sprint_id": None,
                "assignee_id": None,
                "due_date": "2026-09-30",
            },
        ),
        ("GET", "/api/v1/projects/mcp-check/tickets?status=BACKLOG&limit=10", None),
        ("GET", "/api/v1/tickets/ticket-1", None),
        ("PATCH", "/api/v1/tickets/ticket-1", {"title": "Renamed"}),
        (
            "PATCH",
            "/api/v1/tickets/ticket-1/status",
            {"status": "IN_PROGRESS", "resolution_notes": None},
        ),
        ("DELETE", "/api/v1/tickets/ticket-1", None),
    ]


@pytest.mark.anyio
async def test_membership_tools_delegate_to_the_api(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        return {} if method != "DELETE" else None

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        await client.call_tool("list_project_members", {"slug": "mcp-check"})
        await client.call_tool(
            "add_project_member",
            {"slug": "mcp-check", "email": "member@example.com"},
        )
        await client.call_tool(
            "update_project_member",
            {"slug": "mcp-check", "user_id": "user-1", "role": "OWNER"},
        )
        await client.call_tool("remove_project_member", {"slug": "mcp-check", "user_id": "user-1"})

    assert calls == [
        ("GET", "/api/v1/projects/mcp-check/members", None),
        (
            "POST",
            "/api/v1/projects/mcp-check/members",
            {"email": "member@example.com", "role": "MEMBER"},
        ),
        (
            "PATCH",
            "/api/v1/projects/mcp-check/members/user-1",
            {"role": "OWNER"},
        ),
        ("DELETE", "/api/v1/projects/mcp-check/members/user-1", None),
    ]


@pytest.mark.anyio
async def test_sprint_tools_expose_typed_input_schemas():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {
        "create_project",
        "list_projects",
        "get_project",
        "update_project",
        "delete_project",
        "list_sprints",
        "create_sprint",
        "start_sprint",
        "close_sprint",
        "get_sprint",
        "update_sprint",
        "get_sprint_history",
        "create_ticket",
        "list_tickets",
        "get_ticket",
        "update_ticket",
        "update_ticket_status",
        "delete_ticket",
        "list_project_members",
        "add_project_member",
        "update_project_member",
        "remove_project_member",
    }
    assert all(tool.description for tool in tools.values())
    assert tools["create_project"].input_schema["required"] == ["name"]
    assert tools["list_sprints"].input_schema["required"] == ["slug"]
    assert tools["create_sprint"].input_schema["required"] == [
        "slug",
        "name",
        "goal",
        "start_date",
        "end_date",
    ]
    assert tools["create_sprint"].input_schema["properties"]["start_date"]["format"] == "date"
    assert tools["create_sprint"].input_schema["properties"]["end_date"]["format"] == "date"
    assert tools["start_sprint"].input_schema["required"] == ["sprint_id"]
    assert tools["close_sprint"].input_schema["required"] == ["sprint_id", "next_sprint_id"]
    assert tools["get_sprint"].input_schema["required"] == ["sprint_id"]
    assert tools["update_sprint"].input_schema["required"] == ["sprint_id"]
    assert tools["get_sprint_history"].input_schema["required"] == ["sprint_id"]
    assert tools["create_ticket"].input_schema["required"] == ["slug", "title"]
    assert (
        tools["create_ticket"].input_schema["properties"]["due_date"]["anyOf"][0]["format"]
        == "date"
    )
    assert tools["list_tickets"].input_schema["required"] == ["slug"]
    assert tools["get_ticket"].input_schema["required"] == ["ticket_id"]
    assert tools["update_ticket"].input_schema["required"] == ["ticket_id", "changes"]
    assert tools["update_ticket_status"].input_schema["required"] == ["ticket_id", "status"]
    assert tools["delete_ticket"].input_schema["required"] == ["ticket_id"]
    assert tools["list_project_members"].input_schema["required"] == ["slug"]
    assert tools["add_project_member"].input_schema["required"] == ["slug", "email"]
    assert tools["update_project_member"].input_schema["required"] == [
        "slug",
        "user_id",
        "role",
    ]
    assert tools["remove_project_member"].input_schema["required"] == ["slug", "user_id"]


@pytest.mark.anyio
async def test_sprint_tools_delegate_to_the_api_and_limit_list_fields(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        if method == "GET":
            return [
                {
                    "id": "sprint-1",
                    "project_id": "project-1",
                    "name": "Sprint 1",
                    "goal": "Ship reports",
                    "status": "PLANNING",
                    "start_date": "2026-09-28",
                    "end_date": "2026-10-05",
                    "committed_points": 8,
                    "completed_points": None,
                    "closed_at": None,
                }
            ]
        return {"id": "sprint-1", "status": "PLANNING"}

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        listed = await client.call_tool("list_sprints", {"slug": "demo"})
        await client.call_tool(
            "create_sprint",
            {
                "slug": "demo",
                "name": "Sprint 2",
                "goal": "Ship reports",
                "start_date": "2026-09-28",
                "end_date": "2026-10-05",
            },
        )
        await client.call_tool("start_sprint", {"sprint_id": "sprint-1"})
        await client.call_tool(
            "close_sprint", {"sprint_id": "sprint-1", "next_sprint_id": "sprint-2"}
        )

    assert calls == [
        ("GET", "/api/v1/projects/demo/sprints", None),
        (
            "POST",
            "/api/v1/projects/demo/sprints",
            {
                "name": "Sprint 2",
                "goal": "Ship reports",
                "start_date": "2026-09-28",
                "end_date": "2026-10-05",
            },
        ),
        ("PATCH", "/api/v1/sprints/sprint-1", {"status": "ACTIVE"}),
        ("POST", "/api/v1/sprints/sprint-1/close", {"next_sprint_id": "sprint-2"}),
    ]
    assert listed.is_error is False
    assert listed.structured_content == {
        "result": [
            {
                "id": "sprint-1",
                "name": "Sprint 1",
                "status": "PLANNING",
                "start_date": "2026-09-28",
                "end_date": "2026-10-05",
                "goal": "Ship reports",
                "committed_points": 8,
                "completed_points": None,
            }
        ]
    }


@pytest.mark.anyio
async def test_remaining_sprint_tools_delegate_to_the_api(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        return {}

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        await client.call_tool("get_sprint", {"sprint_id": "sprint-1"})
        await client.call_tool(
            "update_sprint",
            {
                "sprint_id": "sprint-1",
                "name": "Sprint 2",
                "start_date": "2026-10-06",
                "end_date": "2026-10-13",
            },
        )
        await client.call_tool("get_sprint_history", {"sprint_id": "sprint-1"})

    assert calls == [
        ("GET", "/api/v1/sprints/sprint-1", None),
        (
            "PATCH",
            "/api/v1/sprints/sprint-1",
            {
                "name": "Sprint 2",
                "start_date": "2026-10-06",
                "end_date": "2026-10-13",
            },
        ),
        ("GET", "/api/v1/sprints/sprint-1/history", None),
    ]


@pytest.mark.anyio
async def test_create_sprint_rejects_non_iso_dates_without_api_call(monkeypatch):
    calls = []

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "create_sprint",
            {
                "slug": "demo",
                "name": "Sprint 2",
                "goal": "Ship reports",
                "start_date": "not-a-date",
                "end_date": "2026-10-05",
            },
        )

    assert result.is_error is True
    assert calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "message"), [(403, "Forbidden"), (409, "Conflict"), (422, "Validation failed")]
)
async def test_sprint_tool_propagates_safe_api_errors(monkeypatch, status, message):
    async def fake_request(method, path, json=None):
        raise ValueError(f"Kanban Flow API {status}: {message}")

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        result = await client.call_tool("start_sprint", {"sprint_id": "sprint-1"})

    assert result.is_error is True
    assert result.content[0].text == f"Kanban Flow API {status}: {message}"
    assert "test-token" not in result.content[0].text


@pytest.mark.anyio
async def test_sprint_tools_quote_user_supplied_path_segments(monkeypatch):
    calls = []
    slug = "demo?next=/api/v1/tokens#\\%"
    sprint_id = "sprint?next=/api/v1/tokens#\\%"
    next_sprint_id = "next?kept/raw#in%body\\"

    async def fake_request(method, path, json=None):
        calls.append((method, path, json))
        return [] if method == "GET" else {"id": "sprint-1"}

    monkeypatch.setattr(mcp_server, "api_request", fake_request)

    async with Client(mcp) as client:
        await client.call_tool("list_sprints", {"slug": slug})
        await client.call_tool(
            "create_sprint",
            {
                "slug": slug,
                "name": "Sprint 2",
                "goal": "Ship reports",
                "start_date": "2026-09-28",
                "end_date": "2026-10-05",
            },
        )
        await client.call_tool("start_sprint", {"sprint_id": sprint_id})
        await client.call_tool(
            "close_sprint", {"sprint_id": sprint_id, "next_sprint_id": next_sprint_id}
        )

    assert calls == [
        ("GET", "/api/v1/projects/demo%3Fnext%3D%2Fapi%2Fv1%2Ftokens%23%5C%25/sprints", None),
        (
            "POST",
            "/api/v1/projects/demo%3Fnext%3D%2Fapi%2Fv1%2Ftokens%23%5C%25/sprints",
            {
                "name": "Sprint 2",
                "goal": "Ship reports",
                "start_date": "2026-09-28",
                "end_date": "2026-10-05",
            },
        ),
        (
            "PATCH",
            "/api/v1/sprints/sprint%3Fnext%3D%2Fapi%2Fv1%2Ftokens%23%5C%25",
            {"status": "ACTIVE"},
        ),
        (
            "POST",
            "/api/v1/sprints/sprint%3Fnext%3D%2Fapi%2Fv1%2Ftokens%23%5C%25/close",
            {"next_sprint_id": next_sprint_id},
        ),
    ]
