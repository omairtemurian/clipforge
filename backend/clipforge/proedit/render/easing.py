"""Easing curves of Pro Edit motion (SPEC-v3 3.3): how a zoom or pan moves
from its start value to its end value. ease(name, p) maps the progress p
(0..1) to the share of the change made: 0 at p 0, 1 at p 1.

- linear: p.
- ease_in_out: cubic, slow at both ends (easeInOutCubic).
- back: runs past the end by about 10 % of the change and settles back
  (easeOutBack, overshoot constant 1.70158).
- elastic: springs past the end and rings down (easeOutElastic, period 1/3
  of the move).

The formulas are those of https://easings.net (Robert Penner's easing
equations); back and elastic overshoot, so a zoom using them may go past
its end scale for a few frames.
"""

import math

from clipforge.proedit.edl_params import Ease

BACK_OVERSHOOT = 1.70158
ELASTIC_PERIOD = 2 * math.pi / 3


def ease(name: Ease, p: float) -> float:
    """Return the share of the change made at progress p (clamped to 0..1)
    on the curve name (module docstring)."""
    p = min(max(p, 0.0), 1.0)
    if name == "linear":
        return p
    if name == "ease_in_out":
        return 4 * p**3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
    if name == "back":
        return 1 + (BACK_OVERSHOOT + 1) * (p - 1) ** 3 + BACK_OVERSHOOT * (p - 1) ** 2
    if p in (0.0, 1.0):
        return p
    return 2 ** (-10 * p) * math.sin((10 * p - 0.75) * ELASTIC_PERIOD) + 1
