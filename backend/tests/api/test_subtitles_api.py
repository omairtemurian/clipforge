"""The settings panel's speech languages and SRT upload (api/sources)."""

from apihelpers import assert_error
from clipforge import config
from clipforge.pipeline.subtitle_import import subtitles_path
from fastapi.testclient import TestClient

SRT = (
    "1\n00:00:01,000 --> 00:00:03,000\nHello there\n\n"
    "2\n00:00:04,000 --> 00:00:05,500\nBye\n"
)


def test_speech_languages_are_whispers_by_name(client: TestClient) -> None:
    languages = client.get("/api/speech-languages").json()

    assert len(languages) == 100
    assert {"code": "en", "name": "English"} in languages
    names = [language["name"] for language in languages]
    assert names == sorted(names)


def test_an_srt_upload_is_saved_under_a_token(client: TestClient) -> None:
    files = {"file": ("talk.srt", SRT.encode(), "application/x-subrip")}

    response = client.post("/api/subtitles", files=files)

    assert response.status_code == 201
    body = response.json()
    assert body["cues"] == 2
    path = subtitles_path(body["subtitles_id"], config.settings)
    assert path.read_text(encoding="utf-8") == SRT


def test_a_file_that_is_not_srt_is_refused(client: TestClient) -> None:
    for data in (b"just text", b"\xff\xfe\x00bad"):
        files = {"file": ("talk.srt", data, "application/x-subrip")}
        response = client.post("/api/subtitles", files=files)
        assert_error(response, 422, "invalid_subtitles")


def test_a_vtt_upload_is_saved_under_a_token(client: TestClient) -> None:
    vtt = "WEBVTT\n\n00:01.000 --> 00:03.000\nHello there\n"
    files = {"file": ("talk.vtt", vtt.encode(), "text/vtt")}

    response = client.post("/api/subtitles", files=files)

    assert response.status_code == 201
    assert response.json()["cues"] == 1


def test_a_malformed_file_is_refused_with_its_line_number(
    client: TestClient,
) -> None:
    srt = b"1\n00:00:01,000 --> 00:00:03,000\nHi\n\n2\n00:00:04,000 --> later\nBye\n"
    files = {"file": ("talk.srt", srt, "application/x-subrip")}

    response = client.post("/api/subtitles", files=files)

    assert_error(response, 422, "invalid_subtitles")
    assert "line 6: cannot read the timing" in response.text
