"""The settings panel's saved default and "My presets" (api/presets)."""

import pytest
from apihelpers import assert_error
from clipforge import config, processing_presets
from fastapi.testclient import TestClient

DEFAULTS = {
    "genre": "auto",
    "length_presets": ["auto"],
    "custom_length_min_s": None,
    "custom_length_max_s": None,
    "timeframe_start": None,
    "timeframe_end": None,
    "num_clips": 7,
    "aspect": "9:16",
    "caption_template": "karaoke_bold",
    "caption_colors": {
        "primary_color": None,
        "highlight_color": None,
        "emphasis_color": None,
    },
    "keyword_prompt": None,
    "remove_fillers": False,
    "auto_cut": True,
    "auto_cut_min_pause_s": 0.5,
    "auto_zoom": True,
    "auto_headline": True,
    "auto_color": False,
    "captions": True,
    "language": None,
    "subtitles_id": None,
    "clipping": "ai",
    "clip_anything": False,
    "search_terms": [],
    "brand_template_id": None,
    "reframe_preset": None,
    "default_layout": "auto",
    "zoom_out_moments": "balanced",
    "camera_motion": "calm",
}
SUBTITLES = "0123456789abcdef0123456789abcdef"


def test_processing_defaults_use_the_configured_clip_count(
    client: TestClient,
) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir, default_num_clips=7
    )

    response = client.get("/api/processing-defaults")

    assert response.status_code == 200
    assert response.json() == DEFAULTS


def test_a_saved_default_is_what_the_panel_opens_with(client: TestClient) -> None:
    chosen = {
        "genre": "gaming",
        "length_presets": ["lt30", "60_90"],
        "timeframe_start": 10,
        "timeframe_end": 70,
        "num_clips": 4,
        "auto_color": True,
        "language": "de",
        "subtitles_id": SUBTITLES,
    }

    saved = client.put("/api/processing-defaults", json=chosen)

    assert saved.status_code == 200
    body = client.get("/api/processing-defaults").json()
    assert body == saved.json()
    assert (body["genre"], body["length_presets"], body["num_clips"]) == (
        "gaming",
        ["lt30", "60_90"],
        4,
    )
    assert (body["auto_color"], body["language"]) == (True, "de")
    # The timeframe and the subtitles belong to one video.
    assert (body["timeframe_start"], body["timeframe_end"]) == (None, None)
    assert body["subtitles_id"] is None
    assert processing_presets.presets_path().is_file()


def test_presets_are_saved_listed_replaced_and_deleted(client: TestClient) -> None:
    assert client.get("/api/processing-presets").json() == []

    first = {"name": "Shorts", "settings": {"genre": "vlog", "num_clips": 3}}
    other = {"name": "  Long talks ", "settings": {"length_presets": ["300_600"]}}
    assert client.put("/api/processing-presets", json=first).status_code == 200
    assert client.put("/api/processing-presets", json=other).status_code == 200
    again = {"name": "Shorts", "settings": {"genre": "news", "timeframe_end": 9}}
    replaced = client.put("/api/processing-presets", json=again).json()
    assert replaced["settings"]["timeframe_end"] is None

    presets = client.get("/api/processing-presets").json()
    assert [(p["name"], p["settings"]["genre"]) for p in presets] == [
        ("Long talks", "auto"),
        ("Shorts", "news"),
    ]
    assert presets[0]["settings"]["length_presets"] == ["300_600"]

    assert client.delete("/api/processing-presets/Shorts").status_code == 204
    names = [p["name"] for p in client.get("/api/processing-presets").json()]
    assert names == ["Long talks"]
    assert_error(client.delete("/api/processing-presets/Shorts"), 404, "not_found")


def test_a_preset_needs_a_name_and_valid_settings(client: TestClient) -> None:
    for body in (
        {"name": " ", "settings": {}},
        {"name": "x" * 61, "settings": {}},
        {"name": "Bad", "settings": {"length_presets": []}},
    ):
        response = client.put("/api/processing-presets", json=body)
        assert response.status_code == 422


def test_presets_stop_at_the_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing_presets, "MAX_PRESETS", 2)
    for name in ("a", "b"):
        body = {"name": name, "settings": {}}
        assert client.put("/api/processing-presets", json=body).status_code == 200
    replace = {"name": "a", "settings": {"genre": "news"}}
    assert client.put("/api/processing-presets", json=replace).status_code == 200
    third = client.put("/api/processing-presets", json={"name": "c", "settings": {}})
    assert_error(third, 409, "preset_limit")


def test_a_broken_presets_file_reads_as_nothing_saved(client: TestClient) -> None:
    path = processing_presets.presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert client.get("/api/processing-presets").json() == []
    assert client.get("/api/processing-defaults").json()["genre"] == "auto"
