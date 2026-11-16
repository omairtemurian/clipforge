"""The typed parameters of every kind of edit decision (SPEC-v3 3.1). Each kind
has its own model; unknown keys are rejected so a misspelled parameter of the
Director or the editor is an error and not a silent default."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Ease = Literal["linear", "ease_in_out", "back", "elastic"]
PopAnimation = Literal["none", "fade", "pop", "slide", "bounce"]
Unit = Annotated[float, Field(ge=0, le=1)]
HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
# The silence before a drop lasts 100-300 ms (SPEC-v3 3.3), to the nearest
# 20 ms because times are snapped to the frame grid.
SILENCE_MIN_S = 0.1
SILENCE_MAX_S = 0.3
SILENCE_SLACK_S = 0.02
# A loop ending ends at the clip end, give or take a frame (the clip end
# need not be on the frame grid).
LOOP_END_SLACK_S = 0.05


class Params(BaseModel):
    """Base of the parameter models: no unknown keys."""

    model_config = ConfigDict(extra="forbid")


class ZoomPunchParams(Params):
    """A fast punch-in: scale 110-130 % that is instant (0 frames) or eased
    over 2-4 frames, centered on the face track by default."""

    scale: float = Field(default=1.2, ge=1.1, le=1.3)
    ease: Ease = "ease_in_out"
    ease_frames: int = Field(default=0, ge=0, le=4)
    center: Literal["face", "frame"] = "face"

    @model_validator(mode="after")
    def _instant_or_two_to_four(self) -> Self:
        if self.ease_frames == 1:
            raise ValueError("ease_frames must be 0 (instant) or 2 to 4")
        return self


class ZoomPushParams(Params):
    """A slow push-in during the setup, e.g. 100 -> 112 %."""

    scale_from: float = Field(default=1.0, ge=1.0, le=1.5)
    scale_to: float = Field(default=1.12, ge=1.0, le=1.5)
    ease: Ease = "ease_in_out"
    center: Literal["face", "frame"] = "face"

    @model_validator(mode="after")
    def _grows(self) -> Self:
        if self.scale_to <= self.scale_from:
            raise ValueError("scale_to must be larger than scale_from")
        return self


class ZoomOutRevealParams(Params):
    """A zoom-out after the payoff, back to the full frame by default."""

    scale_from: float = Field(default=1.2, ge=1.05, le=1.5)
    scale_to: float = Field(default=1.0, ge=1.0, le=1.5)
    ease: Ease = "ease_in_out"
    center: Literal["face", "frame"] = "face"

    @model_validator(mode="after")
    def _shrinks(self) -> Self:
        if self.scale_to >= self.scale_from:
            raise ValueError("scale_to must be smaller than scale_from")
        return self


class PanParams(Params):
    """A keyframed pan of the crop center, in shares of the frame (0 left or
    top, 1 right or bottom), at a scale of at least 100 %."""

    from_x: Unit
    from_y: Unit
    to_x: Unit
    to_y: Unit
    scale: float = Field(default=1.1, ge=1.0, le=2.0)
    ease: Ease = "ease_in_out"

    @model_validator(mode="after")
    def _moves(self) -> Self:
        if (self.from_x, self.from_y) == (self.to_x, self.to_y):
            raise ValueError("a pan must end somewhere else than it starts")
        return self


class ShakeParams(Params):
    """A camera shake: strength 0-1 of the frame and its rate in Hz."""

    strength: float = Field(default=0.5, gt=0, le=1)
    frequency_hz: float = Field(default=12.0, ge=1, le=30)
    seed: int = 0


class FlashParams(Params):
    """A flash of a color; peak is its strongest opacity."""

    color: Literal["white", "black"] = "white"
    peak: float = Field(default=0.8, gt=0, le=1)


class GlitchParams(Params):
    """A digital glitch; the seed makes the render deterministic."""

    strength: float = Field(default=0.5, gt=0, le=1)
    seed: int = 0


class RgbSplitParams(Params):
    """The red and blue channels shifted apart by offset_px at angle_deg."""

    offset_px: float = Field(default=8.0, gt=0, le=40)
    angle_deg: float = Field(default=0.0, ge=-180, le=180)


class FreezeFrameParams(Params):
    """Holds the frame at t_start until t_end; has no parameters."""


class SpeedRampParams(Params):
    """The speed changes from speed_from to speed_to over the item."""

    speed_from: float = Field(default=1.0, ge=0.1, le=4.0)
    speed_to: float = Field(default=0.4, ge=0.1, le=4.0)
    ease: Ease = "ease_in_out"

    @model_validator(mode="after")
    def _changes(self) -> Self:
        if self.speed_from == self.speed_to:
            raise ValueError("speed_to must differ from speed_from")
        return self


class SlowmoParams(Params):
    """Slow motion at speed (a share of normal), eased in and out over
    ramp_s seconds each."""

    speed: float = Field(default=0.5, ge=0.1, lt=1.0)
    ramp_s: float = Field(default=0.15, ge=0, le=1)


class TransitionParams(Params):
    """How the picture changes at the item; whoosh adds the matching sound.
    A loop transition is the loop-friendly ending (proedit/retention.py):
    the clip's last frames blend into its first frame and its sound into
    its opening sound, so it must end at the clip end."""

    type: Literal["crossfade", "whip", "zoom", "glitch", "flash", "loop"] = "crossfade"
    whoosh: bool = True


class GradeChangeParams(Params):
    """A color grade: black and white, dark, desaturated or a bundled LUT
    (named in lut, which only the lut look takes). normalize corrects
    exposure and white balance first; skin_protect caps the saturation
    change of skin colors (dark, desat and lut; black and white takes all
    color by design)."""

    look: Literal["bw", "dark", "desat", "lut"]
    amount: float = Field(default=1.0, gt=0, le=1)
    lut: str | None = Field(default=None, min_length=1)
    skin_protect: bool = True
    normalize: bool = True

    @model_validator(mode="after")
    def _lut_only_for_lut(self) -> Self:
        if self.look == "lut" and self.lut is None:
            raise ValueError("the lut look needs a lut name")
        if self.look != "lut" and self.lut is not None:
            raise ValueError("lut is only for the lut look")
        return self


class VignetteParams(Params):
    """A darkened frame edge."""

    strength: float = Field(default=0.4, gt=0, le=1)


class GrainParams(Params):
    """Film grain; the seed makes the render deterministic."""

    strength: float = Field(default=0.2, gt=0, le=1)
    seed: int = 0


class OverlayParams(Params):
    """An overlay asset (an asset id or the name of a procedural overlay),
    placed on the screen, a face or an object."""

    asset: str = Field(min_length=1)
    anchor: Literal["screen", "face", "object"] = "screen"
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    scale: float = Field(default=0.3, gt=0, le=2)
    rotation_deg: float = Field(default=0.0, ge=-180, le=180)
    animation: PopAnimation = "pop"


class TextPopParams(Params):
    """A short text that pops in."""

    text: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#FFFFFF", pattern=HEX_COLOR)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    scale: float = Field(default=1.0, gt=0, le=3)
    animation: PopAnimation = "pop"


class EmojiPopParams(Params):
    """An emoji that pops in."""

    emoji: str = Field(min_length=1, max_length=8)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    scale: float = Field(default=1.0, gt=0, le=3)
    animation: PopAnimation = "pop"


class CaptionStyleParams(Params):
    """A kinetic per-word caption style (proedit/captions.py)."""

    style: Literal["pop", "bounce", "single_word", "neon"] = "pop"
    shake_on_loud: bool = False
    emphasis_scale: float = Field(default=1.2, ge=1.0, le=1.6)
    emoji: bool = False


class SfxParams(Params):
    """A sound effect asset (a library asset id or a bundled sound's name) at
    gain_db, pitched by pitch_semitones (varispeed: a higher pitch also
    plays faster). fit "natural" plays it from t_start at its own length,
    cut at t_end; "stretch" time-stretches it to last the item exactly (a
    whoosh matched to its motion, proedit/audio)."""

    asset: str = Field(min_length=1)
    gain_db: float = Field(default=-6.0, ge=-40, le=6)
    pitch_semitones: float = Field(default=0.0, ge=-12, le=12)
    fit: Literal["natural", "stretch"] = "natural"


class MusicBedParams(Params):
    """A music bed asset (a library asset id or a bundled track's name) at
    gain_db, looped; duck lowers it by duck_db under speech. offset is the
    music second the bed starts at; None continues the bed of the same
    asset before it as if the music had played on (0 for the first), so
    beds around a silence_before_drop are one piece of music."""

    asset: str = Field(min_length=1)
    gain_db: float = Field(default=-18.0, ge=-40, le=0)
    duck: bool = True
    duck_db: float = Field(default=12.0, ge=0, le=24)
    offset: float | None = Field(default=None, ge=0)


class SilenceBeforeDropParams(Params):
    """The music goes silent for 100-300 ms before the drop; has no
    parameters (the item's length is the silence)."""


class AudioFxParams(Params):
    """An audio effect on the program sound."""

    effect: Literal["bass_boost", "reverb_tail", "lowpass_sweep", "stutter"]
    amount: float = Field(default=0.5, gt=0, le=1)
