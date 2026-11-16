# LUT licenses

The bundled color looks of the Pro Edit renderer: 3D LUTs in the `.cube`
format that ffmpeg's `lut3d` filter reads. They are original works of the
ClipForge project, made from scratch in code
(`backend/clipforge/proedit/render/luts.py`, `LOOKS`) and written to this
folder by `uv run python -m clipforge.proedit.render.luts` (from `backend/`).
No third-party LUT, film emulation or color profile was copied or sampled.
They carry the license of the ClipForge project itself; no attribution is
required. A test (`backend/tests/unit/test_proedit_luts.py`) checks that the
files are exactly what the code writes.

| File | Look | Used by |
| --- | --- | --- |
| `teal_orange.cube` | filmic S-curve contrast, teal shadows, orange highlights, +8 % saturation | Cinematic |
| `clean_pop.cube` | light correction: gentle S-curve contrast, +12 % saturation | Clean Pro |
| `cold_night.cube` | darker midtones (power 1.3), blue shadows, -30 % saturation | dark / night looks |

All three are 33-point LUTs (33 x 33 x 33 colors, red changing fastest),
input and output domain 0..1, values with 4 decimals.

Derived LUTs (a look at less than full amount, or with skin-tone
protection) are computed from these files at render time and cached in
`data/proedit/luts/`; they are not bundled.
