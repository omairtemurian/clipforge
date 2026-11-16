"""What a Pro Edit run hands the Director (SPEC-v3 3.4, 3.8): the clip's
signals, the owner's preset, intensity, style recipe and music, the
campaign of the clip's project and the catalog of assets it may name. The
plan ends on a loop-friendly ending when the owner asks for one or the
style recipe's references loop (style/recipe.recipe_loops).

Music: "auto" is the preset's pick of the bundled loops by mood and BPM
(director_music.pick_music; none suits it: no bed), "none" is no bed, and
anything else must be a music asset of the catalog (a library asset id or
a bundled loop's name). Its beat grid is read from the file (beats.
music_grid) with the clip starting at the music's start.
"""

from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import assets, campaigns
from clipforge.db import ProjectRow
from clipforge.models import (
    PROEDIT_MUSIC_AUTO,
    PROEDIT_MUSIC_NONE,
    Campaign,
    Clip,
    ProEditOptions,
    StyleRecipe,
)
from clipforge.pipeline.detectors import DetectFaces
from clipforge.proedit.audio.sounds import find_sound
from clipforge.proedit.beats import music_grid
from clipforge.proedit.director_catalog import CatalogAsset, asset_catalog
from clipforge.proedit.director_music import (
    MusicChoice,
    bundled_candidates,
    pick_music,
)
from clipforge.proedit.director_prompt import DirectorRequest
from clipforge.proedit.preset_defs import get_preset
from clipforge.proedit.rows import StyleRecipeRow
from clipforge.proedit.signals import build_signals
from clipforge.proedit.style.recipe import recipe_loops


class RunInputError(ValueError):
    """The owner's options name a style recipe or music that does not
    exist (the API answers 422)."""


def catalog(session: Session) -> tuple[CatalogAsset, ...]:
    """Return the catalog of assets a plan may name: the bundled sounds,
    loops and overlays and the library's sound assets."""
    return tuple(asset_catalog(assets.list_assets(session)))


def check_options(session: Session, options: ProEditOptions) -> None:
    """Raise RunInputError if options name a style recipe or music that does
    not exist."""
    recipe_of(session, options)
    music_asset(options, catalog(session))


def recipe_of(session: Session, options: ProEditOptions) -> StyleRecipe | None:
    """Return the style recipe options aim for (None: none); raises
    RunInputError if it does not exist."""
    if options.style_recipe_id is None:
        return None
    row = session.get(StyleRecipeRow, options.style_recipe_id)
    if row is None:
        raise RunInputError(f"style recipe {options.style_recipe_id} does not exist")
    return row.to_model()


def music_asset(options: ProEditOptions, known: tuple[CatalogAsset, ...]) -> str | None:
    """Return the asset of the bed options choose (module docstring), None
    for no bed; raises RunInputError for music the catalog lacks."""
    if options.music == PROEDIT_MUSIC_NONE:
        return None
    if options.music == PROEDIT_MUSIC_AUTO:
        pick = pick_music(get_preset(options.preset).music, bundled_candidates())
        return None if pick is None else pick.asset
    if any(a.kind == "music" and a.id == options.music for a in known):
        return options.music
    raise RunInputError(f"music {options.music!r} is not a music asset")


def music_choice(session: Session, asset: str | None) -> MusicChoice | None:
    """Return the bed of asset with its beat grid (None: no bed); raises
    RunInputError if its file is missing."""
    if asset is None:
        return None
    library = {str(a.id): Path(a.path) for a in assets.list_assets(session) if a.path}
    path = find_sound(asset, library)
    if path is None or not path.is_file():
        raise RunInputError(f"the file of music {asset!r} is missing")
    return MusicChoice(asset, music_grid(path), 0.0)


def project_campaign(
    session: Session, engine: Engine, project_id: int
) -> Campaign | None:
    """Return the campaign of project project_id, None if it has none (or
    it was deleted)."""
    project = session.get(ProjectRow, project_id)
    if project is None or project.campaign_id is None:
        return None
    try:
        return campaigns.get_campaign(engine, project.campaign_id)
    except campaigns.CampaignNotFound:
        return None


def director_request(
    engine: Engine,
    clip: Clip,
    options: ProEditOptions,
    work: Path,
    *,
    detect: DetectFaces | None = None,
    version: int = 1,
) -> DirectorRequest:
    """Return what the Director plans clip from (module docstring) with
    options; work is the work directory of its project's process job and
    detect, if given, finds faces instead of the face models
    (signals.build_signals). Raises RunInputError for a missing recipe or
    music and StepError for missing signals."""
    with Session(engine) as session:
        known = catalog(session)
        recipe = recipe_of(session, options)
        music = music_choice(session, music_asset(options, known))
        campaign = project_campaign(session, engine, clip.project_id)
    return DirectorRequest(
        signals=build_signals(work, clip, detect=detect),
        preset=get_preset(options.preset),
        preset_id=options.preset,
        intensity=options.intensity,
        music=music,
        recipe=recipe,
        campaign=campaign,
        catalog=known,
        version=version,
        loop_ending=options.loop_ending
        or (recipe is not None and recipe_loops(recipe)),
    )
