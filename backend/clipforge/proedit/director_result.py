"""What the Director made (director_llm.director_plan) and the lines the
run's notes show of it (SPEC-v3 3.8)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import get_args

from clipforge.models import ProEditPlan
from clipforge.proedit.composites import Composite
from clipforge.proedit.director_build import LeftOut
from clipforge.proedit.director_cost import CostEstimate
from clipforge.proedit.snap import PlanNote


@dataclass(frozen=True)
class DirectorResult:
    """A plan and how it was made: the post-processing notes, the estimate
    shown before the run (None without an LLM), the LLM calls made, the
    problems of each invalid reply, the tokens the answers reported and
    their cost (None: no price set), why the rule-based Director made
    the plan (None: the LLM did) and then the composite moves (Skull
    Moment, bass drop) it left out."""

    plan: ProEditPlan
    notes: list[PlanNote]
    estimate: CostEstimate | None = None
    calls: int = 0
    invalid_replies: list[list[str]] = field(default_factory=list)
    tokens: int = 0
    cost_usd: float | None = None
    fallback: str | None = None
    left_out: list[LeftOut] = field(default_factory=list)

    def edit_notes(self) -> list[str]:
        """One line per item post-processing moved or dropped ("Dropped
        shake at 16.37 s: why") and per composite move left out ("Left out
        skull_moment at 16.37 s: why"), in time order."""
        lines = [(n.t or 0.0, n.line()) for n in self.notes]
        lines += [
            (lo.t, f"Left out {lo.move} at {lo.t:.2f} s: {lo.why}")
            for lo in self.left_out
        ]
        return [line for _, line in sorted(lines, key=lambda n: n[0])]


def composite_left_outs(left_out: Sequence[LeftOut]) -> list[LeftOut]:
    """The composite moves (Skull Moment, bass drop) of left_out."""
    return [lo for lo in left_out if lo.move in get_args(Composite)]
