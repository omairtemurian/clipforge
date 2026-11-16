"""Unit tests of the bundled LUTs and skin-tone protection of the Pro Edit
renderer (SPEC-v3 3.3, TASK-208): the bundled .cube files are exactly what
luts.py writes, .cube files read back as written, skin weights follow the
skin hue range and protection keeps skin saturation within its cap."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.proedit.render.fx_basic import look_lut, saturation_lut
from clipforge.proedit.render.luts import (
    LOOKS,
    LUT_SIZE,
    bundled_path,
    bundled_values,
    cube_text,
    identity_grid,
    read_cube,
    write_bundled,
)
from clipforge.proedit.render.skin import (
    SKIN_MAX_CHANGE,
    chroma,
    protect_skin,
    scale_chroma,
    skin_weight,
)

SKIN = np.array([[0xE0, 0xAC, 0x69]]) / 255
BLUE = np.array([[0.2, 0.35, 0.8]])
GRAY = np.array([[0.5, 0.5, 0.5]])
# Allowed slack at grid points: the 4-decimal rounding of .cube values and
# the gamut clip of protected colors.
SLACK = 0.01


def test_the_bundled_luts_are_what_the_code_writes(tmp_path: Path) -> None:
    for written in write_bundled(tmp_path):
        assert written.read_text() == bundled_path(written.stem).read_text()
    assert sorted(path.stem for path in tmp_path.iterdir()) == sorted(LOOKS)


def test_a_cube_file_reads_back_as_written(tmp_path: Path) -> None:
    grid = identity_grid()
    assert grid.shape == (LUT_SIZE**3, 3)
    assert list(grid[1]) == [1 / (LUT_SIZE - 1), 0.0, 0.0]
    path = tmp_path / "identity.cube"
    path.write_text(cube_text("identity", grid))
    assert np.abs(read_cube(path) - grid).max() <= 5.1e-5
    path.write_text("LUT_3D_SIZE 2\n0 0 0\n")
    with pytest.raises(ValueError, match="33-point"):
        read_cube(path)


def test_an_unknown_lut_is_not_bundled() -> None:
    with pytest.raises(ValueError, match="no bundled LUT 'sepia'"):
        bundled_path("sepia")


def test_each_look_changes_colors_and_keeps_the_gray_axis_near_gray() -> None:
    for name in LOOKS:
        values = bundled_values(name)
        assert np.abs(values - identity_grid()).max() > 0.05
        assert values.min() >= 0.0 and values.max() <= 1.0


def test_skin_weight_follows_the_skin_hues() -> None:
    assert skin_weight(SKIN)[0] == 1.0
    assert skin_weight(BLUE)[0] == 0.0
    assert skin_weight(GRAY)[0] == 0.0
    assert skin_weight(np.array([[1.0, 0.0, 0.0]]))[0] == pytest.approx(2 / 3)


def test_protection_caps_the_skin_saturation_change() -> None:
    grid = identity_grid(17)
    for graded in (scale_chroma(grid, 0.0), scale_chroma(grid, 1.6)):
        protected = protect_skin(grid, graded)
        skin = skin_weight(grid) == 1.0
        before, after = chroma(grid)[skin], chroma(protected)[skin]
        change = np.abs(after - before) / np.maximum(before, 1e-6)
        assert change.max() <= SKIN_MAX_CHANGE + SLACK
        others = skin_weight(grid) == 0.0
        assert np.array_equal(protected[others], graded[others])


@pytest.mark.parametrize("name", list(LOOKS))
def test_a_protected_look_keeps_skin_within_the_cap(name: str, data_dir: Path) -> None:
    grid = identity_grid()
    values = read_cube(look_lut(name, 1.0, skin_protect=True))
    skin = (skin_weight(grid) == 1.0) & (chroma(grid) > 0.1)
    change = np.abs(chroma(values)[skin] / chroma(grid)[skin] - 1)
    assert change.max() <= SKIN_MAX_CHANGE + SLACK
    assert look_lut(name, 1.0, skin_protect=False) == bundled_path(name)


def test_derived_luts_are_cached_by_content(data_dir: Path) -> None:
    first = saturation_lut(0.4)
    assert saturation_lut(0.4) == first
    assert saturation_lut(0.5) != first
    assert first.is_relative_to(data_dir)
    assert look_lut("clean_pop", 0.5, skin_protect=False) != bundled_path("clean_pop")
    values = read_cube(first)
    blue = np.argmin(np.abs(identity_grid() - [0.2, 0.35, 0.8]).sum(axis=1))
    assert chroma(values[blue]) == pytest.approx(
        0.4 * chroma(identity_grid()[blue]), abs=SLACK
    )
