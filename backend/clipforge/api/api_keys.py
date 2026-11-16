"""API key endpoints (SPEC-v2 3.14): the owner makes, lists and revokes the
keys of the public REST API /api/v1.

    GET    /api-keys        -> [ApiKey]
    POST   /api-keys        ApiKeyCreate -> ApiKeyCreated (201; the key, once)
    DELETE /api-keys/{id}   -> 204 (revoked)
    GET    /agent-setup     -> AgentSetup (what the MCP config snippets need)

Human only: a call with an API key or from an agent gets 403 human_only,
so an agent cannot make itself keys.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Engine

from clipforge import api_keys
from clipforge.api.deps import get_engine, require_human
from clipforge.api.errors import not_found
from clipforge.models import AgentSetup, ApiKey, ApiKeyCreate, ApiKeyCreated

router = APIRouter(dependencies=[Depends(require_human)])

EngineDep = Annotated[Engine, Depends(get_engine)]

# The checkout whose pyproject.toml has the clipforge-mcp script.
PROJECT_DIR = Path(__file__).resolve().parents[3]
MCP_COMMAND = "uv"
MCP_SCRIPT = "clipforge-mcp"


@router.get("/api-keys")
def list_api_keys(engine: EngineDep) -> list[ApiKey]:
    """Return every API key, oldest first (never the key itself)."""
    return api_keys.list_keys(engine)


@router.post("/api-keys", status_code=201)
def create_api_key(body: ApiKeyCreate, engine: EngineDep) -> ApiKeyCreated:
    """Make a new API key; the answer is the only time the key is shown."""
    return api_keys.create_key(engine, body.name)


@router.delete("/api-keys/{key_id}", status_code=204)
def delete_api_key(key_id: int, engine: EngineDep) -> Response:
    """Revoke an API key: requests with it get 401 from now on."""
    try:
        api_keys.delete_key(engine, key_id)
    except api_keys.ApiKeyNotFound as exc:
        raise not_found("API key", key_id) from exc
    return Response(status_code=204)


@router.get("/agent-setup")
def agent_setup(request: Request) -> AgentSetup:
    """Return how an AI agent reaches this app: its address as the caller
    sees it, and the command that starts the MCP server of this checkout."""
    api_url = str(request.base_url).rstrip("/")
    return AgentSetup(
        api_url=api_url,
        project_dir=str(PROJECT_DIR),
        mcp_command=MCP_COMMAND,
        mcp_args=["run", "--project", str(PROJECT_DIR), MCP_SCRIPT],
        docs_url=f"{api_url}/api/docs",
    )
