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
        return httpx.Response(403, json={"detail": "Bearer test-token cannot create sprints"})

    with pytest.raises(
        ValueError, match=r"Kanban Flow API 403: Bearer \[redacted\] cannot create sprints"
    ) as error:
        await api_request(
            "POST", "/api/v1/projects/demo/sprints", transport=httpx.MockTransport(handler)
        )

    assert "test-token" not in str(error.value)


@pytest.mark.anyio
async def test_api_request_handles_non_json_api_errors(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    async def handler(request):
        return httpx.Response(502, content=b"upstream response was not JSON")

    with pytest.raises(ValueError, match="Kanban Flow API 502: Bad Gateway"):
        await api_request("GET", "/api/v1/projects", transport=httpx.MockTransport(handler))


def test_mcp_settings_defaults_and_server_are_importable(monkeypatch):
    monkeypatch.setenv("KANBANFLOW_API_TOKEN", "test-token")

    settings = MCPSettings()

    assert settings.base_url == "http://localhost:8000"
    assert settings.timeout == 10
    assert mcp is not None
