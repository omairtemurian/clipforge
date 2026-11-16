"""Tests of the procedural overlay assets (SPEC-v3 3.3, TASK-212)."""

import numpy as np
import pytest
from clipforge.proedit.overlays.procedural import (
    BONE,
    MARK,
    MAX_DRAW_PX,
    PROCEDURAL_ASSETS,
    asset_problem,
    sprite,
    supersample,
)


def opaque_share(asset: str, width: int) -> float:
    """The share of the sprite's pixels that are fully opaque."""
    alpha = np.asarray(sprite(asset, width).getchannel("A"))
    return float((alpha == 255).mean())


@pytest.mark.parametrize("asset", [*PROCEDURAL_ASSETS, "emoji:💀", "emoji:😂"])
def test_known_assets_can_be_drawn(asset: str) -> None:
    assert asset_problem(asset) is None


@pytest.mark.parametrize(
    ("asset", "problem"),
    [
        (
            "cat",
            "no overlay asset 'cat' (one of skull, skeleton, arrow, circle or "
            "emoji:<emoji>)",
        ),
        ("emoji:", "the overlay asset 'emoji:' names no emoji"),
        ("emoji:a", "the emoji font has no glyph for U+0061 of 'emoji:a'"),
    ],
)
def test_unknown_assets_are_refused(asset: str, problem: str) -> None:
    assert asset_problem(asset) == problem


@pytest.mark.parametrize(
    ("asset", "width", "size"),
    [
        ("skull", 100, (100, 110)),
        ("skeleton", 50, (50, 100)),
        ("arrow", 120, (120, 60)),
        ("circle", 64, (64, 64)),
        ("emoji:💀", 80, (80, 65)),
    ],
)
def test_sprites_are_as_wide_as_asked_with_their_design_aspect(
    asset: str, width: int, size: tuple[int, int]
) -> None:
    image = sprite(asset, width)
    assert image.mode == "RGBA"
    assert image.size == size


@pytest.mark.parametrize("asset", [*PROCEDURAL_ASSETS, "emoji:💀"])
def test_sprites_are_drawn_on_a_transparent_ground(asset: str) -> None:
    alpha = np.asarray(sprite(asset, 120).getchannel("A"))
    assert alpha[0, 0] == 0
    assert 0.03 < opaque_share(asset, 120) < 0.9


@pytest.mark.parametrize("asset", [*PROCEDURAL_ASSETS, "emoji:😂"])
def test_sprites_are_drawn_the_same_every_time(asset: str) -> None:
    first, second = sprite(asset, 97), sprite(asset, 97)
    assert first.tobytes() == second.tobytes()


def test_the_skull_is_bone_and_the_arrow_red() -> None:
    skull = np.asarray(sprite("skull", 100))
    arrow = np.asarray(sprite("arrow", 120))
    # The forehead and the middle of the arrow's shaft.
    assert tuple(skull[25, 50]) == BONE
    assert tuple(arrow[30, 40]) == MARK


def test_the_circle_is_a_ring() -> None:
    ring = np.asarray(sprite("circle", 100).getchannel("A"))
    assert ring[50, 50] == 0
    assert ring[50, 8] == 255


def test_huge_sprites_are_drawn_less_supersampled() -> None:
    assert supersample(200) == 4
    assert supersample(MAX_DRAW_PX // 2) == 2
    assert supersample(MAX_DRAW_PX * 2) == 1
