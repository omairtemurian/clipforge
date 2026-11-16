"""The automation loop of an AI agent through the public API /api/v1 with
an API key (owner's request of 2026-10-31): create a project from a URL and
poll its job, list and score clips, edit a clip's text and trim, render,
write post copy, draft a scheduled post and read its status. Queueing and
publishing stay the owner's (403 human_only). Every answer is checked
against the OpenAPI document."""

import json
from pathlib import Path
from typing import Any

from api_key_fakes import make_key
from apihelpers import assert_error
from clipforge.api.app import create_app
from fakes import FIXTURES, FakeLLMClient
from fastapi.testclient import TestClient
from loop_fakes import finish_render, processed_clip
from openapi_check import load_document, public_operations, schema_errors
from post_api_fakes import LATER, accounts
from sqlalchemy import Engine

DOCUMENT = load_document()
OPERATIONS = {operation.label: operation for operation in public_operations(DOCUMENT)}
REPLY = json.loads((FIXTURES / "post_copy" / "replies.json").read_text())["first"]
URL = "https://www.youtube.com/watch?v=abc"


class Agent:
    """Sends requests with an API key and checks each answer against the
    documented status and schema of its operation."""

    def __init__(self, client: TestClient, key: str) -> None:
        self.client = client
        self.headers = {"Authorization": f"Bearer {key}"}

    def send(self, method: str, path: str, url: str, status: int, **kw: Any) -> Any:
        """Send method url (of operation path); check status and schema."""
        response = self.client.request(method, url, headers=self.headers, **kw)
        assert response.status_code == status, response.text
        operation = OPERATIONS[f"{method} /api/v1{path}"]
        schema = operation.response_schema(status)
        if schema is None:
            return None
        body = response.json()
        assert schema_errors(body, schema, DOCUMENT) == []
        return body


def test_an_agent_runs_the_loop_up_to_a_scheduled_draft(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient(json.dumps(REPLY))
    app = create_app(run_worker=False, caption_previews=False, llm=llm)
    with TestClient(app) as client:
        engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
        agent = Agent(client, make_key(client))

        project = agent.send(
            "POST", "/projects", "/api/v1/projects", 201, json={"url": URL}
        )
        pid = project["id"]
        (job,) = agent.send(
            "GET",
            "/projects/{project_id}/jobs",
            f"/api/v1/projects/{pid}/jobs",
            200,
        )
        polled = agent.send("GET", "/jobs/{job_id}", f"/api/v1/jobs/{job['id']}", 200)
        assert (polled["kind"], polled["status"]) == ("process", "queued")

        project_id, clip_id = processed_clip(engine, sample_mp4)
        clips = agent.send(
            "GET",
            "/projects/{project_id}/clips",
            f"/api/v1/projects/{project_id}/clips",
            200,
        )
        assert [(c["id"], c["scores"]["overall"]) for c in clips] == [(clip_id, 82)]
        clip_url = f"/api/v1/clips/{clip_id}"
        edited = agent.send(
            "PATCH",
            "/clips/{clip_id}",
            clip_url,
            200,
            json={"title": "Best pizza", "start": 10.5},
        )
        assert (edited["title"], edited["start"]) == ("Best pizza", 10.5)
        agent.send("GET", "/clips/{clip_id}/transcript", f"{clip_url}/transcript", 200)
        render = agent.send(
            "POST", "/clips/{clip_id}/render", f"{clip_url}/render", 202
        )
        assert (render["kind"], render["status"]) == ("render", "queued")
        finish_render(engine, project_id, clip_id)

        copy = agent.send(
            "POST",
            "/clips/{clip_id}/post-copy",
            f"{clip_url}/post-copy",
            200,
            json={"platform": "tiktok"},
        )
        (account_id,) = accounts(engine, "tiktok")
        listed = agent.send("GET", "/accounts", "/api/v1/accounts", 200)
        assert [a["id"] for a in listed] == [account_id]
        target = {"account_id": account_id, "text": {"caption": copy["caption"]}}
        (draft,) = agent.send(
            "POST",
            "/clips/{clip_id}/posts",
            f"{clip_url}/posts",
            201,
            json={"targets": [target], "scheduled_at": LATER},
        )
        assert (draft["status"], draft["scheduled_at"]) == ("draft", LATER)

        post_url = f"/api/v1/posts/{draft['id']}"
        queue = client.post(f"{post_url}/queue", json={}, headers=agent.headers)
        publish = client.post(f"{post_url}/publish", headers=agent.headers)
        statuses = agent.send("GET", "/posts", f"/api/v1/posts?clip_id={clip_id}", 200)
    assert_error(queue, 403, "human_only")
    assert_error(publish, 403, "human_only")
    assert [(p["id"], p["status"]) for p in statuses] == [(draft["id"], "draft")]
