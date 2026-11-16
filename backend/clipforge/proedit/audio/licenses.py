"""The licenses Pro Edit audio may have (SPEC-v3 1.2, 5.1): CC0 and CC BY.

An audio asset is only accepted from a source when its license is CC0 or
CC BY; CC BY-NC, CC BY-SA, CC BY-ND and Sampling+ are rejected. Freesound
names a license either with its name ("Creative Commons 0", "Attribution",
"Attribution NonCommercial", as its API documentation lists them) or with
the URL of the deed (as its API answers can carry), so both forms are read.
license_label turns either into the label that an asset stores ("CC0 1.0",
"CC BY 4.0", or "CC BY" when the version is not named), None for any license
that is not allowed.
"""

import re

CC0 = "CC0"
CC_BY = "CC BY"
NAMES = {"creative commons 0": f"{CC0} 1.0", "attribution": CC_BY}
DEED = re.compile(
    r"^https?://creativecommons\.org/(?:publicdomain/zero/(?P<zero>[\d.]+)"
    r"|licenses/by/(?P<by>[\d.]+))/?$",
    re.IGNORECASE,
)


def license_label(value: object) -> str | None:
    """Return the label of the CC0 or CC BY license that value (a Freesound
    license name or deed URL) names, None for any other license, for an
    unknown value or for a value that is not text."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    named = NAMES.get(text.lower())
    if named is not None:
        return named
    deed = DEED.match(text)
    if deed is None:
        return None
    if deed["zero"]:
        return f"{CC0} {deed['zero']}"
    return f"{CC_BY} {deed['by']}"


def is_allowed(label: str) -> bool:
    """Return whether label is a label that license_label returns (CC0 or
    CC BY, with or without a version)."""
    return _is(label, CC_BY) or _is(label, CC0)


def needs_credit(label: str) -> bool:
    """Return whether an asset of license label must be credited (CC BY;
    CC0 needs no credit)."""
    return _is(label, CC_BY)


def _is(label: str, family: str) -> bool:
    """Return whether label is family, with or without a version."""
    return label == family or label.startswith(f"{family} ")
