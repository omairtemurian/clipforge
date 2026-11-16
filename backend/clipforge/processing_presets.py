"""The settings panel's saved default and "My presets" (STEERING item 10).

Both are kept in {data_dir}/processing_presets.json. What is saved leaves
out the settings that belong to one video: its timeframe and uploaded
subtitles (portable).
"""

from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from clipforge import config
from clipforge.models import ProcessingPreset, ProcessingSettings
from clipforge.pipeline.step import write_json

PRESETS_FILE = "processing_presets.json"
# Settings of one video, which a preset or the default does not keep.
VIDEO_FIELDS = {"timeframe_start", "timeframe_end", "subtitles_id"}
# The most presets kept; saving another past it is refused.
MAX_PRESETS = 50


class PresetLimitError(ValueError):
    """Saving a new preset would keep more than MAX_PRESETS."""


class PresetStore(BaseModel):
    """The content of processing_presets.json."""

    default: ProcessingSettings | None = None
    presets: list[ProcessingPreset] = Field(default_factory=list)


def presets_path() -> Path:
    """Return the file of the saved default and presets."""
    return config.settings.data_dir / PRESETS_FILE


def portable(settings: ProcessingSettings) -> ProcessingSettings:
    """Return settings without the fields of one video (VIDEO_FIELDS)."""
    return settings.model_copy(update=dict.fromkeys(VIDEO_FIELDS))


def load_store() -> PresetStore:
    """Return what is saved; nothing if the file is missing or not valid
    (a broken file is replaced at the next save)."""
    try:
        return PresetStore.model_validate_json(presets_path().read_bytes())
    except (FileNotFoundError, ValidationError):
        return PresetStore()


def _save(store: PresetStore) -> None:
    """Write store to the presets file in one step."""
    path = presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, store)


def get_default() -> ProcessingSettings:
    """Return the saved default settings, or ProcessingSettings() if none."""
    saved = load_store().default
    return ProcessingSettings() if saved is None else saved


def set_default(settings: ProcessingSettings) -> ProcessingSettings:
    """Save settings (portable) as the default and return what was saved."""
    store = load_store()
    store.default = portable(settings)
    _save(store)
    return store.default


def save_preset(name: str, settings: ProcessingSettings) -> ProcessingPreset:
    """Save settings (portable) as the preset name, replacing one of that
    name, and return it. Raises PresetLimitError past MAX_PRESETS."""
    store = load_store()
    preset = ProcessingPreset(name=name.strip(), settings=portable(settings))
    others = [p for p in store.presets if p.name != preset.name]
    if len(others) == len(store.presets) and len(others) >= MAX_PRESETS:
        raise PresetLimitError(f"at most {MAX_PRESETS} presets can be saved")
    store.presets = sorted([*others, preset], key=lambda p: p.name.lower())
    _save(store)
    return preset


def delete_preset(name: str) -> bool:
    """Delete the preset name; return False if there is none."""
    store = load_store()
    kept = [p for p in store.presets if p.name != name]
    if len(kept) == len(store.presets):
        return False
    store.presets = kept
    _save(store)
    return True
