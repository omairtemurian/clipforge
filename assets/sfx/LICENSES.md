# Sound effect licenses

The bundled sound effects of ClipForge: the pack that the viral hooks
(`backend/clipforge/hooks_templates`) and the auto SFX pass
(`backend/clipforge/pipeline/sfx.py`, `BUNDLED_SFX`) play. `BUNDLED_SFX`
carries the same license and attribution into the asset library, and the
tags below are what the pass searches by. Every sound is CC0 (Creative
Commons 0, public domain); no attribution is required, and "ClipForge
(CC0)" or the source named below is given anyway.

| File | Title | Tags | Length |
| --- | --- | --- | --- |
| `whoosh_swift.flac` | Swift Whoosh | whoosh, transition, cut, swipe, fast | 0.5 s |
| `whoosh_soft.flac` | Soft Whoosh | whoosh, transition, cut, soft, slow | 0.9 s |
| `tick_click.flac` | Click | click, tick, cut, ui, small | 0.06 s |
| `pop_bubble.flac` | Bubble Pop | pop, emphasis, light, ui, word | 0.15 s |
| `ding_bell.flac` | Bell Ding | ding, bell, emphasis, idea, win | 1.0 s |
| `sparkle_chime.flac` | Sparkle Chime | sparkle, chime, magic, positive, emphasis | 1.3 s |
| `impact_boom.flac` | Deep Boom | impact, boom, dramatic, reveal, hit | 1.2 s |
| `riser_swell.flac` | Tension Riser | riser, build, tension, dramatic, reveal | 1.6 s |
| `rimshot_badum.flac` | Rimshot | rimshot, punchline, joke, comedy, drums | 1.4 s |
| `crowd_laugh.flac` | Crowd Laugh | laugh, crowd, punchline, joke, comedy | 3.8 s |

Generating a sound from a text prompt is not offered: no local sound
effect model has an open license (docs/decisions.md, 2026-11-02), so the
pass searches this pack by tag instead.

## crowd_laugh.flac

- Source: "crowd_laugh.wav" by moxobna, Freesound sound 76693,
  https://freesound.org/people/moxobna/sounds/76693/ (a group of people
  laughing together; the original is a 0:53.983, 44.1 kHz, 16-bit stereo
  WAV).
- License: Creative Commons 0 (CC0 1.0 Universal public domain
  dedication), https://creativecommons.org/publicdomain/zero/1.0/, as the
  source page states. Checked on 2026-10-31. No attribution is required;
  it is given here anyway.
- Downloaded on 2026-10-31 from the page's public high-quality preview,
  https://cdn.freesound.org/previews/76/76693_43834-hq.mp3 (MP3, 44.1 kHz,
  stereo).
- Changes: cut to 1.40-5.20 s of the recording (3.8 s), mixed down to mono,
  resampled to 48 kHz and stored as 16-bit FLAC (195 KB), with ffmpeg 9.0.1:

  ```sh
  ffmpeg -i 76693_43834-hq.mp3 \
    -af "atrim=start=1.40:duration=3.8,asetpts=PTS-STARTPTS" \
    -ac 1 -ar 48000 -sample_fmt s16 -c:a flac -compression_level 12 \
    -fflags +bitexact -flags:a +bitexact -map_metadata -1 crowd_laugh.flac
  ```

- Used by `scripts/make_fixture.sh` for the three laughs of
  `backend/tests/fixtures/sample.mp4`.

## whoosh_swift.flac and whoosh_soft.flac

- Source: original sounds synthesized by ClipForge with ffmpeg 9.0.2 from
  seeded noise (`anoisesrc`); no recording or third-party sample is used.
- License: Creative Commons 0 (CC0 1.0 Universal public domain
  dedication), https://creativecommons.org/publicdomain/zero/1.0/.
  Dedicated by the ClipForge project on 2026-11-02.
- Made (bit-exact, so they can be rebuilt) with:

  ```sh
  # whoosh_swift.flac: 0.5 s of filtered pink noise swelling and fading.
  ffmpeg -f lavfi \
    -i "anoisesrc=color=pink:sample_rate=48000:amplitude=0.9:duration=0.5:seed=37" \
    -af "highpass=f=350,lowpass=f=5000,volume='pow(sin(PI*min(t/0.5,1)),3)*3':eval=frame,alimiter=limit=0.7:level=false" \
    -ac 1 -ar 48000 -sample_fmt s16 -c:a flac -compression_level 12 \
    -fflags +bitexact -flags:a +bitexact -map_metadata -1 whoosh_swift.flac
  # whoosh_soft.flac: 0.9 s of darker brown noise.
  ffmpeg -f lavfi \
    -i "anoisesrc=color=brown:sample_rate=48000:amplitude=0.9:duration=0.9:seed=73" \
    -af "highpass=f=150,lowpass=f=2500,volume='pow(sin(PI*min(t/0.9,1)),2)*4':eval=frame,alimiter=limit=0.6:level=false" \
    -ac 1 -ar 48000 -sample_fmt s16 -c:a flac -compression_level 12 \
    -fflags +bitexact -flags:a +bitexact -map_metadata -1 whoosh_soft.flac
  ```

- Used by the viral hook templates (`backend/clipforge/hooks_templates`).

## pop_bubble.flac, ding_bell.flac, impact_boom.flac, riser_swell.flac, tick_click.flac, sparkle_chime.flac and rimshot_badum.flac

- Source: original sounds synthesized by ClipForge with
  `scripts/make_sfx.py` from sine waves and seeded noise (numpy); no
  recording or third-party sample is used.
- License: Creative Commons 0 (CC0 1.0 Universal public domain
  dedication), https://creativecommons.org/publicdomain/zero/1.0/.
  Dedicated by the ClipForge project on 2026-11-02.
- Format: 48 kHz mono 16-bit FLAC, peaks at -3 dBFS. Rebuild (same files,
  bit-exact FLAC) from the repo root with:

  ```sh
  uv run --project backend python scripts/make_sfx.py
  ```

- Used by the auto SFX pass (`backend/clipforge/pipeline/sfx.py`).
