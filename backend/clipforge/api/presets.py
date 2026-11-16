"""The settings panel's saved default and "My presets" (processing_presets)."""

from fastapi import APIRouter, Response

from clipforge import processing_presets as store
from clipforge.api.errors import ApiError
from clipforge.models import PresetName, ProcessingPreset, ProcessingSettings

router = APIRouter()


@router.get("/processing-defaults")
def get_processing_defaults() -> ProcessingSettings:
    """Return the settings a new project gets when none are chosen: the
    saved default, or the built-in one."""
    return store.get_default()


@router.put("/processing-defaults")
def put_processing_defaults(body: ProcessingSettings) -> ProcessingSettings:
    """Save body, without its timeframe and subtitles, as the default."""
    return store.set_default(body)


@router.get("/processing-presets")
def list_processing_presets() -> list[ProcessingPreset]:
    """Return the saved presets by name."""
    return store.load_store().presets


@router.put("/processing-presets")
def put_processing_preset(body: ProcessingPreset) -> ProcessingPreset:
    """Save body's settings, without timeframe and subtitles, under its name,
    replacing a preset of that name (409 preset_limit past MAX_PRESETS)."""
    try:
        return store.save_preset(body.name, body.settings)
    except store.PresetLimitError as exc:
        raise ApiError(409, "preset_limit", str(exc)) from exc


@router.delete("/processing-presets/{name}", status_code=204)
def delete_processing_preset(name: PresetName) -> Response:
    """Delete the preset name (404 not_found if there is none)."""
    if not store.delete_preset(name):
        raise ApiError(404, "not_found", f"no preset is called {name!r}")
    return Response(status_code=204)
