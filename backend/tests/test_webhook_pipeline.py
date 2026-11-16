"""A real process job (the fixture video) and a real render job raise
clip.rendered and project.completed, and the webhook worker delivers them
signed (respx: the endpoint is made up)."""

import json
from pathlib import Path

import pytest
import respx
from clipforge import jobs
from clipforge.models import ProcessingSettings
from fake_clock import FakeWallClock
from fakes import FIXTURES, FakeLLMClient
from sqlalchemy import Engine
from webhook_fakes import (
    START,
    delivery_log,
    endpoint,
    expected_signature,
    make_worker,
    register,
)


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg", "face_cfg")
def test_a_processed_video_delivers_its_clips_then_the_project(
    engine: Engine,
    data_dir: Path,
    sample_mp4: Path,
    respx_mock: respx.MockRouter,
) -> None:
    hook = register(engine, ["project.completed", "clip.rendered"])
    route = endpoint(respx_mock, 200)
    jobs.enqueue_process(engine, str(sample_mp4), ProcessingSettings(num_clips=1))

    assert jobs.run_next(
        engine, llm=FakeLLMClient(), transcript=FIXTURES / "transcript.json"
    )

    clock = FakeWallClock(START)
    assert len(make_worker(engine, clock).poll()) == 2
    sent = [call.request for call in route.calls]
    bodies = [json.loads(request.content) for request in sent]
    assert [body["event"] for body in bodies] == ["clip.rendered", "project.completed"]
    clip = bodies[0]["data"]["clip"]
    project = bodies[1]["data"]["project"]
    assert clip["project_id"] == project["id"]
    assert bodies[1]["data"]["clips"] == [{"id": clip["id"], "title": clip["title"]}]
    for request in sent:
        assert request.headers["X-ClipForge-Signature"] == expected_signature(
            hook.secret, request.headers["X-ClipForge-Timestamp"], request.content
        )
    assert {log.status for log in delivery_log(engine, hook.id)} == {"delivered"}
