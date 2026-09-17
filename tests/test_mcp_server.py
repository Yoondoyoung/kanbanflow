import httpx
import pytest
from mcp.client import Client

from app import mcp_server
from app.mcp_server import MCPSettings, api_request, mcp


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


def test_mcp_settings_defaults_and_server_are_importable(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    settings = MCPSettings()

    assert settings.base_url == "http://localhost:8000"
    assert settings.timeout == 10
    assert mcp is not None


@pytest.mark.anyio
async def test_sprint_tools_expose_typed_input_schemas():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {"list_sprints", "create_sprint", "start_sprint", "close_sprint"}
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
