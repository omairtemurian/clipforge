"""The audio effects of a Pro Edit render (SPEC-v3 3.1, 3.3): audio_fx items
on the program sound (speech, SFX and music), each on its window only.

An item splits the sound in two: the dry part is gated off in the window
and the wet part, run through the effect, gated on (envelope.gate_filter:
on every sample, ramping over FX_RAMP_S inside the window's edges, so the
two add up to the untouched sound outside it); they are added back up
(`amix`, normalize=0). The effects, by params.amount (0-1]:
- bass_boost: a low shelf (`bass`) at BASS_HZ raising the lows by
  amount * BASS_MAX_DB.
- reverb_tail: the window's sound plus echoes (`aecho` in and out gain 1,
  so the window itself is unchanged) at REVERB_DELAYS_MS, decaying from
  amount * REVERB_DECAY; the echoes ring on past the window (the gate is
  before the echo).
- lowpass_sweep: a `lowpass` whose cutoff opens exponentially from
  SWEEP_OPEN_HZ * (SWEEP_FLOOR_HZ / SWEEP_OPEN_HZ) ** amount at the start to
  SWEEP_OPEN_HZ at the end (muffled, opening into what follows), set every
  SWEEP_STEP_S by `asendcmd` (a command takes effect on the next audio
  frame).
- stutter: the window's first slice repeated over the window (`aloop`),
  2 + round(amount * STUTTER_EXTRA) times, each slice faded over
  STUTTER_FADE_S so the repeats do not click. `adelay`'s padding frames
  have no timestamp (the gate's t would be NaN): `asetpts=N/SR/TB` after
  it numbers them.
The items are applied in time order (the audio_fx track has no overlaps).
"""

from collections.abc import Sequence

from clipforge.proedit.audio.envelope import gate_filter
from clipforge.proedit.audio.sfx_mix import NO_SFX_FILTER, SAMPLE_RATE
from clipforge.proedit.edl import AudioFxItem, TypedEdlItem

FX_RAMP_S = 0.005
BASS_HZ = 100
BASS_MAX_DB = 12.0
REVERB_DELAYS_MS = (43, 79, 127, 181, 241, 317, 409)
REVERB_DECAY = 0.6
REVERB_FALLOFF = 0.75
SWEEP_OPEN_HZ = 20000.0
SWEEP_FLOOR_HZ = 200.0
SWEEP_STEP_S = 0.02
STUTTER_EXTRA = 6
STUTTER_FADE_S = 0.003


def fx_items(items: Sequence[TypedEdlItem]) -> list[AudioFxItem]:
    """Return the audio_fx items of items in time order."""
    effects = [item for item in items if isinstance(item, AudioFxItem)]
    return sorted(effects, key=lambda item: (item.t_start, item.id))


def sweep_hz(item: AudioFxItem, t: float) -> float:
    """Return the lowpass cutoff of a lowpass_sweep item at clip second t
    (clamped to its window)."""
    floor = SWEEP_OPEN_HZ * (SWEEP_FLOOR_HZ / SWEEP_OPEN_HZ) ** item.params.amount
    share = min(max((t - item.t_start) / (item.t_end - item.t_start), 0.0), 1.0)
    return float(floor * (SWEEP_OPEN_HZ / floor) ** share)


def sweep_filters(item: AudioFxItem) -> list[str]:
    """Return the filters of a lowpass_sweep item: the cutoff commands and
    the lowpass they steer."""
    name = f"lowpass@sweep{item.id}"
    steps = int((item.t_end - item.t_start) / SWEEP_STEP_S) + 1
    commands = ";".join(
        f"{t:.6f} {name} frequency {sweep_hz(item, t):.1f}"
        for t in (item.t_start + n * SWEEP_STEP_S for n in range(steps))
    )
    return [f"asendcmd=c='{commands}'", f"{name}=f={sweep_hz(item, item.t_start):.1f}"]


def stutter_filters(item: AudioFxItem) -> list[str]:
    """Return the filters that turn the sound into a stutter item's
    repeated slice, placed at its start."""
    length = item.t_end - item.t_start
    repeats = 2 + round(item.params.amount * STUTTER_EXTRA)
    size = round(length / repeats * SAMPLE_RATE)
    slice_s = size / SAMPLE_RATE
    fade = min(STUTTER_FADE_S, slice_s / 4)
    return [
        f"atrim=start={item.t_start:.6f}:duration={slice_s:.6f}",
        "asetpts=PTS-STARTPTS",
        f"afade=t=in:st=0:d={fade:.6f}",
        f"afade=t=out:st={slice_s - fade:.6f}:d={fade:.6f}",
        f"aloop=loop=-1:size={size}",
        f"atrim=duration={length:.6f}",
        "asetpts=N/SR/TB",
        f"adelay=delays={item.t_start * 1000:.3f}:all=1",
        "asetpts=N/SR/TB",
    ]


def wet_filters(item: AudioFxItem) -> list[str]:
    """Return the chain of item's wet part: its effect, gated to its
    window."""
    window = [(item.t_start, item.t_end)]
    gate = gate_filter(window, FX_RAMP_S, inside=True)
    amount = item.params.amount
    match item.params.effect:
        case "bass_boost":
            return [f"bass=g={amount * BASS_MAX_DB:.3f}:f={BASS_HZ}", gate]
        case "reverb_tail":
            decays = "|".join(
                f"{amount * REVERB_DECAY * REVERB_FALLOFF**n:.4f}"
                for n in range(len(REVERB_DELAYS_MS))
            )
            delays = "|".join(str(d) for d in REVERB_DELAYS_MS)
            echo = f"aecho=in_gain=1:out_gain=1:delays={delays}:decays={decays}"
            return [gate, echo]
        case "lowpass_sweep":
            return [*sweep_filters(item), gate]
        case "stutter":
            return [*stutter_filters(item), gate]


def fx_graph(items: Sequence[TypedEdlItem], source: str, out: str) -> str:
    """Return the filters that apply the audio_fx items of items to the
    sound labelled source, into out; source passes through untouched when
    there are none."""
    effects = fx_items(items)
    if not effects:
        return f"{source}{NO_SFX_FILTER}{out}"
    parts = [f"{source}aresample={SAMPLE_RATE}[fx_in0]"]
    for n, item in enumerate(effects):
        dry, wet, into = f"[fx{item.id}_dry]", f"[fx{item.id}_wet]", f"[fx_in{n + 1}]"
        gate = gate_filter([(item.t_start, item.t_end)], FX_RAMP_S, inside=False)
        parts += [
            f"[fx_in{n}]asplit=2{dry}[fx{item.id}_src]",
            f"{dry}{gate}[fx{item.id}_d]",
            f"[fx{item.id}_src]{','.join(wet_filters(item))}{wet}",
            f"[fx{item.id}_d]{wet}amix=inputs=2:duration=first:normalize=0{into}",
        ]
    parts.append(f"[fx_in{len(effects)}]{NO_SFX_FILTER}{out}")
    return ";".join(parts)
