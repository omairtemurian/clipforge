"""Tests that the models match SPEC 5 fields, literals, and constraints."""

import json
from datetime import UTC, datetime
from typing import Any, get_args

import pytest
from clipforge import config
from clipforge.config import Settings
from clipforge.models import (
    BrandTemplate,
    Clip,
    ClipCandidate,
    Job,
    ProcessingSettings,
    Project,
    Scores,
    Segment,
    SignalEvent,
    SourceMeta,
    Timeline,
    TrackItem,
    Transcript,
    Word,
)
from pydantic import BaseModel, ValidationError

SPEC_FIELDS: dict[type[BaseModel], str] = {
    Word: "text start end speaker prob approximate",
    Segment: "id start end text words speaker",
    Transcript: "language duration segments approximate_times",
    SignalEvent: "kind start end intensity",
    ProcessingSettings: "genre length_presets custom_length_min_s custom_length_max_s "
    "timeframe_start timeframe_end "
    "num_clips aspect caption_template caption_colors keyword_prompt remove_fillers "
    "auto_cut auto_cut_min_pause_s auto_zoom auto_headline auto_color captions "
    "language subtitles_id clipping clip_anything search_terms brand_template_id "
    "reframe_preset default_layout zoom_out_moments camera_motion",
    ClipCandidate: "start end title hook_text description hashtags "
    "emphasis_words reason hook flow value trend",
    Scores: "overall hook flow value trend laugh energy",
    # emphasis_words extends SPEC 5 so captions can find them (docs/decisions.md).
    Clip: "id project_id segments tracks title hook_text description hashtags "
    "emphasis_words reason scores layout caption_template caption_overrides "
    "cut_ranges status output_path caption_style crop_offset framing auto_cut"
    " auto_zoom zoom_keyframes scene_reframes auto_color show_captions result_set"
    " transitions hook enhance parent_clip_id variant",
    Project: "id source_url source_path title duration thumbnail_path settings "
    "status created_at source_rights credit_line campaign_id source_published_at"
    " result_set overall_progress eta_seconds opened_at archived_at",
    Job: "id project_id clip_id kind step progress status error log_path "
    "priority attempts overall_progress eta_seconds",
    BrandTemplate: "id name logo_path logo_position logo_opacity font "
    "primary_color intro_path outro_path",
    TrackItem: "id kind asset_id start end props",
    Timeline: "video broll overlays text music sfx voiceover",
}

SPEC_NULLABLE: dict[type[BaseModel], str] = {
    ProcessingSettings: "custom_length_min_s custom_length_max_s timeframe_start "
    "timeframe_end keyword_prompt "
    "language subtitles_id brand_template_id reframe_preset",
    Clip: "output_path hook parent_clip_id",
    Project: "source_url source_rights campaign_id source_published_at "
    "eta_seconds opened_at archived_at",
    Job: "clip_id error eta_seconds",
    BrandTemplate: "intro_path outro_path",
    TrackItem: "asset_id",
}

SPEC_LITERALS = [
    (SignalEvent, "kind", "laugh applause cheer music scene_cut silence energy_peak"),
    (
        ProcessingSettings,
        "genre",
        "auto comedy sports_commentary faith news vlog gaming podcast talk "
        "interview other",
    ),
    (ProcessingSettings, "clipping", "ai captions_only keyword_search"),
    (
        ProcessingSettings,
        "default_layout",
        "auto dynamic fill fit split grid pip screenshare gameplay square_blur",
    ),
    (Clip, "layout", "fill fit split grid pip screenshare gameplay square_blur"),
    (Clip, "status", "candidate rendering rendered failed"),
    (Project, "status", "queued running done failed"),
    (Job, "kind", "process render reprompt proedit"),
    (Job, "status", "queued running done failed"),
    (BrandTemplate, "logo_position", "tl tr bl br"),
]

WORD = {"text": "WHAT", "start": 110.2, "end": 110.6, "speaker": "S0", "prob": 0.9}
VIDEO_ITEM = {"id": "video-0", "kind": "source", "start": 100.0, "end": 140.0}
SCORES = {"overall": 72, "hook": 80, "flow": 70, "value": 60, "trend": 50}
CLIP_TEXT = {
    "title": "Airport security",
    "hook_text": "He packed WHAT?",
    "description": "A bit about airport security.",
    "hashtags": ["comedy", "standup", "travel"],
    "emphasis_words": ["WHAT"],
    "reason": "Setup, punchline, big laugh.",
}
VALID: dict[type[BaseModel], dict[str, Any]] = {
    Word: WORD,
    Transcript: {
        "language": "en",
        "duration": 600.0,
        "segments": [
            {"id": 0, "start": 110.0, "end": 111.0, "text": "He packed WHAT?"}
            | {"words": [WORD], "speaker": "S0"}
        ],
    },
    SignalEvent: {"kind": "laugh", "start": 111.0, "end": 113.1, "intensity": 0.85},
    ClipCandidate: {"start": 100.0, "end": 140.0, **CLIP_TEXT}
    | {"hook": 80, "flow": 70, "value": 60, "trend": 50},
    Scores: SCORES | {"laugh": 0.8, "energy": 0.5},
    Clip: {"id": 1, "project_id": 1, "segments": [[100.0, 140.0]], **CLIP_TEXT}
    | {"tracks": {"video": [VIDEO_ITEM]}}
    | {"scores": SCORES | {"laugh": 0.8, "energy": 0.5}, "layout": "fill"}
    | {"caption_template": "karaoke_bold", "caption_overrides": [WORD]}
    | {"cut_ranges": [[110.0, 111.5]], "status": "candidate", "output_path": None},
    Project: {"id": 1, "source_url": None, "source_path": "data/input/set.mp4"}
    | {"title": "Set", "duration": 600.0, "thumbnail_path": "data/work/1/thumb.jpg"}
    | {"settings": {"genre": "comedy", "num_clips": 5}, "status": "queued"}
    | {"created_at": datetime(2026, 10, 30, 21, 0, tzinfo=UTC)},
    Job: {"id": 1, "project_id": 1, "clip_id": None, "kind": "process"}
    | {"step": "transcribe", "progress": 0.5, "status": "running", "error": None}
    | {"log_path": "data/work/1/job.log", "priority": 0, "attempts": 1},
    BrandTemplate: {"id": 1, "name": "Main", "logo_path": "data/brand/logo.png"}
    | {"logo_position": "tr", "logo_opacity": 0.8, "font": "Inter Bold"}
    | {"primary_color": "#FF6B35", "intro_path": None, "outro_path": None},
}
SCORE_FIELDS = ("hook", "flow", "value", "trend")
INVALID: dict[type[BaseModel], list[tuple[str, Any]]] = {
    SignalEvent: [("intensity", -0.1), ("intensity", 1.1), ("kind", "cough")],
    Scores: [("overall", 100), ("laugh", 1.5), ("energy", -0.5)],
    Clip: [("layout", "stretch"), ("status", "done"), ("cut_ranges", [[110.0]])]
    + [("segments", []), ("segments", [[100.0, 100.0]]), ("segments", [[-1, 5]])]
    + [("segments", [[100.0]]), ("tracks", {"video": [VIDEO_ITEM | {"end": 99}]})]
    + [("tracks", {"video": [VIDEO_ITEM | {"kind": "sticker"}]})],
    Project: [("status", "ready")],
    Job: [("kind", "export"), ("progress", 1.01)],
    BrandTemplate: [("name", ""), ("logo_position", "center")]
    + [("logo_opacity", 1.2), ("primary_color", "orange")]
    + [("primary_color", "#ff6b3")],
}


def candidate(**overrides: Any) -> ClipCandidate:
    """Build a valid ClipCandidate with some fields replaced."""
    return ClipCandidate.model_validate(VALID[ClipCandidate] | overrides)


@pytest.mark.parametrize(("model", "fields"), SPEC_FIELDS.items())
def test_models_have_spec_fields_in_order(model: type[BaseModel], fields: str) -> None:
    assert list(model.model_fields) == fields.split()


@pytest.mark.parametrize("model", SPEC_FIELDS)
def test_only_spec_nullable_fields_accept_none(model: type[BaseModel]) -> None:
    nullable = {
        name
        for name, info in model.model_fields.items()
        if type(None) in get_args(info.annotation)
    }
    assert nullable == set(SPEC_NULLABLE.get(model, "").split())


@pytest.mark.parametrize(("model", "field", "values"), SPEC_LITERALS)
def test_literal_values_match_spec(
    model: type[BaseModel], field: str, values: str
) -> None:
    assert get_args(model.model_fields[field].annotation) == tuple(values.split())


def test_length_presets_are_a_list_of_presets() -> None:
    annotation = ProcessingSettings.model_fields["length_presets"].annotation
    [preset] = get_args(annotation)
    assert get_args(preset) == tuple(
        "auto lt30 0_60 30_60 60_90 60_180 90_180 180_300 300_600 600_900 "
        "custom".split()
    )


@pytest.mark.parametrize(
    ("data", "presets"),
    [
        ({}, ["auto"]),
        ({"length_preset": "60_90"}, ["60_90"]),
        ({"length_presets": ["600_900", "lt30", "lt30"]}, ["lt30", "600_900"]),
        ({"length_presets": ["auto", "30_60"]}, ["30_60"]),
    ],
)
def test_length_presets_read_v1_settings_and_are_tidied(
    data: dict[str, object], presets: list[str]
) -> None:
    assert ProcessingSettings.model_validate(data).length_presets == presets


@pytest.mark.parametrize(
    "data",
    [
        {"length_presets": []},
        {"length_presets": ["2m"]},
        {"language": "xx"},
        {"subtitles_id": "../etc/passwd"},
    ],
)
def test_processing_settings_reject_bad_lengths_languages_and_subtitles(
    data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProcessingSettings.model_validate(data)


def test_nested_field_types() -> None:
    assert Segment.model_fields["words"].annotation == list[Word]
    assert Transcript.model_fields["segments"].annotation == list[Segment]
    assert Clip.model_fields["scores"].annotation is Scores
    assert Clip.model_fields["caption_overrides"].annotation == list[Word]
    assert Clip.model_fields["cut_ranges"].annotation == list[tuple[float, float]]
    assert Clip.model_fields["tracks"].annotation is Timeline
    for track in Timeline.model_fields.values():
        assert track.annotation == list[TrackItem]
    assert Project.model_fields["settings"].annotation is ProcessingSettings


@pytest.mark.parametrize("model", VALID)
def test_valid_models_round_trip_through_json(model: type[BaseModel]) -> None:
    instance = model.model_validate(VALID[model])
    assert model.model_validate_json(instance.model_dump_json()) == instance


def test_clip_start_and_end_are_derived_from_its_segments() -> None:
    clip = Clip.model_validate(VALID[Clip] | {"segments": [[30, 40], [5, 9]]})
    assert (clip.start, clip.end) == (5.0, 40.0)
    dumped = json.loads(clip.model_dump_json())
    assert dumped["segments"] == [[30.0, 40.0], [5.0, 9.0]]
    assert (dumped["start"], dumped["end"]) == (5.0, 40.0)
    assert dumped["tracks"]["video"] == [VIDEO_ITEM | {"asset_id": None, "props": {}}]
    assert dumped["tracks"]["voiceover"] == []
    schema = Clip.model_json_schema(mode="serialization")["properties"]
    assert schema["start"]["readOnly"] and schema["end"]["readOnly"]
    assert "start" not in Clip.model_json_schema(mode="validation")["properties"]


def test_cut_ranges_serialize_as_pairs() -> None:
    clip = Clip.model_validate(VALID[Clip])
    assert json.loads(clip.model_dump_json())["cut_ranges"] == [[110.0, 111.5]]
    assert isinstance(clip.caption_overrides[0], Word)


@pytest.mark.parametrize(
    ("field", "valid", "invalid"),
    [
        ("title", "t" * 70, "t" * 71),
        ("hook_text", "h" * 60, "h" * 61),
        ("description", "d" * 300, "d" * 301),
        ("hashtags", list("abc"), list("ab")),
        ("hashtags", list("abcdefgh"), list("abcdefghi")),
        ("hashtags", ["comedy", "standup", "travel"], ["#comedy", "standup", "x"]),
        ("hashtags", ["comedy", "standup", "travel"], ["comedy", "stand#up", "x"]),
        *[(name, 0, -1) for name in SCORE_FIELDS],
        *[(name, 99, 100) for name in SCORE_FIELDS],
    ],
)
def test_candidate_enforces_field_limits(field: str, valid: Any, invalid: Any) -> None:
    assert getattr(candidate(**{field: valid}), field) == valid
    with pytest.raises(ValidationError) as excinfo:
        candidate(**{field: invalid})
    assert excinfo.value.errors()[0]["loc"][0] == field


def test_candidate_json_schema_carries_limits_for_the_llm() -> None:
    props = ClipCandidate.model_json_schema()["properties"]
    assert props["title"]["maxLength"] == 70
    assert props["hook_text"]["maxLength"] == 60
    assert props["description"]["maxLength"] == 300
    assert (props["hashtags"]["minItems"], props["hashtags"]["maxItems"]) == (3, 8)
    assert props["hashtags"]["items"]["pattern"] == "^[^#]+$"
    for name in SCORE_FIELDS:
        assert (props[name]["minimum"], props[name]["maximum"]) == (0, 99)


@pytest.mark.parametrize(
    ("num_clips", "valid"), [(0, False), (1, True), (30, True), (31, False)]
)
def test_num_clips_is_bounded_1_to_30(num_clips: int, valid: bool) -> None:
    if valid:
        assert ProcessingSettings(num_clips=num_clips).num_clips == num_clips
        return
    with pytest.raises(ValidationError) as excinfo:
        ProcessingSettings(num_clips=num_clips)
    assert excinfo.value.errors()[0]["loc"] == ("num_clips",)


def test_processing_settings_defaults_follow_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "settings", Settings(default_num_clips=7))
    settings = ProcessingSettings()
    assert settings.model_dump(exclude_none=True) == {
        "genre": "auto",
        "length_presets": ["auto"],
        "num_clips": 7,
        "aspect": "9:16",
        "caption_template": "karaoke_bold",
        "caption_colors": {},
        "remove_fillers": False,
        "auto_cut": True,
        "auto_cut_min_pause_s": 0.5,
        "auto_zoom": True,
        "auto_headline": True,
        "auto_color": False,
        "captions": True,
        "clipping": "ai",
        "clip_anything": False,
        "search_terms": [],
        "default_layout": "auto",
        "zoom_out_moments": "balanced",
        "camera_motion": "calm",
    }

    monkeypatch.setattr(config, "settings", Settings(default_num_clips=40))
    with pytest.raises(ValidationError):
        ProcessingSettings()


@pytest.mark.parametrize(
    ("start", "end"), [(30.0, 30.0), (40.0, 30.0), (None, 0.0), (-1.0, None)]
)
def test_timeframe_rejects_empty_or_negative_ranges(
    start: float | None, end: float | None
) -> None:
    with pytest.raises(ValidationError):
        ProcessingSettings(timeframe_start=start, timeframe_end=end)


@pytest.mark.parametrize(
    ("start", "end", "valid"),
    [(0.0, 60.0, True), (5.0, 30.0, True), (30.0, 30.0, False), (5.0, 61.0, False)],
)
def test_source_meta_timeframe_lies_within_the_video(
    start: float, end: float, valid: bool
) -> None:
    fields = {"title": "Show", "duration": 60.0, "width": 1280, "height": 720}
    meta = fields | {"fps": 30.0, "timeframe_start": start, "timeframe_end": end}
    if valid:
        assert SourceMeta.model_validate(meta).channel is None
    else:
        with pytest.raises(ValidationError, match="start < end <= duration"):
            SourceMeta.model_validate(meta)


def test_timeframe_accepts_open_and_closed_ranges() -> None:
    assert ProcessingSettings(timeframe_start=30.0).timeframe_end is None
    assert ProcessingSettings(timeframe_end=90.0).timeframe_start is None
    both = ProcessingSettings(timeframe_start=30.0, timeframe_end=90.0)
    assert (both.timeframe_start, both.timeframe_end) == (30.0, 90.0)


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [
        (model, field, value)
        for model, cases in INVALID.items()
        for field, value in cases
    ],
)
def test_models_reject_invalid_values(
    model: type[BaseModel], field: str, value: Any
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate(VALID[model] | {field: value})
    assert excinfo.value.errors()[0]["loc"][0] == field
