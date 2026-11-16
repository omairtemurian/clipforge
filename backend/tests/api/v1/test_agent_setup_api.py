"""Tests of GET /api/agent-setup: what the Settings page needs to write MCP
config snippets (this app's address, the checkout with clipforge-mcp), for
the owner only."""

import tomllib
from pathlib import Path

from apihelpers import assert_error
from fastapi.testclient import TestClient


def test_the_setup_points_at_this_app_and_its_mcp_server(
    client: TestClient,
) -> None:
    response = client.get("/api/agent-setup")

    assert response.status_code == 200
    setup = response.json()
    assert setup["api_url"] == "http://testserver"
    assert setup["docs_url"] == "http://testserver/api/docs"
    project_dir = Path(setup["project_dir"])
    assert setup["mcp_command"] == "uv"
    assert setup["mcp_args"] == ["run", "--project", str(project_dir), "clipforge-mcp"]
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text())
    assert "clipforge-mcp" in pyproject["project"]["scripts"]


def test_the_docs_link_answers(client: TestClient) -> None:
    docs_path = client.get("/api/agent-setup").json()["docs_url"]

    assert client.get(docs_path.removeprefix("http://testserver")).status_code == 200


def test_an_agent_cannot_read_the_setup(
    client: TestClient, agent: dict[str, str]
) -> None:
    assert_error(client.get("/api/agent-setup", headers=agent), 403, "human_only")
    assert_error(client.get("/api/v1/agent-setup", headers=agent), 404, "not_found")
