"""The live preview of a caption style: POST /api/caption-templates/{name}/
preview draws a template's sample caption with a clip's caption style."""

import pytest
from apihelpers import assert_error
from fastapi.testclient import TestClient
from test_caption_templates_api import png_size

URL = "/api/caption-templates/{}/preview"


def test_a_style_preview_is_a_png_that_shows_the_style(client: TestClient) -> None:
    template = client.get("/api/caption-templates/neon/preview.png").content

    plain = client.post(URL.format("neon"), json={})
    styled = client.post(
        URL.format("neon"),
        json={"primary_color": "#FF0000", "max_lines": 2, "animation": "reveal"},
    )

    for response in (plain, styled):
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert png_size(response.content) == (540, 960)
    assert plain.content == template
    assert styled.content != template


def test_a_style_font_must_be_bundled(client: TestClient) -> None:
    response = client.post(URL.format("neon"), json={"font": "Comic Sans MS"})

    message = assert_error(response, 422, "validation_error")
    assert "Comic Sans MS" in message


@pytest.mark.parametrize(
    "body",
    [{"max_lines": 3}, {"max_words_per_line": 7}, {"animation": "spin"}],
)
def test_an_invalid_style_is_rejected(client: TestClient, body: object) -> None:
    assert_error(client.post(URL.format("neon"), json=body), 422, "validation_error")


def test_an_unknown_template_has_no_preview(client: TestClient) -> None:
    response = client.post(URL.format("wobbly"), json={})

    assert_error(response, 404, "not_found")
