"""Settings endpoints: read, change (saved in .env.local) and test the LLM."""

import json
import stat
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from apihelpers import assert_error
from clipforge import config
from clipforge.api.app import create_app
from fastapi.testclient import TestClient

KEY = "sk-secret-key-123"
CHAT_OK = {"choices": [{"message": {"content": '{"ok": true}'}}]}


@pytest.fixture
def env_file(work_in_tmp: Path) -> Path:
    """The .env.local that the Settings API writes (in the temporary cwd)."""
    return work_in_tmp / ".env.local"


def test_get_shows_the_settings_without_keys(client: TestClient) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, openai_api_key=KEY
    )

    response = client.get("/api/settings")

    body = response.json()
    assert body["llm_provider"] == "copilot"
    assert body["llm_model"] == "claude-sonnet-5.5"
    assert body["copilot_account"] == ""
    assert body["whisper_model"] == "small"
    assert body["credit_template"] == "Credit: {channel}"
    assert body["openai_api_key_set"] is True
    assert body["github_copilot_token_set"] is False
    assert body["data_dir"] == str(config.settings.data_dir)
    assert KEY not in response.text
    assert "openai_api_key" not in body


def test_put_saves_to_env_local_and_applies_at_once(
    client: TestClient, env_file: Path
) -> None:
    env_file.write_text("# mine\nHF_TOKEN=hf-1\nLLM_MODEL=old\n")

    response = client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "llm_model": "gpt-5",
            "openai_api_key": KEY,
            "whisper_model": "medium",
            "credit_template": 'Via "{channel}" \\ {title}',
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_provider"] == "openai" and body["llm_model"] == "gpt-5"
    assert body["openai_api_key_set"] is True
    assert KEY not in response.text
    assert client.get("/api/settings").json() == body
    assert config.settings.openai_api_key == KEY
    assert config.settings.credit_template == 'Via "{channel}" \\ {title}'
    lines = env_file.read_text().splitlines()
    assert lines[:2] == ["# mine", "HF_TOKEN=hf-1"]
    assert 'LLM_MODEL="gpt-5"' in lines and "LLM_MODEL=old" not in lines
    fresh = config.Settings(data_dir=config.settings.data_dir)
    assert fresh.openai_api_key == KEY and fresh.whisper_model == "medium"


def test_put_saves_the_ytdlp_cookie_settings(
    client: TestClient, env_file: Path, work_in_tmp: Path
) -> None:
    cookies = work_in_tmp / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    assert client.get("/api/settings").json()["ytdlp_cookies_from_browser"] == ""

    response = client.put(
        "/api/settings",
        json={
            "ytdlp_cookies_from_browser": "chrome:Profile 1",
            "ytdlp_cookies_file": str(cookies),
        },
    )

    body = response.json()
    assert body["ytdlp_cookies_from_browser"] == "chrome:Profile 1"
    assert body["ytdlp_cookies_file"] == str(cookies)
    assert config.settings.ytdlp_cookies_from_browser == "chrome:Profile 1"
    assert 'YTDLP_COOKIES_FROM_BROWSER="chrome:Profile 1"' in env_file.read_text()
    cleared = client.put("/api/settings", json={"ytdlp_cookies_from_browser": ""})
    assert cleared.json()["ytdlp_cookies_from_browser"] == ""


def test_put_saves_the_copilot_account(client: TestClient, env_file: Path) -> None:
    response = client.put("/api/settings", json={"copilot_account": "omairtemurian"})

    assert response.json()["copilot_account"] == "omairtemurian"
    assert config.settings.copilot_account == "omairtemurian"
    assert "COPILOT_ACCOUNT=" in env_file.read_text()


def test_put_without_changes_writes_nothing(client: TestClient, env_file: Path) -> None:
    response = client.put("/api/settings", json={})

    assert response.status_code == 200
    assert not env_file.exists()


def test_a_new_env_file_is_private_and_a_key_can_be_cleared(
    client: TestClient, env_file: Path
) -> None:
    client.put("/api/settings", json={"openai_api_key": KEY})
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    body = client.put("/api/settings", json={"openai_api_key": ""}).json()

    assert body["openai_api_key_set"] is False
    assert config.settings.openai_api_key == ""


def test_data_dir_does_not_change(client: TestClient, env_file: Path) -> None:
    data_dir = config.settings.data_dir
    env_file.write_text(f'DATA_DIR="{data_dir.parent / "other"}"\n')

    client.put("/api/settings", json={"whisper_model": "tiny"})

    assert config.settings.data_dir == data_dir
    assert_error(
        client.put("/api/settings", json={"data_dir": "/tmp/x"}),
        422,
        "validation_error",
    )


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"credit_template": "{nope}"}, "credit_template"),
        ({"llm_provider": "bard"}, "llm_provider"),
        ({"openai_base_url": "ftp://x"}, "openai_base_url"),
        ({"ollama_host": "localhost:11434"}, "ollama_host"),
        ({"llm_model": " "}, "llm_model"),
        ({"copilot_account": "-u root"}, "copilot_account"),
        ({"openai_api_key": "a\nb"}, "openai_api_key"),
        ({"ffmpeg_bin": "/nonexistent/ffmpeg"}, "ffmpeg_bin"),
        ({"ytdlp_cookies_from_browser": "netscape"}, "ytdlp_cookies_from_browser"),
        ({"ytdlp_cookies_file": "/nonexistent/c.txt"}, "ytdlp_cookies_file"),
        ({"unknown": 1}, "unknown"),
    ],
)
def test_put_rejects_invalid_values_and_saves_nothing(
    client: TestClient, env_file: Path, change: dict[str, object], field: str
) -> None:
    response = client.put("/api/settings", json={"whisper_model": "tiny", **change})

    assert field in assert_error(response, 422, "validation_error")
    assert not env_file.exists()
    assert config.settings.whisper_model == "small"


def test_an_environment_variable_wins_so_the_change_is_refused(
    client: TestClient, env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file.write_text("LLM_MODEL=kept\n")
    monkeypatch.setenv("LLM_MODEL", "from-env")

    response = client.put("/api/settings", json={"llm_model": "new"})

    assert "llm_model" in assert_error(response, 409, "conflict")
    assert env_file.read_text() == "LLM_MODEL=kept\n"


@pytest.fixture
def llm_calls() -> list[httpx.Request]:
    """The requests that the test-llm endpoint sent (to the mock transport)."""
    return []


@pytest.fixture
def llm_client(data_dir: Path, llm_calls: list[httpx.Request]) -> Iterator[TestClient]:
    """A client whose test-llm requests go to a transport that answers
    OpenAI chat requests, fails others with a 401 that echoes the request."""

    def handler(request: httpx.Request) -> httpx.Response:
        llm_calls.append(request)
        if request.url.host == "bad.example":
            echo = request.headers.get("authorization", "")
            return httpx.Response(401, text=f"bad credentials {echo}")
        return httpx.Response(200, json=CHAT_OK)

    app = create_app(
        run_worker=False,
        caption_previews=False,
        llm_transport=httpx.MockTransport(handler),
    )
    with TestClient(app) as client:
        yield client


def test_test_llm_uses_the_saved_settings(
    llm_client: TestClient, llm_calls: list[httpx.Request]
) -> None:
    llm_client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "llm_model": "m-1",
            "openai_base_url": "https://llm.example/v1",
            "openai_api_key": KEY,
        },
    )

    response = llm_client.post("/api/settings/test-llm")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "openai",
        "model": "m-1",
        "message": '{"ok": true}',
    }
    (request,) = llm_calls
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content)["model"] == "m-1"
    assert KEY not in response.text


def test_test_llm_tries_the_body_without_saving_it(
    llm_client: TestClient, llm_calls: list[httpx.Request], env_file: Path
) -> None:
    response = llm_client.post(
        "/api/settings/test-llm",
        json={
            "llm_provider": "openai",
            "openai_base_url": "https://other.example/v1",
            "openai_api_key": KEY,
        },
    )

    assert response.json()["ok"] is True
    assert llm_calls[0].url.host == "other.example"
    assert not env_file.exists()
    assert config.settings.llm_provider == "copilot"


def test_test_llm_failure_is_ok_false_and_never_echoes_the_key(
    llm_client: TestClient,
) -> None:
    response = llm_client.post(
        "/api/settings/test-llm",
        json={
            "llm_provider": "openai",
            "openai_base_url": "https://bad.example/v1",
            "openai_api_key": KEY,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "401" in body["message"] and "***" in body["message"]
    assert KEY not in response.text


def test_test_llm_rejects_an_invalid_body(llm_client: TestClient) -> None:
    response = llm_client.post(
        "/api/settings/test-llm", json={"credit_template": "{nope}"}
    )

    assert_error(response, 422, "validation_error")
