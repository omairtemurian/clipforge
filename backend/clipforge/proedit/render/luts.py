"""The bundled color looks of a Pro Edit grade (SPEC-v3 3.3 color): original
3D LUTs, defined here as functions of an RGB color and written as .cube
files to assets/luts (python -m clipforge.proedit.render.luts), under the
project's license (assets/luts/LICENSES.md).

- teal_orange: filmic contrast, shadows toward teal and highlights toward
  orange, a little more saturation (the Cinematic look);
- clean_pop: a light correction, gentle contrast and saturation (Clean Pro);
- cold_night: darker midtones, blue shadows, less saturation (a moody
  night look).

A .cube file (Iridas/Resolve format, as ffmpeg's lut3d reads it) has
LUT_3D_SIZE^3 output colors in 0..1, red changing fastest, then green,
then blue. The files are generated at LUT_SIZE points per channel with
CUBE_DECIMALS decimals, so the same code always writes the same files.
"""

import io
from collections.abc import Callable
from functools import cache
from pathlib import Path

import numpy as np

from clipforge.proedit.render.skin import Rgb, luma, scale_chroma

LUTS_DIR = Path(__file__).resolve().parents[4] / "assets" / "luts"
LUT_SIZE = 33
CUBE_DECIMALS = 4
TEAL = np.array([-1.0, 0.2, 0.8])
ORANGE = np.array([1.0, 0.45, -0.7])
NIGHT_BLUE = np.array([-0.3, 0.0, 1.0])

Look = Callable[[Rgb], Rgb]


def identity_grid(size: int = LUT_SIZE) -> Rgb:
    """Return the size^3 input colors of a LUT in .cube order (red fastest)."""
    steps = np.linspace(0.0, 1.0, size)
    blue, green, red = np.meshgrid(steps, steps, steps, indexing="ij")
    return np.stack([red, green, blue], axis=-1).reshape(-1, 3)


def contrast(rgb: Rgb, amount: float) -> Rgb:
    """Return rgb on an S-curve: amount (0..1) of the way to smoothstep."""
    return rgb + amount * (rgb * rgb * (3 - 2 * rgb) - rgb)


def tint(rgb: Rgb, shadows: Rgb, highlights: Rgb, strength: float) -> Rgb:
    """Return rgb pushed toward the color shadows in its dark parts and
    highlights in its bright parts (each up to strength)."""
    level = luma(np.clip(rgb, 0.0, 1.0))[..., None]
    pushed = rgb + strength * ((1 - level) ** 2 * shadows + level**2 * highlights)
    return np.asarray(np.clip(pushed, 0.0, 1.0))


def teal_orange(rgb: Rgb) -> Rgb:
    """The teal and orange film look."""
    return scale_chroma(tint(contrast(rgb, 0.3), TEAL, ORANGE, 0.07), 1.08)


def clean_pop(rgb: Rgb) -> Rgb:
    """The light correction look."""
    return scale_chroma(np.clip(contrast(rgb, 0.2), 0.0, 1.0), 1.12)


def cold_night(rgb: Rgb) -> Rgb:
    """The cold, dark night look."""
    darker = contrast(np.power(np.clip(rgb, 0.0, 1.0), 1.3), 0.15)
    return scale_chroma(tint(darker, NIGHT_BLUE, np.zeros(3), 0.06), 0.7)


LOOKS: dict[str, Look] = {
    "teal_orange": teal_orange,
    "clean_pop": clean_pop,
    "cold_night": cold_night,
}


def cube_text(title: str, values: Rgb, size: int = LUT_SIZE) -> str:
    """Return the .cube file of the LUT whose output colors (in .cube
    order) are values."""
    if values.shape != (size**3, 3):
        raise ValueError(f"a {size}-point LUT has {size**3} colors")
    lines = io.StringIO()
    clean = np.clip(values, 0.0, 1.0) + 0.0
    np.savetxt(lines, clean, fmt=f"%.{CUBE_DECIMALS}f", delimiter=" ")
    head = (
        f"# ClipForge original LUT, project license (assets/luts/LICENSES.md)\n"
        f'TITLE "{title}"\nLUT_3D_SIZE {size}\n'
        f"DOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n"
    )
    return head + lines.getvalue()


def read_cube(path: Path) -> Rgb:
    """Return the output colors of the .cube file path (in .cube order).
    Raises ValueError if it is not a LUT_SIZE-point 0..1 3D LUT."""
    size, rows = 0, []
    for line in path.read_text().splitlines():
        word = line.split(maxsplit=1)[0] if line.strip() else "#"
        if word.startswith("#") or word in ("TITLE", "DOMAIN_MIN", "DOMAIN_MAX"):
            continue
        if word == "LUT_3D_SIZE":
            size = int(line.split()[1])
        else:
            rows.append([float(part) for part in line.split()])
    values = np.array(rows, dtype=np.float64)
    if size != LUT_SIZE or values.shape != (size**3, 3):
        raise ValueError(f"{path.name} is not a {LUT_SIZE}-point 3D LUT")
    return values


def bundled_path(name: str) -> Path:
    """Return the .cube file of the bundled look name. Raises ValueError for
    a name not in LOOKS."""
    if name not in LOOKS:
        raise ValueError(f"no bundled LUT {name!r} (bundled: {', '.join(LOOKS)})")
    return LUTS_DIR / f"{name}.cube"


@cache
def bundled_values(name: str) -> Rgb:
    """Return the output colors of the bundled look name, read from its file."""
    return read_cube(bundled_path(name))


def write_bundled(directory: Path = LUTS_DIR) -> list[Path]:
    """Write the .cube file of every look of LOOKS into directory."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, look in LOOKS.items():
        path = directory / f"{name}.cube"
        path.write_text(cube_text(f"ClipForge {name}", look(identity_grid())))
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in write_bundled():
        print(written_path)
