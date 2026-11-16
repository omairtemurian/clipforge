"""The Edit Decision List of a Pro Edit plan (SPEC-v3 3.1): every kind has typed
params (a union discriminated by kind), and a plan is checked against the
clip's duration and the overlap rules of its tracks. Intensity budgets and
snapping are separate (TASK-204)."""

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from clipforge.models import EdlItem, EdlKind, EdlSource, ProEditPlan
from clipforge.proedit import edl_params as p

Track = Literal[
    "zoom", "fx", "grade", "overlay", "captions", "sfx", "music", "audio_fx"
]

TRACK_OF_KIND: dict[EdlKind, Track] = {
    "zoom_punch": "zoom",
    "zoom_push": "zoom",
    "zoom_out_reveal": "zoom",
    "pan": "zoom",
    "shake": "fx",
    "flash": "fx",
    "glitch": "fx",
    "rgb_split": "fx",
    "freeze_frame": "fx",
    "speed_ramp": "fx",
    "slowmo": "fx",
    "transition": "fx",
    "grade_change": "grade",
    "vignette": "grade",
    "grain": "grade",
    "overlay": "overlay",
    "text_pop": "overlay",
    "emoji_pop": "overlay",
    "caption_style": "captions",
    "sfx": "sfx",
    "music_bed": "music",
    "silence_before_drop": "music",
    "audio_fx": "audio_fx",
}

# Stackable kinds may overlap each other, at most `limit` at a time; they do
# not conflict with the other kinds of their track.
STACK_GROUPS: tuple[tuple[frozenset[EdlKind], int], ...] = (
    (frozenset({"text_pop", "emoji_pop"}), 3),
    (frozenset({"sfx"}), 2),
)
STACKABLE: frozenset[EdlKind] = frozenset().union(*(g for g, _ in STACK_GROUPS))
# Layer kinds are drawn by a step of their own on top of the other kinds of
# their track (vignette and grain over a grade, a shake over a freeze frame),
# so they only conflict with items of their own kind.
LAYER_KINDS: frozenset[EdlKind] = frozenset({"vignette", "grain", "shake"})

# Times are compared to the nearest microsecond.
EPSILON = 1e-6


class EdlValidationError(ValueError):
    """A plan or an item broke a rule; problems lists every one, each naming
    the item ids, so the Director can be asked to fix them."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class _Item(BaseModel):
    id: int = Field(ge=1)
    t_start: float = Field(ge=0)
    t_end: float = Field(gt=0)
    reason: str = Field(min_length=1, pattern=r"\S")
    source: EdlSource = "auto"


class ZoomPunchItem(_Item):
    kind: Literal["zoom_punch"]
    params: p.ZoomPunchParams


class ZoomPushItem(_Item):
    kind: Literal["zoom_push"]
    params: p.ZoomPushParams


class ZoomOutRevealItem(_Item):
    kind: Literal["zoom_out_reveal"]
    params: p.ZoomOutRevealParams


class PanItem(_Item):
    kind: Literal["pan"]
    params: p.PanParams


class ShakeItem(_Item):
    kind: Literal["shake"]
    params: p.ShakeParams


class FlashItem(_Item):
    kind: Literal["flash"]
    params: p.FlashParams


class GlitchItem(_Item):
    kind: Literal["glitch"]
    params: p.GlitchParams


class RgbSplitItem(_Item):
    kind: Literal["rgb_split"]
    params: p.RgbSplitParams


class FreezeFrameItem(_Item):
    kind: Literal["freeze_frame"]
    params: p.FreezeFrameParams


class SpeedRampItem(_Item):
    kind: Literal["speed_ramp"]
    params: p.SpeedRampParams


class SlowmoItem(_Item):
    kind: Literal["slowmo"]
    params: p.SlowmoParams


class TransitionItem(_Item):
    kind: Literal["transition"]
    params: p.TransitionParams


class GradeChangeItem(_Item):
    kind: Literal["grade_change"]
    params: p.GradeChangeParams


class VignetteItem(_Item):
    kind: Literal["vignette"]
    params: p.VignetteParams


class GrainItem(_Item):
    kind: Literal["grain"]
    params: p.GrainParams


class OverlayItem(_Item):
    kind: Literal["overlay"]
    params: p.OverlayParams


class TextPopItem(_Item):
    kind: Literal["text_pop"]
    params: p.TextPopParams


class EmojiPopItem(_Item):
    kind: Literal["emoji_pop"]
    params: p.EmojiPopParams


class CaptionStyleItem(_Item):
    kind: Literal["caption_style"]
    params: p.CaptionStyleParams


class SfxItem(_Item):
    kind: Literal["sfx"]
    params: p.SfxParams


class MusicBedItem(_Item):
    kind: Literal["music_bed"]
    params: p.MusicBedParams


class SilenceBeforeDropItem(_Item):
    kind: Literal["silence_before_drop"]
    params: p.SilenceBeforeDropParams


class AudioFxItem(_Item):
    kind: Literal["audio_fx"]
    params: p.AudioFxParams


TypedEdlItem = Annotated[
    ZoomPunchItem
    | ZoomPushItem
    | ZoomOutRevealItem
    | PanItem
    | ShakeItem
    | FlashItem
    | GlitchItem
    | RgbSplitItem
    | FreezeFrameItem
    | SpeedRampItem
    | SlowmoItem
    | TransitionItem
    | GradeChangeItem
    | VignetteItem
    | GrainItem
    | OverlayItem
    | TextPopItem
    | EmojiPopItem
    | CaptionStyleItem
    | SfxItem
    | MusicBedItem
    | SilenceBeforeDropItem
    | AudioFxItem,
    Field(discriminator="kind"),
]
_ITEM_ADAPTER: TypeAdapter[TypedEdlItem] = TypeAdapter(TypedEdlItem)

assert set(TRACK_OF_KIND) == set(get_args(EdlKind)), "a kind has no track"


def _label(item: EdlItem) -> str:
    return f"item {item.id} ({item.kind})"


def _span(item: EdlItem) -> str:
    return f"{item.t_start:g}-{item.t_end:g} s"


def _error_text(error: ValidationError) -> str:
    texts = []
    for e in error.errors():
        where = ".".join(str(part) for part in e["loc"][1:])
        texts.append(f"{where}: {e['msg']}" if where else e["msg"])
    return "; ".join(texts)


def parse_item(item: EdlItem) -> TypedEdlItem:
    """Return the item with its params as the typed model of its kind (the
    defaults filled in); raise EdlValidationError naming the item and the
    bad params."""
    try:
        typed = _ITEM_ADAPTER.validate_python(item.model_dump())
    except ValidationError as error:
        raise EdlValidationError([f"{_label(item)}: {_error_text(error)}"]) from error
    return typed


def is_loop_ending(item: EdlItem) -> bool:
    """Whether item is the loop-friendly ending (a loop transition): the
    owner's option, pinned to the clip end (proedit/retention.py)."""
    return item.kind == "transition" and item.params.get("type") == "loop"


def _duration_problems(item: EdlItem, clip_duration: float) -> list[str]:
    problems: list[str] = []
    if item.t_end > clip_duration + EPSILON:
        problems.append(
            f"{_label(item)} ends at {item.t_end:g} s, past the clip end "
            f"at {clip_duration:g} s"
        )
    if is_loop_ending(item) and item.t_end < clip_duration - p.LOOP_END_SLACK_S:
        problems.append(
            f"{_label(item)} is a loop ending at {item.t_end:g} s; it must end "
            f"at the clip end at {clip_duration:g} s"
        )
    if item.kind == "silence_before_drop":
        length = item.t_end - item.t_start
        low = p.SILENCE_MIN_S - p.SILENCE_SLACK_S
        high = p.SILENCE_MAX_S + p.SILENCE_SLACK_S
        if not low <= length <= high:
            problems.append(
                f"{_label(item)} lasts {length:g} s; the silence before a "
                f"drop lasts {p.SILENCE_MIN_S:g} to {p.SILENCE_MAX_S:g} s"
            )
    return problems


def excludes(a: EdlKind, b: EdlKind) -> bool:
    """Whether items of kinds a and b may not overlap: both exclusive kinds of
    one track, and when either is a layer kind, the same kind."""
    if a in STACKABLE or b in STACKABLE or TRACK_OF_KIND[a] != TRACK_OF_KIND[b]:
        return False
    return a == b or not (a in LAYER_KINDS or b in LAYER_KINDS)


def _overlaps(a: EdlItem, b: EdlItem) -> bool:
    return a.t_start < b.t_end - EPSILON and b.t_start < a.t_end - EPSILON


def _overlap_problems(items: list[EdlItem]) -> list[str]:
    problems: list[str] = []
    for track in get_args(Track):
        exclusive = sorted(
            (
                i
                for i in items
                if TRACK_OF_KIND[i.kind] == track and i.kind not in STACKABLE
            ),
            key=lambda i: (i.t_start, i.id),
        )
        for n, a in enumerate(exclusive):
            for b in exclusive[n + 1 :]:
                if b.t_start >= a.t_end - EPSILON:
                    break
                if excludes(a.kind, b.kind) and _overlaps(a, b):
                    problems.append(
                        f"items {a.id} ({a.kind}, {_span(a)}) and {b.id} "
                        f"({b.kind}, {_span(b)}) overlap on the {track} track"
                    )
    return problems


def _stack_problems(items: list[EdlItem]) -> list[str]:
    problems: list[str] = []
    for kinds, limit in STACK_GROUPS:
        group = sorted(
            (i for i in items if i.kind in kinds), key=lambda i: (i.t_start, i.id)
        )
        reported: set[int] = set()
        for item in group:
            # The most overlapping moment of a set of intervals is the start
            # of one of them.
            live = [
                o
                for o in group
                if o.t_start <= item.t_start + EPSILON
                and o.t_end > item.t_start + EPSILON
            ]
            if len(live) > limit and item.id not in reported:
                reported.update(o.id for o in live)
                ids = ", ".join(str(o.id) for o in live)
                names = " and ".join(sorted(kinds))
                problems.append(
                    f"items {ids} are {len(live)} {names} items at "
                    f"{item.t_start:g} s; at most {limit} may be on screen "
                    f"or sound together"
                )
    return problems


def plan_problems(plan: ProEditPlan, clip_duration: float) -> list[str]:
    """List every rule that the plan breaks for a clip of clip_duration
    seconds (empty when it is valid): typed params, the clip end, the
    overlaps per track and the stackable limits."""
    problems: list[str] = []
    for item in plan.items:
        try:
            parse_item(item)
        except EdlValidationError as error:
            problems.extend(error.problems)
        problems.extend(_duration_problems(item, clip_duration))
    problems.extend(track_problems(plan.items))
    return problems


def track_problems(items: list[EdlItem]) -> list[str]:
    """List the overlaps per track and the stackable limits that items
    break (no params or clip end checks)."""
    return [*_overlap_problems(items), *_stack_problems(items)]


def validate_plan(plan: ProEditPlan, clip_duration: float) -> list[TypedEdlItem]:
    """Return the plan's items with typed params, in time order; raise
    EdlValidationError with every problem when the plan is not valid for a
    clip of clip_duration seconds."""
    problems = plan_problems(plan, clip_duration)
    if problems:
        raise EdlValidationError(problems)
    return sorted(
        (parse_item(item) for item in plan.items),
        key=lambda i: (i.t_start, i.id),
    )
