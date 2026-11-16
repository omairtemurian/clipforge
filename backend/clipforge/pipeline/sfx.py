"""Auto sound effects (SPEC-v2 3.5): the bundled CC0 pack, a search of it
by tag, and where the LLM puts its sounds in a clip.

The pack is the sounds of assets/sfx (BUNDLED_SFX, with the license and
attribution that assets/sfx/LICENSES.md gives), each with tags (what it is,
what it fits). A clip's moments are the cuts that join its parts and its
spoken words, in the order of the render (clip_moments), numbered in the
prompt (prompts/sfx.md). The LLM picks moments and describes the sound it
wants with tags from the pack (SfxPick); search_sfx finds the sound that
has most of them, and place_sfx puts it there: a cut gets the sound so
that its middle falls on the cut, a word gets it from the word's start.
Items go on the sfx track (sfx_items, merge_sfx) with ids that start with
AUTO_ID, so a second run replaces the earlier one's items and keeps the
owner's own.

Sounds are not generated from a prompt: no local sound effect model is
open-licensed (docs/decisions.md), so the pack is searched instead.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from clipforge.llm import LLMClient, reply_json
from clipforge.models import Clip, SfxPick, SfxReply, TrackItem
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.pipeline.sections import played_spans

logger = logging.getLogger(__name__)

SFX_DIR = Path(__file__).resolve().parents[3] / "assets" / "sfx"
SFX_LICENSE = "CC0-1.0"
PROMPT = PROMPTS_DIR / "sfx.md"
AUTO_ID = "auto-sfx"
# How loud an auto sound is next to the clip's voice (AudioProps.volume).
SFX_VOLUME = 0.6
# Sounds are at least this many seconds apart (the prompt says so too).
MIN_GAP_S = 2.0
# A sound on a cut starts at most this long before it, so its middle (a
# whoosh's peak) falls on the cut.
CUT_LEAD_MAX_S = 0.4
# A sound that would last less than this in the clip is not placed.
MIN_SOUND_S = 0.05
# Seconds below which two cut points of a clip are the same join.
JOIN_EPSILON = 1e-6

MomentKind = Literal["cut", "word"]


class SfxError(RuntimeError):
    """The LLM sent no valid sound effects for a clip."""


@dataclass(frozen=True)
class BundledSfx:
    """A sound of assets/sfx: its file name, title, tags and length in
    seconds."""

    file: str
    title: str
    tags: tuple[str, ...]
    seconds: float

    @property
    def attribution(self) -> str:
        """The attribution the library shows (CC0 needs none)."""
        return f'"{self.title}" by ClipForge, {SFX_LICENSE} (assets/sfx)'


BUNDLED_SFX: tuple[BundledSfx, ...] = (
    BundledSfx(
        "whoosh_swift.flac",
        "Swift Whoosh",
        ("whoosh", "transition", "cut", "swipe", "fast"),
        0.5,
    ),
    BundledSfx(
        "whoosh_soft.flac",
        "Soft Whoosh",
        ("whoosh", "transition", "cut", "soft", "slow"),
        0.9,
    ),
    BundledSfx(
        "tick_click.flac", "Click", ("click", "tick", "cut", "ui", "small"), 0.06
    ),
    BundledSfx(
        "pop_bubble.flac",
        "Bubble Pop",
        ("pop", "emphasis", "light", "ui", "word"),
        0.15,
    ),
    BundledSfx(
        "ding_bell.flac", "Bell Ding", ("ding", "bell", "emphasis", "idea", "win"), 1.0
    ),
    BundledSfx(
        "sparkle_chime.flac",
        "Sparkle Chime",
        ("sparkle", "chime", "magic", "positive", "emphasis"),
        1.3,
    ),
    BundledSfx(
        "impact_boom.flac",
        "Deep Boom",
        ("impact", "boom", "dramatic", "reveal", "hit"),
        1.2,
    ),
    BundledSfx(
        "riser_swell.flac",
        "Tension Riser",
        ("riser", "build", "tension", "dramatic", "reveal"),
        1.6,
    ),
    BundledSfx(
        "rimshot_badum.flac",
        "Rimshot",
        ("rimshot", "punchline", "joke", "comedy", "drums"),
        1.4,
    ),
    BundledSfx(
        "crowd_laugh.flac",
        "Crowd Laugh",
        ("laugh", "crowd", "punchline", "joke", "comedy"),
        3.8,
    ),
)


@dataclass(frozen=True)
class Moment:
    """A moment of a rendered clip that a sound can go on: time, in seconds
    from its start; kind, a "cut" (where two parts join) or a "word" (where
    it starts); text, that word."""

    time: float
    kind: MomentKind
    text: str = ""


@dataclass(frozen=True)
class Placement:
    """A sound at a place of the rendered clip: seconds from its start to
    its end, and the moment it is for."""

    sound: BundledSfx
    start: float
    end: float
    moment: Moment


def bundled_sfx(path: Path | str) -> BundledSfx | None:
    """Return the pack's sound whose file is named like path, or None."""
    name = Path(path).name
    return next((sound for sound in BUNDLED_SFX if sound.file == name), None)


def pack_tags() -> list[str]:
    """Return every tag of the pack, sorted."""
    return sorted({tag for sound in BUNDLED_SFX for tag in sound.tags})


def search_sfx(
    tags: Sequence[str],
    avoid: Sequence[BundledSfx] = (),
    pack: Sequence[BundledSfx] = BUNDLED_SFX,
) -> BundledSfx | None:
    """Return the sound of pack that has most of tags (not case sensitive;
    the first of the pack on a tie), or None if none has any. A sound not in
    avoid wins over one that is, even with fewer tags, so a clip does not
    get the same sound twice while there is another that fits."""
    wanted = {tag.strip().lower() for tag in tags}
    ranked = [
        (sound in avoid, -len(wanted & set(sound.tags)), index, sound)
        for index, sound in enumerate(pack)
        if wanted & set(sound.tags)
    ]
    return min(ranked, key=lambda item: item[:3])[3] if ranked else None


def clip_joins(clip: Clip, fps: int) -> list[float]:
    """Return when the render of clip at fps frames a second joins two
    parts that are not next to each other in the source (a cut, or a
    section after another), in seconds from its start, in order."""
    spans = played_spans(clip.start, clip.end, clip.segments, clip.cut_ranges, fps)
    joins, elapsed = [], 0.0
    for index, (start, end) in enumerate(spans):
        if index and abs(start - spans[index - 1][1]) > JOIN_EPSILON:
            joins.append(elapsed)
        elapsed += end - start
    return joins


def clip_moments(words: Sequence[CaptionWord], joins: Sequence[float]) -> list[Moment]:
    """Return the cuts at joins (seconds) and the words (CaptionWord, in
    milliseconds from the clip's start) as moments in time order, a cut
    before the word that starts at the same time."""
    moments = [Moment(time, "cut") for time in joins]
    moments += [
        Moment(word.start / 1000, "word", word.text.strip())
        for word in words
        if word.text.strip()
    ]
    return sorted(moments, key=lambda moment: (moment.time, moment.kind != "cut"))


def system_prompt(max_items: int) -> str:
    """Return the system prompt: sfx.md with the pack's tags, the most
    sounds to place and SfxReply's JSON Schema."""
    schema = json.dumps(SfxReply.model_json_schema(), indent=2)
    tags = ", ".join(pack_tags())
    fields = {"tags": tags, "max_items": str(max_items), "gap": f"{MIN_GAP_S:g}"}
    return fill(PROMPT, {**fields, "schema": schema})


def user_prompt(moments: Sequence[Moment], errors: str | None = None) -> str:
    """Return the user message that lists moments, one per line as
    "<number>: cut at <t>s" or "<number>: <t>s <word>"; errors, given when
    the previous reply was not valid, asks to reply again."""
    lines = [
        f"{number}: cut at {moment.time:.2f}s"
        if moment.kind == "cut"
        else f"{number}: {moment.time:.2f}s {moment.text}"
        for number, moment in enumerate(moments)
    ]
    text = "The moments of the clip:\n" + "\n".join(lines)
    if errors is None:
        return text
    return (
        f"{text}\n\nYour previous reply was not valid:\n{errors}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def pick_problems(
    picks: Sequence[SfxPick], moments: Sequence[Moment], max_items: int
) -> list[tuple[int, str]]:
    """Return what is wrong with each of picks, as (its index, problem), in
    order: a moment the clip does not have, one picked before, a sound less
    than MIN_GAP_S from an earlier usable pick, tags that no sound of the
    pack has, or a pick past the first max_items usable ones."""
    problems: list[tuple[int, str]] = []
    usable: list[SfxPick] = []
    for index, pick in enumerate(picks):
        if pick.moment >= len(moments):
            problems.append((index, f"moment {pick.moment} does not exist"))
            continue
        time = moments[pick.moment].time
        if any(other.moment == pick.moment for other in usable):
            problems.append((index, f"moment {pick.moment} is picked twice"))
        elif any(abs(moments[o.moment].time - time) < MIN_GAP_S for o in usable):
            problems.append((index, f"moment {pick.moment} is too close to another"))
        elif search_sfx(pick.tags) is None:
            problems.append((index, f"no sound has the tags {pick.tags}"))
        elif len(usable) >= max_items:
            problems.append((index, f"more than {max_items} sounds"))
        else:
            usable.append(pick)
    return problems


def usable_picks(
    picks: Sequence[SfxPick], moments: Sequence[Moment], max_items: int
) -> list[SfxPick]:
    """Return the picks that pick_problems finds nothing wrong with."""
    wrong = {index for index, _ in pick_problems(picks, moments, max_items)}
    return [pick for index, pick in enumerate(picks) if index not in wrong]


def find_sfx(
    llm: LLMClient, moments: Sequence[Moment], max_items: int, clip_id: int
) -> list[SfxPick]:
    """Ask llm for the sounds of clip clip_id, which has moments (no
    sounds, and the LLM is not asked, if it has none), and return the usable
    picks in time order. A reply that is not valid is sent back with its
    errors up to curate.MAX_RETRIES times; after the last try the usable
    picks of a valid reply are kept. Raises SfxError if no reply was valid
    and LLMError if the LLM cannot be reached."""
    if not moments:
        return []
    system = system_prompt(max_items)
    errors, picks = None, None
    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.complete_json(system, user_prompt(moments, errors))
        try:
            picks = SfxReply.model_validate_json(reply_json(reply)).sounds
        except ValidationError as exc:
            errors = describe_errors(exc)
        else:
            problems = pick_problems(picks, moments, max_items)
            errors = "\n".join(f"- sounds.{i}: {p}" for i, p in problems) or None
            if errors is None:
                break
        logger.warning(
            "clip %d: sfx reply %d of %d is not valid:\n%s",
            clip_id,
            attempt,
            MAX_RETRIES + 1,
            errors,
        )
    if picks is None:
        raise SfxError(
            f"the LLM sent no valid sound effects for clip {clip_id} "
            f"in {MAX_RETRIES + 1} tries"
        )
    kept = usable_picks(picks, moments, max_items)
    return sorted(kept, key=lambda pick: moments[pick.moment].time)


def place_sfx(
    picks: Sequence[SfxPick], moments: Sequence[Moment], length: float
) -> list[Placement]:
    """Return where the sounds of picks (usable ones, in time order) go in a
    clip of length seconds: each pick's best sound (search_sfx, avoiding
    those placed already), on a cut from half its length (at most
    CUT_LEAD_MAX_S) before it, on a word from its start; the end is cut at
    the clip's end, and a sound left under MIN_SOUND_S is dropped."""
    placed: list[Placement] = []
    for pick in picks:
        moment = moments[pick.moment]
        sound = search_sfx(pick.tags, [p.sound for p in placed])
        if sound is None:
            continue
        lead = min(sound.seconds / 2, CUT_LEAD_MAX_S) if moment.kind == "cut" else 0
        start = max(moment.time - lead, 0.0)
        end = min(start + sound.seconds, length)
        if end - start >= MIN_SOUND_S:
            placed.append(Placement(sound, round(start, 3), round(end, 3), moment))
    return placed


def sfx_items(
    placements: Sequence[Placement], asset_ids: Mapping[str, int]
) -> list[TrackItem]:
    """Return the sfx track items of placements, each playing the library
    asset of its sound's file (asset_ids by file name; a sound with none is
    left out), at SFX_VOLUME, with ids AUTO_ID-1, AUTO_ID-2, ..."""
    items: list[TrackItem] = []
    for placement in placements:
        asset_id = asset_ids.get(placement.sound.file)
        if asset_id is None:
            logger.warning("sfx %s is not in the library", placement.sound.file)
            continue
        items.append(
            TrackItem(
                id=f"{AUTO_ID}-{len(items) + 1}",
                kind="audio",
                asset_id=asset_id,
                start=placement.start,
                end=placement.end,
                props={"volume": SFX_VOLUME},
            )
        )
    return items


def merge_sfx(track: Sequence[TrackItem], auto: Sequence[TrackItem]) -> list[TrackItem]:
    """Return the sfx track with its earlier auto items (ids that start with
    AUTO_ID) replaced by auto, the owner's own items kept, in time order."""
    own = [item for item in track if not item.id.startswith(AUTO_ID)]
    return sorted([*own, *auto], key=lambda item: item.start)
