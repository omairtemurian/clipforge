"""The Pro Edit critic's vision requests and capability check (SPEC-v3 3.7,
TASK-222): each provider's image request shape (recorded reply shapes in
tests/fakes.py), and whether the configured model accepts images, probed
once per model; a model without vision runs the Director only."""

import base64
import io
from pathlib import Path

import pytest
from clipforge.llm import CopilotClient, OllamaClient, OpenAICompatClient
from clipforge.llm_anthropic import AnthropicClient
from clipforge.llm_claude_code import ClaudeCodeClient
from clipforge.proedit.critic.capability import (
    DIRECTOR_ONLY,
    PROBE_RGB,
    check_vision,
    probe_image,
)
from clipforge.proedit.critic.vision import (
    VISION_HEADER,
    VisionUnsupported,
    complete_with_images,
)
from critic_fakes import SEES_RED, ReplyServer, jpeg
from fakes import anthropic_reply, ollama_reply, openai_reply, responses_reply
from PIL import Image as PILImage

COPILOT = "https://api.githubcopilot.com"
RED = jpeg((255, 0, 0), (4, 4))
BLUE = jpeg((0, 0, 255), (4, 4))


def openai_client(server: ReplyServer) -> OpenAICompatClient:
    return OpenAICompatClient(
        "https://llm.test/v1", "key", "vis-1", transport=server.transport
    )


def test_openai_compatible_requests_carry_text_then_data_url_images() -> None:
    server = ReplyServer(openai_reply('{"ok": 1}'))

    reply = complete_with_images(openai_client(server), "sys", "look", [RED, BLUE])

    assert reply == '{"ok": 1}'
    request = server.requests[0]
    assert str(request.url) == "https://llm.test/v1/chat/completions"
    assert VISION_HEADER not in request.headers
    assert server.body(0) == {
        "model": "vis-1",
        "messages": [
            {"role": "system", "content": "sys"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {"type": "image_url", "image_url": {"url": RED.data_url()}},
                    {"type": "image_url", "image_url": {"url": BLUE.data_url()}},
                ],
            },
        ],
        "response_format": {"type": "json_object"},
    }
    assert RED.data_url().startswith("data:image/jpeg;base64,/9j/")


def test_copilot_requests_set_the_vision_header() -> None:
    server = ReplyServer(openai_reply('{"ok": 1}'))
    client = CopilotClient("gpt-4.1", "tok", transport=server.transport)

    complete_with_images(client, "sys", "look", [RED])

    request = server.requests[0]
    assert str(request.url) == f"{COPILOT}/chat/completions"
    assert request.headers[VISION_HEADER] == "true"
    assert request.headers["Copilot-Integration-Id"] == "vscode-chat"
    assert server.body(0)["messages"][1]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": RED.data_url()},
    }


def test_copilot_responses_only_models_get_input_images() -> None:
    models = [{"id": "gpt-6-luna", "supported_endpoints": ["/responses"]}]
    server = ReplyServer(responses_reply('{"ok": 1}'), models=models)
    client = CopilotClient("gpt-6-luna", "tok", transport=server.transport)

    assert complete_with_images(client, "sys", "look", [RED]) == '{"ok": 1}'

    request = server.requests[0]
    assert str(request.url) == f"{COPILOT}/responses"
    assert request.headers[VISION_HEADER] == "true"
    assert server.body(0)["input"][1] == {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "look"},
            {"type": "input_image", "image_url": RED.data_url()},
        ],
    }


def test_anthropic_requests_put_base64_image_blocks_before_the_text() -> None:
    server = ReplyServer(anthropic_reply('{"ok": 1}'))
    client = AnthropicClient(
        "https://api.anthropic.test", "key", "claude-x", transport=server.transport
    )

    assert complete_with_images(client, "sys", "look", [RED]) == '{"ok": 1}'

    body = server.body(0)
    assert body["system"] == "sys"
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": RED.base64(),
                    },
                },
                {"type": "text", "text": "look"},
            ],
        }
    ]


def test_ollama_requests_list_base64_images_on_the_user_message() -> None:
    server = ReplyServer(ollama_reply('{"ok": 1}', tokens=(10, 2)))
    client = OllamaClient(
        "http://ollama.test:11434", "llava", transport=server.transport
    )

    assert complete_with_images(client, "sys", "look", [RED, BLUE]) == '{"ok": 1}'

    body = server.body(0)
    assert str(server.requests[0].url) == "http://ollama.test:11434/api/chat"
    assert body["messages"][1] == {
        "role": "user",
        "content": "look",
        "images": [RED.base64(), BLUE.base64()],
    }
    assert (body["format"], body["stream"]) == ("json", False)


def test_claude_code_cannot_send_images() -> None:
    with pytest.raises(VisionUnsupported, match="claude_code"):
        complete_with_images(ClaudeCodeClient("claude", "sonnet"), "s", "u", [RED])


def test_the_probe_is_a_red_png() -> None:
    probe = probe_image()
    assert probe.media_type == "image/png"
    with PILImage.open(io.BytesIO(base64.b64decode(probe.base64()))) as picture:
        assert picture.getpixel((10, 10)) == PROBE_RGB


def test_a_model_that_names_the_probe_color_has_vision() -> None:
    server = ReplyServer(openai_reply(SEES_RED))

    check = check_vision(openai_client(server))

    assert (check.vision, check.director_only, check.message) == (True, False, None)
    content = server.body(0)["messages"][1]["content"]
    assert content[1]["image_url"]["url"] == probe_image().data_url()


def test_the_answer_is_cached_per_model() -> None:
    server = ReplyServer(openai_reply(SEES_RED), openai_reply(SEES_RED))

    check_vision(openai_client(server))
    check_vision(openai_client(server))
    other = OpenAICompatClient(
        "https://llm.test/v1", "key", "vis-2", transport=server.transport
    )
    check_vision(other)

    assert [server.body(n)["model"] for n in range(len(server.requests))] == [
        "vis-1",
        "vis-2",
    ]


@pytest.mark.parametrize("status", [400, 413, 415, 422])
def test_a_model_that_refuses_images_runs_the_director_only(status: int) -> None:
    server = ReplyServer(status)

    check = check_vision(openai_client(server))

    assert check.director_only
    assert check.message == f"The model vis-1 does not accept images: {DIRECTOR_ONLY}"
    assert check_vision(openai_client(server)) == check
    assert len(server.requests) == 1


def test_a_model_that_does_not_see_the_image_runs_the_director_only() -> None:
    server = ReplyServer(openai_reply('{"color": "I cannot see images"}'))

    check = check_vision(openai_client(server))

    assert check.director_only
    assert check.message == f"The model vis-1 does not see images: {DIRECTOR_ONLY}"


def test_a_failed_probe_is_not_cached() -> None:
    server = ReplyServer(500, openai_reply(SEES_RED))

    first = check_vision(openai_client(server))
    second = check_vision(openai_client(server))

    assert first.director_only
    assert first.message is not None
    assert first.message.startswith("Could not check whether vis-1 accepts images")
    assert first.message.endswith(DIRECTOR_ONLY)
    assert second.vision
    assert len(server.requests) == 2


def test_no_llm_or_claude_code_runs_the_director_only_without_a_request(
    tmp_path: Path,
) -> None:
    def never(*args: object, **kwargs: object) -> object:
        raise AssertionError("the Claude Code CLI must not run")

    none = check_vision(None)
    claude = check_vision(
        ClaudeCodeClient(str(tmp_path / "claude"), "sonnet", run=never)
    )  # type: ignore[arg-type]

    assert none.director_only
    assert none.message == f"No LLM is configured: {DIRECTOR_ONLY}"
    assert claude.director_only
    assert claude.message == (
        f"The claude_code provider cannot send images: {DIRECTOR_ONLY}"
    )
