import httpx
import pytest

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


def test_mcp_settings_defaults_and_server_are_importable(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    settings = MCPSettings()

    assert settings.base_url == "http://localhost:8000"
    assert settings.timeout == 10
    assert mcp is not None
