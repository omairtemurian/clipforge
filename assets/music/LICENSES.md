# Music licenses

The bundled background music of ClipForge: four short loops that the
render plays (looped) on a clip's music track. They are listed in the app
by `backend/clipforge/pipeline/music.py` (`BUNDLED_TRACKS`), which carries
the same license and attribution into the asset library.

All four are original compositions synthesized by ClipForge with
`scripts/make_music.py` from sine waves and seeded noise (numpy); no
recording, sample pack or third-party melody is used.

- License: Creative Commons 0 (CC0 1.0 Universal public domain
  dedication), https://creativecommons.org/publicdomain/zero/1.0/.
  Dedicated by the ClipForge project on 2026-11-02. No attribution is
  required; "ClipForge (CC0)" is given anyway.
- Format: 48 kHz mono 16-bit FLAC, about -22 LUFS integrated, peaks under
  -4 dBFS; each loop is a whole number of bars and has no seam (notes that
  ring past the end wrap to its start).
- Rebuild (same files, bit-exact FLAC) from the repo root with:

  ```sh
  uv run --project backend python scripts/make_music.py
  ```

| File | Title | Mood tags | Tempo, key | Length |
| --- | --- | --- | --- | --- |
| `bright_steps.flac` | Bright Steps | upbeat, happy, pop | 120 bpm, C major (C G Am F) | 32.0 s |
| `slow_tide.flac` | Slow Tide | calm, ambient, soft | 72 bpm, D major (Dmaj7 Bm7 Gmaj7 A) | 26.7 s |
| `night_drive.flac` | Night Drive | dramatic, electronic, driving | 100 bpm, A minor (Am F C G) | 38.4 s |
| `paper_lanterns.flac` | Paper Lanterns | chill, lofi, relaxed | 84 bpm swung, F major (Fmaj7 Em7 Dm7 Cmaj7) | 22.9 s |
