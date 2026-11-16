"""The `proedit:` section of the settings (SPEC-v3 0.13, 1.6, 6), read from
config.yaml (or the PROEDIT environment variable as JSON) into
config.settings.proedit.

enabled only controls whether Pro Edit is available: off, the app shows no
Pro Edit entry and every Pro Edit endpoint answers 404 proedit_disabled.
Nothing of Pro Edit runs unless the owner asks for it, so turning it on
changes nothing of the normal pipeline.

monthly_cap_usd caps what the Director's and the critic's LLM calls
may spend in a calendar month (None: no cap). No LLM provider of ClipForge
reports a price, so the spend is the tokens the answers report times
usd_per_million_tokens, the owner's price of the configured model; a cap
needs that price.

critic_threshold is the score (0 to 10) every checklist point of the critic
must reach for a Pro Edit to pass; critic_max_frames caps the frames of the
proxy render the critic looks at; critic_max_rounds (0 to 3; 0: no critic)
caps the critic's rounds of scores and revisions (SPEC-v3 3.7).
"""

from typing import Self

from pydantic import BaseModel, Field, model_validator

DISABLED_ERROR = "proedit_disabled"
DISABLED_MESSAGE = "Pro Edit is turned off (proedit.enabled in config.yaml)"


class ProEditConfig(BaseModel):
    enabled: bool = True
    monthly_cap_usd: float | None = Field(default=None, gt=0)
    usd_per_million_tokens: float | None = Field(default=None, ge=0)
    critic_threshold: float = Field(default=7, ge=0, le=10)
    critic_max_frames: int = Field(default=24, ge=1, le=60)
    critic_max_rounds: int = Field(default=2, ge=0, le=3)

    @model_validator(mode="after")
    def _cap_needs_a_price(self) -> Self:
        if self.monthly_cap_usd is not None and self.usd_per_million_tokens is None:
            raise ValueError(
                "proedit.monthly_cap_usd needs proedit.usd_per_million_tokens "
                "(the price of the LLM model) to count the spend in USD"
            )
        return self
