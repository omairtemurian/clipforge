"""What the Pro Edit dialog offers for a clip (SPEC-v3 3.8).

The six presets with their display texts and music, the music beds the
owner may pick (the bundled loops by name, the library's music uploads by
asset id: the ids ProEditOptions.music takes), the style recipes, and the
campaign of the clip's project: the dialog warns when its rules do not
say that heavy edits are allowed, and its autopilot's Pro Edit cap (once
the owner saved the autopilot settings) caps the intensity slider; with no
campaign or no saved settings the slider reaches extreme (SPEC-v3 9.9).
"""

from collections.abc import Iterable
from pathlib import Path
from typing import get_args

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.assets import BUNDLED_TAG
from clipforge.autopilot.rows import AutopilotSettingsRow
from clipforge.models import (
    Clip,
    MusicTrack,
    ProEditChoices,
    ProEditMusicOption,
    ProEditPreset,
    ProEditPresetInfo,
    StyleRecipe,
)
from clipforge.proedit.preset_defs import PresetDef, load_presets
from clipforge.proedit.rows import StyleRecipeRow
from clipforge.proedit.run_inputs import project_campaign


def preset_infos() -> list[ProEditPresetInfo]:
    """Return the presets in the order of ProEditPreset's ids."""
    presets = load_presets()
    return [
        _preset_info(preset_id, presets[preset_id])
        for preset_id in get_args(ProEditPreset)
    ]


def _preset_info(preset_id: ProEditPreset, preset: PresetDef) -> ProEditPresetInfo:
    return ProEditPresetInfo(
        id=preset_id,
        name=preset.name,
        description=preset.description,
        music_moods=list(preset.music.moods),
        bpm_min=preset.music.bpm[0],
        bpm_max=preset.music.bpm[1],
    )


def music_options(tracks: Iterable[MusicTrack]) -> list[ProEditMusicOption]:
    """Return the music library's tracks as Pro Edit music choices: a
    bundled loop by its file name (the catalog's id), an upload by its
    asset id."""
    return [
        ProEditMusicOption(
            id=_music_id(track),
            title=track.title,
            tags=track.tags,
            bundled=track.bundled,
        )
        for track in tracks
    ]


def _music_id(track: MusicTrack) -> str:
    if track.bundled or BUNDLED_TAG in track.asset.tags:
        return Path(track.asset.path).stem
    return str(track.asset.id)


def style_recipes(session: Session) -> list[StyleRecipe]:
    """Return the style recipes, oldest first."""
    rows = session.exec(select(StyleRecipeRow).order_by(col(StyleRecipeRow.id)))
    return [row.to_model() for row in rows]


def clip_choices(
    engine: Engine, clip: Clip, tracks: Iterable[MusicTrack]
) -> ProEditChoices:
    """Return what the dialog offers for a Pro Edit of clip (module
    docstring); tracks is the music library."""
    with Session(engine) as session:
        recipes = style_recipes(session)
        campaign = project_campaign(session, engine, clip.project_id)
        settings = (
            None if campaign is None else session.get(AutopilotSettingsRow, campaign.id)
        )
    choices = ProEditChoices(
        presets=preset_infos(), music=music_options(tracks), recipes=recipes
    )
    if campaign is not None:
        choices.campaign_id = campaign.id
        choices.campaign_name = campaign.name
        choices.allow_heavy_edits = campaign.allow_heavy_edits
    if settings is not None:
        choices.max_intensity = settings.proedit_max_intensity
    return choices
