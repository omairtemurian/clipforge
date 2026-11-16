"""What the LLM Director costs (SPEC-v3 1.6, 3.5): an estimate before it
runs, the month's Pro Edit spend in the usage meter and the monthly cap.

Every Director (and critic) call records its tokens in the usage meter as
PROEDIT (the Pro Edit category), with cost_usd = tokens x
proedit.usd_per_million_tokens when the owner set a price (no provider
reports one). The estimate counts CHARS_PER_TOKEN characters a token for the
system and user messages and for a reply as long as the rule-based plan of
the same clip; MAX_CALLS calls when every retry is needed. check_monthly_cap
raises ProEditCapExceeded (a UsageCapExceeded, so the API answers it like
the other caps) when the month's spend plus one call would pass
proedit.monthly_cap_usd.
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from clipforge import usage
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.proedit.config import ProEditConfig

PROEDIT = "proedit"
# A rough rule of thumb for English and JSON text (no tokenizer is bundled
# for every provider).
CHARS_PER_TOKEN = 4
MAX_CALLS = MAX_RETRIES + 1
TOKENS_PER_MILLION = 1_000_000


class ProEditCapExceeded(usage.UsageCapExceeded):
    """The Pro Edit monthly cap is reached; the message says how to go on."""


def tokens_of(text: str) -> int:
    """Return the estimated tokens of text."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def usd_per_token(cfg: ProEditConfig) -> float | None:
    """Return the owner's price of a token, None if none is set."""
    price = cfg.usd_per_million_tokens
    return None if price is None else price / TOKENS_PER_MILLION


def usd_text(usd: float) -> str:
    """Return usd for a sentence: "$0.25", "$0.0031" under a cent."""
    return f"${usd:,.2f}" if usd >= 0.01 or usd == 0 else f"${usd:.4f}"


class CostEstimate(BaseModel):
    """The estimated LLM use of a Director run: the tokens of one call
    (input and output) and their cost in USD (None: no price set), and the
    most calls a run makes (every retry)."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    max_calls: int = Field(ge=1)
    usd: float | None = Field(ge=0)

    @property
    def tokens(self) -> int:
        """The tokens of one call."""
        return self.input_tokens + self.output_tokens

    @property
    def max_usd(self) -> float | None:
        """The cost when every retry is needed."""
        return None if self.usd is None else self.usd * self.max_calls

    def text(self) -> str:
        """The estimate as the UI shows it before a run."""
        most = self.tokens * self.max_calls
        if self.usd is None or self.max_usd is None:
            return (
                f"About {self.tokens:,} LLM tokens, at most {most:,} if the "
                "Director must retry (no price set: proedit.usd_per_million_tokens)."
            )
        return (
            f"About {self.tokens:,} LLM tokens ({usd_text(self.usd)}), at most "
            f"{most:,} ({usd_text(self.max_usd)}) if the Director must retry."
        )


def estimate_cost(
    system: str, user: str, reply: str, cfg: ProEditConfig
) -> CostEstimate:
    """Return the estimate of a run that sends system and user and gets a
    reply about as long as reply."""
    input_tokens, output_tokens = tokens_of(system) + tokens_of(user), tokens_of(reply)
    price = usd_per_token(cfg)
    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        max_calls=MAX_CALLS,
        usd=None if price is None else (input_tokens + output_tokens) * price,
    )


def month_spend_usd(engine: Engine, now: datetime | None = None) -> float:
    """Return the USD that Pro Edit's priced LLM calls spent in the month of
    now (default: the current time)."""
    today = (usage.utc_now() if now is None else now).date()
    summary = usage.month_summary(engine, today)
    spent = next((k.cost_usd for k in summary.kinds if k.kind == PROEDIT), None)
    return spent or 0.0


@contextmanager
def metered(
    engine: Engine | None,
    project_id: int | None,
    cfg: ProEditConfig,
    tally: list[int],
) -> Iterator[None]:
    """Record the tokens of the LLM calls made inside as PROEDIT for
    project_id at the owner's price, and append each call's tokens to
    tally; nothing is recorded without an engine."""
    if engine is None:
        yield
        return
    with usage.recording(
        engine, project_id, kind=PROEDIT, usd_per_token=usd_per_token(cfg), tally=tally
    ):
        yield


def check_monthly_cap(
    engine: Engine,
    cfg: ProEditConfig,
    estimate: CostEstimate,
    now: datetime | None = None,
    *,
    who: str = "the Director",
) -> None:
    """Raise ProEditCapExceeded when this month's Pro Edit spend plus one
    call of estimate would pass the cap; nothing without a cap."""
    cap = cfg.monthly_cap_usd
    if cap is None or estimate.usd is None:
        return
    moment = usage.utc_now() if now is None else now
    spent = month_spend_usd(engine, moment)
    if spent + estimate.usd > cap:
        raise ProEditCapExceeded(
            f"The Pro Edit monthly cap of {usd_text(cap)} is reached: "
            f"{usd_text(spent)} spent in {moment:%Y-%m} and {who} needs "
            f"about {usd_text(estimate.usd)} more. Raise or remove "
            "proedit.monthly_cap_usd in config.yaml to run it."
        )
