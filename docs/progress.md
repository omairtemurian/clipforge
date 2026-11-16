# Progress

## 2026-11-06 — TASK-237 V3-24 Skull Moment survives budgets, dropped items reported (owner review)

- Root cause: the skull steps were placed and budgeted one item at a time (Standard 2 effects per 5 s dropped the freeze/grade/overlay), the LLM could not ask for a whole moment, and the director's notes were never stored (`run.notes` was `[]`).
- Skull Moment and bass drop are composites inferred from their items (`proedit/composites.py`): one budget unit, never split by snap/punchline/holds, kept or dropped whole; the rule director places them all-or-nothing; the LLM asks with `moments` and they are expanded with the rule director's code (`director_expand.py`).
- Every moved/dropped/left-out item is a run note ("Dropped sfx at 1.90 s: ...") shown under "Moved or dropped" in the Pro Edit dialog and editor (`RunNotes.tsx`).
- "Stronger Standard": the code matches the SPEC-v3 table, so it is a DECIDE in docs/questions.md.
- Screenshot `.agent/screenshots/TASK-237-1.png`. `make e2e`: `56 passed (16.2m)`. `make check` (exit 0):

```
All checks passed!
Success: no issues found in 459 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5745 passed, 12 skipped in 1305.78s (0:21:45) =================
      Tests  954 passed (954)
✓ built in 241ms
```

## 2026-11-06 — TASK-236 V3-23 e2e regressions + Pro Edit UI gaps (Hermes review)

- Product fixes: `zoomed_side` never scales below the frame (v2-autopilot SIGBUS render, 2 -> 3 drafts); the editor is no longer dirty after saving layers whose props the backend filled in (`lib/tidyLayers.sameLayers`, overlays); queued Pro Edit renders invalidate the variant's runs (v3-proedit "Render plan v2"); the inbox Pro Edit card plays the rendered variant video (`variantVideoUrl`); the Pro Edit dialog scrolls its options with the footer always in view.
- Test fixes (shared e2e state / layout, reasons in docs/decisions.md): overlays waits for both save PATCHes and frees its library upload; zoom-out zooms in before reading the chip label; settings marks notifications read first; watchlist checks the alerts state the API reports. No assertion removed.
- New tests: `test_zoom_graph.py` (zoom back to 1), `tests/pipeline/test_zoom_frame_sizes.py`, vitest `tidyLayers.test.ts`, `useClipEdits` (saved with defaults), `VariantCards` (thumbnail), `ProEditDialog` (options group/footer), `ProEditEditor` (follows the render it queued).
- Screenshots `.agent/screenshots/TASK-236-1.png` (inbox variant thumbnail), `TASK-236-2.png` (dialog footer at 1280x720).
- `make e2e`, two runs in a row (a previous run was voided by the laptop hibernating at 1% battery mid-run; reruns under `caffeinate -i -s`):

```
  56 passed (17.5m)
  56 passed (16.3m)
```

- `make check` (exit 0):

```
All checks passed!
Success: no issues found in 456 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5721 passed, 12 skipped in 1333.16s (0:22:13) =================
 Test Files  151 passed (151)
      Tests  952 passed (952)
✓ built in 281ms
```

## 2026-11-09 — TASK-235 V3-22 e2e v3 Pro Edit flows, README Pro Edit section, parity v3

- `e2e/v3-proedit.spec.ts`: (1) Skull Moment at Pro -> progress steps -> side-by-side previews -> move an EDL item (plan v2) -> render plan v2 -> approve the Pro Edit variant in the inbox (only the variant is queued); (2) style recipe from 2 links (test-mode stand-in serving the fixture) -> analyze, media deleted -> Phonk Edit with the recipe -> style-match score. Helpers in `e2e/proedit-flow.ts`.
- Backend: `GET /api/testmode/style-references/{name}.mp4` stand-in (test mode only) + 2 tests.
- README Features bullet + `### Pro Edit` section; `docs/parity.md` v3 column, v3-only rows, SPEC-v3 coverage table; decision entry.
- Verification: `npx playwright test -c e2e v3-proedit` -> `2 passed (2.7m)`; `uv run pytest backend/tests/api/test_testmode_routes.py -q` -> `8 passed`.
- `make check` (exit 0):

```
All checks passed!
Success: no issues found in 456 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5719 passed, 12 skipped in 1405.21s (0:23:25) =================
 Test Files  150 passed (150)
      Tests  946 passed (946)
✓ built in 251ms
```

## 2026-11-03 — TASK-202 V3-02 Pro Edit skeleton + `proedit.enabled` flag + golden isolation test

- Backend: `ProEditConfig{enabled=True}` (`proedit/config.py`) as
  `Settings.proedit` (`config.yaml` `proedit: enabled: true`); router
  `/api/proedit` (`api/proedit.py`) gated by `require_proedit` (404
  `proedit_disabled` when off): `GET /proedit/status`,
  `GET /proedit/clips/{id}/variants` (`proedit/variants.list_variants`).
- Frontend: `src/features/proedit/` (`useProEditEnabled`, `ProEditLink` (replaced by `ProEditButton` in TASK-225) in the
  editor TopBar, `ProEditRoute` at `/clips/:clipId/proedit`).
- Golden: `tests/pipeline/test_proedit_isolation.py` +
  `tests/fixtures/golden_normal_pipeline.json`.
- Screenshots `.agent/screenshots/TASK-202-1..2.png`.
- `make check` (exit 0): `4658 passed, 12 skipped in 1176.12s (0:19:36)`;
  vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`.

## 2026-11-03 — TASK-151 T50b Missed-while-offline policy + posting history

- Backend: post status `skipped` (queued -> skipped -> queued | canceled);
  settings `post_missed_policy` (`post_late` | `skip`, default post_late)
  and `post_missed_grace_s` (600 s); the posting worker's `catch_up()` on
  start (`post_queue.missed_posts`/`skip`); `post_history.py` +
  `GET /api/posts/history` (published/failed/skipped, newest first).
- Frontend: Post history page `/post-history` (sidebar "Post history",
  status filter, View post / Open clip, details sheet with reason and
  "Post now"), Skipped pill, Settings → Posting "Posts missed while
  ClipForge was off".
- Verification: `uv run pytest backend/tests/publishers/test_framework.py
  backend/tests/scheduler backend/tests/api/test_post_history_api.py -q` ->
  `123 passed`; `npx playwright test -c e2e/playwright.config.ts
  post-history.spec.ts` -> `1 passed (9.1s)`; screenshots
  `.agent/screenshots/TASK-151-1..3.png`.
- `make check` (exit 0): `4239 passed, 12 skipped in 960.31s (0:16:00)`;
  vitest `Test Files  121 passed (121)`, `Tests  764 passed (764)`; frontend
  build `✓ built in 249ms`.

## 2026-11-03 — TASK-149 T49d Calendar UI + bulk scheduler dialog

- `/calendar` (`pages/CalendarPage.tsx`, `components/calendar/`): month/week
  grid, status pills, 3 cards a day then "See N more", filters, drag a
  scheduled post to another day (same time), details sheet
  (`components/PostEditor.tsx`: edit text, reschedule, schedule, cancel,
  open clip), bulk scheduler (`components/BulkScheduleDialog.tsx`). Sidebar
  group "Post" (Calendar, Social accounts). No backend change.
- Verification: `npx vitest run src/lib src/pages/Calendar.test.tsx
  src/components/PostEditor.test.tsx src/components/BulkScheduleDialog.test.tsx
  src/components/posts src/components/accounts src/components/settings
  src/routes.test.tsx` -> `Tests  447 passed (447)`; `npx playwright test -c
  e2e calendar.spec.ts` -> `1 passed (9.7s)`, no console errors; screenshots
  `.agent/screenshots/TASK-149-1..6.png`.
- `make check` (exit 0): `4213 passed, 12 skipped in 919.65s (0:15:19)`;
  vitest `Test Files  119 passed (119)`, `Tests  755 passed (755)`; frontend
  build `✓ built in 228ms`.

## 2026-11-02 — TASK-200 Light theme (default) + dark toggle, Poppins, Phosphor

- Light default + grey dark theme (`src/index.css`), Light/Dark/System
  (`lib/theme.ts`, `hooks/useTheme.ts`, `#theme-init` in `index.html`,
  Settings → Appearance, sidebar sun/moon), Poppins in `public/fonts`,
  Phosphor icons (lucide/Geist removed), shared component restyle.
- Verification: `npx vitest run src/lib/theme.test.ts
  src/components/ThemeSwitch.test.tsx src/lib/themeTokens.test.ts` -> pass;
  `npx playwright test -c e2e theme.spec.ts` -> `2 passed (7.5s)`;
  screenshots `.agent/screenshots/TASK-200-*.png` (no console errors).
- `make check` (exit 0): `4195 passed, 12 skipped in 924.87s (0:15:24)`;
  vitest `Test Files  114 passed (114)`, `Tests  727 passed (727)`; frontend
  build `✓ built in 242ms`.

## 2026-11-02 — TASK-119 T40a Stock B-roll clients (Pexels, Pixabay)

- `backend/clipforge/stock/`: `pexels.py` and `pixabay.py` clients
  (`search(query, orientation, min_duration_s, per_page)` -> `StockClip`),
  `base.py` (errors, `get_json` with API-call metering, 24 h `SearchCache`,
  `best_file`, `download_clip` -> `Asset` with license, attribution, page URL
  and tags `stock`/provider/..), `__init__.py` (`provider()`,
  `provider_statuses()`). `Settings.pexels_api_key` / `pixabay_api_key`;
  models `StockClip`, `StockProviderStatus`.
- Verification: `uv run pytest backend/tests/stock -q` -> `19 passed`.
- `make check` (exit 0): `4091 passed, 12 skipped in 891.91s (0:14:51)`; vitest
  `Tests  666 passed (666)`; frontend build `✓ built in 284ms`.
## 2026-11-02 — TASK-118 T39d Audio panel (music, SFX)

- New rail panel "Audio" (`components/AudioPanel.tsx`; groups in
  `components/audio/`: `MusicSection`, `SfxSection`, `PreviewButton`), `api/audio.ts`, `lib/audio.ts`,
  `hooks/useSoundPreview.ts`. Music picker with preview, tags, attribution
  and license, volume / fade in / fade out / duck; "Suggest sound effects"
  (`POST /auto-sfx`) plus the pack to preview and add. No voiceover UI (scope cut).
- Verification: `npx vitest run src/pages/EditorAudio.test.tsx
  src/lib/audio.test.ts` -> `Tests  13 passed (13)`; e2e
  `npx playwright test -c e2e audio.spec.ts` -> `1 passed (30.7s)`;
  screenshots `.agent/screenshots/TASK-118-{1,2}.png`.
- `make check` (exit 0): `4055 passed, 12 skipped in 908.13s (0:15:08)`;
  backend result from the earlier run; after removing the voiceover UI,
  vitest `Test Files  101 passed (101)`, `Tests  656 passed (656)`;
  frontend build `✓ built in 240ms`.

## 2026-11-02 — TASK-117 T39c TTS voiceover (Kokoro/Piper)

- `engines/tts.py` (Kokoro in-process, Piper program; install checks,
  voices, `synthesize`), `engines/tts_files.py` (pinned downloads,
  `download_models.py --kokoro --piper`), `pipeline/voiceover.py` (cached
  `speak`, items, duck filter), ducking in `timeline_graph.mix_graph`,
  `api/voiceover.py` (`GET /api/voices`, `POST/PATCH/DELETE
  /api/clips/{id}/voiceover[/{item}]`), `PIPER_BIN`.
- Feasibility on macOS arm64: `uv run python scripts/download_models.py
  --kokoro --piper` -> `Kokoro voiceover model: models/kokoro (353.7 MB, 0s)`,
  `Piper voice: models/piper (63.5 MB, 4s)`; engine statuses
  `name='kokoro' ... installed=True version='0.6.1' error=None`,
  `name='piper' ... installed=True`; 42 Kokoro voices + 1 Piper voice;
  `synthesize('Hello from ClipForge.', 'kokoro:af_heart', ...)` -> `1.572` s,
  `piper:en_US-ljspeech-medium` at speed 1.25 -> `1.3699773242630386` s.
- Duck (astats, fixture speech, muted voiceover 3.7-5.9 s):
  `duck=true inside 4.0-5.5 s: -40.134808 dB; outside 1.0-2.5 s: -28.084274 dB`,
  `duck=false inside 4.0-5.5 s: -28.085976 dB; outside 1.0-2.5 s: -28.084274 dB`.
- Verification: `uv run pytest backend/tests/engines/test_tts.py
  backend/tests/pipeline/test_voiceover.py backend/tests/api/test_voiceover_api.py -q`
  -> `24 passed`.
- `make check`: `4055 passed, 12 skipped in 887.87s (0:14:47)`; vitest
  `Test Files  99 passed (99)`, `Tests  643 passed (643)`; `✓ built in 234ms`.
- `make check-engines`: `backend/tests/engines/test_tts.py ..`;
  `9 passed, 7 skipped, 4051 deselected in 9.65s` (the skips: no Ollama
  server; demucs, mflux, realesrgan, coqui-tts, sentence-transformers not
  installed).

## 2026-11-02 — TASK-116 T39b Auto SFX

- `assets/sfx` pack of 10 CC0 sounds (7 new, synthesized by
  `scripts/make_sfx.py`), tagged in `pipeline/sfx.BUNDLED_SFX`, registered as
  bundled `sfx` assets; `pipeline/sfx.py` (moments, LLM picks with retries,
  tag search, placement, track items); `GET /api/sfx`, `GET /api/sfx/{id}/file`,
  `POST /api/clips/{id}/auto-sfx`. Generate-by-prompt documented as not
  available (docs/decisions.md).
- Verification: `uv run pytest backend/tests/pipeline/test_sfx.py
  backend/tests/api/test_sfx_api.py -q` -> `26 passed`. Render check: a bundled
  boom placed in the fixture's silent gap: -50 dB or less without it, over -30
  dB with it.
- `make check`: `4030 passed, 13 skipped in 782.64s (0:13:02)`; vitest `Test Files  99 passed (99)`, `Tests  643 passed (643)`; `✓ built in 257ms`.

## 2026-11-02 — TASK-115 T39a Music library + auto-duck

- 4 original CC0 loops in `assets/music` (synthesized by
  `scripts/make_music.py`, listed in `LICENSES.md`, registered as bundled
  assets), music uploads (kind `music`), `GET /api/music` + file route,
  `MusicProps` (volume, offset, fade in/out, duck), looping music inputs and
  a sidechaincompress duck keyed by the clip's sound.
- Duck measured on the fixture speech, each loop at volume 0.5: speech
  windows -38.0..-39.5 dB (undocked -26..-27.3), gaps -27.4..-31.7 dB.
- Verification: `uv run pytest backend/tests/pipeline/test_music_duck.py
  backend/tests/api/test_music_api.py -q` -> `18 passed`.
- `make check`: `4004 passed, 13 skipped in 813.81s (0:13:33)`; vitest
  `Tests  643 passed (643)`; `✓ built in 171ms`.

## 2026-11-02 — TASK-114 T38d Cleanup + enhancement UI

- Editor rail panel "Cleanup": what-will-be-removed checkbox list over the
  TASK-111 preview/apply endpoints, plus an enhancement strength slider with a
  DeepFilterNet engine gate. Backend wiring added: `Clip.enhance` (migration
  026), `PUT /clips/{id}/enhance`, and the enhanced voice as a render input.
- Verification: `uv run pytest backend/tests/api/test_clip_enhance_api.py
  backend/tests/pipeline/test_enhance_render.py
  backend/tests/unit/test_migration_v2_clip_enhance.py -q` -> passed;
  `npx vitest run src/pages/EditorCleanup.test.tsx src/lib/cleanup.test.ts`
  -> `Tests  13 passed (13)`; `npx playwright test -c e2e cleanup.spec.ts`
  -> `1 passed (30.2s)`.
- `make check`: `3981 passed, 13 skipped in 804.09s` with 3 stale count tests
  (fixed, `157 passed`); vitest `Tests  643 passed (643)`;
  `✓ built in 252ms`.

## 2026-11-02 — TASK-113 T38c DeepFilterNet engine

- Feasibility on macOS arm64: pip `deepfilternet` 0.5.6 installs in a
  scratch venv but `import df` -> `ModuleNotFoundError: No module named
  'torchaudio.backend'` (and it pins numpy<2). The official release program
  works: `file deep-filter` -> `Mach-O 64-bit executable arm64`;
  `deep-filter --version` -> `deep_filter 0.5.6`; 6 s of 48 kHz speech
  enhanced in 0.26 s.
- `engines/deepfilternet.py` (`DeepFilterNetEngine`, `deep_filter_binary`,
  `download_deep_filter`, `attenuation_limit_db`, `deep_filter_audio`),
  `pipeline/enhance.enhance_speech` (engine, else ffmpeg), `DEEP_FILTER_BIN`,
  `scripts/download_models.py --deepfilternet`.
- `uv run python scripts/download_models.py --deepfilternet` ->
  `DeepFilterNet program: models/deepfilternet (27.9 MB, 13s)`;
  engine status `installed=True version='0.5.6'`.
- Measured SNR vs clean (fixture's first 6 s + white noise a=0.03): noisy
  6.33 dB; `-a 12` 17.17 dB; strength 1 (`-a 100`) 22.02 dB.
- `uv run pytest backend/tests/engines/test_deepfilternet.py -q` ->
  `14 passed in 3.55s` (with `DEEP_FILTER_BIN=clipforge-none`: 12 passed,
  2 skipped `engine_deepfilternet: DEEP_FILTER_BIN ... is not found`).
- `make check-engines` -> `6 passed, 8 skipped, 3973 deselected in 4.70s`
  (both engine_deepfilternet tests and its VERIFY probe pass).
- `make check` (exit 0, second run; the first failed only on the
  `.env.example` key lists, now including `DEEP_FILTER_BIN`):
  `3974 passed, 13 skipped in 802.15s (0:13:22)`; vitest
  `Test Files  98 passed (98)`, `Tests  634 passed (634)`; `✓ built in 167ms`.

## 2026-11-02 — TASK-112 T38b Speech enhancement: ffmpeg fallback

- `pipeline/enhance.py` (`enhance_filter`, `measure_noise_floor`,
  `enhance_audio`): highpass 80 Hz + optional `arnndn` (RNNoise model
  `bd.rnnn`, `enhance_model.py`, downloaded by `scripts/download_models.py`)
  + `afftdn`; strength 0-1 sets `nr` 6-30 dB, `rf`, arnndn `mix`.
- Verification: `uv run pytest backend/tests/pipeline/test_enhance_ffmpeg.py -q`
  -> `14 passed in 2.92s`. Measured (astats RMS of the noise-only stretch of
  the fixture, a tone + white noise; noisy -35.2 dB, tone -13.4 dB):
  afftdn strength 0.25/0.5/0.75/1.0 -> -47.3/-53.3/-59.2/-65.1 dB (tone
  -13.5 dB throughout); with the real RNNoise model -48.7/-56.8/-65.3/-74.3 dB.
- `make check` (exit 0): `3960 passed, 14 skipped in 787.67s (0:13:07)`;
  vitest `Test Files  98 passed (98)`, `Tests  634 passed (634)`;
  frontend build `✓ built in 220ms`.

## 2026-11-02 — TASK-111 T38a Speech cleanup

- `clipforge/fillers/` (filler lists for en, es, fr, de, it, pt, nl, ru,
  pl, tr, fa, ar; `filler_words(language, extra)`), `pipeline/polish.py`
  takes a filler list and pause threshold, `pipeline/bad_takes.py` +
  `prompts/bad_takes.md` (LLM false starts / repeated takes with retries),
  `pipeline/cleanup.py` (preview, checked items -> cut ranges),
  `api/clip_cleanup.py` (`GET /filler-languages`,
  `POST /clips/{id}/cleanup/preview`, `POST /clips/{id}/cleanup/apply`);
  `fit_cuts` moved to `pipeline/sections.py`. Types regenerated.
- Verification: `uv run pytest tests/pipeline/test_cleanup.py
  tests/pipeline/test_bad_takes.py tests/api/test_clip_cleanup_api.py` ->
  30 passed; affected polish/cleanup/section/split/cuts tests -> `102 passed`.
- `make check`: PASS (exit 0, first run): `All checks passed!`,
`3946 passed, 14 skipped in 790.08s (0:13:10)`; vitest
`Test Files  98 passed (98)`, `Tests  634 passed (634)`; `✓ built in 165ms`.

## 2026-11-02 — TASK-110 T37c Hooks/headline/motion graphics UI

- Editor rail: "Hooks" panel (`HookPanel`: template list, text source
  captions / AI line / own text, length slider, edit text, write again,
  remove; `HeadlineGroup`: set, write with AI, remove) and "Graphics" panel
  (`MotionGraphicsPanel`: find N graphics, replace, remove all, edit text and
  style or delete each graphic). `api/clipGraphics.ts`, `lib/viralHooks.ts`;
  `LayerTextField` shared with the Text layers panel; `PanelSlider.onCommit`.
- Verification: `npx vitest run src/pages/EditorHooks.test.tsx` -> 9 passed;
  `npx playwright test -c e2e e2e/hooks.spec.ts` -> `1 passed (31.0s)`
  (screenshots `.agent/screenshots/TASK-110-1.png`, `-2.png`).
- `make check` (exit 0, first run): `All checks passed!` /
  `3915 passed, 14 skipped in 709.36s (0:11:49)`; vitest `Test Files  98 passed (98)` /
  `Tests  634 passed (634)`; `✓ built in 221ms`.

## 2026-11-02 — TASK-109 T37b Auto headline + motion graphics

- `brand_style.py` (brand font/color or defaults), `pipeline/headline.py`
  (headline text item: brand font, brand-color box, slide down, 3 s; kept
  edits on regenerate), `pipeline/motion_graphics.py` (word-snapped
  lower-thirds and number callouts from LLM picks), `clip_graphics.py` +
  `prompts/headline.md`, `prompts/motion_graphics.md` (LLM with retries on
  unsaid quotes), `api/clip_graphics.py` (`POST/DELETE
  /clips/{id}/headline`, `POST/DELETE /clips/{id}/motion-graphics`);
  `save_clips` gives new clips a headline item when the project has a brand
  template; captions skip `hook_text` while a headline item exists;
  `hook_theme.ask_line`, `text_overlay.wrap_lines`/`fit_scale` shared.
  Types regenerated.
- Verification: `uv run pytest backend/tests/pipeline/test_motion_graphics.py
  backend/tests/pipeline/test_headline.py
  backend/tests/api/test_clip_graphics_api.py` -> 29 passed (real renders
  show the brand color at the headline, lower-third and callout); affected
  hook/caption/clips/timeline/brand/model tests -> `312 passed`.
- `make check` (exit 0, first run): `All checks passed!` /
  `3915 passed, 14 skipped in 771.88s (0:12:51)`; vitest `Test Files  97 passed (97)` /
  `Tests  625 passed (625)`; `✓ built in 271ms`.

## 2026-11-02 — TASK-108 T37a Viral hook templates

- `Clip.hook` (`ClipHook`: template, text, duration; migration 025, types
  regenerated), 6 YAML templates in `hooks_templates/` with 2 original CC0
  whooshes (`assets/sfx/whoosh_swift.flac`, `whoosh_soft.flac`),
  `pipeline/hooks.py` (text layers + whoosh layer + punch-in filter,
  caption text), `hook_theme.py` + `prompts/hook_theme.md` (LLM line),
  `api/clip_hook.py` (`GET /hook-templates`, `POST/PATCH/DELETE
  /clips/{id}/hook`), render/preview pass the punch, multi-line drawtext
  centred (`text_align=C`), v1 hook_text skipped while a hook is set.
- Verification: `uv run pytest backend/tests/pipeline/test_hooks.py
  backend/tests/api/test_clip_hook_api.py
  backend/tests/unit/test_migration_v2_clip_hook.py` -> 34 passed (real
  renders of every template: length kept, text/zoom/whoosh only in the
  first seconds); affected render/caption/timeline/clip API/unit tests ->
  `1844 passed, 13 skipped`.
- `make check`: (exit 0, second run; the first had only the known flaky real-MLX transcription test fail, which passed alone): `All checks passed!` /
  `3886 passed, 14 skipped in 757.51s (0:12:37)`; vitest `Test Files  97 passed (97)` /
  `Tests  625 passed (625)`; `✓ built in 165ms`.

## 2026-11-02 — TASK-107 T36d Overlays/transitions/media library UI

- Editor rail panels: Media (`MediaLibrary.tsx`, `api/mediaLibrary.ts`),
  Text layers (`TextOverlayPanel.tsx`, `editor/TextLayerFields.tsx`),
  Transitions (`TransitionPicker.tsx`); `lib/newLayerItems.ts` (drag MIME
  carries the kind, track compatibility, new item ids/props),
  `lib/overlays.ts` (text props, transitions). `Track`/`Timeline` accept
  media drops at the pointer's clip time; `useClipEdits` edits, saves and
  undoes `transitions`.
- Verification: `npx vitest run src/lib/newLayerItems.test.ts
  src/lib/overlays.test.ts src/pages/EditorOverlays.test.tsx
  src/hooks/useClipEdits.test.ts` -> passed; `npx playwright test -c e2e
  overlays.spec.ts` -> `1 passed (31.2s)`; screenshots
  `.agent/screenshots/TASK-107-1..3.png`.
- `make check` (exit 0): `All checks passed!` /
  `3852 passed, 14 skipped in 724.25s (0:12:04)`; vitest `Test Files  97 passed (97)` /
  `Tests  625 passed (625)`; `✓ built in 218ms`.

## 2026-11-02 — TASK-106 T36c Transitions: crossfade, zoom punch, whip, slide

- `pipeline/transitions.py` (`XFADE`, `Join`, `clip_joins`, `fit_join`,
  `has_joins`, `join_graph`), `Transition`/`ClipTransitions` +
  `Clip.transitions` in `models.py` (types regenerated), migration 024,
  `render_graph.cut_graph`/`clip_graph` `joins`, `render_clip(transitions=)`,
  preview key includes `transitions`, PATCH versions it (undo).
- Each transition pads the part before the cut with its last frame and the
  part after with its first (`tpad` clone) and `xfade`s them centred on the
  cut, so the clip keeps its length; audio stays a hard cut. `auto` applies
  to jump cuts inside a section, `sections[i]` to the cut after section i.
- Verification: `uv run pytest backend/tests/pipeline/test_transitions.py
  backend/tests/api/test_clip_transitions_api.py -q` -> 13 + 6 passed.
  Real renders (red 1.5 s -> blue 1.5 s, 0.4 s transition): every kind keeps
  3.0 s video and audio, pure red before 1.3 s / blue after 1.7 s, mixed
  colours inside 1.3-1.7 s; a hard jump cut + section crossfade renders 2.8 s.
- `make check` (exit 0): `All checks passed!` /
  `3852 passed, 14 skipped in 720.55s (0:12:00)`; vitest `Test Files  94 passed (94)` /
  `Tests  605 passed (605)`; `✓ built in 163ms`.

## 2026-11-02 — TASK-105 T36b Text overlays (up to 5 layers) with animations

- `pipeline/text_overlay.py` (`MAX_TEXT_LAYERS`, `text_layer_problems`,
  `animation_seconds`, `text_filter` moved here from `timeline_graph`),
  `TextProps` stroke/stroke_width/box_opacity/animation_in/animation_out/
  in_seconds/out_seconds + `TextAnimation` in `models.py` (types regenerated),
  `timeline.track_problems` refuses a 6th text item, `clip_layers` draws only
  the first 5.
- Verification: `uv run pytest backend/tests/pipeline/test_text_overlay.py
  backend/tests/api/test_timeline_api.py backend/tests/unit/test_timeline_graph.py
  backend/tests/pipeline/test_timeline_render.py -q` -> `31 passed in 8.39s`.
  Measured in the real render (frames of the 180x320 clip): fade item
  1.0-2.5 s red max 0 @0.8 s, 146 @1.1, 255 @1.75, 61 @2.45, 1 @2.8; slide
  right in: text centre x 65.5 @1.05 s, 74.5 @1.25, 84.5 @1.6, 89.5 @2.0; pop
  in: text width 46 px @1.15 s, 60 @1.5, 67 @2.0.
- `make check` (exit 0): `All checks passed!` /
  `3832 passed, 14 skipped in 709.51s (0:11:49)`; vitest `Test Files  94 passed (94)` /
  `Tests  605 passed (605)`; `✓ built in 163ms`.

## 2026-11-02 — TASK-104 T36a Media library uploads

- `media_library.py` (store/validate/thumbnail/uses), `media_sniff.py`
  (first-bytes format), `MediaItem`/`MediaMeta`/`MediaUpdate` in `models.py`
  (types regenerated), `GET/POST /api/library`, `PATCH/DELETE
  /api/library/{id}`, `GET /api/library/{id}/file|thumbnail` in `api/media.py`.
- Verification: `uv run pytest backend/tests/api/test_media_library.py -q`
  -> `25 passed in 14.56s` (real ffmpeg files: png, jpg, webp, gif, mp4, mp3,
  wav, m4a, ogg, flac; truncated, text, empty, wrong kind, over-size,
  duplicate, tags, Range, delete 409 while a clip plays it).
- `make check` (exit 0): `All checks passed!` /
  `3816 passed, 14 skipped in 660.72s (0:11:00)`; vitest `Test Files  94 passed (94)` /
  `Tests  605 passed (605)`; `✓ built in 167ms`.

## 2026-11-02 — TASK-103 T35c Section ops UI

- Editor rail "Sections" panel (`components/timeline/SectionMenu.tsx`,
  `SectionList.tsx`, `SectionPicker.tsx`; `api/clipSections.ts`;
  `lib/sections.ts`): sections in play order with drag-rearrange, arrows and
  delete, an add-section picker from the source transcript (new `GET
  /api/projects/{id}/transcript`), and at the playhead "Split section in
  two", "Split into two clips" and "Duplicate clip".
- Verification: `uv run pytest backend/tests/api/test_source_transcript.py -q`
  -> `2 passed`; `npx vitest run src/pages/EditorSections.test.tsx
  src/lib/sections.test.ts` -> all passed; `npx playwright test -c e2e
  e2e/sections.spec.ts` -> `1 passed`; screenshots
  `.agent/screenshots/TASK-103-1.png`, `TASK-103-2.png`.
- `make check` (exit 0): `All checks passed!` /
  `3791 passed, 14 skipped in 645.78s (0:10:45)`; vitest `Test Files  94 passed (94)` /
  `Tests  605 passed (605)`; `✓ built in 235ms`.
## 2026-11-02 — TASK-102 T35b Duplicate clip + split one clip into two

- `clip_split.py` (`duplicate_clip`, `split_clip`, `split_sections`,
  `frame_at`), `api/clip_copies.py` (`POST /api/clips/{id}/duplicate`,
  `POST /api/clips/{id}/split`), `ClipSplit` in `models.py`, types regenerated.
- Verification: `uv run pytest backend/tests/test_clip_duplicate_split.py
  backend/tests/api/test_clip_copies_api.py -q` -> `13 passed`; split parts
  last as long as the clip (`pytest.approx`, 1e-6 s) with cuts across the split.
- `make check` (exit 0): `All checks passed!` /
  `3785 passed, 14 skipped in 704.08s (0:11:44)`; vitest `Test Files  92 passed (92)` /
  `Tests  589 passed (589)`; `✓ built in 253ms`. (Two earlier runs failed only
  `test_transcribe_mlx.py::test_the_real_mlx_model_transcribes_the_fixture_and_the_overlap_merges`,
  a real-model test that is flaky: it also failed alone on HEAD once and
  passed alone and in the pipeline dir with these changes.)

## 2026-11-02 — TASK-101 T35a Section ops backend: trim/extend, add, split, delete, rearrange

- A clip's sections (segments) now play in their order: gaps are cut,
  kept parts reordered, captions moved with them (`pipeline/sections.py`);
  render, preview, clip length and captions follow.
- Endpoints (`api/clip_sections.py`): `PUT /api/clips/{id}/sections/{i}`
  (trim/extend, clamped to the source and neighbors), `POST .../sections`
  (add from source), `POST .../sections/split` `{at}`, `POST
  .../sections/reorder` `{order}`, `DELETE .../sections/{i}`; 404/409/422;
  each op is a version; cut ranges fitted, video track rebuilt.
- Verification: `uv run pytest backend/tests/test_section_ops.py
  backend/tests/api/test_clip_sections_api.py
  backend/tests/pipeline/test_section_render.py -q` — all passed
  (rearranged render: duration 4.6 s, onsets [1.0, 2.6, 4.1]).
- `make check` (exit 0): `All checks passed!` /
  `3772 passed, 14 skipped in 692.44s (0:11:32)`; vitest
  `Test Files  92 passed (92)` / `Tests  589 passed (589)`; `✓ built in 197ms`.

## 2026-11-02 — TASK-100 T34d Keyboard precise editing + undo/redo + autosave in UI

- Editor autosave (2 s debounce, top bar status + on/off toggle); undo/redo
  through unsaved edits, then the saved versions (`POST /api/clips/{id}/undo`,
  `/redo`); "Version history" dialog with Restore
  (`POST .../versions/{n}/restore`).
- Keys: Delete a selected layer item, cmd+C / cmd+V copy-paste it at the
  playhead, < / > playback speed (and a speed menu); existing frame/1 s
  step, S split, +/- zoom.
- New: `api/clipVersions.ts`, `hooks/{useUndo,useAutosave,useTimelineKeys}.ts`,
  `lib/{layerItems,playbackRate,versions}.ts`, `components/editor/VersionHistory.tsx`;
  tests for each, `pages/EditorHistory.test.tsx`, `e2e/timeline-keys.spec.ts`
  (1 passed), `e2e/autosave.ts`.
- Screenshots: `.agent/screenshots/TASK-100-1.png` … `TASK-100-3.png`.
- `make check` (exit 0): `All checks passed!` /
  `3736 passed, 14 skipped in 684.13s (0:11:24)`; vitest
  `Test Files  92 passed (92)` / `Tests  589 passed (589)`; `✓ built in 235ms`.
- `e2e/zoom-out.spec.ts` fails on HEAD before this task too (segment label
  hidden when narrow); see HANDOFF.

## 2026-11-01 — TASK-99 T34c Timeline editor UI: tracks, playhead, zoom, snap

- Editor timeline: Text/Overlays/B-roll rows above the video, Voiceover/
  Music/SFX below the audio, track-name gutter; items move/trim by drag,
  arrow-key nudge, snap toggle (words, segment/cut edges, playhead, other
  items), undo/redo, saved via `PATCH /api/clips/{id}/tracks`.
- New: `lib/snap.ts`, `lib/layers.ts`, `components/timeline/{Timeline,Track,TrackLabels}.tsx`,
  `useSaveTracks`, `useDragFrom`; tests `lib/snap.test.ts`, `lib/layers.test.ts`,
  `pages/EditorLayers.test.tsx`, `e2e/timeline-layers.spec.ts` (1 passed).
- Screenshots: `.agent/screenshots/TASK-99-1.png`, `TASK-99-2.png`.
- `make check` (exit 0): `3736 passed, 14 skipped in 682.87s (0:11:22)`;
  vitest `Tests  559 passed (559)`; frontend build `✓ built in 178ms`.

## 2026-11-01 — TASK-98 T34b Undo/redo history, autosave, version restore

- Migration `023_v2_clip_versions`; `clip_versions.py` stores a version at
  every clip edit (SQLAlchemy `before_flush` hook), undo/redo/restore,
  retention `clip_versions_kept` (100). Endpoints `GET /api/clips/{id}/versions`,
  `GET .../versions/{n}`, `POST .../undo`, `.../redo`, `.../versions/{n}/restore`.
- Tests: `tests/test_clip_versions.py`, `tests/api/test_clip_versions_api.py`.
- Verification: `make check` (exit 0); the run's tail:
  `================= 3736 passed, 14 skipped in 680.12s (0:11:20) =================`
  ` Test Files  83 passed (83)` / `      Tests  536 passed (536)` /
  `✓ built in 273ms`

## 2026-11-01 — TASK-97 T34a Multi-track timeline backend

- Tracks broll, overlays, text, music, sfx, voiceover on each clip
  (SPEC-v2 3.5): `PUT`/`PATCH /api/clips/{id}/tracks` validate the items
  (kind per track, start < end inside the rendered clip, asset exists with a
  matching kind and file, strict props, font) and store tidied props.
- Render (and preview) draws B-roll, overlays and text under the captions
  and mixes music/sfx/voiceover after loudnorm (`pipeline/timeline_graph.py`).
- Real-ffmpeg fixture with one item per track: ffprobe duration ±0.2 s,
  layer pixel colors and RMS levels (`tests/pipeline/test_timeline_render.py`).
- Verification: `make check` (exit 0). Earlier runs failed on a duplicate
  test basename (`test_timeline.py`, split into `unit/test_timeline_tracks.py`
  and `unit/test_timeline_graph.py`) and on a v1 model test that used `image`
  as an unknown kind (now `sticker`); the final run:
  `================= 3716 passed, 14 skipped in 687.83s (0:11:27) =================`
  ` Test Files  83 passed (83)` / `      Tests  536 passed (536)` /
  `✓ built in 180ms`

## 2026-11-01 — TASK-96 T33h Captions v2 editor UI

- Captions panel: "All templates" gallery dialog, server-drawn live preview
  (`POST /caption-templates/{name}/preview`, debounced), font select with
  TTF/OTF upload, stroke color, lines, words per line, animation; per-word
  popover (highlight, emoji, censor, color); speaker colors; translate / show
  the original; auto censor (beep/mute) and the censor list; brand vocabulary
  dialog with replace everywhere. Transcript "Download transcript" menu (clip
  and whole video, .txt/.srt/.vtt).
- Backend `CaptionMark.color`: a word's own color in the burned-in captions.
- e2e `e2e/captions-v2.spec.ts` (1 passed); screenshots
  `.agent/screenshots/TASK-96-{1..4}.png`.
- Verification: `make check` (exit 0). The first run failed only on the real
  MLX model test (`test_transcribe_mlx.py`, word order, passes alone: 26
  passed); the rerun passed:
  `================= 3690 passed, 14 skipped in 687.68s (0:11:27) =================`
  ` Test Files  83 passed (83)` / `      Tests  536 passed (536)` /
  `✓ built in 258ms`

## 2026-11-01 — TASK-199 More caption styles and 13 bundled fonts

- 13 fonts added to `assets/fonts/` (Poppins Black, Anton, Bebas Neue, Bangers,
  Archivo Black, Lilita One, Titan One, Bungee, Passion One, Righteous,
  Staatliches: OFL; Luckiest Guy, Permanent Marker: Apache 2.0) from
  google/fonts at a pinned commit, each with its license file and a row
  (license, source, SHA-256) in `assets/fonts/LICENSES.md`.
- 17 new templates (30 in all) and four animations: `shake`, `underline`,
  `pill`, `hollow` (`pipeline/caption_effects.py`).
- `ProcessingSettings.caption_colors` (`CaptionColors`: primary, highlight,
  emphasis, all optional) is copied into each new clip's `caption_style` by
  `clips.save_clips`; it is saved in presets. Settings panel "Caption colors"
  (`CaptionColorsField`): two pickers, "White + green/yellow/orange" chips,
  "Template colors" reset.
- Screenshots `.agent/screenshots/TASK-199-{1,2}.png`; e2e
  `e2e/caption-styles.spec.ts`.

## 2026-11-01 — TASK-196b UI polish pass, part 2

- New `Panel`/`PanelGroup` primitive (`components/ui/panel.tsx`): the editor
  rail renders each panel in it; Captions ("Style", "Caption words") and
  Layout ("Framing", "Auto edits") use collapsible groups.
- Editor, settings panel, processing, Campaigns, Watchlist, Accounts,
  Settings and Brand templates use the TASK-196 tokens: type scale (new
  `text-micro`), `cardClass`/new `choiceClass`, `NativeSelect` (new `block`
  prop) for every select, `Pill` (mode badge, restrictions, step states,
  duration), `Skeleton` loading, `EmptyState` (Watchlist channels/streamers,
  alerts, Accounts), `shadow-popover` on dialogs/popovers, `pageColumn`.
- Accessibility (manual check): tabbed through the editor rail buttons, panel
  group toggles (Enter/Space toggle, `aria-expanded` updates), Accounts filter
  chips, number stepper, transcript search, log drawer button, empty-state
  actions (focus the add field); every element shows a visible focus ring.
- Screenshots `.agent/screenshots/TASK-196b-<page>[-1280].png`.
- `npx playwright test -c e2e` -> 17 passed; vitest 510 passed.

## 2026-11-01 — TASK-196 UI polish pass, part 1

- Design tokens in `frontend/src/index.css` (colors, type scale, spacing,
  containers, shadows, transitions), `cn` extended for them, shared
  primitives `Pill`, `Skeleton`, `EmptyState`, `NativeSelect`, `Card`; shell,
  Home, Projects and gallery polished. Editor + settings pages: TASK-196b.
- Accessibility (manual check, axe is not a dependency): tabbed through the
  sidebar (links, logo, collapse toggle), breadcrumb, search, tool chips,
  source input, "View all", project cards and menus, gallery toolbar selects,
  clip cards; every element shows a visible `focus-visible` ring.
- `grep -ri` for the reference tool's name in frontend/src: no matches.
- Screenshots `.agent/screenshots/TASK-196-<page>-{before,after}[-1280].png`.
- `npx playwright test -c e2e smoke.spec.ts projects.spec.ts upload.spec.ts
  captions-only.spec.ts` -> 5 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 229 source files
================= 3397 passed, 14 skipped in 534.29s (0:08:54) =================
 Test Files  76 passed (76)
      Tests  503 passed (503)
```

## 2026-11-01 — STEERING: ingest H.264 preference, hardware transcode, progress

- yt-dlp `format_sort` prefers H.264/AAC (1080p cap kept); conversions use
  `Settings.video_encoder` (h264_videotoolbox) with libx264 fallback; ffmpeg
  `-progress` drives Job.progress in the 0.51-0.9 ingest band, the log
  ("Converting video to H.264: 42%") and the "Converting video" sub-step.
- `uv run pytest backend/tests/unit/test_ffmpeg_progress.py
  backend/tests/pipeline/test_transcode.py
  backend/tests/pipeline/test_ingest_formats.py
  backend/tests/pipeline/test_ingest.py backend/tests/pipeline/test_ingest_url.py
  -q` -> all passed; vitest processingSteps + Processing passed.
- Screenshot: .agent/screenshots/STEERING-ingest-1.png.

## 2026-11-01 — TASK-93 Brand vocabulary (T33e)

- `GET/PUT /api/vocabulary` (`{data_dir}/vocabulary.json`, `models.Vocabulary`):
  terms are Whisper `hotwords` (faster-whisper 1.2.1 signature verified:
  `hotwords`, `initial_prompt`), corrections {heard: correct} are applied to
  each transcript after transcription (`pipeline/transcript_correct.py`).
  `POST /api/projects/{id}/replace-everywhere` changes the project's
  transcript and all its clips; `remember` saves a correction.
- `uv run pytest backend/tests/unit/test_vocabulary.py
  backend/tests/pipeline/test_transcribe_vocabulary.py
  backend/tests/api/test_vocabulary_api.py -q` -> all passed (33 tests; the
  slow one runs the real `small` model with hotwords).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 227 source files
================ 3368 passed, 14 skipped in 1020.31s (0:17:00) =================
 Test Files  74 passed (74)
      Tests  489 passed (489)
```

## 2026-11-01 — TASK-92 Caption translation + RTL (T33d)

- `pipeline/caption_cues.py` groups a clip's words into timed cues;
  `pipeline/caption_translate.py` + `prompts/caption_translate.md` have the
  LLM translate them (index-checked replies, retries); each cue keeps its
  source times. Saved as `caption_style.translation`;
  `POST/DELETE /api/clips/{id}/caption-translation`. `polish.rendered_words`
  spreads a cue's translation over its span (captions, SRT, clip text).
- RTL: style `Encoding -1` (libass auto base direction) when text has
  R/AL characters; `fonts.covering_font` draws Arabic-script text in bundled
  Vazirmatn Bold and Hebrew in Noto Sans Hebrew Bold (OFL, LICENSES.md).
- Tests: `tests/pipeline/test_caption_rtl.py` (20: libass shaping of
  Persian/Arabic/Hebrew vs visual-order presentation forms, fonts, ASS),
  `tests/pipeline/test_caption_translate.py` (13, mocked LLM),
  `tests/api/test_caption_translation_api.py` (3).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 224 source files
================= 3335 passed, 14 skipped in 515.82s (0:08:35) =================
 Test Files  74 passed (74)
      Tests  489 passed (489)
```

## 2026-11-01 — TASK-90 AI emojis, keyword highlights, speaker colors (T33b)

- `pipeline/caption_emphasis.py` + `prompts/caption_emphasis.md`: the LLM
  gets the clip's numbered words and marks emphasis words and emojis
  (`WordMarks`); they become `CaptionMark`s (source "ai") in
  `caption_style.word_marks`. Editor marks (source "user") beat AI marks
  and survive a new AI pass. `caption_style.speaker_colors` colors each
  diarized speaker's words. ASS output shows all three.
- Tests: `tests/pipeline/test_caption_emphasis.py` (mocked LLM replies,
  retries, exact ASS lines, cuts, speaker colors),
  `tests/api/test_caption_marks_api.py`, frontend `clipLook.test.ts`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 221 source files
================= 3281 passed, 14 skipped in 499.94s (0:08:19) =================
 Test Files  74 passed (74)
      Tests  489 passed (489)
```

## 2026-11-01 — TASK-89 Animated caption templates + live preview (T33a)

- 13 original caption templates (7 new: pop_punch, spotlight, storyteller,
  soft_fade, ember_box, tidal_bounce, headline_duo). Schema adds stroke
  color, one or two lines, 1-6 words per line and an animation (pop,
  bounce, fade, reveal as ASS `\t`/`\fad`/`\alpha` tags); a clip's
  caption style can override every field (bundled fonts only).
- `POST /api/caption-templates/{name}/preview` draws the live preview of a
  style; every template's preview PNG is drawn at startup as before.
- Tests: exact ASS of each new template on the six-word fixture, a preview
  PNG per template, libass-rendered animation pixels, preview API.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 220 source files
================= 3264 passed, 14 skipped in 529.48s (0:08:49) =================
 Test Files  74 passed (74)
      Tests  487 passed (487)
```

## 2026-11-01 — TASK-67 Dropbox import (T27e)

- `sources/dropbox.py`: shared-link parsing (file links only),
  `sharing/get_shared_link_metadata`, `sharing/get_shared_link_file`
  download (size-checked `.part` file); ingest uses it for Dropbox links
  when connected. `api/dropbox.py`: status, connect, callback page,
  disconnect, file lookup, import (412 needs_credentials without
  DROPBOX_APP_KEY). OAuth through the shared helper (PKCE S256,
  `token_access_type=offline`, no app secret).
- Tests: `tests/sources/test_dropbox.py` (28), `tests/api/test_dropbox_api.py`
  (12), recorded-shape JSON in `tests/fixtures/dropbox/`. No UI (task scope).

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 200 source files
================= 2870 passed, 13 skipped in 377.75s (0:06:17) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
```

## 2026-11-01 — TASK-164 Public REST API /api/v1 (T55a)

- Backend: `api/v1/` mounts the core routers (projects, uploads, sources,
  presets, jobs, clips, clip files, campaign rules, brand, caption
  templates, post copy, thumbnails, posts, read-only accounts) again under
  `/api/v1` behind `v1/auth.require_api_key` (`X-API-Key` or
  `Authorization: Bearer`; 401 `api_key_missing`/`api_key_invalid`) and a
  per-key rate limit (`api_rate_limit_per_min`, 429 + `Retry-After`).
  Keys: `api_keys.py` (`cfk_` + 256 random bits, SHA-256 digest stored,
  shown once, `last_used_at`), migration 020, owner-only `/api/api-keys`
  (list/create/revoke). OpenAPI at `/api/docs` (`/api/openapi.json`), every
  v1 operation documents 401/429/4XX `ErrorBody`. Agents may draft only:
  queue/publish stay 403 `human_only`.
- Tests: `tests/api/v1/` (OpenAPI contract tests over every v1 operation,
  agent automation loop, keys API, rate limit), `unit/test_api_keys.py`,
  `unit/test_migration_v2_api_keys.py`; `tests/openapi_check.py` mini
  schema validator. Docs: `docs/public-api.md`, README "Public API".
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 191 source files
================= 2720 passed, 13 skipped in 389.50s (0:06:29) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
✓ built in 213ms
```

## 2026-11-01 — TASK-150 Posting worker (T50a)

- Backend: `scheduler/post_worker.py` (`PostWorker`: due pickup, quota
  guard, rate limits, publish, recover interrupted uploads; started in the
  app lifespan, `run_posting`), `scheduler/post_queue.py` (`due_posts`,
  `defer`, `upload_starts`, `fail_interrupted`), `scheduler/rate_limits.py`
  (`RateLimit`, `account_limits`, `platform_limits`, `wait_until`),
  `scheduler/retry.py` (`RetryPolicy`); `publish_post` takes `retry`/`now`
  (backoff, last attempt fails, quota refusal not counted);
  `QuotaExceeded.retry_at`, `DailyQuota.next_reset/allows`,
  `PublisherEntry.quotas`, `youtube.UPLOAD_QUOTAS`; `queue_post` resets
  attempts; migration 019 (`attempted_at`, `next_attempt_at`); settings
  `post_poll_s`, `post_max_attempts`, `post_retry_base_s`,
  `post_retry_max_s`, `post_account_gap_s`, `post_platform_hourly`.
- Tests: `scheduler/test_post_worker.py`, `test_post_rate_limits.py`,
  `test_retry_policy.py`, `unit/test_migration_v2_post_attempts.py`
  (fake wall clock `fake_clock.FakeWallClock`, helpers
  `post_worker_fakes.py`).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 187 source files
================= 2515 passed, 13 skipped in 298.62s (0:04:58) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
✓ built in 243ms
```

## 2026-11-01 — TASK-147 Post API + "Schedule post" modal (T49b)

- Backend: `api/posts.py` (list/get, drafts per account, PATCH edit and
  reschedule, queue, publish now, cancel, bulk schedule), `api/post_checks.py`
  (rights, campaign permission + rules, render, account, platform
  readiness), `post_payload.py` (PostText -> native payload + limits),
  `post_schedule.py` (bulk run, daily caps), `posts.py` (`list_posts`,
  `update_post`, `cancel_post`, `scheduled_times`, `PostLocked`),
  `deps.require_human`; models `PostText`, `PostTarget`, `PostCreate`,
  `PostPatch`, `PostQueue`, `BulkSchedule`; types regenerated.
- Frontend: `components/posts/` (`SchedulePostModal`, `PostAccounts`,
  `PostTexts`, `PostWhen`, `PostButton`), `api/posts.ts`,
  `lib/postForm.ts`; Post button on `ClipCard` and the editor `TopBar`.
- Tests: `api/test_posts.py`, `test_post_publish_api.py`,
  `test_post_bulk_api.py`, `unit/test_post_payload.py`;
  `postForm.test.ts`, `SchedulePostModal.test.tsx`; e2e `posts.spec.ts`
  (screenshots `.agent/screenshots/TASK-147-{1,2,3}.png`).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 178 source files
================= 2453 passed, 13 skipped in 288.26s (0:04:48) =================
 Test Files  66 passed (66)
      Tests  447 passed (447)
✓ built in 246ms
```

## 2026-11-01 — TASK-146 Bulk scheduler core (T49a)

- `scheduler/slots.py` (`slot_instant`, `day_slots`, `iter_slots`,
  `generate_slots`, `allocate`, `AccountTarget`, `SlotAssignment`,
  `NoFreeSlot`, `HORIZON_DAYS`); `models.ScheduleRules` + `Weekday` /
  `WEEKDAYS`; frontend types regenerated.
- Tests: `scheduler/test_slots.py` (posts/day, times, skip days, start
  date, Europe/Zurich spring-forward + fall-back), `test_slot_allocation.py`
  (multi-account, max/day, busy posts, determinism, horizon),
  `test_schedule_rules.py`; helpers `schedule_fakes.py`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 174 source files
================= 2400 passed, 13 skipped in 261.24s (0:04:21) =================
 Test Files  64 passed (64)
      Tests  438 passed (438)
✓ built in 218ms
```

## 2026-11-01 — TASK-142 Facebook Pages reel publisher (T47c)

- `publishers/facebook.py` (`FacebookPublisher`, `facebook_client`,
  `from_settings`, registered in `registry.ENTRIES`),
  `publishers/facebook_api.py` (Page list, reel status, permalink,
  collaborators), `publishers/facebook_post.py` (options, reel checks,
  publish body, status mapping), `publishers/meta_upload.py` (rupload send,
  shared with Instagram); `meta_graph.MetaPublisher` / `GraphSession` base
  shared by both Meta publishers; `models.FacebookPostOptions`.
- Tests: `publishers/test_facebook.py`, `test_facebook_refusals.py`,
  `test_facebook_post.py`, `api/test_facebook_connect_api.py`, recorded
  answers in `fixtures/facebook_publish/`, helpers
  `facebook_publish_fakes.py`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 172 source files
================= 2362 passed, 13 skipped in 289.05s (0:04:49) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-11-01 — TASK-141 Instagram Reels publisher (T47b)

- `publishers/instagram.py` (`InstagramPublisher`, `instagram_client`,
  `from_settings`, registered in `registry.ENTRIES`),
  `publishers/instagram_api.py` (Graph calls, publishing limit, resumable
  upload), `publishers/instagram_post.py` (options, reel checks, container
  body, status failures), `publishers/meta_graph.py` (Meta app, long-lived
  tokens, Graph errors); `models.InstagramPostOptions`; settings
  `meta_app_id` / `meta_app_secret` / `meta_login_config_id`;
  `Publisher.finish_sign_in`, `Upload.account_external_id`,
  `base.clip_caption`; `OAuthClient.token_method` / `refresh_grant`.
- Tests: `publishers/test_instagram.py`, `test_instagram_refusals.py`,
  `test_instagram_post.py`, `api/test_instagram_connect_api.py`,
  `unit/test_oauth.py`, recorded answers in `fixtures/instagram_publish/`,
  helpers `instagram_publish_fakes.py`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 168 source files
================= 2307 passed, 13 skipped in 292.97s (0:04:52) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-11-01 — TASK-140 TikTok publisher (T47a)

- `publishers/tiktok.py` (`TikTokPublisher`, `tiktok_client`,
  `from_settings`, registered in `registry.ENTRIES`),
  `publishers/tiktok_api.py` (answers/errors, `chunk_plan`, `send_file`),
  `publishers/tiktok_post.py` (`CreatorInfo`, `options_of`, `post_info`,
  `result_of`, `failure`, `fit_utf16`); `models.TikTokPostOptions`;
  settings `tiktok_client_key` / `tiktok_client_secret`; `OAuthClient`
  `client_id_param` / `scope_separator` / `pkce_hex` / `granted()`;
  `code_challenge(hex_digest=)`.
- Tests: `publishers/test_tiktok.py`, `test_tiktok_refusals.py`,
  `test_tiktok_post.py`, `api/test_tiktok_connect_api.py`,
  `unit/test_oauth.py` (hex challenge), recorded answers in
  `fixtures/tiktok_publish/`, helpers `tiktok_publish_fakes.py`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 164 source files
================= 2245 passed, 13 skipped in 287.28s (0:04:47) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-11-01 — TASK-139 YouTube publisher (T46b)

- `publishers/youtube.py` (`YouTubePublisher`, `youtube_client`,
  `from_settings`, registered in `registry.ENTRIES`),
  `publishers/youtube_upload.py` (resumable session, chunked PUTs, resume,
  `api_error`), `publishers/youtube_metadata.py` (`options_of`,
  `video_resource`, `fit_tags`), `publishers/quota.py` (`DailyQuota`,
  `QuotaExceeded`); `models.YouTubePostOptions`; settings
  `youtube_daily_uploads` / `youtube_daily_quota_units`; `usage.current()`;
  `OAuthSession.request` takes headers/content/json; publish run and account
  callback meter inside `usage.recording`; `PublishBlocked` -> 409 handler.
- Tests: `publishers/test_youtube.py`, `test_youtube_quota.py`,
  `test_youtube_metadata.py`, `api/test_youtube_connect_api.py`, recorded
  answers in `fixtures/youtube_publish/`, helpers `youtube_publish_fakes.py`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 161 source files
================= 2204 passed, 13 skipped in 272.17s (0:04:32) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-11-01 — TASK-176 campaign creator watch (T58b.1)

- `campaign_watch.py` (`sync_channels`, `is_watched`), `auto_import.py`
  (`campaign_channels`, `remove_campaign_channels`, `add_channel(campaign_id=)`),
  migration 017 (`watched_channel.campaign_id`, `project.source_published_at`),
  `Project.fresh_upload` (derived, 48 h), `CAMPAIGN_PRIORITY = 200`,
  `youtube_watcher._import` applies the campaign preset; the campaign
  endpoints sync the watch on create/PATCH/screenshot and delete removes it.
- Tests: `unit/test_campaign_watch.py` (incl. worker dequeue order),
  `api/test_campaign_watch_api.py`, `unit/test_migration_v2_campaign_watch.py`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 147 source files
================= 2101 passed, 13 skipped in 262.84s (0:04:22) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-10-31 — TASK-195 fast creator watch (T28c)

- `backend/clipforge/watch/`: YouTube WebSub subscribe/verify/signed push
  (`websub.py`, `youtube_watcher.py`), per-feed 60 s polling with
  ETag/Last-Modified, jitter and backoff (`rss_poll.py`), Twitch app token,
  Helix polling and EventSub `stream.online` webhooks (`twitch_api.py`,
  `twitch_watcher.py`, `twitch_eventsub.py`), @handle lookup
  (`youtube_handles.py`), alerts (`events.py`), derived HMAC secrets
  (`keys.py`). Migration 014; `/api/watch/{status,events,streamers}` and
  the push callbacks; new uploads at `TOP_PRIORITY`.
- Frontend: Watchlist page (`/watchlist`, `/auto-import` redirects) with
  push/polling banner and badges, Twitch streamers, Recent alerts and
  desktop alert permission; `useWatchAlerts` toasts + notifies on any page.
- Tests: test_watch_schedule, test_watch_polling, test_websub,
  test_twitch_watch, test_migration_v2_watch, test_watch_api,
  test_watch_callbacks (recorded responses, fake clock, no network);
  Watchlist/StreamerSection/RecentAlerts/useWatchAlerts/lib watch Vitest;
  e2e/watchlist.spec.ts.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 140 source files
================= 1985 passed, 13 skipped in 254.02s (0:04:14) =================
 Test Files  59 passed (59)
      Tests  412 passed (412)
$ npx playwright test -c e2e
  8 passed (1.2m)
```

## 2026-10-31 — TASK-66 Google Drive import (T27d)

- Shared OAuth helper (`oauth.py`, `oauth_flows.py`, `oauth_tokens.py`):
  PKCE S256 + state, code exchange, refresh (60 s margin, retry once after
  401, `invalid_grant` forgets the token), 0600 token files by token_ref.
- `sources/gdrive.py`: Drive link/id parsing, files.get metadata and
  alt=media download (size-checked `.part` file); ingest uses it for Drive
  links when connected. `api/gdrive.py`: status, connect, callback page,
  disconnect, file lookup, import (412 needs_credentials without
  GOOGLE_OAUTH_CLIENT_ID).
- Home: "Google Drive" button and dialog (needs credentials / connect /
  paste link) feeding the settings panel.
- Tests: test_oauth (13), tests/sources/test_gdrive (26),
  test_gdrive_api (12) with respx recorded responses;
  HomePage.drive.test.tsx (5); e2e/gdrive.spec.ts (2).

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 121 source files
================= 1885 passed, 13 skipped in 263.07s (0:04:23) =================
 Test Files  53 passed (53)
      Tests  371 passed (371)
$ cd e2e && npx playwright test -c . smoke.spec.ts gdrive.spec.ts
  4 passed (5.3s)
```

## 2026-10-31 — TASK-65 local inbox folder watch (T27c)

- `inbox_watch.InboxWatcher` polls `INBOX_DIR` every `INBOX_POLL_S`; a
  video file with the same size and mtime in two polls becomes a project;
  imports are recorded by path+size+mtime (`inbox_import`, migration 012);
  non-video, hidden and empty files are ignored; a used-up usage cap makes
  files wait. Started by the app lifespan.
- Tests: test_inbox_watch (fake clock), test_migration_inbox_import,
  test_inbox_api.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 115 source files
================= 1834 passed, 13 skipped in 233.45s (0:03:53) =================
 Test Files  52 passed (52)
      Tests  366 passed (366)
```

## 2026-11-01 — TASK-39 clip settings panel parity (STEERING 10)

- Genres (11, own curate prompts), multi-select clip lengths
  (`length_presets`, migration 011), toggles (auto headline, zoom, cut,
  color, fillers), speech language + SRT upload (skip Whisper), AI / No
  clipping tabs, find-moments prompt, timeframe inputs, caption grid with
  "No captions", aspect select, My presets, Save as default, copyright note.
- Tests: test_auto_color, test_srt_import, test_presets_api,
  test_subtitles_api, test_migration_settings_panel, snap no-clipping,
  SettingsPanel(.presets).test.tsx, processingSettings.test.ts.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 112 source files
================= 1802 passed, 13 skipped in 232.88s (0:03:52) =================
 Test Files  51 passed (51)
      Tests  361 passed (361)
```

## 2026-10-31 — TASK-63: Generic video URL import via yt-dlp (T27a)

- New `pipeline/extractors.py`: `extractor_for`, `is_direct_media`,
  `require_supported`, `UnsupportedSource` (a `StepError`). Called by
  `download.download`/`probe`, `POST /projects` and `POST /sources/probe`
  (422 `unsupported_source`). Direct media links use `DIRECT_FORMAT`.
- Tests: `tests/pipeline/test_download_generic.py` (extractor list, Vimeo/Zoom,
  real generic extractor on a file:// fixture, ingest end to end) plus new
  cases in `test_projects.py` and `test_sources_api.py`.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 91 source files
================= 1491 passed, 9 skipped in 236.90s (0:03:56) ==================
 Test Files  39 passed (39)
      Tests  300 passed (300)
✓ built in 217ms
```

## 2026-10-31 — TASK-54: Player crop frame: drag/resize crop box, aspect + layout toolbar (T21c)

- Checks (SPEC 0.1): ffmpeg `crop` evaluates `w`/`h` once and `x`/`y` per
  frame (so the window size is per clip, keyframes move x and y); `pad`
  options `w:h:x:y:color` (black fit = `scale=...:force_original_aspect_ratio=
  decrease:force_divisible_by=2,pad=...:black`). Render + ffprobe + pixel
  test on a four-color 1280x720 source.
- New: `Framing`/`CropPoint`/`CropTrack` models, `Clip.framing` (migration
  003), `CropKeyframe.y`, `CropPlan.background`; `pipeline/framing.py`
  (`framed_plan`, `apply_crop_tool`, `crop_track`), `reframe.replan`,
  `reframe.scene_cuts`; layouts crop y expression and black fit; render and
  preview use `framed_plan`; `GET /clips/{id}/crop?aspect=`
  (`api/clip_crop.py`). Frontend: `PlayerToolbar`, `PlayerCrop`,
  `PreviewColumn`, `lib/cropFrame.ts`, `useCropTrack`, `ClipLook.framing`.
- Tests: `test_framing.py`, `test_framing_render.py`,
  `test_clip_crop_api.py`, db/migration/model updates; `cropFrame.test.ts`
  (clamp inside frame, keeps aspect), `EditorCrop.test.tsx` (menus,
  tracker, drag/resize/arrow keyframes, undo, reset, close on split).
- Playwright (1440x900, seeded uvicorn + vite): toolbar, crop tool, drag +
  corner resize (keyframe at 00:10.00), aspect menu, 1:1 window, fit
  background menu; console errors: none. PATCHed framing (1:1, black,
  scale 0.6, tracker off) renders a 540x540 preview.
  Screenshots `.agent/screenshots/TASK-54-1..6.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1314 passed, 1 skipped in 121.52s (0:02:01) ==================
 Test Files  30 passed (30)
      Tests  245 passed (245)
✓ built in 131ms
```

## 2026-10-31 — TASK-44: Editor panels: Captions + Layout (T21a)

- Checks (SPEC 0.1): ffmpeg's crop filter clamps x to the frame on the
  right (gradient render test: offset 0.5 -> x 602, -0.25 -> 300, clamps to
  876 and 0); react-hooks lint rejects setState in effects, so gesture ids
  come from `useGesture` (pointerdown/focus).
- New: `Clip.caption_style` + `crop_offset` (models, ClipRow, ClipPatch,
  migration 002), `CaptionTemplate.styled`, `clip_template`, `nudge_plan`
  (render + preview); frontend `CaptionsPanel`, `LayoutPanel`, `ColorField`,
  `PanelSlider`, `CaptionSample`, `CaptionWordTexts`, `lib/clipLook.ts`,
  `lib/wordTexts.ts`, `hooks/useGesture.ts`, `ui/toggle-row.tsx`;
  `useClipEdits.look/setLook`, `EditorRail` tabs.
- Tests: `test_caption_style.py`, nudge tests in `test_layouts.py`, PATCH
  style/offset tests; `clipLook`, `wordTexts`, `useClipEdits` (PATCH
  payload), `EditorPanels` (templates, size/color undo steps, word text,
  layout, crop offset).
- Playwright (1440x900, seeded uvicorn + vite): Captions tab (template,
  colors, position, emoji, word edit), Layout tab (nudge, split, fill);
  console errors: none. Screenshots `.agent/screenshots/TASK-44-1..4.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1296 passed, 1 skipped in 116.16s (0:01:56) ==================
 Test Files  28 passed (28)
      Tests  226 passed (226)
✓ built in 133ms
```

## 2026-10-31 — TASK-53: Transcript editor polish: pause pills, selection toolbar, extend clip, speech cleanup (T20d)

- Checks (SPEC 0.1): radix DropdownMenu inside the transcript `<p>` needs
  `modal={false}` and span content; jsdom has no `scrollIntoView`; the
  fixture clip 0.5-34.35 without laughs gives 4 suggestions (um, pause
  3.1 s, like, pause 1.2 s), with laughs only the two fillers.
- New: `CleanupSuggestion` schema; `polish.cleanup_suggestions` (fillers and
  pauses, `filler_cuts` now derived from it), `load_polish_inputs`; `GET
  /api/clips/{id}/cleanup-suggestions?start&end`. Frontend:
  `TranscriptToolbar`, `ClipWords`, `SelectionToolbar`, `TranscriptContext`,
  `SpeechCleanup`; `lib/transcriptView.ts`, `lib/cleanup.ts`,
  `hooks/useTranscriptSearch.ts`; `useClipEdits` adds title/hook texts,
  `setTexts`, `cutAll` (one undo step); PATCH body has title + hook_text.
- Tests: `test_cleanup_suggestions.py` (4), `test_cleanup_suggestions_api.py`
  (3); `transcriptView.test.ts`, `cleanup.test.ts`,
  `EditorTranscriptTools.test.tsx` (pause pill cut, toolbar hook/title +
  delete, cleanup dialog -> cuts + undo, search n/m + Enter, extend to a
  context word, current word while playing); updated
  `EditorTranscript.test.tsx`, `EditorTimeline.test.tsx`.
- Playwright (1440x900 and 1280x800, seeded uvicorn + vite): 10 pause pills,
  current word "tried" while playing, selection -> Use as hook, Delete cut,
  cleanup 3 of 4 applied (cuts 4, length 00:29.08), search "floor" 1/1,
  extend to a context word -> Out 00:36.94; console errors: none.
  Screenshots `.agent/screenshots/TASK-53-1..5.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1284 passed, 1 skipped in 119.81s (0:01:59) ==================
 Test Files  24 passed (24)
      Tests  202 passed (202)
✓ built in 221ms
```

## 2026-10-31 — TASK-52: Editor timeline: filmstrip, waveform, ruler, zoom, split, segment row (T20c)

- Checks (SPEC 0.1): ffmpeg-full 9.0.2 `fps=R,scale=-2:90,tile=Nx1` writes a
  short last row padded black (0.2 s for 60 tiles); a source with no audio
  makes `-map 0:a:0 ... -f s16le pipe:1` exit 234, so the audio is probed
  first; jsdom has no `createImageBitmap`/`URL.createObjectURL`.
- New: `pipeline/preview_assets.py` (filmstrip ≤240 tiles at 1 s+ intervals,
  90 px high; waveform 50 peaks/s at 8 kHz mono; cached per clip span in
  previews/, an older filmstrip of the clip is deleted); `GET
  /api/clips/{id}/filmstrip` + `/waveform` (409 without a source, 500
  render_failed on ffmpeg errors). Frontend: `TimelineControls`,
  `TimelineTracks`, `TimelineRuler`, `TimelineSegments`, `TimelineFilmstrip`,
  `TimelineWaveform`, `TimelineHandle`; `lib/segments.ts`,
  `lib/timelineMedia.ts`, `lib/timelineActions.ts`, `hooks/useTimelineState.ts`,
  `hooks/useDrag.ts`, `api/timelineAssets.ts`; `useClipEdits` adds splits and
  `patch` (`clipPatch`: {start, end, cut_ranges}); shortcuts S, +/-, arrows.
  Removed `components/Timeline.tsx`.
- Tests: `test_preview_assets.py` (4), `test_timeline_assets_api.py` (5:
  both endpoints, cache hit without ffmpeg, new span → new strip, errors);
  `segments.test.ts` (split at playhead → segments, snapping, skip),
  `timelineMedia.test.ts`, zoom math in `timeline.test.ts`,
  `EditorTimeline.test.tsx` (S split, select + Delete segment, snap toggle,
  zoom, hide, step/skip, filmstrip + waveform, end-handle drag → PATCH body).
- Playwright (1440x900 and 1280x800, seeded uvicorn + vite): 17 filmstrip
  tiles, split at 27.10, segment delete merges into the cut, zoom 225% with
  the playhead kept on screen, end handle drag → 00:30.65, hide/show;
  console errors: none (after fixing a StrictMode-revoked blob URL).
  Screenshots `.agent/screenshots/TASK-52-1..5.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1277 passed, 1 skipped in 132.11s (0:02:12) ==================
 Test Files  21 passed (21)
      Tests  183 passed (183)
✓ built in 134ms
```

## 2026-10-31 — TASK-43: Editor transcript editing, cuts, undo/redo, shortcuts (T20b)

- Checks (SPEC 0.1): lucide-react exports `Undo2`, `Redo2`, `MoveHorizontal`;
  React 18.3 (no `useEffectEvent`: latest handlers kept in a ref set in an
  effect); `caption_lines.word_groups` yields the Whisper words of each
  piece of a segment's text; FastAPI `Query(ge=0, le=300)` answers 422.
- New: `GET /api/clips/{id}/transcript` (`clip_transcript.py`),
  `lib/history.ts`, `lib/cuts.ts`, `hooks/useClipEdits.ts`,
  `hooks/useEditorShortcuts.ts`, `components/editor/{TranscriptEditor,
  TranscriptColumn,TopBar}.tsx`; `Timeline` passes a drag gesture id.
- Tests: `test_clip_transcript.py` (4), `test_clip_transcript_api.py` (3),
  `history.test.ts` (9: undo/redo reducer), `cuts.test.ts` (8: selection ->
  cut_ranges merge/trim, restore, struck words), `useEditorShortcuts.test.ts`
  (6), `EditorTranscript.test.tsx` (10: seek, drag/shift select + Delete,
  undo/redo buttons and cmd+Z, restore, extend, drag = one undo step,
  Space, error/empty states).
- Playwright (headless shell 1248, 1440x900 and 1280x800, seeded uvicorn +
  vite): drag-select "one of those" + Delete -> 2 cuts struck, cmd+Z -> 1,
  shift+cmd+Z -> 2, click "Like," restores, "Extend to here" on "floor?" ->
  In 00:12.99, Space plays; console errors: none. Screenshots
  `.agent/screenshots/TASK-43-1..5.png`.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 72 source files
================= 1248 passed, 1 skipped in 137.96s (0:02:17) ==================
 Test Files  18 passed (18)
      Tests  156 passed (156)
✓ built in 222ms
```

## 2026-10-31 — TASK-42: Editor player + timeline handles (T20a)

- Checks (SPEC 0.1): `GET /clips/{id}` returns one clip; `/clips/{id}/preview`
  is the saved clip rendered with its cuts removed (so preview time != source
  time); lucide-react exports `ArrowLeft`, `Play`, `Pause`, `Gauge`,
  `GripVertical` (`Loader2` is an alias); `HTMLMediaElement.play()` returns a
  promise; `setPointerCapture` is missing in jsdom (called with `?.`).
- New: `pages/Editor.tsx` (route `/clips/:clipId`, full screen outside
  `AppShell`), `components/Timeline.tsx`, `components/editor/{PreviewPlayer,
  ClipDetails,EditorRail,TimelinePanel}.tsx`, `components/ScoreBreakdown.tsx`
  (extracted from `ScoreBadge`), `hooks/usePreviewPlayer.ts`,
  `hooks/useElementWidth.ts`, `lib/timeline.ts`, `useClip` in `api/clips.ts`,
  `formatTimecode` in `lib/format.ts`, `SCORE_TEXT` in `lib/clips.ts`.
- Tests: `timeline.test.ts` (px<->time, clamping, min length, cuts fit/merge,
  preview<->source mapping, ruler), `format.test.ts` (timecode),
  `Editor.test.tsx` (7: layout, play/pause, pointer drag of the end handle,
  keyboard + min length, seek across a cut, score rail, missing clip).
- Playwright (headless shell 1248, 1440x900 and 1280x720; vite + uvicorn
  without worker, temp `DATA_DIR`, seeded clip 12-38 s with cut 20-23 s): the
  real 540p preview plays and the playhead moves; mouse drags move the
  handles (12/38 -> 9.76/42.83), end stops 1 s after start, handles stop at
  the window edges (0-60 s); a click at source 27 s seeks the preview to 12 s.
  Console: no errors. Screenshots `.agent/screenshots/TASK-42-1..5.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1241 passed, 1 skipped in 139.41s (0:02:19) ==================
 Test Files  14 passed (14)
      Tests  123 passed (123)
✓ built in 234ms
```

## 2026-10-31 — TASK-41: Clips gallery (T19)

- Checks (SPEC 0.1): `GET /projects/{id}/clips` has `sort`, `min_score`, `q`
  (api/clips.py); `/clips/{id}/preview` renders a 540p mp4 on first request;
  `/clips/{id}/download` is 404 until rendered; radix-ui exports `Popover` and
  `Slider` (single value `[n]`); no clip delete existed, so
  `DELETE /clips/{id}` was added (2 API tests).
- New: `pages/Gallery.tsx`, `components/{ClipCard,ScoreBadge,GalleryToolbar}.tsx`,
  `api/clips.ts` (`useClips`, `useClipCount` moved here, `useRenderingClipIds`,
  `useRenderClips`, `useDeleteClip`), `lib/clips.ts`.
- Tests: `clips.test.ts` (badge tone at 59/60/79/80, filter/sort),
  `ScoreBadge.test.tsx` (colors at 59/60/79/80, breakdown), `Gallery.test.tsx`
  (10: order, search/min score/sort, hover preview, download, render all,
  remove, empty states).
- Playwright (headless chromium 1440x900 and 1280x720; vite + uvicorn
  without worker, temp `DATA_DIR`, 8 seeded clips): cards sorted by score,
  hover plays the real preview mp4, score popover, search. Console: no
  errors. Screenshots `.agent/screenshots/TASK-41-1..5.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1241 passed, 1 skipped in 135.07s (0:02:15) ==================
 Test Files  12 passed (12)
      Tests  101 passed (101)
✓ built in 208ms
```

## 2026-10-31 — TASK-40: Processing view (T18)

- Checks (SPEC 0.1): `GET /jobs/{id}/events` (api/jobs.py) sends
  `{step, progress, status, message}` at once and on each change, then ends
  after done/failed; browser `EventSource` has `onmessage`/`close()` and
  reconnects by itself (so the hook closes it on a terminal event).
- New: `pages/Processing.tsx`, `components/processing/{StepList,LogDrawer}.tsx`,
  `hooks/{useJobEvents,useElapsed}.ts`, `api/jobs.ts` (`useProcessJob`),
  `lib/processingSteps.ts`, `testing/fakeEventSource.ts`.
- Playwright (headless chromium 1280x800, vite + uvicorn without worker, temp
  `DATA_DIR`, a script moved a seeded process job through the steps): bar and
  steps follow the events, log drawer lines, leave/return resumes (43 %, Find
  clips running), done switches to the clips text, failed shows the error.
  Console: no errors. Screenshots `.agent/screenshots/TASK-40-1..4.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1239 passed, 1 skipped in 132.58s (0:02:12) ==================
 Test Files  9 passed (9)
      Tests  73 passed (73)
✓ built in 238ms
```

## 2026-10-31 — TASK-39: Settings panel + Get clips (T17b)

- Checks (SPEC 0.1): yt-dlp 2026.10.26 `extract_info(url, download=False)`
  returns title/duration/thumbnail (`_type` "playlist" for lists); radix-ui 1.8.1
  `Slider.Root/Track/Range/Thumb` (`minStepsBetweenThumbs`) and
  `Switch.Root/Thumb` need `ResizeObserver` (jsdom polyfill in test-setup.ts).
- New: `api/sources.py` (`POST /sources/probe`, `GET /processing-defaults`),
  `download.probe()`, `models.HttpUrl`; frontend `SettingsPanel.tsx`,
  `components/settings/*`, `api/sources.ts`, `api/templates.ts`,
  `lib/processingSettings.ts`, `lib/useSourceDetails.ts`, `pages/ProjectPage.tsx`,
  `testing/mockApi.ts`.
- Playwright (headless chromium, 1440x900, `make dev`, temp `DATA_DIR`): live
  probe of "Me at the zoo" (thumbnail, 00:19), all controls changed and the
  POST body equals the chosen settings (POST mocked), navigation to
  /projects/77, file upload (duration 01:00 read by the browser), playlist link
  shows the error and disables "Get clips". Console: only the expected 422.
  Screenshots `.agent/screenshots/TASK-39-1..6.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1239 passed, 1 skipped in 138.32s (0:02:18) ==================
 Test Files  7 passed (7)
      Tests  53 passed (53)
✓ built in 250ms
```

## 2026-10-31 — TASK-38: Home page (T17a)

- Checks (SPEC 0.1): lucide-react exports `Link2`, `Upload`, `UploadCloud`,
  `Film`, `FolderOpen`, `Loader2`; TanStack Query v5 `refetchInterval` takes
  `(query) => number | false`; a drag event's `dataTransfer.types` contains
  "Files" for files (jsdom has no DragEvent: tests use `fireEvent.dragEnter`).
- New: `GET /media/{id}/thumbnail` (thumb.jpg of the latest process job);
  `api/projects.ts` (`useProjects`, `useClipCount`, `useAddProject`),
  `lib/videoSource.ts`, `lib/format.ts`, `lib/useFileDrop.ts`,
  `components/SourceInput|ProjectCard|RecentProjects.tsx`, `pages/HomePage.tsx`.
- Playwright (headless chromium, 1440x900, `make dev`, temp `DATA_DIR`): empty
  state from the real API, bad link shows the inline error, grid with the 4
  statuses (API answers mocked, thumbnail is a real frame), full-page drop
  overlay; no console errors. Screenshots `.agent/screenshots/TASK-38-1..4.png`.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 70 source files
================= 1231 passed, 1 skipped in 112.81s (0:01:52) ==================
 Test Files  5 passed (5)
      Tests  40 passed (40)
✓ built in 158ms
```

## 2026-10-31 — TASK-37: Frontend shell (T16b)

- Checks (SPEC 0.1): lucide-react 1.65 exports `House`, `FolderOpen`,
  `Palette`, `Settings`, `CircleHelp`, `PanelLeftClose/Open`; React Router 7
  `<Route element>` layouts with `<Outlet/>`; Vitest has no globals, so
  `test-setup.ts` calls RTL `cleanup` after each test.
- New: `components/AppShell|Sidebar|TopBar|Toaster|PageHeader.tsx`,
  `navigation.ts`, `pages/*`, `routes.tsx`, `api/client.ts` (`apiFetch`,
  `ApiError`), `api/queryClient.ts`, `lib/toast.ts`.
- Playwright (headless chromium, 1440x900, `make dev`): `/`, `/projects`,
  `/brand-templates`, `/settings` render their h1; `apiFetch("/projects/9999")`
  shows the toast "project 9999 not found". Screenshots
  `.agent/screenshots/TASK-37-1..6.png`.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 70 source files
================= 1229 passed, 1 skipped in 123.24s (0:02:03) ==================
 Test Files  2 passed (2)
      Tests  15 passed (15)
✓ built in 199ms
```

## 2026-10-31 — TASK-36: Type generation script (T16a)

- Checks (SPEC 0.1): `json2ts -h` (json-schema-to-typescript 16.0.0) has
  `--unreachableDefinitions`, `--no-additionalProperties`, `--no-format`,
  `--maxItems`, `--bannerComment`; `pydantic.json_schema.models_json_schema`
  takes `(model, mode)` pairs and `ref_template`; json2ts does not read
  `prefixItems` (tuples), so the script turns it into the draft-07 `items`.
- New `scripts/gen_types.py`: JSON schemas of every model of `models.py`
  and of the API (`settings_edit`, `api/settings`, `api/caption_templates`)
  -> json2ts -> the frontend's prettier -> `frontend/src/api/types.ts`
  (generated header). `--check` exits 1 when the file is stale; `make
  lint` (so `make check`) runs it. New devDependency
  `json-schema-to-typescript`.
- Stale check demonstrated: adding `extra_demo: int = 0` to `Word` in
  models.py made `gen_types.py --check` print "types.ts is stale" and exit
  1; reverting it gave exit 0.

Verification command and real output:

```text
$ make check
Success: no issues found in 70 source files
uv run python scripts/gen_types.py --check
================= 1229 passed, 1 skipped in 139.22s (0:02:19) ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 101ms
```

## 2026-10-31 — TASK-35: API brand templates, caption templates, settings (T15e)

- Checks (SPEC 0.1): FastAPI `Form()` params and `UploadFile` can be mixed
  (an empty file input arrives as `filename=""`, `size=0`; an empty text
  field counts as absent); pydantic-settings reads `.env`, `.env.local`
  from the cwd after the real environment and before config.yaml
  (`settings_customise_sources`); `ffmpeg ... -f lavfi -i color=...,
  subtitles=...` draws one libass frame (`-ss` as an output option).
- New `api/brand.py` + `brand_files.py` (CRUD, logo/intro/outro uploads
  staged, validated, then published), `api/caption_templates.py` +
  `caption_previews.py` (6 PNGs 540x960 drawn at startup, cached by hash in
  `data/caption_previews/`), `api/settings.py` + `settings_edit.py` +
  `env_file.py` (GET/PUT /settings saved in `.env.local`, POST
  /settings/test-llm); `config.LlmProvider`; `create_app(caption_previews=,
  llm_transport=)`.
- Tests (+66): `tests/api/test_brand_settings.py` (27),
  `test_settings_api.py`, `test_caption_templates_api.py`,
  `tests/unit/test_env_file.py`; the API conftest runs every test in an
  empty cwd so the real `.env.local` is never read or written.
- Live smoke: uvicorn + curl in a scratch cwd: 6 previews drawn at startup,
  preview 200 image/png, PUT /settings wrote a 0600 `.env.local` and the
  response had `openai_api_key_set: true` and no key, test-llm against a
  closed port -> ok false, brand create 201, create without a name -> 422.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 69 source files
================= 1222 passed, 1 skipped in 118.87s (0:01:58) ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 105ms
```

## 2026-10-31 — TASK-34: API clips (T15d)

- Checks (SPEC 0.1): fastapi 0.162 / starlette 1.10 `FileResponse(path,
  filename=...)` sets `Content-Disposition: attachment; filename="..."`
  (`filename*=utf-8''` for non-ASCII); `Query(ge=, le=)` gives a 422;
  pydantic `ConfigDict(extra="forbid")` rejects unknown PATCH fields.
- New `api/clips.py` (list/get/PATCH/regenerate-text) and
  `api/clip_files.py` (render, preview, download, srt, download.zip,
  premiere.xml); `deps.py` gained `get_llm`, `clip_row`, `project_row`,
  `work_dir` (projects.py and media.py reuse `project_row`).
- New `clip_edit.py`, `clip_text.py` + `prompts/clip_text.md`,
  `preview.py`; `render_clip(size=)`, `write_captions(output=)`; models
  `ClipText`, `ClipPatch`; `seed.add_work`, `seed.add_plan`.
- Tests: `tests/api/test_clip_endpoints.py` (23), `test_clip_files.py`
  (12; the second preview runs no ffmpeg).
- Live smoke: uvicorn + curl on a seeded project: preview 540x960 2.1 s
  (after a 0.4 s cut) in 0.67 s, then 0.06 s cached and byte-identical;
  render job -> done; download `1-yoga-body.mp4`, SRT, zip (mp4, srt,
  json), premiere.xml 200; end before start -> 422; clip 99 -> 404.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 61 source files
================= 1156 passed, 1 skipped in 106.94s (0:01:46) ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 100ms
```

## 2026-10-31 — TASK-33: API jobs + SSE events (T15c)

- Checks (SPEC 0.1): fastapi 0.162 / starlette 1.10 `StreamingResponse`
  takes an async generator and `media_type="text/event-stream"`; an SSE
  event is `data: <text>\n\n`, a line starting with `:` is a comment
  (keep-alive); `anyio.to_thread.run_sync` runs the blocking SQLite read.
- New `api/jobs.py`: GET /projects/{id}/jobs (newest first), GET
  /jobs/{id} and GET /jobs/{id}/events. Event data is JSON {step,
  progress, status, message}; one event at once, another on each change,
  the stream ends after status done or failed (or when the job row is
  deleted). Job has no message column: message is the error of a failed
  job, else a sentence for the status.
- Tests: `tests/api/test_job_endpoints.py` (8; named so as not to clash
  with `tests/unit/test_jobs.py`, there is no `__init__.py`), `add_job`
  moved to `tests/seed.py`.
- Live smoke: uvicorn + curl, uploaded junk -> SSE gave running, then
  failed with the ffprobe error and closed; /projects/1/jobs listed it;
  /jobs/9 -> 404 JSON.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 57 source files
================== 1121 passed, 1 skipped in 118.01s (0:01:58) ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 114ms
```

## 2026-10-31 — TASK-32: API projects, upload, media Range, error handler (T15b)

- Checks (SPEC 0.1): starlette 1.10 `FileResponse` handles `Range` itself
  (single and multiple ranges: 206 + `Content-Range: bytes a-b/size`; 416 +
  `bytes */size` when unsatisfiable); `UploadFile.file` is a file object
  (`shutil.copyfileobj`); FastAPI form/file parameters need
  `python-multipart` (added with `uv add python-multipart`, 0.0.32);
  Starlette re-raises an unhandled exception after the `Exception`
  handler's response, so `TestClient(raise_server_exceptions=False)` sees
  the 500 JSON.
- New `api/`: `app.py` (`create_app(run_worker, llm, transcript)`, the
  lifespan checks ffmpeg, runs `init_db()` and starts/stops the `JobWorker`;
  `app = create_app()` for uvicorn), `errors.py` ({error, message} for
  `ApiError`, HTTP errors, 422 and unhandled exceptions), `deps.py`,
  `projects.py` (POST /projects, POST /projects/upload, GET /projects,
  GET/DELETE /projects/{id}) and `media.py` (GET /media/{id}/source).
  `ProjectCreate` in models.py; `jobs.process_work_dir` is now public.
- Tests: `tests/api/test_projects.py`, `test_media_errors.py` (33; the
  worker test uploads junk and sees the project fail).
- Live smoke: uvicorn on 127.0.0.1, 422 JSON for a bad URL, upload of
  sample.mp4 -> project 1 whose job ingested it, `curl -r 0-9` on the
  media URL -> 206 Partial Content, content-length 10.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 56 source files
================== 1113 passed, 1 skipped in 93.85s (0:01:33) ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 109ms
```

## 2026-10-31 — TASK-31: SQLite job worker (T15a)

- Checks (SPEC 0.1): `threading.Event.wait(timeout)` returns True when set
  (used to sleep between polls and be woken by `wake()`); SQLModel
  `delete(ClipRow).where(...)` runs via `session.exec`; SQLite engines are
  shared across threads (SQLAlchemy 2 pool), each call opens its own Session.
- New `jobs.py`: `enqueue_process` (= `process.create_job`),
  `enqueue_render(engine, clip_id)` (render job with clip_id, log in
  `work/<job_id>/job.log`, renders from the project's latest process job's
  work dir), `reset_stale_jobs` (running -> queued, step/progress/error
  cleared, process project -> queued), `run_next` (claim oldest queued, run,
  never raises) and `JobWorker` (thread `clipforge-jobs`, `start` resets
  stale jobs, `wake`, `stop`). A restarted process job first deletes its
  project's clips (save_clips would duplicate them). New `joblog.py`
  (`job_log` moved out of process.py, now writes INFO even when the package
  logger is at WARNING, as under uvicorn).
- Tests: `test_jobs.py` (lifecycle queued -> running -> done of a real
  process job on the fixture and then a render job through the worker
  thread; failing process/render jobs; stale reset; enqueue errors),
  `test_joblog.py`.

Verification command and real output:

```text
$ make check
All checks passed!
Success: no issues found in 52 source files
================= 1080 passed, 1 skipped in 105.94s (0:01:45) ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 98ms
```

## 2026-10-31 — TASK-30: Premiere FCP7 XML, xmeml v4 (T14b)

- Checks (SPEC 0.1): Apple's FCP7 XML reference and its xmeml v4 DTD
  (ids are CDATA, so repeated `<file id="file-1"/>` references are valid;
  no `numOutputChannels`/`premiere*` attributes); a Premiere Pro export
  (OTIO's sample `premiere_example.xml`: `xmeml version="4"`,
  `file://localhost/...` pathurls, stereo as two mono tracks with
  sourcetrack trackindex 1/2 and outputchannelindex 1/2, links with
  groupindex 1 for audio) and auto-editor's fcp7 writer (same layout).
  Python 3.11: `ET.indent(tree, space)`; `ET.tostring(root,
  encoding="unicode")` writes no declaration; a \x0b in text makes the
  output unparseable ("not well-formed (invalid token)").
- Real run (test mode, `DATA_DIR=/tmp/cf30/data`):
  `CLIPFORGE_TEST_MODE=1 uv run clipforge run
  backend/tests/fixtures/sample.mp4 --num-clips 3 --fixtures-dir
  backend/tests/fixtures` (exit 0, 3 of 3 clips rendered), then
  `clips.export_premiere(create_db_engine(), 1, data_dir / "work/1")`:
  "wrote Premiere XML of 3 clips of project 1 to
  /tmp/cf30/data/output/1/premiere.xml" (372 lines). Sequences, best first:
  "01 My Body Had One Question in Yoga Class" (clip 1, 0.5-34.35 s: in 15,
  out 1030, 1015 frames), "02 My Smart Fridge and My Car Both Judge Me"
  (16.9-53.05 s: 507-1592), "03 Car Assistant Recalculates His Life
  Choices" (35.8-59.8 s: 1074-1794); each a video and one audio clipitem
  (the fixture is mono 48 kHz), file 1800 frames at 30 NDF, pathurl
  `file://localhost/tmp/cf30/data/work/1/source.mp4`.
  - `xmllint --noout --dtdvalid xmeml_v4.dtd premiere.xml`: valid (exit 0,
    no output).
  - OpenTimelineIO 0.18.1 + otio-fcp-adapter (`uv run --python 3.11
    --no-project --with opentimelineio --with otio-fcp-adapter`, not a
    project dependency) reads a SerializableCollection of 3 timelines
    named like the sequences, durations 1015/1085/720; Video and Audio
    clips start at 15/507/1074 with that target_url.
  - The same clips on a stereo 44.1 kHz source at 30000/1001 fps
    (build_xmeml): DTD-valid; OTIO tracks Video, Audio, Audio, clip 1 in 15
    for 1014 frames at rate 29.97.
- New tests: unit/test_fcpxml.py (rate table, frames at 30 and 29.97 fps,
  pathurl encoding, file described once, mono/stereo/5.1 tracks and links,
  escaping and stripped control characters, export_premiere on the
  fixture, missing project/meta.json/source.mp4/audio); DB row helpers in
  tests/seed.py.
- `make check` (exit 0), last lines:
  ```text
  Success: no issues found in 50 source files
  ================== 1063 passed, 1 skipped in 72.54s (0:01:12) ==================
   Test Files  1 passed (1)
        Tests  1 passed (1)
  ✓ built in 97ms
  ```

## 2026-10-31 — TASK-29: Export SRT, JSON metadata, zip (T14a)

- Checks (SPEC 0.1), Python 3.11 + ffmpeg-full 9.0.2:
  - `help(zipfile.ZipFile)`: `ZipFile(file, mode='r', compression=0,
    allowZip64=True, compresslevel=None, *, strict_timestamps=True,
    metadata_encoding=None)`; `write(filename, arcname=None,
    compress_type=None, compresslevel=None)`.
  - `string.Formatter().parse`: "{}" gives field ''; "{channel:{title}}"
    spec '{title}'; "Credit: {channel" raises "expected '}' before end of
    string"; "Credit: channel}" "Single '}' encountered in format string";
    the generator is lazy (errors come from `list(...)`).
  - ffmpeg's srt muxer/demuxer: `ffmpeg -i ours.srt out.srt` (re-encoded
    and `-c:s copy`) gives the same bytes, with a UTF-8 em dash, é and an
    emoji; it writes a blank line after every cue, the last one too.
- Real run (test mode, `DATA_DIR=/tmp/cf29/data`, fixture sample): output
  `data/output/1/` = 1.json, 1.mp4, 1.srt. 1.srt has 25 cues for clip A's
  62 words, from "1 / 00:00:00,000 --> 00:00:01,030 / Hi everyone." to
  "25 / 00:00:31,220 --> 00:00:32,350 / about the cheese."; the last ASS
  line of captions_1.ass also ends 0:00:32.35. `ffmpeg -i 1.srt rt.srt`:
  `cmp` identical. 1.json: title "My Body Had One Question in Yoga Class",
  its description, hashtags ["standupcomedy", "yoga", "smartfridge",
  "comedy"], `"credit": null` (a local file has no channel).
- New tests: unit/test_export.py (exact SRT text, edge cases, ffmpeg round
  trip, write_srt after cuts and overrides, credit lines, metadata, zip
  members and compression), unit/test_clips_export.py (zip order, kept
  SRT, fresh JSON with "Credit: Sample Comedian", missing video, empty zip,
  errors), test_config.py (credit_template validation); test_run_minimal
  checks the real SRT and JSON.
- `make check` (exit 0), last lines:
  ```text
  Success: no issues found in 49 source files
  ================== 1039 passed, 1 skipped in 72.93s (0:01:12) ==================
   Test Files  1 passed (1)
        Tests  1 passed (1)
  ✓ built in 79ms
  ```

## 2026-10-31 — TASK-28: Loudnorm two-pass + cut_ranges render (T13b)

- Checks (SPEC 0.1), ffmpeg-full 9.0.2: `ffmpeg -h filter=X` for loudnorm
  (i, lra, tp, measured_i/tp/lra/thresh, offset, linear, print_format),
  trim, atrim, setpts, asetpts, split, asplit, concat, aresample, aselect,
  ebur128, drawbox and aevalsrc. Real runs:
  - Pass 1 on clip A after its cuts (loglevel info, JSON after
    "[Parsed_loudnorm_N @ 0x...]"): input_i -22.76, input_tp -0.33,
    input_lra 13.90, input_thresh -33.19, target_offset 1.30 (uncut:
    -22.97). Silence (anullsrc) reports "-inf"/"inf": not normalized.
  - Pass 2 (linear=true; loudnorm goes dynamic for clip A, LRA 13.9 > 7):
    -14.2 LUFS by ebur128 (-14.1 uncut); the flashes clip: -14.0.
  - Cuts: trim/atrim + setpts/asetpts=PTS-STARTPTS per kept part, then
    concat. aselect keeps whole 1024-sample frames (0.51 s -> 0.512 s);
    atrim 0.51 s exactly, so trim+concat it is. Kept parts on 30 fps
    frames: clip A 928 frames (30.9333 s), audio 1,484,000 samples
    (30.9167 s) = 33.85 - 2.9 s +- one frame.
  - loudnorm's output timestamps are wrong after concat (time base
    1/1000000) and at EOF (+83 ms before its flush): without
    `asetpts=N/SR/TB+STARTPTS` the mp4 has 1-sample audio packets and lasts
    31.000 s (33.900 s uncut) instead of 30.9167 s (33.85 s); with it the
    packets are 1024 samples, back to back (test checks this).
  - Sync: a 12 s black/silent video with white frames + 1 kHz beeps at 2,
    5 and 8 s, clip 1-10 s, cuts (3.01, 4.49) and (4.9, 5.6): 6.8 s out;
    flashes at 1.0 and 4.8 s (frames 30 and 144), beeps 4 samples earlier
    (by design), with and without loudnorm; the 5 s flash is cut.
- `make check` (exit 0), last lines:
  ```text
  Success: no issues found in 48 source files
  ================== 1000 passed, 1 skipped in 74.50s (0:01:14) ==================
   Test Files  1 passed (1)
        Tests  1 passed (1)
  ✓ built in 102ms
  ```

## 2026-10-31 — TASK-27: Filler removal + caption re-timing (T13a)

- Checks (SPEC 0.1): no third-party API is new; polish is pure Python on
  the existing pydantic models (Transcript, SignalList, CutRange).
- `pipeline/polish.py`: `filler_cuts` finds um/uh/erm/ah and a "like"
  with at least 0.35 s of silence on both sides, in caption words
  (`caption_lines.word_groups`, now shared with `clip_words`); gaps of
  more than 0.6 s between kept words (or the clip edges) are cut to 0.3 s
  (0.15 s kept on each side) unless a laugh or applause overlaps them.
  `cut_spans`/`output_ms`/`retime` move caption words onto the cut
  timeline in ms and drop the words that a cut removes.
- Fixture (exact): clip A 0.5-34.35 -> cuts [(6.2, 7.55), (22.6, 24.15)]
  ("Um," and "Like," with their pauses; the "like" of "like a hawk" stays;
  the laugh gaps and the exactly-0.6 s gaps stay); B -> [(22.6, 24.15),
  (41.5, 42.85)]; C -> [(41.5, 42.85)]. Re-timed A: "body." 5220-5550 ms
  stays, "so" 7200 -> 5850, "hawk." 21570 -> 20220, "it" 23800 -> 20900,
  "cheese." 31930 -> 29030; 62 -> 60 words.
- Wiring: `captions.write_captions` retimes by `clip.cut_ranges`;
  `clips.save_clips(..., work)` stores the filler cuts when the project's
  `remove_fillers` is on. Render applies cut_ranges in TASK-28.
- `make check` (exit 0), last lines:
  ```text
  Success: no issues found in 46 source files
  ================== 961 passed, 1 skipped in 63.52s (0:01:03) ===================
   Test Files  1 passed (1)
        Tests  1 passed (1)
  ✓ built in 80ms
  ```

## 2026-10-31 — TASK-26: Burn captions in render (T12c)

- Checks (SPEC 0.1), ffmpeg-full 9.0.2 with libass 0.17.5: `ffmpeg -h
  filter=subtitles` lists `filename` (alias `f`) and `fontsdir`; the man
  pages ffmpeg-filters "Notes on filtergraph escaping" and ffmpeg-utils
  "Quoting and escaping" (two levels; unescaped whitespace is stripped at
  the ends). Real runs: the new `ffmpeg.filter_value` survives a round
  trip through `metadata=mode=add` and `mode=print` (quotes, brackets,
  commas, semicolons, colons, backslashes, `=`, `%`, spaces at the ends);
  libass loads every font of `assets/fonts` and selects
  Montserrat-ExtraBold, Inter-Bold and NotoEmoji-Regular for the six
  templates with no "Glyph ... not found"; a missing ASS file exits 254
  with "Unable to open <path>"; a wrong fontsdir is silent (system font).
- render: `clip_graph` chains the layout graph into `[framed]`, then
  `subtitles=filename=<ass>:fontsdir=<assets/fonts>` (absolute, escaped
  paths) into `[v]`; `render_clip(..., captions=)`. `clips.render_clip_row`
  writes captions_<clip_id>.ass before each render, so a render always
  shows the clip's current overrides, template and hook.
- Pixel diff (`pipeline/test_render_captions.py`): one 8 s clip rendered
  with and without captions; at 1.0 s the hook band (9-20% of the height)
  and the caption band (44-56%) differ (more than 2% of their pixels by
  more than 64), at 3.0 s only the caption band, at 5.9 s (a pause) no
  band at all; the ffprobe checks (`render_problems`) pass on the
  captioned file. An 8 s 1080x1920 clip renders in about 0.7 s.
- CLI smoke: `clipforge run` in test mode on the fixture rendered 2
  captioned clips ("wrote captions of clip 1 (62 words, template
  karaoke_bold)"); frames at 1.0, 2.2 and 3.0 s of clip 1 and 6.5 s of
  clip 2: `.agent/screenshots/TASK-26-1.png`.
- Tests (+17): `pipeline/test_render_captions.py` (12: bands at three
  times, ffprobe, fonts of each of the six templates, hostile file and
  fonts dir names, missing ASS), `unit/test_ffmpeg.py` (4: filter_value
  exact strings, three round trips), `unit/test_clips.py` (1: no
  transcript is a StepError and leaves the clip unchanged);
  `pipeline/test_run_minimal.py` now also checks the captions file and
  log line, and samples the crop color at 3.0 s (the hook covers 1.0 s).

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
107 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 45 source files
================== 928 passed, 1 skipped in 64.08s (0:01:04) ===================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 80ms
```

## 2026-10-31 — TASK-25: ASS generator + hook overlay (T12b)

- Checks (SPEC 0.1), in source: libass 0.17.5 (ass.c, ass_parse.c,
  ass_render.c): style and event fields, text escapes (only `\N`, `\n`,
  `\h`, `\{`, `\}`), BorderStyle 3 box in OutlineColour, MarginV ignored
  for middle alignment, collisions resolved per Layer, events shown in
  [Start, End), "YCbCr Matrix: None"; ffmpeg vf_subtitles.c (8.0, 9.0,
  master: renders at frame pts in ms, `fontsdir`) and drawutils.c.
- Syntax: Homebrew ffmpeg 9.0.1 (no libass) read the generated files
  (`ffmpeg -i captions.ass out.srt`: styles, times, escapes). Rendering:
  the read-only libass probe drew all six templates on 1080x1920 frames
  with `subtitles=...:fontsdir=assets/fonts` (highlight, 110% emphasis,
  box, Noto Emoji glyph, hook at the top, bottom and middle):
  `.agent/screenshots/TASK-25-1.png`.
- New `pipeline/caption_lines.py` (caption words from transcript.json:
  enrich pieces in the clip, caption_overrides, emphasis phrases, lines,
  active spans) and `pipeline/captions.py` (styles Caption and Hook, one
  Dialogue per active word, hook 0-2.5 s at the top on layer 1,
  `write_captions(job_dir, clip, frame)` -> captions_<clip_id>.ass).
  `enrich.piece_words` is shared with `text_pieces`.
- Tests (+57): `unit/test_captions.py` (15: exact Dialogue lines of a
  six-word fixture for each template, a whole file, styles for 16:9, 1:1
  and a box, hook time/alignment/escaping, no hook when blank,
  caption_overrides, missing transcript or template),
  `unit/test_caption_lines.py` (27: clip selection, pieces, overrides,
  emphasis phrases, punctuation and pause breaks, max words, active
  spans), `unit/test_captions_format.py` (15: times, colors, escapes,
  emoji, zero-length events).

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
105 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 45 source files
======================= 911 passed, 1 skipped in 47.97s ========================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 79ms
```

## 2026-10-31 — TASK-24: Caption templates, fonts, emoji map (T12a)

- Checks (SPEC 0.1): libass ass_fontselect.c (master) matches Windows
  name IDs 1/4 and the PostScript name; fontTools 4.68.0 `TTFont(path,
  lazy=True)` (context manager), `NameRecord.toUnicode()`,
  `getBestCmap()`; Unicode emoji-test.txt 18.0. Homebrew ffmpeg 9.0.1_1:
  "Unknown filter 'subtitles'." (no libass; docs/questions.md).
- Read-only probe with a libass-enabled ffmpeg outside the project:
  `fontselect: (Montserrat ExtraBold, 400, 0) -> Montserrat-ExtraBold`,
  `(Inter Bold, 400, 0) -> Inter-Bold`, `(Noto Emoji, 400, 0) ->
  NotoEmoji-Regular`; all 207 distinct emoji of the map drawn with
  `{\fnNoto Emoji}` (no "Glyph ... not found"); the six templates
  rendered on 1080x1920 fit every line.
- New `assets/fonts/`: Montserrat-ExtraBold.ttf, Inter-Bold.ttf,
  NotoEmoji-VariableFont_wght.ttf, their OFL texts and LICENSES.md
  (sources, sha256). New `clipforge/fonts.py` (`FONTS_DIR`, `EMOJI_FONT`,
  `font_names`, `bundled_fonts`) and `clipforge/captions_templates/`
  (`CaptionTemplate`, `EmojiMap`, `read_yaml`, `load_template`,
  `load_templates`, `get_template`, `load_emoji_map`; six template YAMLs;
  `emoji_map.yaml`, 266 keywords). fonttools direct dependency,
  types-PyYAML dev dependency, mypy override for fontTools.
- Tests (+39): `unit/test_templates.py`: the six SPEC templates load with
  exactly the SPEC fields and max_words_per_line 3..4; the default
  template exists; each template font is the family or full name of
  exactly one bundled file (fontTools), weights 800/700; every font is
  OFL with its license file and LICENSES.md entry; bundled_fonts
  (names, first file wins, non-fonts skipped); 12 invalid templates, bad
  YAML and an unbundled font rejected; emoji map entries, no duplicate
  keys, every emoji in the Noto Emoji cmap; 10 invalid maps and a YAML
  boolean key rejected.

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
100 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 43 source files
======================= 854 passed, 1 skipped in 47.30s ========================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 77ms
```

## 2026-10-31 — TASK-23: Layouts fill/fit/split in render (T11b)

- ffmpeg 9.0.1 checks (SPEC 0.1): `ffmpeg -h filter=crop` (x/y are
  expressions, evaluated per frame with `t`), `-h filter=sendcmd`
  (commands/filename only), scale (`force_original_aspect_ratio`,
  `force_divisible_by`), boxblur (`luma_radius`, `luma_power`), overlay,
  split, vstack (`inputs`), fps, setsar. A flat crop x sum of 98+ terms
  fails ("Failed to configure input pad on Parsed_crop_0", exit 234;
  libavutil/eval.c MAX_DEPTH 100); a balanced sum works for 900 and 5000
  keyframes (0.5 px error). Input `-ss` makes crop's `t` start at 0.
- New `pipeline/layouts.py` (`window_x`, `crop_window`, `layout_graph`:
  fill, fit over a quarter-size blurred copy, split stacked) and
  `pipeline/tracking.py` (tracking moved from reframe, plus `center_x`,
  `face_pairs`, `track_centers`). reframe: `SPLIT_SHARE = 3/5`,
  `wants_split`, `choose_layout`, `split_windows`; `CropPlan.layout`
  and `.split` (`CropWindow`). render: `render_clip(source, output,
  start, end, plan, layout, settings)` with `-filter_complex`. clips:
  `set_planned_layouts` (process job, after reframe) and
  `render_clip_row(engine, clip_id, work)` (loads the crop plan).
- Tests (+26): `unit/test_split_trigger.py` (17: 59/100 and 60/100 fill,
  61/100 split, 3/5 vs 4/5, 3 faces, empty, layout per aspect, face
  pairs, split window sizes, left/right tracking, clamping, scene cut),
  `pipeline/test_layouts.py` (8: expression strings, balanced depth,
  frame-exact crop over 59 s on a lossless gradient, each layout
  ffprobed 1080x1920 h264/yuv420p/aac 30 fps 4 s, fit and split pixels),
  `unit/test_clips.py` (+2: planned layouts, missing plan);
  test_run_minimal and test_reframe check layout and the log lines.
- Smoke run (`DATA_DIR=/tmp/cf_smoke/data MODELS_DIR=$PWD/models
  CLIPFORGE_TEST_MODE=1 uv run clipforge run
  backend/tests/fixtures/sample.mp4 --fixtures-dir backend/tests/fixtures`):
  exit 0; "reframed clip 1 (0.5-34.4s): faces in 170 of 170 frames, crop
  404x720, layout fill"; "rendered 0.5-34.4s as .../output/1/1.mp4 (9:16,
  fill)"; 3 of 3 rendered, each h264 1080x1920 SAR 1:1 yuv420p 30/1 +
  aac (33.87 s, 36.17 s, 24.00 s); clip rows layout fill. Frames at 1,
  18 and 35 s of clip 2 keep the moving face centered.

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
97 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 41 source files
======================= 815 passed, 1 skipped in 47.80s ========================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 103ms
```

## 2026-10-31 — TASK-22: Reframe -> crop_<clip_id>.json (T11a)

- Library checks (installed source, SPEC 0.1): mediapipe 0.10.33 has only
  the Tasks API (`mediapipe.tasks.python.vision.FaceDetector`,
  `FaceDetectorOptions(base_options=BaseOptions(model_asset_path=),
  running_mode=RunningMode.IMAGE, min_detection_confidence=0.5)`,
  `detect(mp.Image(image_format=ImageFormat.SRGB, data=uint8 HxWx3))`,
  `Detection.bounding_box` origin_x/origin_y/width/height,
  `categories[].score`); no `mp.solutions`. `libmediapipe.dylib` of
  0.10.33 has no `play.googleapis.com` or Clearcut string (0.10.35, 1.x
  and 1.2.0 do); its 7 `googleapis.com` strings are protobuf
  `type.googleapis.com/` type URLs. A corrupt model raises "The model is
  not a valid Flatbuffer buffer" (plain Exception). httpx 0.28.1
  `Client.stream`, `iter_bytes`, `MockTransport`. ffmpeg 9.0.1: `-ss S -i
  src -t n/5 -vf fps=5,scale=640:360 -f rawvideo -pix_fmt rgb24` returns
  n frames (fewer at the end of the video).
- New `pipeline/faces.py` (`sample_times`, `analysis_size`,
  `face_detector`, `find_faces`), `pipeline/reframe.py` (`reset_flags`,
  `subject_centers`, `fill_gaps`, `smooth`, `track_subject`, `plan_crop`,
  `reframe_clip`, `reframe_clips`, `crop_path`), schemas `FaceBox`,
  `CropKeyframe`, `CropPlan` (models.py); candidate rules moved to
  `candidate_rules.py`. `model_files.download_face_model` (sha256-pinned,
  `.part` then replace) and its entry in `scripts/download_models.py`.
  `run_process_job` saves the clips, reframes them (Job.step "reframe"),
  then renders.
- Tests (+37): `unit/test_smoothing.py` (20: exact dead-zone/EMA numbers,
  aim hold, even x, scene-cut reset vs none, reset flags, largest face,
  > 1 s gap hold, backfill, faceless shots, no face -> center for 4
  aspect/size pairs, edges, plan_crop, sample counts),
  `pipeline/test_reframe.py` (12: fixture face tracked in all 170 samples
  within 25 px and inside the window; two-shot video: window holds in
  each shot and jumps at the cut, eases 15% without it; missing/corrupt
  model; skip/force; find_faces scaling and missing frames; telemetry
  guard), `unit/test_face_model_download.py` (5, MockTransport + slow
  sha check); test_run_minimal checks the crop plans and the reframe log
  line (needs `face_cfg`).
- Real download: `download_face_model(Settings(models_dir=/tmp/facedl))`
  fetched 229746 bytes, sha256 b4578f35...2380b0152f; `uv run python
  scripts/download_models.py` -> "face model: models/face (0.2 MB, 0s)".
- Smoke run (`DATA_DIR=/tmp/cf_smoke/data MODELS_DIR=$PWD/models
  CLIPFORGE_TEST_MODE=1 uv run clipforge run
  backend/tests/fixtures/sample.mp4 --fixtures-dir backend/tests/fixtures`):
  exit 0 in 12.0 s; "reframed clip 1 (0.5-34.4s): faces in 170 of 170
  frames, crop 404x720", clip 2 181 of 181, clip 3 120 of 120;
  crop_1.json x 18 -> 472, crop_2.json 256 -> 742, crop_3.json 528 ->
  842 (the face moves right); 3 of 3 clips rendered (still center crop).

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
93 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 39 source files
======================= 789 passed, 1 skipped in 43.73s ========================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 103ms
```

## 2026-10-31 — TASK-21: Snap -> clips in DB (T10b)

- No new library. Checked: 36.1 - 0.3 is 35.800000000000004 and 4.6 -
  4.25 is 0.34999999999999964 (why snap compares times to the ms), while
  1.83 - 0.3 is exactly 1.53; `%.1f` of 34.35 is "34.4" (render's log).
- New `snap` step (`pipeline/snap.py`, STEP_NAMES after score): reads
  meta.json, transcript.json, signals.json, scored.json and the job genre.
  A clip starts at the first word in [start - 0.3 s, end) that begins a
  segment or follows a >= 0.35 s pause (else the first word there) and
  ends at the end of the last word that starts before end plus a tail
  (+0.3 s; comedy: until the laugh after it ends, at most +1.5 s), which
  stops at the next word and at the timeframe end. A clip without words
  is dropped (WARNING); the rest keep order and scores in snapped.json
  (`SNAPPED`), each logged "snapped A-Bs to C-Ds".
- Run integration: `process.run_process_job` saves snapped.json's clips
  (status candidate) instead of scored.json's; `clipforge run -h` names
  snap. `enrich.timeframe_segments` is shared by enrich and snap; tests
  get `builders.FIXTURE_LAUGHS`.
- Tests (+53): `unit/test_snap.py` (40: opening words and the 0.35 s
  pause to the ms; start rule incl. the 0.3 s edge and its float noise;
  first-word fallback; dropped clips; +0.3 s tails; comedy laugh tails
  capped at 1.5 s and at the next word; applause and energy ignored;
  timeframe end; property test: 1000 random clips per genre never start
  or end strictly inside a fixture word), `unit/test_snap_step.py` (13:
  auto/comedy/podcast on the fixture, logs, timeframe, skip/force, missing
  inputs, step order, CLI `step snap`); test_run_minimal: best clip
  0.5-34.35 s, rendered 33.85 s. Mutation check: 12 mutations of snap.py
  (pause `>` for `>=`, no ms rounding, exclusive 0.3 s edge, no next-word
  cap, applause as laugh, no 1.5 s cap, no timeframe limit, word cut, ...)
  each fail a test.
- Smoke run (`DATA_DIR=/tmp/cf_smoke/data MODELS_DIR=$PWD/models
  CLIPFORGE_TEST_MODE=1 uv run clipforge run
  backend/tests/fixtures/sample.mp4 --fixtures-dir backend/tests/fixtures`):
  exit 0; "snapped 0.5-35.2s to 0.5-34.35s", "16.9-54.9s to
  16.9-53.05s", "35.8-59.5s to 35.8-59.8s"; the clip rows hold those
  times; renders of 33.87, 36.17 and 24.0 s; 3 of 3 clips rendered.

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
87 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 36 source files
backend/tests/unit/test_snap.py ........................................ [ 87%]
backend/tests/unit/test_snap_step.py .............                       [ 89%]
======================= 752 passed, 1 skipped in 38.71s ========================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 83ms
```

## 2026-10-31 — fix(TASK-16): real CC0 laughter in the fixture (STEERING)

- Owner chose option B (questions.md). Sourced CC0 laughter (network OK):
  18 recordings verified as CC0 on their pages (Freesound, Wikimedia
  Commons), downloaded as public previews and scored with the project's
  YAMNet; picked Freesound 76693 "crowd_laugh.wav" by moxobna (Laughter
  0.9+ at 1.2-7 s). A per-slot simulation (fixture speech + gated excerpt,
  signals.py's frame merge) chose the excerpt offsets.
- New `assets/sfx/crowd_laugh.flac` (3.8 s, mono 48 kHz FLAC, 195 KB) and
  `assets/sfx/LICENSES.md` (URL, author, CC0 1.0, date, preview URL,
  exact ffmpeg command; rerunning it reproduces the file bit for bit).
- `scripts/make_fixture.sh`: the laugh bursts are excerpts of the clip
  (`LAUGH_SFX`, `LAUGH_CUTS` "offset gain", `laugh_track()` graph) in
  place of `anoisesrc`; same times, about the same -16.5 dBFS level, same
  30 ms gate. Found and fixed: adelay's "13.8s" is 13.8 ms (integer ms
  via awk now), and adelay/amix frames without timestamps made aeval
  output NaN (asetpts=N/SR/TB). Regenerated sample.mp4 twice: identical
  bytes; expected.json unchanged.
- Detection on the real pipeline: laughs 14.16-16.08, 33.36-34.8,
  52.08-54.48 (all within 0.5 s); energy peaks one per laugh; 20
  silences. Genre auto is now comedy: A 71, B 63, C 42.
- Tests: the strict xfail `test_laughs_are_detected_within_half_a_second_
  of_expected` is a normal passing test; the waterfall test became
  `test_yamnet_hears_laughter_in_the_laughs_and_nowhere_else` (Laughter
  is the top class of every inside frame, > 0.3; < 0.01 elsewhere);
  test_fixture's SCRIPT_OPTIONS lists the new filters; test_run_minimal
  pins A at 71/88/laugh 0.847/energy 0.071; docstrings updated.

## 2026-10-31 — TASK-20: Score -> scored.json (T10a)

- No new library. Checked: `math.fsum([0.6, 0.25, 0.15]) == 1.0`, so the
  SPEC weights stay exact; 32.2 - 3.0 is 29.200000000000003 (why the laugh
  window compares to the millisecond); `sorted(..., reverse=True)` keeps
  equal keys in order; pydantic-settings deep-merges `score_weights` with
  config.yaml (decisions.md).
- New `score` step (`pipeline/score.py`, STEP_NAMES after curate): reads
  meta.json, signals.json and candidates.json and the job genre
  (`job_genre`); llm = mean(hook, flow, value, trend)/99, laugh = max
  laugh intensity in [end-3 s, end+2 s], energy = fraction of the clip
  that energy peaks cover (union, capped at 1); overall = round(99 *
  weighted sum) with `score_weights` scaled to 1 (laugh weighs 0 unless
  comedy, the rest scaled up). Keeps the best `num_clips` (stable sort)
  in scored.json (`ScoredList` of `ScoredCandidate`, best first) and logs
  the weights and each kept clip.
- Run integration: `process.run_process_job` saves scored.json's clips
  (`clips.save_clips` keeps their order and scores); the TASK-15
  LLM-average ranking (`rank_candidates`, `candidate_scores`) is gone.
  `CANDIDATES`/`SCORED` file names moved to step.py.
- Tests (+47): `unit/test_score.py` (35: SPEC example = round(99*(0.6*65/
  99+0.25*0.8+0.15*0.5)) = 66; podcast/talk/interview renormalized to
  0.8/0/0.2 -> 62; laugh window edges incl. float noise; loudest laugh,
  applause ignored; energy union/clipping/rounding; weight errors; rank
  ties), `unit/test_score_step.py` (14: ranking by energy and laughs,
  auto -> comedy, logs, skip/force, missing inputs, bad weights, CLI
  `step score`); test_clips.py rewritten; test_run_minimal pins the best
  clip's scores. Mutation check: dropping the ms rounding fails the
  window-edge test; summing peaks instead of their union fails 2 tests.
- Smoke run: `DATA_DIR=$(mktemp -d)/data MODELS_DIR=$PWD/models
  CLIPFORGE_TEST_MODE=1 uv run clipforge run
  backend/tests/fixtures/sample.mp4 --fixtures-dir backend/tests/fixtures`
  exit 0: "kept the best 3 of 3 candidates; podcast weights: llm 0.80,
  laugh 0.00, energy 0.20", "0.5-35.2s overall 68 (llm 0.83, laugh 0.00,
  energy 0.12)", B 61, C 56; scored.json A energy 0.124; 3 of 3 clips
  rendered in that order.

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
84 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 35 source files
backend/tests/unit/test_score.py ...................................     [ 83%]
backend/tests/unit/test_score_step.py ..............                     [ 85%]
================== 692 passed, 1 skipped, 1 xfailed in 38.56s ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 103ms
```

## 2026-10-31 — TASK-19: Genre prompts + auto genre (T09b)

- No new library. Checked: `string.Template.substitute` raises KeyError
  for a missing field and ValueError for a stray "$", "$$" gives "$", and
  filled-in values are not scanned again (so the genre rules can go into
  the base); a nested `Literal["auto", ContentGenre]` is flat at runtime
  (`get_args`), in pydantic's JSON schema enum and for mypy narrowing.
- Prompts: `curate_base.md` is the shared frame (transcript format, new
  legend of the [LAUGH 2.1s 0.85] / [APPLAUSE ...] / [SCENE CUT] markers,
  `$genre_rules`, rules for each clip, keyword request, `{"clips": [...]}`
  only). `curate_comedy.md`: setup -> punchline -> laugh, start at the
  start of a sentence before the setup, end after the laugh marker (line
  end + laugh seconds, worked example). `curate_podcast.md`,
  `curate_talk.md`, `curate_interview.md`: strong first sentence hook, one
  complete idea, a satisfying end. `curate_prompt.system_prompt(genre,
  processing, cfg)`.
- `pipeline/genre.py`: `auto_genre` (comedy if more than 1 laugh event
  starts per minute of the timeframe, else podcast; logs its count) and
  `job_genre` (the chosen genre, or auto from signals.json).
- Curate reads enriched.txt (`step.load_text`, `enrich.parse_line`), asks
  with the job genre's prompt (logs "asking for podcast clips (genre
  auto)"), and its first/last windows take lines rounded just outside the
  timeframe. CLI `--genre` help explains auto.
- Tests (+42): `unit/test_genre.py` (27: auto both branches incl. exactly
  1/min, timeframe and applause ignored, chosen genre needs no
  signals.json, every genre's prompt has length range + keyword + reply
  format, comedy rule, curate sends the job genre's prompt);
  test_curate.py (enriched.txt with markers reaches the LLM verbatim, bad
  line / not UTF-8, missing enriched.txt or signals.json, open window
  edges); test_enrich_lines.py (parse_line). Mutation check: `>=` instead
  of `>` fails 3 tests, closed first window edge fails 1.
- Smoke run: `DATA_DIR=$(mktemp -d) CLIPFORGE_TEST_MODE=1 uv run clipforge
  run backend/tests/fixtures/sample.mp4 --fixtures-dir
  backend/tests/fixtures` logged "genre auto: 0 laugh events in
  0.0s-60.0s (0.00 per minute) -> podcast", "asking for podcast clips
  (genre auto)", "kept 3 of 5 clip candidates" and rendered 3 of 3 clips.
- Live (not in make check): Copilot gpt-4.1 with the comedy prompt on the
  fixture's lines plus its 3 expected laughs replied `{"clips":[...]}`
  with 3 setup -> punchline -> laugh clips: 0.5-16.0, 16.9-34.8 and
  35.8-54.6, each ending at its line end + laugh seconds.

```text
$ make check
uv run ruff check backend scripts
All checks passed!
uv run ruff format --check backend scripts
81 files already formatted
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 34 source files
backend/tests/unit/test_curate.py .........................              [ 19%]
backend/tests/unit/test_genre.py ...........................             [ 51%]
================== 645 passed, 1 skipped, 1 xfailed in 37.77s ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 104ms
```

## 2026-10-31 — TASK-18: Enrich -> enriched.txt (T09a)

- No new library. faster-whisper 1.2.1 checked in its source and with the
  `models/whisper/small` tokenizer: words are split at tokens that start
  with a space, so " It was twenty-five dollars." gives the words " It",
  " was", " twenty", "-five", " dollars." and Segment.text glues them.
  The enrich step therefore keeps Segment.text and inserts markers only
  between its whitespace-separated pieces (decisions.md).
- New `enrich` step (`pipeline/enrich.py`, STEP_NAMES between signals and
  curate): reads meta.json, transcript.json and signals.json, writes
  enriched.txt (SPEC 6.4) with "[LAUGH 2.1s 0.85]", "[APPLAUSE ...]" and
  "[SCENE CUT]" markers after the last word that starts before each
  event. The line format (`PromptLine`, `timestamp`, `enriched_lines`)
  moved from curate_prompt.py into it; curate formats transcript.json
  with `enriched_lines(segments, [])` until TASK-19 reads enriched.txt.
  `step.write_text` writes files atomically (also behind `write_json`).
- Tests (39, of which 9 moved from test_curate_prompt.py):
  `unit/test_enrich.py` checks the exact enriched.txt of 3 segments with
  a laugh in the pause after a punchline, a scene cut inside a segment,
  and a silence and an energy peak that get no marker:

```text
[00:00.5-00:01.4] S0: Hi everyone.
[00:01.5-00:02.9] S0: So, I tried yoga. [LAUGH 2.1s 0.85]
[00:05.1-00:07.4] S0: The teacher says, [SCENE CUT] listen to your body.
```

  plus timeframe, skip/force, empty file, missing inputs and `clipforge
  step enrich`; `unit/test_enrich_lines.py` checks timestamps, markers and
  their placement ("twenty-five" stays whole; text its words do not spell
  is one piece; the fixture's expected laughs end the lines of their
  punchlines, the 4th, 8th and 11th).
  Mutation check: bisect_right instead of bisect_left fails 7 tests,
  durations with 2 decimals fail 9.
- Smoke run: `DATA_DIR=$(mktemp -d) CLIPFORGE_TEST_MODE=1 uv run clipforge
  run backend/tests/fixtures/sample.mp4 --fixtures-dir
  backend/tests/fixtures` logged "enrich: wrote 14 lines, 0 markers"
  (no laugh or cut is detected in the fixture) and rendered 3 clips;
  `clipforge step enrich 1` then skipped, `--force` rewrote the same
  bytes. With a laugh 13.8-16.3 and a cut at 21.0 added to signals.json:
  "... why are we on the floor? [LAUGH 2.5s 0.85]" and "It watches
  [SCENE CUT] me like a hawk."
- `make check` (exit 0), last lines:

```text
backend/tests/unit/test_curate_prompt.py ................                [ 22%]
backend/tests/unit/test_enrich.py .........                              [ 30%]
backend/tests/unit/test_enrich_lines.py ..............................   [ 35%]
================== 603 passed, 1 skipped, 1 xfailed in 38.49s ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 91ms
```

## 2026-10-31 — TASK-17: Signals: silence, energy peaks, scene cuts (T08b)

- PySceneDetect checked with `help(scenedetect.detect)` and its source:
  `detect(video_path, detector, ..., start_time=, end_time=, backend=
  "opencv")` wraps `open_video` + `SceneManager.detect_scenes(video,
  end_time=)` + `get_scene_list()`; `ContentDetector(threshold=27.0,
  min_scene_len=15)`. Added `scenedetect` 0.7.2 (+ opencv-python
  5.0.0.93) with `uv add scenedetect`.
- The `signals` step (`pipeline/signals.py` `run`, in STEP_NAMES between
  transcribe and curate) writes signals.json (`SignalList`):
  `detect_audio_signals` (one YAMNet + RMS pass: laughs, applause,
  `level_events.silences`, `level_events.energy_peaks`) and
  `scene_cuts.detect_scene_cuts` (30 s slices, progress). Definitions and
  the measurements behind them: decisions.md.
- Fixture: 20 silences = the 20 gaps >= 0.35 s of expected.json (within
  0.06 s); energy peaks 13.85-16.24, 33.21-35.12, 52.19-52.6, 53.24-54.54
  (the laughs); no scene cut. `clipforge run` in test mode logs "found 0
  laugh, 0 applause, 0 scene_cut, 20 silence, 4 energy_peak events in
  0.0s-60.0s"; `clipforge step signals 1` then skips.
- Tests (33 new): `unit/test_silence_energy.py` (1 s tone + 0.5 s pause
  + 1 s tone -> one silence 1.0075-1.4875; 0.3 s pause none; -43 vs
  -37 dBFS; a 1.5 s loud burst in noise or speech-like sound -> one peak
  25.0-26.5; none for steady noise/speech/tone/silence, quiet bursts,
  0.1 s clicks; bursts 0.3 s apart merge), `pipeline/test_scene_cuts.py`
  (two_scenes cut at 2.0 within a frame, slices == one pass, timeframe,
  errors), `pipeline/test_signals_step.py` (signals.json on the fixture,
  progress, skip/force, scene cut as an instant, missing inputs/model).
  The whole-pipeline tests are now `slow` (YAMNet).
- `make check` (exit 0), last lines:

```text
backend/tests/pipeline/test_scene_cuts.py .......                        [  6%]
backend/tests/pipeline/test_signals_laugh.py x.....                      [  7%]
backend/tests/pipeline/test_signals_step.py ...........                  [  9%]
backend/tests/unit/test_silence_energy.py .................              [ 85%]
================== 573 passed, 1 skipped, 1 xfailed in 37.74s ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 76ms
```

## 2026-10-31 — TASK-16: Signals: YAMNet laugh/applause (T08a)

- YAMNet backend decided by installing both on this Mac (decisions.md):
  ONNX (`audiomagic/yamnet-onnx`, pinned revision + sha256) on
  onnxruntime 1.31.1; TF Hub's `import tensorflow_hub` fails with
  `ModuleNotFoundError: No module named 'pkg_resources'` (setuptools 84).
  `scripts/download_models.py` now also fetches it into `models/yamnet`.
- Added `pipeline/yamnet.py` (load the model + class map, `frame_count`,
  `Yamnet.scores`), `pipeline/loudness.py` (librosa RMS envelope in dBFS,
  level, rolling-median baseline), `pipeline/signal_merge.py` (pure
  `merge_active_frames`, `intensity`), `pipeline/audio_analysis.py` (one
  chunked pass over the timeframe of audio.wav: scores + envelope) and
  `pipeline/signals.py` (`detect_laughs_and_applause`, `frame_spans`,
  `signal_event`). Not a pipeline step yet: TASK-17 adds signals.json.
- Tests (72 new): `unit/test_laugh_merge.py` (merge at a 0.75 s gap,
  split at 1 s, drop < 0.4 s, 0.3 not active, mean of active frames, the
  YAMNet time grid, intensity 0.4/0.25/0.8/0, event intensity 0.5 at
  10 dB over the median), `unit/test_loudness.py`, `unit/test_yamnet.py`
  (Laughter/Applause indexes read from the class map: 13 and 62),
  `unit/test_audio_analysis.py`, YAMNet download in
  `unit/test_model_files.py`, `pipeline/test_signals_laugh.py` (chunked
  == one pass, timeframe only, progress; the expected.json laugh check is
  a strict xfail: the fixture's pink noise is Waterfall 0.94 / Laughter
  0.001 to YAMNet, questions.md).
- `make check` (exit 0), last lines:

```text
backend/tests/pipeline/test_signals_laugh.py ..x.....                    [  6%]
================== 540 passed, 1 skipped, 1 xfailed in 31.20s ==================
 Test Files  1 passed (1)
      Tests  1 passed (1)
✓ built in 100ms
```

- `uv run python scripts/download_models.py` (second run; the first one
  downloaded YAMNet and checked both sha256s):

```text
whisper model 'small': models/whisper/small (486.2 MB, 0s)
YAMNet model is in models/yamnet
YAMNet model: models/yamnet (16.1 MB, 0s)
```

- Hand check on real sounds (not committed: ESC-50 is CC BY-NC): 12
  laughing and 6 clapping clips from ESC-50, each put at 10 s into 30 s of
  silence, run through `detect_laughs_and_applause`. Laughs were found in
  8 of 12 (the other 4 peak at Laughter 0.13-0.28), applause in 4 of 6
  (0.13 and 0.23); no laugh in a clap clip or applause in a laugh clip.
  11 of the 12 first events start 0.17 s before to 0.32 s after the
  clip's sound (the other 0.89 s after); events end where YAMNet stops
  hearing the class, often before the clip does. Excerpt of the real
  output (`loud` = where the clip is within 30 dB of its peak):

```text
1-110537-A-22 [clap] loud 10.00-14.99  maxL 0.01 maxA 1.00 active L frames []
    applause 10.32-14.64 int 0.99
1-36164-B-26 [laugh] loud 10.00-14.61  maxL 0.92 maxA 0.00 active L frames [21, 22, 23, 24, 25, 29]
    laugh 10.32-12.72 int 0.68
    laugh 14.16-14.64 int 0.52
2-109759-B-26 [laugh] loud 10.00-14.99  maxL 0.64 maxA 0.01 active L frames [20, 21, 22, 29]
    laugh 9.84-11.28 int 0.58
    laugh 14.16-14.64 int 0.44
1-30039-A-26 [laugh] loud 10.00-14.99  maxL 0.16 maxA 0.00 active L frames []
```

- On sample.mp4 (ingested), `detect_laughs_and_applause` returns no event
  (0.8 s); max Laughter 0.0008, max Applause 0.00003 over the 60 s.

## 2026-10-31 — TASK-15: Minimal render + `clipforge run` (T07)

- Added `backend/clipforge/pipeline/render.py`: `render_clip` trims
  [start, end] (input `-ss` + `-t`), crops the largest centered window of
  the aspect's shape (`center_crop`, even sizes), scales to the SPEC 6.11
  size (`SIZES`), encodes libx264 yuv420p (render fps/crf/preset) + AAC
  (audio_bitrate) with +faststart into a `.tmp.mp4`, and only renames it
  to `{data_dir}/output/{project_id}/{clip_id}.mp4` when ffprobe finds
  the right size, codecs and a duration within ±0.2 s (`render_problems`);
  otherwise RenderError and no file is left.
- Added `clips.py` (pass-through until score/snap: best `num_clips`
  candidates by LLM average become clip rows, overall = rounded average,
  layout fill; `render_clip_row` marks a clip rendered or failed),
  `process.py` (`create_job`, `run_process_job`, `run_step` moved from
  cli.py; job/project status, title/duration/thumbnail, job.log) and
  `testmode.py` (`CLIPFORGE_TEST_MODE=1` + `--fixtures-dir`: recorded
  transcript.json and llm_response.json, read from files only).
- `clipforge run <file|url> [--genre] [--aspect] [--num-clips N]
  [--fixtures-dir DIR]` prints one path per rendered clip; exit 1 if a
  step or a clip fails, 2 for bad arguments.
- Tests (63 new, 469 total): `pipeline/test_run_minimal.py` (per aspect:
  exact size, h264/yuv420p/aac, ±0.2 s, 30 fps, `crf=20.0` in the x264
  SEI, moov before mdat, yellow left/blue right of centre, clip rows
  rendered at output/<project_id>/<clip_id>.mp4; a too-short clip ->
  RenderError, no file; a bad preset -> exit 1 and 2 failed clips; the
  console script in test mode), `unit/test_render.py`, `test_clips.py`,
  `test_process.py`, `test_testmode.py`, run arguments in `test_cli.py`.
- AC3: `CLIPFORGE_TEST_MODE=1 DATA_DIR=/tmp/cf-ac3 uv run clipforge run
  backend/tests/fixtures/sample.mp4 --fixtures-dir backend/tests/fixtures;
  echo "exit=$?"` (8.1 s), last lines:

```text
INFO clipforge.pipeline.curate: kept 3 of 5 clip candidates; 0 of 1 windows skipped
INFO clipforge.pipeline.render: rendered 0.5-35.2s as /tmp/cf-ac3/output/1/1.mp4 (9:16, crop=404:720:438:0)
INFO clipforge.pipeline.render: rendered 16.9-54.9s as /tmp/cf-ac3/output/1/2.mp4 (9:16, crop=404:720:438:0)
INFO clipforge.pipeline.render: rendered 35.8-59.5s as /tmp/cf-ac3/output/1/3.mp4 (9:16, crop=404:720:438:0)
INFO clipforge.process: job 1 rendered 3 of 3 clips; 0 failed
/tmp/cf-ac3/output/1/1.mp4
/tmp/cf-ac3/output/1/2.mp4
/tmp/cf-ac3/output/1/3.mp4
exit=0
```

- ffprobe of those clips (`stream=codec_name,width,height,pix_fmt,
  r_frame_rate`, `format=duration`), then the DB rows:

```text
output/1/1.mp4 h264,1080,1920,yuv420p,30/1 aac,0/0 34.700000
output/1/2.mp4 h264,1080,1920,yuv420p,30/1 aac,0/0 38.000000
output/1/3.mp4 h264,1080,1920,yuv420p,30/1 aac,0/0 23.700000
[(1, 1, 'rendered', '/tmp/cf-ac3/output/1/1.mp4'), (2, 1, 'rendered', '/tmp/cf-ac3/output/1/2.mp4'), (3, 1, 'rendered', '/tmp/cf-ac3/output/1/3.mp4')]
[(1, 'process', 'render', 1.0, 'done', None)]
[(1, 'done', 'ClipForge sample fixture', 60.0)]
```

- One of 8 full pytest runs hung (pytest at 99% CPU for 8 min, no child
  process) and was stopped; the 7 others, `make check` included, passed
  in about 29 s (HANDOFF "Open problems").
- `make check` (exit 0) tail:

```text
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 25 source files
All matched files use Prettier code style!
======================= 469 passed, 1 skipped in 29.06s ========================
      Tests  1 passed (1)
✓ built in 98ms
```

## 2026-10-31 — TASK-14: Curate: chunking, prompt, schema, retries, dedupe (T06b)

- Added `backend/clipforge/pipeline/curate.py` (`run`, `plan_windows`,
  `ask_window`, `parse_reply`): transcript.json becomes SPEC 6.4 lines
  `[mm:ss.s-mm:ss.s] S0: text` (no markers until enrich, TASK-18), cut
  into `chunk_minutes` windows overlapping by `chunk_overlap_s`
  (`plan_chunks`), and each window is sent to the LLM (`settings.llm`, else
  `create_client(cfg)`). A reply that fails `CandidateList` validation is
  sent back with its errors ("- clips.0.title: String should have at most
  70 characters") up to 2 times; then the window is skipped and logged.
  The kept candidates go to `candidates.json` (atomic, best first).
  `"curate"` is in `STEP_NAMES`: `clipforge step curate <job_id>` works.
- Added `pipeline/curate_prompt.py` (prompt text, error list),
  `pipeline/curate_select.py` (validate_candidate + timeframe filter, IoU
  > 0.5 dedupe keeping the higher LLM average, max_clips_from_llm cap)
  and `prompts/curate_base.md` (own wording: length range, keyword
  request, `ClipCandidate.model_json_schema()`, `{"clips": [...]}` only).
- `models.py`: `CandidateList`; `step.py`: `TRANSCRIPT`, `load_json`,
  `StepSettings.llm`; `test_fixtures_valid.py` uses `CandidateList`.
- Tests (73 new): `unit/test_curate.py` (25-min windows [0,600],
  [540,1140], [1080,1500]; invalid -> valid retry with the error in the
  2nd prompt; 3 invalid -> skipped + logged, no exception; run() on the
  fixture -> [A, B, C]; lt30 + keyword; timeframe; cap; skip/force; LLM
  500 and unreachable Ollama -> StepError; missing inputs),
  `test_curate_select.py` (exact IoU numbers incl. 31.4/34.7 and exactly
  0.5 kept), `test_curate_prompt.py` (schema embedded, length rules,
  keyword, error list capped and without the bad values).
- Mutation check: 8 hand-made bugs (no sort before dedupe, unrounded IoU,
  `>=` threshold, no cap, no timeframe check, 1 retry, closed windows,
  errors not sent back) each made the tests fail.
- Live (not in `make check`): curate on the fixture job with Copilot
  gpt-4.1 while tuning the prompt; every reply parsed on the first try
  (13-61 s each). With the final prompt, 3 of 6 runs kept a clip
  (0.5-32.8 s or 0.5-51.6 s); the others proposed only the 12-16 s jokes,
  which the 20-75 s range drops. lt30 + keyword "technology" (an earlier
  prompt version) kept 2 of 2, both about technology.
- CLI smoke (DATA_DIR in /tmp, real `clipforge step ingest`, fixture
  transcript): `clipforge step curate 1` exits 0, prints the
  candidates.json path and leaves the job at step=curate, progress=1.0;
  with LLM_PROVIDER=ollama OLLAMA_HOST=http://127.0.0.1:9 it exits 1 with
  "clipforge: error: the LLM request failed: ollama: cannot reach
  http://127.0.0.1:9/api/chat: [Errno 61] Connection refused".
- `make check` tail:

```text
uv run mypy --strict backend/clipforge scripts/download_models.py
Success: no issues found in 21 source files
All matched files use Prettier code style!
======================= 406 passed, 1 skipped in 14.50s ========================
      Tests  1 passed (1)
✓ built in 75ms
```

## 2026-10-31 — TASK-13: LLM clients (T06a)

- Added `backend/clipforge/llm.py`: the `LLMClient` protocol
  (`complete_json(system, user) -> str`), `CopilotClient` (default:
  https://api.githubcopilot.com/chat/completions, token from
  GITHUB_COPILOT_TOKEN or `gh auth token -u omairtemurian -h github.com`),
  `OpenAICompatClient` (`{OPENAI_BASE_URL}/chat/completions`, JSON mode),
  `OllamaClient` (`{OLLAMA_HOST}/api/chat`, format json, no streaming),
  `gh_auth_token` and `create_client` (by LLM_PROVIDER). Added
  `llm_http.py`: `post_json` (httpx; failures become `LLMError` with the
  status and a 500-character body excerpt, the credential redacted) and
  `join_url`. Added httpx 0.28.1 (with httpcore 1.0.9, certifi
  2026.10.23).
- Tests (43 new, plus 1 opt-in live test): `backend/tests/fakes.py`
  (`FakeLLMClient`, `FakeLLMServer`, reply builders);
  `unit/test_llm.py` (exact URL, headers and JSON body for each client
  through httpx.MockTransport; token from the env, from gh once, gh
  failures; the GitHub Models base URL with and without a trailing slash;
  the factory by env); `unit/test_llm_errors.py` (4xx/5xx with excerpt,
  unreachable server, a non-JSON 200, missing content, the token never in
  messages, tracebacks or logs); `unit/test_fakes.py` (fake behaviour; no
  clipforge module defines, imports or names FakeLLMClient or fakes).
- Mutation check: 16 hand-made bugs in llm.py/llm_http.py (a dropped
  header, a wrong body field, no redaction, no excerpt cut, gh run on every
  call, headers in the log line, ...) each made the tests fail.
- Live, opt-in, against Copilot as omairtemurian (token from gh; the reply
  parsed as `{"answer": 4}`):

```text
$ uv run pytest -m live -v
backend/tests/unit/test_llm.py::test_copilot_live_answers_with_json PASSED [100%]

====================== 1 passed, 333 deselected in 2.05s =======================
```

- `make check` tail (the live test is skipped there):

```text
Success: no issues found in 18 source files
All matched files use Prettier code style!
======================= 333 passed, 1 skipped in 14.48s ========================
      Tests  1 passed (1)
✓ built in 89ms
```

## 2026-10-31 — TASK-12: Transcribe with faster-whisper, chunked (T05)

- Added `backend/clipforge/pipeline/transcribe.py` (`run`, `load_model`):
  the meta.json timeframe is cut into `chunk_minutes` chunks overlapping
  by `chunk_overlap_s` (ffmpeg `-ss`/`-t` via `extract_audio_wav(...,
  start=, duration=)`), each transcribed by faster-whisper 1.2.1
  (`WhisperModel(dir, device="auto", compute_type="int8")`,
  `word_timestamps=True, vad_filter=True`), merged and written atomically
  to `transcript.json` (every word speaker S0). `"transcribe"` is in
  `STEP_NAMES`, so `clipforge step transcribe <job_id>` works.
- Added `pipeline/transcript_merge.py` (pure): `plan_chunks`,
  `to_source_time`, `merge_chunks` (splice at a word both chunks heard
  near the middle of the overlap), `build_transcript` (sentence segments).
- Added `backend/clipforge/model_files.py` (`models_dir` setting,
  `models/whisper/<name>`, HF_HOME in `models/huggingface`,
  `download_whisper_model`) and `scripts/download_models.py`; `make setup`
  runs it. `step.py` gained `write_json`, `load_meta` and the job file
  names.
- Tests (41 new): `test_transcribe_merge.py` 19 (exact words for overlap
  dedupe, jitter, repeated words, empty chunks, sentence rules),
  `test_model_files.py` 10 (fake `snapshot_download`), pipeline
  `test_transcribe.py` 9 (errors without a model, skip/force, and 2 slow
  tests with the real "small" model: 5 s tone and 5 s silence clips give a
  strict-valid transcript with no words), 3 `extract_audio_wav` window
  tests. Moving `models/whisper/small` away makes the slow tests skip with
  "whisper model 'small' is not downloaded to .../models/whisper/small;
  run `make setup`".
- Real download (486.2 MB of model files; the Hub's metadata in
  models/huggingface is 64 KB):

```text
$ uv run python scripts/download_models.py
downloading whisper model Systran/faster-whisper-small into models/whisper/small
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
whisper model 'small': models/whisper/small (486.2 MB, 24s)
$ make setup   # (excerpt) the model is skipped when present
uv run python scripts/download_models.py
whisper model 'small' is in models/whisper/small
whisper model 'small': models/whisper/small (486.2 MB, 0s)
```

  Progress bars ("Fetching 4 files: 100%|...| 4/4", "Download complete:
  ... 77.8MB, 23.2MB/s") were seen downloading `tiny` into a scratch dir
  in a pty with a window size; a pty with 0 columns prints none.
- Real speech check (macOS `say`, 101 s, 340 words): one chunk vs
  1-minute chunks with 20 s and 30 s overlap gave the same 340 words in
  order (only "applauds"/"applause" differed, a Whisper decoding
  difference), no duplicates or gaps at the splices; 12.5 s vs 16.8 s /
  19.4 s on the M4 Max. CLI on a project with timeframe 20..70 s:

```text
$ DATA_DIR=/tmp/cf-cli/data uv run clipforge step transcribe 1 --force
INFO clipforge.pipeline.transcribe: transcribing chunk 1/1 (20.0s-70.0s)
INFO faster_whisper: Processing audio with duration 00:50.000
INFO faster_whisper: VAD filter removed 00:00.000 of audio
INFO faster_whisper: Detected language 'en' with probability 1.00
INFO clipforge.pipeline.transcribe: transcribed 173 words in 18 segments (language en) into /tmp/cf-cli/data/work/1/transcript.json
/tmp/cf-cli/data/work/1/transcript.json
$ DATA_DIR=/tmp/cf-cli/data MODELS_DIR=/tmp/cf-nomodels uv run clipforge step transcribe 1 --force
clipforge: error: whisper model 'small' is not downloaded: /tmp/cf-nomodels/whisper/small lacks config.json, model.bin, tokenizer.json; run `uv run python scripts/download_models.py --whisper-model small`
```

  (6.4 s wall time; the job row ended `transcribe|1.0`.) `make check`
  tail (290 backend tests, including the 2 slow ones):

```text
Success: no issues found in 16 source files
All matched files use Prettier code style!
============================= 290 passed in 14.76s =============================
      Tests  1 passed (1)
✓ built in 228ms
```

## 2026-10-31 — TASK-11: Ingest step + `clipforge step` CLI (T04b)

- Added `backend/clipforge/pipeline/`: `step.py` (`StepSettings`,
  `StepError`, `Step` protocol, `job_dir`, `is_done`, lazy `load_step`),
  `download.py` (yt-dlp with SPEC's format string, mp4 merge, playlist
  rejection, logger adapter) and `ingest.py` (`run`: source.mp4 copied or
  converted to h264/aac, audio.wav 16 kHz mono pcm_s16le, thumb.jpg at 10%,
  meta.json last). Added `SourceMeta` to `models.py`.
- Added `backend/clipforge/cli.py` and the `clipforge` console script:
  `clipforge step ingest <job_id> [--force]` sets the job's step and
  progress, prints the output path, exits 1 on job/step errors.
- Added dependencies yt-dlp 2026.10.26 and (dev) types-yt-dlp.
- Tests (36 new): `backend/tests/pipeline/test_ingest.py` (16: outputs,
  WAV format, meta, thumbnail frame, progress, skip/force by mtime, mpeg4
  AVI to h264/aac, stream copy vs encode per stream, yuv444p re-encode,
  timeframe clamp/error, no audio, missing file),
  `test_ingest_url.py` (6: the real yt-dlp downloads `file://` formats
  from canned pages; format string, merge, 1080p cap, single-file
  fallback, failed download, playlist, option keys documented in the
  installed yt-dlp), `backend/tests/unit/test_cli.py` (10, including the
  installed script in a subprocess) and a `SourceMeta` test. Removing
  the height limits from the format string makes the URL tests fail, and
  9 one-at-a-time mutations of `ingest.py` (container check, pix_fmt
  rule, audio copy, skip, thumbnail time, clamp, even-size scale,
  download progress scale, title order) were all caught. The even-size
  one was only caught after switching the test media from lavfi
  `testsrc2` (which rounds 321x241 down to 320x240) to `testsrc`.
- Ran `make check` (all green), then the CLI on a temp data dir (project
  source `backend/tests/fixtures/sample.mp4`, timeframe 5..100):

```text
$ DATA_DIR=/tmp/cf-data uv run clipforge step ingest 1
INFO clipforge.pipeline.ingest: copying sample.mp4 (an h264/aac mp4) to source.mp4
INFO clipforge.pipeline.ingest: timeframe end 100s is after the video end; using 60s
INFO clipforge.pipeline.ingest: ingested 'ClipForge sample fixture' (60.0s) into /tmp/cf-data/work/1
/tmp/cf-data/work/1/meta.json
$ DATA_DIR=/tmp/cf-data uv run clipforge step ingest 1
INFO clipforge.pipeline.ingest: /tmp/cf-data/work/1/meta.json exists; skipping ingest
/tmp/cf-data/work/1/meta.json
$ DATA_DIR=/tmp/cf-data uv run clipforge step ingest 42
clipforge: error: job 42 not found
```

  The first run took 0.6 s; the job row was `ingest|1.0|queued`, and
  audio.wav probed as `pcm_s16le,16000,1`. `make check` tail:

```text
Success: no issues found in 12 source files
All matched files use Prettier code style!
============================= 249 passed in 10.86s =============================
      Tests  1 passed (1)
✓ built in 88ms
```

## 2026-10-30 — TASK-10: ffmpeg.py subprocess wrapper (T04a)

- Added `backend/clipforge/ffmpeg.py`: `run_ffmpeg(args, *, loglevel)`,
  `ffprobe_json(path)`, `probe_media(path) -> MediaInfo`,
  `extract_frame(src, dst, time_s)`, `extract_audio_wav(src, dst)` (16 kHz
  mono pcm_s16le) and `FFmpegError` (command + last 20 stderr lines, at most
  2000 characters, in the message). Commands are argument lists; Path
  arguments are made absolute. Every flag was checked with `ffmpeg -h`,
  `ffmpeg -h muxer=image2`, `ffprobe -h` and `man ffmpeg` first.
- Added `backend/tests/unit/test_ffmpeg.py` (16 tests: invalid input,
  missing input and missing binary for each helper, loglevel, option-like
  file names, stderr tail, no `shell=True` in backend sources) and
  `test_ffmpeg_media.py` (15 tests: fixture values, other codecs, VFR,
  no audio, rotation 90/180/270, audio-only/cover-art/still rejection,
  exact frame 180 at 6.0 s, JPEG, past-end, negative time, WAV format,
  alignment and downmix). All run the real binaries; no mocks.
- Added `backend/tests/conftest.py` with session fixtures `sample_mp4` and
  `expected`; removed the duplicate `expected` fixtures from
  `test_fixture.py` and `test_fixtures_valid.py`.
- Mutation check: 11 one-at-a-time mutations of `ffmpeg.py` (no rotation
  swap, cover art counted as video, relative paths kept, no `-y`, no tail
  cap, loglevel ignored, no downmix, FileNotFoundError not caught, stderr
  dropped, base frame rate instead of average, no negative-time check).
  All 11 were caught; the first run missed the frame-rate one, so the VFR
  test was added. The module was restored byte-identical (`cmp`).
- Ran `grep -rn shell=True backend` (exit 1, no matches), `uv run pytest
  backend/tests/unit/test_ffmpeg.py backend/tests/unit/test_ffmpeg_media.py
  -q` (`31 passed in 2.81s`), then `make check`:

```text
All checks passed!
19 files already formatted
Success: no issues found in 7 source files
All matched files use Prettier code style!
============================= 213 passed in 4.05s ==============================
      Tests  1 passed (1)
✓ built in 75ms
```

## 2026-10-30 — TASK-9: Hand-written transcript and LLM response fixtures

- Added `backend/tests/fixtures/transcript.json`: a 60 s English
  Transcript (14 sentence segments, 104 words, speaker S0) of an original
  three-bit stand-up set (yoga, smart fridge, car assistant). The words fill
  the 19 speech bursts of `expected.json` exactly, and each punchline ends
  0.3 s before a laugh. The three short bursts hold "Um,", "Like," and
  "Uh,"; "like" also appears inside a phrase ("It watches me like a hawk.").
- Added `backend/tests/fixtures/llm_response.json`: `{"clips": [...]}`
  with 5 candidates inside 0..60: a near-duplicate pair (IoU 0.905, weaker
  cut listed first), two other bits, and a 15.8 s clip that the default
  `auto` preset (20-75 s) drops.
- Added `backend/tests/unit/test_fixtures_valid.py` (13 tests): strict
  parsing with unknown keys forbidden, segment and word order and bounds,
  alignment with the speech bursts and laughs, fillers, snap-start
  coverage, the single IoU > 0.5 pair, the candidates each length preset
  keeps, and emphasis words spoken inside each candidate.
- Mutation check: 27 one-at-a-time fixture mutations (e.g. overlapping
  words, word outside its burst, dropped "Um,", extra key, prob 1.2,
  string time, merged sentences, word inside a laugh, swapped dedupe pair,
  "#yoga", score 50.0, end 60.5, unspoken emphasis word, tied averages,
  short clip made long enough). Each failed its intended test (27/27); the
  fixtures were restored byte-identical (`cmp`).
- Ran `uv run ruff check backend && uv run pytest
  backend/tests/unit/test_fixtures_valid.py -q`, then `make check`:

```text
All checks passed!
13 passed in 0.02s
uv run ruff format --check backend
15 files already formatted
Success: no issues found in 6 source files
All matched files use Prettier code style!
182 passed in 1.19s
Tests  1 passed (1)
✓ built in 76ms
```

## 2026-10-30 — Fix (TASK-4): ruff format check in `make lint`

- Owner steering item: SPEC 2 names ruff as the backend lint and format
  tool, so `make lint` (and therefore `make check`) now also runs
  `uv run ruff format --check backend` (`--check` verified in
  `ruff format --help`, ruff 0.17.3). `uv run ruff format backend` left all
  14 files unchanged.
- Negative check: a throwaway misformatted `backend/clipforge/_fmt_probe.py`
  made `make lint` exit 2 at the new step ("unformatted: File would be
  reformatted"); the probe was deleted.
- Ran `uv run ruff format backend && make check`:

```text
14 files left unchanged
uv run ruff format --check backend
14 files already formatted
169 passed in 1.28s
Tests  1 passed (1)
✓ built in 80ms
```

## 2026-10-30 — TASK-8: Fixture video script and expected.json

- Added `scripts/make_fixture.sh`, which builds `backend/tests/fixtures/`
  `sample.mp4` with ffmpeg only: blurred testsrc2 plus a drawn face that moves
  left to right; audio of 19 speech-like sine bursts and 3 pink-noise laugh
  bursts. It writes `expected.json` (media properties, burst times, face path)
  from the same constants. Every ffmpeg filter and option was checked with
  `ffmpeg -h filter=<name>` (list in `docs/HANDOFF.md`).
- Idempotent: a second run (and a run under macOS `/bin/bash` 3.2) produced
  byte-identical files (sha256 checked).
- Added `test_fixture.py` (21 tests): ffprobe properties, expected.json
  shape, burst timeline, decoded audio levels and zero-crossing rates,
  silence between bursts, face position at five times, ffmpeg options exist.
  Mutating expected.json (laugh times, face path, title) failed 6 tests.
- Throwaway check: mediapipe 1.2.0's short-range face detector found the
  drawn face in 30/30 sampled frames (recorded in `docs/decisions.md`).
- Ran `bash scripts/make_fixture.sh && shasum -a 256 ... && bash
  scripts/make_fixture.sh && shasum -a 256 -c ... && uv run pytest
  backend/tests/unit/test_fixture.py -q && make check`:

```text
2cd7b7776821a8869f04a162cde9ec915cf7bb9eb6ba6b762641d81537e42ac8  backend/tests/fixtures/sample.mp4
0312ba956c9789ddca2633d514a855d4466d12b34f598538fc747d0bfd519047  backend/tests/fixtures/expected.json
backend/tests/fixtures/sample.mp4: OK
backend/tests/fixtures/expected.json: OK
21 passed in 0.74s
All checks passed!
Success: no issues found in 6 source files
All matched files use Prettier code style!
169 passed in 1.10s
Tests  1 passed (1)
✓ built in 76ms
```

## 2026-10-30 — TASK-7: Database tables and migrations

- Added `migrations/001_init.sql` (tables `project`, `clip`, `job`,
  `brand_template`; nested fields as JSON text; clips and jobs cascade on
  project delete, render jobs on clip delete; AUTOINCREMENT ids).
- Added `backend/clipforge/db.py`: the engine at `{data_dir}/clipforge.db`
  with foreign keys enforced on every connection, `migrate()` applying
  `migrations/NNN_name.sql` in version order (each in one transaction with
  its `schema_version` row), and SQLModel rows whose JSON columns are
  validated by the SPEC 5 Pydantic models (`to_model()` converts a row).
- Added `conftest.py` DB fixtures, `test_db.py` (applies 001 once, schema
  matches the row classes, round trips, defaults, cascades) and
  `test_migrations.py` (order, rollback, bad files). Mutation check: 16
  deliberate bugs in `db.py` and `001_init.sql`, all caught.
- Ran `make check && uv run pytest backend/tests/unit/test_db.py -q`:

```text
All checks passed!
Success: no issues found in 6 source files
All matched files use Prettier code style!
148 passed in 0.39s
Tests  1 passed (1)
✓ built in 103ms
16 passed in 0.09s
```

## 2026-10-30 — TASK-6: Data models

- Added `backend/clipforge/models.py` with every SPEC 5 schema (Word, Segment,
  Transcript, SignalEvent, ProcessingSettings, ClipCandidate, Scores, Clip,
  Project, Job, BrandTemplate), shared literal types, field limits, and
  `length_range` / `validate_candidate` for SPEC 6.6 timing and preset checks.
- `ClipCandidate` enforces the SPEC 5 limits (title ≤70, hook text ≤60,
  description ≤300, 3–8 hashtags without `#`, scores 0–99); its JSON schema
  carries the same limits for the LLM prompt.
- `ProcessingSettings.num_clips` defaults to config `default_num_clips` and
  accepts 1–30. Decisions recorded in `docs/decisions.md`.
- Added `test_models.py` (fields, literals, limits, defaults, round trip) and
  `test_validate_candidate.py` (timing, preset bounds, reasons). Mutation
  check: 12 deliberate model bugs, all caught by the tests.
- Ran `make check && uv run pytest backend/tests/unit/test_models.py -q` plus
  `uv run pytest backend/tests/unit/test_validate_candidate.py -q`:

```text
All checks passed!
Success: no issues found in 5 source files
All matched files use Prettier code style!
123 passed in 0.10s
Tests  1 passed (1)
✓ built in 110ms
86 passed in 0.08s
31 passed in 0.06s
```

## 2026-10-30 — TASK-5: Configuration

- Added Pydantic Settings configuration with code defaults, YAML loading, and
  environment-variable precedence. Added config.yaml, an environment example,
  Copilot/OpenAI/Ollama configuration, and the credit template default.
- Added unit tests for every SPEC 4 default, missing YAML, YAML overrides,
  `LLM_PROVIDER` environment override, and the example environment keys.
- Updated the locked dependency reference and documented why Copilot is the
  default and why the credit template uses `{channel}`.
- Ran `make check && uv run pytest backend/tests/unit/test_config.py -q`:

```text
Success: no issues found in 4 source files
All matched files use Prettier code style!
5 passed in 0.87s
Test Files  1 passed (1)
✓ built in 252ms
4 passed in 1.69s
```

## 2026-10-30 — TASK-4: Makefile targets

- Added `make setup`, `dev`, `test`, `lint`, and `check`; `make check` covers
  Ruff, mypy, ESLint, TypeScript, Prettier, pytest, Vitest, and the frontend
  production build.
- Added the FastAPI app entry point required to run the backend under uvicorn
  in development, and documented the new API package in the repository
  structure.
- Ran `make check`, `make setup`, `make lint`, and `make test`; all exited 0.
  Development smoke test returned HTTP 200 for `http://127.0.0.1:5173/` and
  `http://127.0.0.1:8000/docs`; both servers were then stopped.
- `npm ci` reported 3 low-severity audit findings; it completed successfully.

Verification output:

```text
$ make check
All checks passed!
Success: no issues found in 3 source files
All matched files use Prettier code style!
1 passed
✓ built in 110ms

$ make setup
Resolved 29 packages in 3ms
Checked 28 packages in 0.86ms
added 504 packages, and audited 505 packages in 3s
3 low severity vulnerabilities

$ make dev (HTTP smoke test)
frontend HTTP 200
backend docs HTTP 200
<title>ClipForge</title>
Development servers stopped
```

## 2026-10-30 — TASK-3: Frontend scaffolding

- Created the Vite React 18 TypeScript frontend with strict checking, Tailwind
  CSS v4, initialized shadcn/ui, React Router, TanStack Query, ESLint, Prettier,
  Vitest, and React Testing Library.
- Added the dark ClipForge app shell and a real navigation test. Vite proxies
  `/api` requests to `http://127.0.0.1:8000`.
- Playwright smoke check passed at `http://127.0.0.1:5173`: heading "ClipForge",
  dark background, and no console errors. Screenshot:
  `.agent/screenshots/TASK-3-1.png`.

Verification commands and real output:

```text
$ npm --prefix frontend run lint
> clipforge-frontend@0.1.0 lint
> eslint .

$ npx --prefix frontend tsc --noEmit -p frontend
(exit 0; no output)

$ npm --prefix frontend test -- --run
Test Files  1 passed (1)
      Tests  1 passed (1)

$ npm --prefix frontend run build
dist/index.html                                              0.44 kB │ gzip:  0.28 kB
✓ built in 78ms

$ uv run pytest backend/tests -q
.                                                                        [100%]
1 passed in 0.00s

$ Playwright smoke test
PASS heading=ClipForge; background=oklch(0.14 0.018 270); console errors=0
```

## 2026-10-30 — TASK-2: Backend scaffolding

- Added the uv-managed Python 3.11 project, locked dependencies, package
  metadata, Ruff/mypy configuration, pytest configuration, and the backend
  package version smoke test.
- Added the required documentation skeleton, copied `.agent/prd/PRD.md`
  byte-for-byte, recorded the PRD decisions, and listed resolved package
  versions from `uv.lock`.
- Updated ignore rules for Python tooling and build outputs. Created local
  `data/` directories; they remain gitignored.

Verification command and real output:

```text
$ uv run ruff check backend && uv run mypy --strict backend/clipforge && uv run pytest backend/tests -q
All checks passed!
Success: no issues found in 1 source file
.                                                                        [100%]
1 passed in 0.01s
```

## 2026-10-30 — TASK-1: Verify project prerequisites and access

- Host tools passed: FFmpeg 9.0.1, ffprobe 9.0.1, uv 0.11.26, Node v24.18.0, npm 11.16.0.
- Installed Python 3.11.15 with uv; `uv python find 3.11` resolved `~/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11`.
- Confirmed `.env.local` contains all seven required keys, is gitignored and untracked; the Copilot, OpenAI, and HF token fields are empty.
- GitHub Copilot API access verified with a token from `gh auth token -u omairtemurian -h github.com`; GET `https://api.githubcopilot.com/models` returned HTTP 200. The token was not printed.
- Confirmed required `.gitignore` entries and tested the pre-push hook: the allowed repository URL exited 0; a different GitHub owner exited 1.
- No npm manifest, Python project, Playwright dependency, or application server exists yet, so dependency installation, `make dev`, and a UI screenshot are deferred until the relevant scaffolding is added.

Verification command and real output:

```text
$ ffmpeg -version | head -1 && uv python find 3.11 && grep -c '=' .env.local
ffmpeg version 9.0.1 Copyright (c) 2000-2026 the FFmpeg developers
~/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11
7
```

## 2026-10-31 — TASK-45: Editor Brand + Text panels, Save/Render/Download (T21b)

- `PATCH /projects/{id}` sets the brand template; the editor rail has Brand
  and Text panels; the top bar saves, renders (job progress) and downloads.
- Browser smoke (Playwright, real worker): edit hook/description, pick the
  brand, Render, Download link GET 200 `video/mp4`; no console errors.
  Screenshots: `.agent/screenshots/TASK-45-1..4.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1318 passed, 1 skipped in 111.91s (0:01:51) ==================
 Test Files  32 passed (32)
      Tests  259 passed (259)
✓ built in 134ms
```


## 2026-10-31 — TASK-46: Brand templates page (T22a)

- `/brand-templates` lists the templates and has a create/edit form: name,
  logo upload, position chips, opacity slider, font select, primary color,
  intro/outro videos (with remove), delete with a confirm step, and a live
  9:16 preview frame. New `GET /brand-fonts` lists the fonts a template accepts.
- Browser smoke (Playwright, real API): validation errors, create with logo,
  edit preview, delete; no console errors. Screenshots:
  `.agent/screenshots/TASK-46-1..4.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1319 passed, 1 skipped in 128.17s (0:02:08) ==================
 Test Files  34 passed (34)
      Tests  277 passed (277)
✓ built in 140ms
```

## 2026-10-31 — TASK-47: Settings page (T22b)

- `/settings` edits the LLM provider/model (+ base URL, Ollama host, key),
  whisper model, models folder, credit template, ffmpeg/ffprobe paths and
  yt-dlp cookies through `GET/PUT /api/settings`; "Test connection" posts the
  form's LLM values to `/api/settings/test-llm`. Keys are write-only.
- Browser smoke (Playwright, real API in a temp cwd): test connection, save,
  reload, key never in the DOM; no console errors. Screenshots:
  `.agent/screenshots/TASK-47-1..3.png`.

Verification command and real output:

```text
$ make check
All checks passed!
================= 1319 passed, 1 skipped in 147.62s (0:02:27) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 231ms
```

## 2026-10-31 — TASK-48: Playwright setup + backend test mode (T23a)

- `e2e/` has a chromium-only Playwright config; its `webServer` starts the
  backend in test mode (`clipforge.api.testapp:create_test_app`, fixture
  transcript + recorded LLM reply) from a fresh `e2e/.run` (cwd and data dir)
  and vite. `make e2e` runs it. Test mode needs `CLIPFORGE_TEST_MODE=1` and
  `CLIPFORGE_FIXTURES_DIR`; either alone is a `ValueError`.

Verification commands and real output:

```text
$ make check
All checks passed!
================= 1326 passed, 1 skipped in 135.05s (0:02:15) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 140ms
$ npx playwright test -c e2e
Running 2 tests using 1 worker
  ✓  1 [chromium] › e2e/smoke.spec.ts:3:1 › home loads without console errors (370ms)
  ✓  2 [chromium] › e2e/smoke.spec.ts:16:1 › the API behind the page is the test-mode backend with no projects (11ms)
  2 passed (3.6s)
```

## 2026-10-31 — TASK-49: Full e2e flow (T23b)

- Checks (SPEC 0.1): Playwright 1.64.1 `locator.setInputFiles`,
  `page.waitForEvent("download")` + `download.saveAs`/`suggestedFilename`,
  `test.afterEach({ request })`; MP4 `mvhd` box layout (version 0: 32-bit
  timescale at +12/duration at +16 after the version byte, version 1: 64-bit
  times).
- New `e2e/flow.spec.ts` (SPEC 9.6): Upload sample.mp4 -> Clip settings
  (defaults) -> Get clips -> gallery "Clips (3)", every card has a score ->
  Edit clip -> click a word + Delete (cut) -> Captions panel, another
  template -> "Clip end" handle Shift+ArrowLeft x2 (-2 s) -> Render ->
  wait for the job's "rendered" toast -> Download: `.mp4`, > 0 bytes,
  `ftyp`, duration = the editor's Length (31.63 s vs 00:31.60; the
  pipeline's earlier render was 33.6 s). No console errors. The test
  deletes its project afterwards (the smoke spec expects none).
- `e2e/playwright.config.ts`: `MODELS_DIR` = repo `models/` for the test
  backend (YAMNet, face model; its cwd is `e2e/.run`). Smoke heading match
  is now `exact` (a project title also starts with "ClipForge").
- Screenshots `.agent/screenshots/TASK-49-1..3.png` (gallery, editor after
  the edits, render running).

Verification commands and real output:

```text
$ for i in 1 2 3; do npx playwright test -c e2e; done   (each run)
  ✓  1 [chromium] › e2e/flow.spec.ts:85:1 › upload, get clips, edit one, render it and download the mp4 (31.0s)
  ✓  2 [chromium] › e2e/smoke.spec.ts:3:1 › home loads without console errors (397ms)
  ✓  3 [chromium] › e2e/smoke.spec.ts:18:1 › the API behind the page is the test-mode backend with no projects (5ms)
  3 passed (34.6s)
$ make check
================= 1326 passed, 1 skipped in 142.44s (0:02:22) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 146ms
```

## 2026-10-31 — TASK-50: README (T24a)

- Checks (SPEC 0.1): `clipforge -h`, `run -h`, `step -h`; `download_models.py
  -h` flags; Makefile targets; `.env.example`/`config.yaml` keys;
  `llm.py`/`ffmpeg.py` error messages quoted in Troubleshooting.
- New `README.md` per SPEC 10: requirements (ffmpeg-full for libass), `make
  setup`, language model providers and `.env`, `make dev`, CLI examples,
  development targets, troubleshooting. Prettier-formatted.
- Every README command was run once (CLI runs with `DATA_DIR` in a temp
  dir): `run` on sample.mp4 in test mode (2 clips; `--aspect 1:1
  --num-clips 5`: 3 clips), `run` of a YouTube URL with `--genre podcast`
  (live Copilot gpt-4.1: ingest worked, 0 clips for the 19 s video),
  `step score 1 --force` (test mode), `step curate 1 --force` (live
  Copilot; with `LLM_PROVIDER=ollama` and no server: "ollama: cannot reach
  http://localhost:11434/api/chat: [Errno 61] Connection refused"),
  `FFMPEG_BIN=/nonexistent/ffmpeg` error text, `make setup` (exit 0, models
  skipped), `make dev` (vite 200 on :5173, `/api/projects` `[]` on :8000,
  stopped), `ffmpeg -filters | grep subtitles`, `make check`; `make e2e` was
  run in TASK-49.

Verification commands and real output:

```text
$ make check
================= 1326 passed, 1 skipped in 127.29s (0:02:07) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 308ms
```

## 2026-10-31 — TASK-51: parity.md + final make check (T24b)

- `docs/parity.md` lists every SPEC 10 feature with done, partial or not
  planned. Each claim was checked in the code first: only brand kit
  (no brand pass in render), ClipAnything-style prompt (transcript and audio
  only) and Premiere XML (never opened in Premiere) are partial; caption
  templates are YAML files (the API only lists and previews them).
- Final `make check` (exit 0) and `npx playwright test -c e2e` (with `make
  dev` stopped).

Verification commands and real output:

```text
$ make check
All checks passed!
================= 1326 passed, 1 skipped in 128.76s (0:02:08) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)

$ npx playwright test -c e2e
  ✓  1 [chromium] › e2e/flow.spec.ts:85:1 › upload, get clips, edit one, render it and download the mp4 (28.9s)
  ✓  2 [chromium] › e2e/smoke.spec.ts:3:1 › home loads without console errors (336ms)
  ✓  3 [chromium] › e2e/smoke.spec.ts:18:1 › the API behind the page is the test-mode backend with no projects (5ms)

  3 passed (32.0s)
```

## 2026-10-31 — TASK-55 V2-PRE prerequisites and engines

- `.env.example` lists the 20 v2 credential names (empty); the staging
  SPEC-v2/PRD-v2 are identical to `.agent/prd/` (`cmp`). Nothing installed.
- `scripts/check_prereqs.py` (names only, exit 0), `make check-engines`,
  ten `engine_*` markers in pyproject.toml, `backend/tests/engine_probes.py`
  and its tests; credential gaps in docs/questions.md, engine table in
  docs/stack.md. With Ollama started by hand the Ollama, Piper and YAMNet
  engine tests pass (3 passed); Ollama was stopped afterwards.
- `test_env_example_has_configured_environment_keys` now expects the v2 names.

Verification commands and real output:

```text
$ uv run python scripts/check_prereqs.py
GOOGLE_OAUTH_CLIENT_ID: missing
...
HF_TOKEN: missing
0 present, 20 missing

$ make check-engines
SKIPPED [1] backend/tests/unit/test_engines.py:14: engine_realesrgan: realesrgan-ncnn-vulkan is not on PATH
================ 2 passed, 8 skipped, 1332 deselected in 1.43s =================

$ make check
================= 1333 passed, 9 skipped in 138.61s (0:02:18) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 238ms
```

## 2026-10-31 — TASK-56 T25a timeline model + v1 data migration

- Checks (SPEC-v2 0.1): pydantic 2.14.2 `computed_field` (serialized, in the
  serialization schema as readOnly, ignored as input); SQLite table rebuild
  and `sqlite_sequence` docs; SQLite JSON float formatting differs between
  3.53.1 and 3.53.4, so the migration uses `printf('%!.17g')` (decisions.md).
- New: `migrations/004_v2_timeline.sql`; `TrackItem`, `Timeline`,
  `SourceSpan`, `Clip.segments`/`tracks` and computed `start`/`end`
  (models.py); `ClipRow.segments`/`tracks` (db.py); `clipforge/timeline.py`
  (`video_items`, `timeline_of`, `with_segments`, `respan`);
  `save_clips` writes one segment + video track, `render_clip_row` reads
  the segments' span, `apply_patch` moves the segments and video track.
  Frontend types regenerated; `mockApi.clip()` builds segments/tracks.
- Tests: `test_migration_v2_timeline.py` (v1 fixture DB built from the v1
  migrations: exact segments incl. 17-digit doubles, video track, other
  fields and jobs unchanged, FK cascade after the rebuild, ids not reused,
  empty DB, applied once), `test_timeline.py`, `api/test_clip_timeline_api.py`
  (app started on a v1 DB migrates it; GET keeps start/end; PATCH moves the
  segments and keeps other tracks; emptied segment -> 422), model/db test
  updates; `tests/v1db.py` shared helper.

Verification commands and real output:

```text
$ make check
All checks passed!
================= 1360 passed, 9 skipped in 148.26s (0:02:28) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 143ms

$ npx playwright test -c e2e
  ✓  1 [chromium] › e2e/flow.spec.ts:85:1 › upload, get clips, edit one, render it and download the mp4 (33.1s)
  ✓  2 [chromium] › e2e/smoke.spec.ts:3:1 › home loads without console errors (391ms)
  ✓  3 [chromium] › e2e/smoke.spec.ts:18:1 › the API behind the page is the test-mode backend with no projects (5ms)
  3 passed (36.9s)
```

## 2026-10-31 — TASK-57 T25b assets, source rights, usage records

- Migration `005_v2_assets_rights.sql`: tables `asset` and `usage_record`
  (indexes on `project_id` and `at`; `project_id` is set NULL when the
  project is deleted), `project.source_rights` (NULL), `credit_line` (''),
  `campaign_id` (NULL). Brand logos, intros and outros of `brand_template`
  are inserted as assets (logo / video, license `user-provided`, tags
  `brand`, `intro`, `outro`).
- `models.py`: `Asset`, `UsageRecord`, `AssetKind`, `SourceRights`;
  `Project.source_rights`, `credit_line`, `campaign_id`, read-only
  `rights_set` (False for v1 projects). `asset_rows.py`: `AssetRow`,
  `UsageRecordRow`. `assets.py`: `add_asset`, `get_asset`, `list_assets`,
  `update_asset`, `delete_asset`, `register_bundled_fonts` (called by
  `init_db`).
- Tests: `test_migration_v2_assets.py` (v1 DB with brand templates: assets
  and order, v1 projects "rights not set", empty DB, applied once, fresh DB,
  usage records survive a project delete), `test_assets.py` (CRUD,
  validation, every kind, filters, bundled fonts with license/attribution,
  idempotent, moved directory, `init_db`), db/model/migration test updates;
  `tests/v1db.py` gained `migrations_through`/`migrate_through` so old
  migration tests stay pinned to their own version.

Verification commands and real output:

```text
$ make check
All checks passed!
================= 1388 passed, 9 skipped in 132.53s (0:02:12) ==================
 Test Files  36 passed (36)
      Tests  291 passed (291)
✓ built in 185ms
```

## 2026-10-31 — TASK-58 T25c source rights + credit line in the API and Home

- `ProjectCreate`/upload form take `source_rights` + `credit_line`;
  `ProjectPatch` changes only the fields sent (422 on a bad enum or a credit
  line over 200 chars, 422 on `{}`); `create_job`/`enqueue_process` store them.
- `clipforge/rights.py`: `rights_ok(project)` (False when unset).
- Home panel: `SourceRightsField` (required "Source rights" select, "Credit
  line" input); `SettingsPanel.onSubmit(settings, rights)`; `useAddProject`
  sends both (JSON or form). Screenshot `.agent/screenshots/TASK-58-1.png`.
- Tests: `backend/tests/api/test_projects_rights.py`, SettingsPanel and Home
  vitest tests, e2e flow chooses the rights.

Verification commands and real output:

```text
$ make check
All checks passed!
================= 1405 passed, 9 skipped in 130.18s (0:02:10) ==================
 Test Files  36 passed (36)
      Tests  292 passed (292)
✓ built in 182ms
$ npx playwright test -c e2e
  3 passed (27.9s)
```

## 2026-10-31 — TASK-59 T26a job worker pool (N workers, priorities, GPU lock)

- Migration 006: `job.priority INTEGER NOT NULL DEFAULT 0` + index
  `ix_job_status_priority`; `Job.priority`/`JobRow.priority`; types.ts
  regenerated. `enqueue_process`/`enqueue_render`/`create_job` take
  `priority`.
- `jobs.claim_next(engine, kinds)`: one atomic `UPDATE ... RETURNING`
  (highest priority, then oldest); `jobs.run_claimed`; `run_next` = both.
- `worker_pool.WorkerPool` replaces `JobWorker`: `workers` threads, per-kind
  `job_concurrency` slots and a shared GPU lock for `gpu_job_kinds`
  (settings `workers`=2, `{process: 1, render: 2}`, `[process]`).
- Tests: `tests/unit/test_worker_pool.py` (WORKERS env, priority order,
  kind filter, GPU lock with 3 fake GPU jobs + control without it, kind
  limit, failing runner frees slot, 8-engine concurrent claim of 150 jobs,
  bad settings), `test_migration_v2_job_priority.py`; v1 tests updated for
  the new field/class (15 repeated runs of the pool tests: all pass).

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 82 source files
================= 1421 passed, 9 skipped in 133.11s (0:02:13) ==================
 Test Files  36 passed (36)
      Tests  292 passed (292)
✓ built in 183ms
$ npx playwright test -c e2e
  3 passed (32.5s)
```

## 2026-10-31 — TASK-60 T26b resumable jobs after restart

- `pipeline/step.py`: `marker_path`, `mark_done`, `step_done`, `done_steps`
  (`steps/<name>.done`). `process.run_step` marks a finished step;
  `run_process_job` skips marked steps and logs `job N resumes; finished:`.
- `process_clips.py` (new): `clear_unsaved_clips`, `make_clips` (save ->
  `clips` marker, reframe + layouts -> `reframe` marker, render skips
  rendered clips). `job_rows.py` (new): `load_job`, `set_step`,
  `save_progress`, `progress_writer`.
- Migration 007 `job.attempts` (v1 started jobs 1, queued 0); `Job.attempts`;
  types.ts regenerated; frontend Job mocks `attempts: 0`. `claim_next`
  counts attempts; `reset_stale_jobs(engine, max_attempts=None)` fails poison
  jobs (setting `job_max_attempts` = 3).
- Tests: `tests/unit/test_job_resume.py` (markers, skip of finished
  stages, render skip, attempts, poison process/render job, SIGKILLed worker
  subprocess resumes at `signals`), `test_migration_v2_job_attempts.py`.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 84 source files
================= 1430 passed, 9 skipped in 166.61s (0:02:46) ==================
 Test Files  36 passed (36)
      Tests  292 passed (292)
✓ built in 138ms
$ npx playwright test -c e2e
  3 passed (36.3s)
```

## 2026-10-31 — TASK-61 T26c engines framework + capability API + Settings engine status

- `clipforge/engines/` (base, checks, registry with a cached
  `install_status`), `GET /api/engines?refresh=true`, `EngineGate`, the
  Engines section of Settings, README "Optional engines". The 10 existing
  engine markers now use the registry's `install_check` for their skip.
- Smoke: Settings page with `make dev` (Ollama up): Ollama and Piper and
  YAMNet installed, the rest "Not installed — see setup", no console errors;
  screenshot `.agent/screenshots/TASK-61-1.png`. `GET /api/engines` returned
  Ollama `version` 0.34.4 from the live server.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 88 source files
================= 1443 passed, 8 skipped in 167.75s (0:02:47) ==================
 Test Files  38 passed (38)
      Tests  296 passed (296)
✓ built in 184ms
$ npx playwright test -c e2e
  3 passed (35.7s)
```

## 2026-10-31 — TASK-62 T26d usage meter: compute time, LLM tokens, API calls, monthly caps

- `clipforge/usage.py`: `record`, `job_usage` (compute seconds per job, run
  by `jobs.run_claimed`), `recording` (tokens of the LLM clients, read from
  `usage` of an OpenAI-style answer and `prompt_eval_count + eval_count` of
  Ollama's), `month_summary`, `check_caps`. `GET /api/usage?month=`; new
  process/render jobs answer 409 `usage_cap_exceeded` once a cap is reached;
  caps are settings (`usage_cap_*`), shown with the totals in the Usage
  section of Settings.
- Smoke: `uvicorn` + `vite` from a temp dir with seeded records: Settings
  shows 1.50 h and 21,500 tokens "Cap reached", saving a compute cap works,
  `POST /api/projects` answered 409 with the cap message, no console errors;
  screenshot `.agent/screenshots/TASK-62-1.png`.

Verification commands and real output:

```text
$ make check
All checks passed!
Success: no issues found in 90 source files
================= 1467 passed, 9 skipped in 140.83s (0:02:20) ==================
 Test Files  39 passed (39)
      Tests  300 passed (300)
✓ built in 189ms
$ npx playwright test -c e2e
  3 passed (24.6s)
```

## 2026-10-31 — STEERING 8 (TASK-13) copilot_account, fenced-JSON replies, default claude-sonnet-5.5

- New setting `copilot_account` (default <your-github-account>) for the
  `gh auth token -u` fallback; default `llm_model` claude-sonnet-5.5;
  `reply_json` strips a code fence around a reply before curate and
  regenerate-text validate it.
- Settings smoke: "GitHub account" shows <your-github-account>; Test connection
  answered "Connected (copilot, claude-sonnet-5.5): {"ok": true}"; no
  console errors; screenshot `.agent/screenshots/fix-copilot-account-1.png`.

Opt-in live tests on this machine (account <your-github-account>, 2026-10-31 20:45):

```text
$ uv run pytest -m live -v backend/tests/unit/test_llm.py backend/tests/unit/test_llm_responses.py -k live
backend/tests/unit/test_llm.py::test_copilot_live_answers_with_json[claude-sonnet-5.5] PASSED [ 33%]
backend/tests/unit/test_llm.py::test_copilot_live_answers_with_json[gpt-6-luna] PASSED [ 66%]
backend/tests/unit/test_llm_responses.py::test_copilot_live_gpt_6_luna PASSED [100%]
======================= 3 passed, 33 deselected in 7.43s =======================
```

Raw replies to the calculator prompt (`create_client(...).complete_json`):

```text
POST https://api.githubcopilot.com/chat/completions "HTTP/1.1 200 OK"
copilot claude-sonnet-5.5 replied in 1.0s
claude-sonnet-5.5 '{"answer": 4}' -> {"answer": 4}
POST https://api.githubcopilot.com/responses "HTTP/1.1 200 OK"
copilot gpt-6-luna replied in 1.6s
gpt-6-luna '{"answer":4}' -> {"answer":4}
```


## 2026-10-31: STEERING 9a, Anthropic API provider (TASK-13)

- `LLM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`
  (default https://api.anthropic.com) and `ANTHROPIC_MODEL` (default
  claude-sonnet-5-5); `anthropic-version: 2026-10-21`, `max_tokens` 8192.
- Settings: "Anthropic API" provider with Model (suggestions from "Load
  models", `POST /settings/anthropic-models`), Base URL and a write-only
  API key; Test connection works as for the other providers.
- Verified with mocked HTTP (unit/test_llm_anthropic.py,
  api/test_settings_anthropic_api.py, Vitest). Live test is opt-in and
  skipped: no Anthropic key on this machine.
- Smoke without a key: "Load models" and Test connection both show
  "anthropic: no API key: set ANTHROPIC_API_KEY (Settings, Anthropic API)";
  no console errors; screenshot `.agent/screenshots/fix-anthropic-provider-1.png`.

## 2026-10-31: STEERING 9b, Claude subscription provider (TASK-13)

- `LLM_PROVIDER=claude_code` runs `claude -p ... --output-format json` in an
  empty temp dir (flags verified on Claude Code 2.1.284); CLAUDE_CODE_BIN
  (default claude), CLAUDE_CODE_MODEL (default sonnet).
- Settings: provider "Claude subscription (Claude Code)" with Model and
  Claude Code program fields; Engines lists "Claude subscription (Claude
  Code)" as Installed 2.1.284 on this Mac.
- Smoke against the real CLI (not logged in): Test connection shows "Failed
  (claude_code, sonnet): claude_code: Claude Code is not logged in. Run
  `claude` in a terminal and log in, then retry. (Failed to authenticate:
  OAuth session expired and could not be refreshed)"; no console errors;
  screenshots `.agent/screenshots/fix-claude-code-provider-1.png`, `-2.png`.
- Live test opt-in, not run (no subscription), as the owner expects.

## 2026-10-31: TASK-64 (T27b) Chunked resumable upload up to 30 GB

- `/api/uploads` sessions with SHA-256-checked chunks, resume from the
  server's offset, 30 GB cap, 507 when the disk is short; the Home upload
  now uses it with an "Uploading N%" bar (`.agent/screenshots/TASK-64-1.png`,
  `-2.png`).
- `uv run pytest backend/tests/api/test_uploads.py backend/tests/api/test_projects.py -q`
  -> `42 passed in 6.56s`.
- `npx playwright test -c e2e upload.spec.ts projects.spec.ts flow.spec.ts`
  -> `3 passed (1.1m)`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 114 source files
================= 1817 passed, 13 skipped in 242.66s (0:04:02) =================
 Test Files  52 passed (52)
      Tests  366 passed (366)
```

## 2026-10-31: TASK-70 (T28a) Auto Import: YouTube channel RSS watch

- Migration 013 (`watched_channel`, `watched_video`), `WatchedChannel`,
  `WatchedChannelCreate`, `WatchedVideo` models, `sources/youtube_feed.py`,
  `auto_import.py` (`AutoImporter`, `add_channel`, `list_channels`,
  `channel_videos`), started by the app lifespan; `AUTO_IMPORT_POLL_S`.
- `uv run pytest backend/tests/unit/test_auto_import.py backend/tests/sources/test_youtube_feed.py backend/tests/unit/test_migration_v2_channels.py -q`
  -> all passed (respx recorded feeds, fake clock).
- Live check (manual): `fetch_feed('UCBR8-60-B28hp2BmDPdntcQ')` -> `YouTube 15
  86Ccatsw92c 2026-10-31 14:00:33+00:00`; unknown channel -> `YouTube has no
  channel UCzzzzzzzzzzzzzzzzzzzzzz (feed 404)`.
- `npx playwright test -c e2e smoke` -> `2 passed (3.9s)`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 125 source files
================= 1922 passed, 13 skipped in 259.51s (0:04:19) =================
 Test Files  53 passed (53)
      Tests  371 passed (371)
```

## 2026-10-31: TASK-71 (T28b) Auto Import UI

- `api/auto_import.py` (`/api/auto-import/channels`: list, add 201/409/422,
  get, PATCH `WatchedChannelPatch`, DELETE 204, `/videos`; 404 for an
  unknown id), `auto_import.get_channel/update_channel/remove_channel`;
  frontend `pages/AutoImportPage.tsx`, `components/autoimport/`,
  `api/autoImport.ts`, `lib/autoImport.ts`, sidebar link and route.
- `uv run pytest backend/tests/api/test_auto_import_api.py -q` -> 10 passed.
- `npx playwright test -c e2e auto-import` -> `1 passed (5.0s)`; screenshots
  `.agent/screenshots/TASK-71-1.png`, `TASK-71-2.png` checked, no console
  errors.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 126 source files
================= 1932 passed, 13 skipped in 243.73s (0:04:03) =================
 Test Files  55 passed (55)
      Tests  389 passed (389)
```

## 2026-10-31: TASK-173 (T58a.1) Campaign model, CRUD API, permission evidence

- Migration `015_v2_campaigns.sql`, `campaigns.py`, `campaign_rows.py`,
  `api/campaigns.py` (`/api/campaigns` CRUD, permission screenshot upload and
  download, `require_campaign_permission` guard -> 409 `permission_missing`).
- `uv run pytest backend/tests/api/test_campaigns.py
  backend/tests/api/test_campaign_permission_api.py
  backend/tests/unit/test_campaign_models.py
  backend/tests/unit/test_migration_v2_campaigns.py
  backend/tests/unit/test_campaigns_no_scraping.py -q` -> all passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 143 source files
================= 2038 passed, 13 skipped in 269.53s (0:04:29) =================
 Test Files  59 passed (59)
      Tests  412 passed (412)
```

## 2026-11-01: TASK-174 (T58a.2) Campaign presets + rule checker

- Migration `016_v2_campaign_preset.sql` (`campaign.caption_template`),
  `campaign_rules.py` (rule checker), `campaign_presets.py` (apply a
  campaign to a project and its clips, preset new clips),
  `api/campaign_rules.py` (`PUT /projects/{id}/campaign`,
  `GET /clips/{id}/campaign-check`, guard `require_campaign_rules` -> 409
  `campaign_rules_failed` with `failed`).
- `uv run pytest backend/tests/unit/test_campaign_rules.py
  backend/tests/unit/test_campaign_presets.py
  backend/tests/api/test_campaign_rules_api.py
  backend/tests/unit/test_migration_v2_campaign_preset.py -q` -> all passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 146 source files
================= 2078 passed, 13 skipped in 268.78s (0:04:28) =================
 Test Files  59 passed (59)
      Tests  412 passed (412)
```

## 2026-11-01: TASK-175 (T58a.3) Campaign forms UI + rule check panel

- Campaigns page + `CampaignForm`, `PermissionEvidence`, `CampaignList`,
  `RuleCheckPanel` (editor rail "Rules"), `ProjectCampaignSelect` (gallery),
  `api/campaigns.ts`, `lib/campaignForm.ts`; `e2e/campaigns.spec.ts`.
- `npx playwright test -c e2e` -> 9 passed (incl. campaigns.spec.ts).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 146 source files
================= 2078 passed, 13 skipped in 278.86s (0:04:38) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-11-01: TASK-138 (T46a) Publisher framework

- Encrypted token store (`token_store.py`, Fernet), migration 018
  (`social_account`, `post`), `posts.py` status machine + rights guard,
  `social_accounts.py`, `publishers/` (base, registry, publish run),
  `/accounts` API (platforms, connect, callback, list, disconnect).
- `uv run pytest -q backend/tests/publishers backend/tests/api/test_accounts_api.py
  backend/tests/unit/test_token_store.py
  backend/tests/unit/test_migration_v2_social.py` -> all passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 157 source files
================= 2164 passed, 13 skipped in 285.49s (0:04:45) =================
 Test Files  63 passed (63)
      Tests  432 passed (432)
```

## 2026-11-01: TASK-145 (T48c) Social accounts settings UI

- Sidebar "Publish -> Social accounts" page (`/accounts`), "Social account
  connections" modal, restriction badges, Remove, developer-app status with
  the env var names (`GET /accounts/platforms` now returns `settings_keys`).
- `npx playwright test -c e2e accounts` -> 1 passed; screenshots
  `.agent/screenshots/TASK-145-1..3.png`.
- `make check` (exit 0):
```text
All checks passed!
================= 2362 passed, 13 skipped in 293.89s (0:04:53) =================
 Test Files  64 passed (64)
      Tests  438 passed (438)
✓ built in 238ms
```

## 2026-11-01: TASK-148 (T49c) Thumbnails/covers + AI post copy

- AI post copy per platform (`post_copy.py`, `post_copy_fit.py`,
  `POST /clips/{id}/post-copy`), "Rewrite with AI" menu (tone/format/
  hashtags), cover frame picker/upload + apply to all (`thumbnails.py`).
- `uv run pytest -q backend/tests/test_post_copy.py
  backend/tests/api/test_post_copy_api.py
  backend/tests/api/test_post_cover_api.py` -> all passed;
  `npx playwright test -c e2e posts.spec.ts` -> 2 passed; screenshots
  `.agent/screenshots/TASK-148-1..2.png`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 183 source files
================= 2494 passed, 13 skipped in 293.58s (0:04:53) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
✓ built in 246ms
```


## 2026-11-01: TASK-165 (T55b) Webhooks + n8n example + docs

- Webhooks (`/api/webhooks`, human only), HMAC-SHA256 signed deliveries with
  retry/backoff and a delivery log, events `project.completed`,
  `clip.rendered`, `post.published`, `post.failed`; migration 021;
  `docs/automation.md` and `examples/n8n-clipforge.json`.
- `uv run pytest -q backend/tests/test_webhooks.py
  backend/tests/test_webhook_delivery.py backend/tests/test_webhook_pipeline.py
  backend/tests/api/v1/test_webhooks_api.py` -> all passed (the pipeline test
  runs a real process job and reads the signed `project.completed` delivery).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 196 source files
================= 2760 passed, 13 skipped in 381.08s (0:06:21) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
```


## 2026-11-01: TASK-166 (T55c) MCP server

- `clipforge-mcp` (`backend/clipforge/mcp_server.py`, `mcp_tools.py`): 53
  MCP tools generated from the `/api/v1` OpenAPI document, stdio, API key
  from `CLIPFORGE_API_KEY`; no tool for queue/publish, 403 if called anyway.
  Guide with client setup and example agent prompt: `docs/mcp.md`.
- `uv run pytest -q backend/tests/api/v1/test_mcp_server.py
  backend/tests/api/v1/test_mcp_tools.py` -> 69 passed (a full automation
  loop through the MCP protocol on the real app).
- Smoke test over real stdio: `uvicorn` on a temporary data dir + `clipforge-mcp`
  launched by `mcp.client.stdio.stdio_client`: `list_tools` -> 53 tools,
  `list_projects` -> `[]`, no error.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 198 source files
================= 2830 passed, 13 skipped in 380.37s (0:06:20) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
```


## 2026-11-01: TASK-68 (T27f) SRT and WebVTT upload

- `pipeline/subtitle_import.py` (renamed from `srt_import.py`) reads SRT and
  WebVTT; words are flagged `approximate`; malformed files are 422 with the
  line number; transcribe logs "skipped transcription" and never loads
  Whisper. Panel button "Upload SRT or VTT (optional)".
- `uv run pytest -q backend/tests/pipeline/test_subtitle_import.py
  backend/tests/pipeline/test_transcribe.py
  backend/tests/api/test_subtitles_api.py` -> 41 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 200 source files
================= 2883 passed, 13 skipped in 390.13s (0:06:30) =================
 Test Files  68 passed (68)
      Tests  454 passed (454)
```

## 2026-11-01: TASK-69 (T27g) Captions/reframe-only mode + import UI

- `clipping: "none"` is now `captions_only` (old saved settings still read);
  Home has the Captions only chip toggle and a Subtitles button; the panel
  opens with both.
- `uv run pytest -q backend/tests/pipeline/test_captions_only.py` -> 4 passed
  (no LLM request, whole video, timeframe, no client made, legacy "none").
- `npx playwright test -c e2e captions-only` -> 1 passed
  (screenshots `.agent/screenshots/TASK-69-1.png`, `-2.png`).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 200 source files
================= 2887 passed, 13 skipped in 388.60s (0:06:28) =================
 Test Files  69 passed (69)
      Tests  456 passed (456)
```

## 2026-11-01: TASK-72 (T29a) Length presets 0-1m..10-15m + custom range

- New presets `0_60`, `60_180`; `custom` with `custom_length_min_s` /
  `custom_length_max_s` (min < max <= 900); threaded through
  `candidate_rules`, curate prompt/windows/selection.
- `uv run pytest -q backend/tests/pipeline/test_length_presets.py` -> 24 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 200 source files
================= 2911 passed, 13 skipped in 414.22s (0:06:54) =================
 Test Files  69 passed (69)
      Tests  456 passed (456)
```

## 2026-11-01: TASK-73 (T29b) Prompt to clip and keyword search

- Prompt to clip: `keyword_prompt` section moved to
  `prompts/prompt_to_clip.md` (`curate_prompt.request_section`).
- Keyword search: `clipping: "keyword_search"` + `search_terms`;
  `pipeline/keyword_search.py` finds every match and builds sentence
  windows without the LLM.
- `uv run pytest -q tests/unit/test_keyword_search.py tests/pipeline/test_prompt_to_clip.py`
  (in backend/) -> 26 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 201 source files
================= 2937 passed, 13 skipped in 416.99s (0:06:56) =================
 Test Files  69 passed (69)
      Tests  456 passed (456)
```

## 2026-11-01: TASK-74 (T29c) Reprompt without re-transcribing

- `POST /api/projects/{id}/reprompt` -> `reprompt` job (`reprompt.py`):
  curate/score/snap only; old clips kept as result set 1, new set rendered
  and made current on success; 409 if the project is not done.
- `uv run pytest -q tests/api/test_reprompt.py` (in backend/) -> 9 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 202 source files
================= 2951 passed, 13 skipped in 395.14s (0:06:35) =================
 Test Files  69 passed (69)
      Tests  456 passed (456)
```

## 2026-11-01: TASK-75 (T29d) Topic chapters, clip by topic

- `POST/GET /api/projects/{id}/chapters` (LLM chapters, contiguous, snapped
  to sentences, `chapters.json`) and `POST /api/projects/{id}/clip-by-topic`
  (a reprompt restricted to the chosen chapters' ranges).
- `uv run pytest -q tests/pipeline/test_chapters.py tests/api/test_chapters_api.py`
  (in backend/) -> 22 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 204 source files
================= 2973 passed, 13 skipped in 429.46s (0:07:09) =================
 Test Files  69 passed (69)
      Tests  456 passed (456)
```

## 2026-11-01: TASK-76 (T29e) Clipping controls UI: reprompt, topics

- Gallery: "Reprompt" dialog, "Topics" dialog (make chapters, pick, clip by
  topic), "Result" select for earlier result sets; `useProcessJob` follows
  reprompt jobs.
- `npx vitest run src/pages/Gallery src/pages/Processing` -> passed;
  `npx playwright test -c e2e reprompt.spec.ts` -> 1 passed (real reprompt on
  the fixture, chapters canned). Screenshots `.agent/screenshots/TASK-76-{1,2}.png`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 204 source files
================= 2973 passed, 13 skipped in 433.27s (0:07:13) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-77 (T30a) Audio event classes as curation signals

- YAMNet scores Laughter, Applause, Cheering and Music in the signals pass:
  per-second scores in `audio_events.json`, cheer/music events in
  signals.json; applause and cheers count in the energy score.
- `uv run pytest tests/pipeline/test_audio_events.py
  tests/pipeline/test_signals_step.py tests/unit/test_score.py -q` -> passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 205 source files
================= 2988 passed, 13 skipped in 403.42s (0:06:43) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-78 (T30b) VLM frame captions via Ollama

- `engines/vlm_ollama.py` (install check + `VisionCaptioner`) and
  `pipeline/frame_captions.py` (frames at scene cuts + every 10 s ->
  `frame_captions.json`). Real model on this Mac: `qwen3.5-35b-128k:latest`.
- `uv run pytest backend/tests/engines -q` -> 10 passed (real VLM test ran).
- `make check-engines` (with `ollama serve` running):
```text
backend/tests/engines/test_vlm_ollama.py .                               [  8%]
backend/tests/unit/test_engines.py .ss.ssss.s.                           [100%]
================ 5 passed, 7 skipped, 2997 deselected in 6.25s =================
```
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 207 source files
================= 2997 passed, 12 skipped in 436.77s (0:07:16) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-79 (T30c) Clip anything: motion + frame captions into curate

- `ProcessingSettings.clip_anything` (settings toggle, AI clipping only). New
  pipeline step `visuals` (between signals and enrich): `pipeline/motion.py`
  (ffmpeg 4 fps 64x36 grey frames -> per-second median frame difference ->
  `motion.json`) and `frame_captions.run` when `ollama_vlm` is installed.
  Curate adds timeline lines (SCENE CUT, LAUGH/APPLAUSE/CHEER/MUSIC, MOTION,
  FRAME captions) and the `clip_anything.md` prompt section; snap keeps
  wordless clips; auto cut is off.
- `uv run pytest tests/pipeline/test_clip_anything.py -q` -> 9 passed.
- Real smoke test (`ollama serve`, `qwen3.5-35b-128k`) on a silent 20 s
  video: visuals step 11.3 s, timeline had the scene cut, motion span and
  two FRAME captions.
- `npx playwright test -c e2e clip-anything` -> 1 passed
  (`.agent/screenshots/TASK-79-1.png`).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 209 source files
================= 3004 passed, 14 skipped in 434.36s (0:07:14) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-80 (T31a) Reframe v2: 4:5 + custom crop ratio

- `clipforge/aspect.py` (`PRESETS`, `check_aspect`, `aspect_size`); `Aspect`
  is a validated "W:H" string; render, reframe, preview, clips and the CLI
  (`--aspect W:H`) size frames with `aspect_size`. 4:5 in the aspect menus.
- `uv run pytest backend/tests/pipeline/test_reframe_ratios.py -q` -> 32
  passed (real ffmpeg renders of 9:16, 1:1, 4:5, 16:9, 3:2, 2:3: ffprobe size,
  even dims, duration +-0.2 s; fit and split at 4:5).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 208 source files
================= 3035 passed, 14 skipped in 451.14s (0:07:31) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-81 (T31b) Moving subject (object) tracking

- `pipeline/object_tracking.py`: in a shot with no face or person, the
  median-background motion regions give the moving subject; an OpenCV CSRT
  tracker (KCF, else a motion-region follower) tracks it forward and back
  from its largest sample. Reframe stores it as `FaceBox(kind="object")`,
  so the fill window follows it. Shots with people are unchanged.
- `uv run pytest backend/tests/pipeline/test_object_tracking.py -q` -> 14
  passed (synthetic moving square: box center within 0.03, crop center
  within 0.1 of the frame width for 9:16, 1:1, 4:5, CSRT and fallback; real
  `reframe_clips` with the face model; CSRT present in this build).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 211 source files
================= 3049 passed, 14 skipped in 455.32s (0:07:35) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-82 (T31c) Manual subject tracking + genre reframe presets

- Manual tracking (click or box at time t, `POST /clips/{id}/scenes/track`)
  was done in STEERING 7b; now also tested through the API on the
  moving-square video (click and box seeds at t=2 and t=1 follow it within
  0.06 frame widths, forward and back).
- `pipeline/reframe_presets.py`: presets podcast-2, standup, gaming, vlog
  map to layout + tracking params (split share, dead-zone, max pan, object
  tracking). `ProcessingSettings.reframe_preset`, `CropPlan.preset`,
  `GET /api/reframe-presets`.
- `uv run pytest backend/tests/pipeline/test_manual_tracking.py backend/tests/api/test_manual_tracking_api.py -q` -> 17 passed.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 212 source files
================= 3066 passed, 14 skipped in 429.39s (0:07:09) =================
 Test Files  70 passed (70)
      Tests  462 passed (462)
```

## 2026-11-01: TASK-83 (T31d) Reframe v2 editor UI

- Layout tab: `ReframeControls` (custom ratio, project reframe style, track
  hint); toolbar aspect menu shows a custom ratio; settings panel
  "Reframe style" select. New e2e `e2e/reframe.spec.ts` (screenshots
  `.agent/screenshots/TASK-83-1.png`, `-2.png`).
- `npx vitest run src/lib/aspectRatio.test.ts src/pages/EditorReframe.test.tsx src/components/SettingsPanel src/pages/EditorCrop src/pages/EditorScenes src/pages/EditorTrack` -> 7 files passed.
- `npx playwright test -c e2e e2e/reframe.spec.ts` -> `1 passed (26.4s)`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 212 source files
================= 3066 passed, 14 skipped in 467.98s (0:07:47) =================
 Test Files  72 passed (72)
      Tests  477 passed (477)
```

## 2026-11-01: TASK-84 (T32a) Layouts: three-speaker grid + picture-in-picture

- `pipeline/layouts.py`: `grid` (three windows, rows in portrait, columns
  otherwise) and `pip` (fill + bordered top-right inset of the other
  speaker, or the whole frame) graphs. `pipeline/layout_windows.py` plans
  split/grid/inset windows; `framing.planned` adds them to older plans
  when a clip or scene uses grid/pip.
- `uv run pytest tests/pipeline/test_layouts_grid_pip.py tests/unit/test_layout_windows.py -q`
  -> `19 passed` + `9 passed` (fixture renders: ffprobe 1080x1920 /
  1920x1080 / 1080x1080, h264/yuv420p/aac, 4.0 s +-0.2; stripe pixels per cell
  and inset).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 213 source files
================= 3094 passed, 14 skipped in 495.36s (0:08:15) =================
 Test Files  72 passed (72)
      Tests  478 passed (478)
```

## 2026-11-01: TASK-85 (T32b) Layouts: screenshare + facecam, gameplay + facecam

- `pipeline/facecam.py`: `screenshare` (video fitted over the plan's
  background, facecam cell after it, 1:1 split) and `gameplay` (facecam
  cell first, 1/3 of the frame; video cover-cropped) graphs, rows in
  portrait and columns otherwise. With no facecam box the video takes the
  whole frame. `pipeline/layout_parts.py` holds the shared crop/fit pieces
  moved out of `layouts.py`.
- Facecam box: auto from the subject face (3x median face height square,
  kept in frame; `layout_windows.facecam_box`, stored on `CropPlan.facecam`)
  or the user box `Framing.facecam` (`FrameBox`, fractions, overrides).
- `uv run pytest tests/pipeline/test_layouts_facecam.py tests/unit/test_facecam.py -q`
  -> `27 passed` (fixture renders: ffprobe 1080x1920 / 1920x1080 /
  1080x1080, h264/yuv420p/aac, duration; facecam/video pixels per cell).
- `EditorSave.test.tsx` "text panel": typing 145 chars with `user.type`
  timed out (5 s) in the full suite under machine load, also on the
  baseline; it now uses `user.paste` (maxLength still enforced).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 215 source files
================= 3121 passed, 14 skipped in 542.45s (0:09:02) =================
 Test Files  72 passed (72)
      Tests  478 passed (478)
```

## 2026-11-01: TASK-86 (T32c) Dynamic per-segment layout switching + default layout

- `ProcessingSettings.default_layout` (`auto` | `dynamic` | a layout).
  `clip_layouts.set_planned_layouts` (moved out of `clips.py`) applies it
  after reframe in the process and reprompt jobs.
- `pipeline/layout_switch.py`: `segment_layout` (speakers/scene ->
  layout), `switch_scenes` (shots at cuts, split on speaker-count changes
  lasting 2 s), `main_layout`. Dynamic clips store their segments as
  `scene_reframes`; edited scenes are kept.
- `render_graph`/`zoom_graph`: zoom centers follow each scene's plan and
  layout (`framing_at`).
- `uv run pytest tests/pipeline/test_layout_switch.py tests/unit/test_clip_layouts.py -q`
  -> `30 passed` (deterministic segment layouts; a 4 s clip rendered as
  grid, split, fit, screenshare, fill: ffprobe 1080x1920 30 fps, duration
  4.0 +-0.2 s, pixels of each part).
- `make check` (exit 0; the first run failed only because
  `frontend/node_modules` had been emptied, restored with `npm ci`):
```text
All checks passed!
Success: no issues found in 217 source files
================= 3152 passed, 14 skipped in 506.67s (0:08:26) =================
 Test Files  72 passed (72)
      Tests  478 passed (478)
```

## 2026-11-01: TASK-87 (T32d) Keyframed manual reframe (drag/resize crop box)

- Built earlier (STEERING 7a, TASK-54 commits): per-scene fixed crop
  keyframes, linear between them, rendered per scene. Added:
  `pipeline/keyframes.py` (`set_keyframe`, `delete_keyframe`,
  `scene_index`, `window_at`) and `api/clip_keyframes.py`
  (`PUT`/`DELETE /api/clips/{id}/crop-keyframes`, model `CropKeyframeSet`).
- `uv run pytest tests/pipeline/test_crop_keyframes.py tests/api/test_crop_keyframes_api.py -q`
  -> `12 passed` (keyframe edits; ffmpeg's crop trace log at 40 frames
  equals `window_at` rounded like vf_crop; a render ffprobe 216x384,
  duration 4.0 +-0.1 s, red -> both halves -> blue as the box moves).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 219 source files
================= 3164 passed, 14 skipped in 500.61s (0:08:20) =================
 Test Files  72 passed (72)
      Tests  478 passed (478)
```

## 2026-11-01: TASK-88 (T32e) Layouts + keyframe crop UI in editor

- `components/LayoutPicker.tsx` (tiles of all 9 framings per scene),
  toolbar menu with all 7 layouts, `components/CropBoxEditor.tsx` (shared
  drag/resize box; crop window keeps shape and sets keyframes, facecam box
  is free), `editor/PlayerFacecam.tsx` (`framing.facecam` in screenshare/
  gameplay scenes), `settings/DefaultLayoutField.tsx` (`default_layout`).
  Backend: `CropTrack.facecam` (the found box) from `framing.crop_track`.
- `npx playwright test -c e2e layouts.spec.ts` -> `1 passed (31.0s)`
  (default layout screenshare -> picker checked -> facecam box dragged ->
  Fixed -> crop window dragged -> keyframe diamond -> saved; no console
  errors). Screenshots `.agent/screenshots/TASK-88-1.png`, `TASK-88-2.png`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 219 source files
================= 3165 passed, 14 skipped in 497.90s (0:08:17) =================
 Test Files  74 passed (74)
      Tests  487 passed (487)
```

## 2026-11-01: TASK-91 (T33c) Custom font upload (TTF/OTF) as Asset

- `fonts.py` (`check_font`, `store_font`, `available_fonts`,
  `render_fonts_dir`), `POST/GET/DELETE /api/fonts` in `api/media.py`,
  `models.FontFile`; brand fonts and caption style fonts accept uploads;
  libass loads them through `{data_dir}/fonts-render`.
- `uv run pytest backend/tests/api/test_font_upload.py -q` -> `18 passed`
  (real ffmpeg/libass picks `ZedDisplay-Bold` from the uploaded file).
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 221 source files
================= 3299 passed, 14 skipped in 545.56s (0:09:05) =================
 Test Files  74 passed (74)
      Tests  489 passed (489)
```

## 2026-11-01: TASK-197 Apple Silicon GPU transcription (MLX Whisper backend)

- `transcribe_backend: auto|faster_whisper|mlx` (default auto), `pipeline/
  transcribe_mlx.py` (choice, model download, output normalised to the same
  `TimedWord`s), Settings API + page ("Running on: Apple GPU (MLX)"),
  `scripts/download_models.py` fetches `models/whisper-mlx/<name>`.
- Benchmark (M4 Max, small): 607 s of speech 75.0 s faster-whisper vs 9.4 s MLX
  (docs/decisions.md TASK-197).
- `uv run pytest backend/tests/pipeline/test_transcribe_mlx.py
  backend/tests/api/test_settings_transcribe_backend.py -q` -> `30 passed`
  (the engine test ran the real MLX model on the fixture).
- `npx playwright test -c e2e transcribe-backend` -> `1 passed`; screenshot
  `.agent/screenshots/TASK-197-1.png`.
- `make check` (exit 0):
```text
All checks passed!
Success: no issues found in 230 source files
================= 3427 passed, 14 skipped in 520.86s (0:08:40) =================
 Test Files  78 passed (78)
      Tests  512 passed (512)
```

## 2026-11-01: TASK-198 Auto zoom-out (smart Fit / Square-over-blur moments)

How the auto layout decides today (before this task):

- `clip_layouts.set_planned_layouts` (run by `process_clips` and `reprompt`)
  applies the project's `ProcessingSettings.default_layout`. The default is
  `auto`: each clip gets ONE layout for its whole length, `plan.layout`, set
  by `reframe.choose_layout` (via `reframe._plan`): the preset's layout, else
  `split` when two faces persist in more than `split_share` (0.5) of the
  samples and the fill window is narrower than the frame, else `fill`.
- Only `default_layout="dynamic"` switches per segment:
  `layout_switch.switch_scenes` cuts the clip at scene cuts, gives each crop
  keyframe `segment_layout` (grid/split by speaker count, `fill` when a face,
  person or object is seen in >= 50 % of the samples, `fit` only when nobody
  and nothing is seen), and joins runs shorter than 2 s (`_smooth`).
- So the fixture clips stay fill-only: `sample.mp4` shows one large drawn
  face in every sample, so `choose_layout` returns `fill` (auto) and every
  dynamic segment has a face in 100 % of its samples (`fill`). No rule looks
  at face size, face spread vs the crop window, lost tracking or motion
  spread, and no zoomed-out layout other than whole-frame `fit` exists.

What was built (TASK-198, backend; UI in TASK-198b): `square_blur` layout,
zoom-out rules (`pipeline/zoom_out_rules.py`, `pipeline/layout_auto.py`,
`pipeline/motion_spread.py`), eased transitions
(`pipeline/zoom_transition.py`, `scene_framing.add_eases`),
`ProcessingSettings.zoom_out_moments` and `config.zoom_out`; applied by
`clip_layouts.set_planned_layouts` for auto/dynamic clips without manual
scenes. Thresholds and choices: docs/decisions.md "TASK-198".

Verification:

- `uv run pytest tests/unit/test_layout_auto.py tests/unit/test_clip_layouts.py
  tests/pipeline/test_zoom_out_render.py tests/pipeline/test_motion_spread.py -q`
  passed; `-m slow tests/pipeline/test_zoom_out_faces.py`: 2 passed
  (sample.mp4 0.5-20.5 s: no zoom-out; wide two-shot: one zoom-out 8.6-12 s).
- `make check`: 3450 passed, 14 skipped; vitest 512 passed.
- Screenshot `.agent/screenshots/TASK-198-1.png`: fill, mid-ease,
  square_blur, fit frames rendered from the wide two-shot fixture.

## 2026-11-01: TASK-198b Auto zoom-out UI

- Segment strip: an auto scene is labelled "Fill"; selecting a segment shows
  Fill / Square / Fit / Split / Track under the timeline
  (`SegmentOverride`, `useSceneEdits.chooseAt`/`choiceAt`). Save changes
  stores it with PATCH `scene_reframes`; Render applies it.
- `ZoomOutMoments` (switch + Subtle/Balanced/Frequent chips; switching on
  picks Balanced) in the settings panel (`StyleTabs`, disabled unless the
  default layout is Automatic or Switch per segment) and in the editor's
  reframe panel (`ProjectZoomOut`). Presets keep it: they store the whole
  `ProcessingSettings`.
- `PUT /api/projects/{id}/zoom-out {intensity}` (`api/project_zoom_out.py`)
  saves `settings.zoom_out_moments` and `zoom_out_apply.reapply_zoom_out`
  plans the clips without manual scenes again (scenes dropped, then
  `set_planned_layouts`). Manual = a scene that is not auto fill / square_blur
  / fit, has crop keyframes, a scale or a track seed, or a clip without
  scenes whose layout is not its crop plan's. A Square or Fit chosen on a
  segment is indistinguishable from a planned one, so it is planned again.
  The rendered videos change on the next render.
- Verification: `uv run pytest backend/tests/unit/test_zoom_out_apply.py
  backend/tests/api/test_project_zoom_out.py -q` 8 passed; vitest
  `EditorSegmentOverride`, `SettingsPanel`, `EditorScenes`, `EditorLayouts`;
  `npx playwright test -c e2e zoom-out` passed; `make check` passed.
  Screenshots `.agent/screenshots/TASK-198b-{1,2,3}.png`.

## 2026-11-01: TASK-94 Auto censor (T33f)

- `pipeline/censor.py`: default + custom lists (any case, `word*`
  prefixes), per-word `CaptionMark.censor`, masking ("F***,"), padded and
  merged windows, beep (`aeval` 1 kHz) / mute (`volume=0`) filters.
  `pipeline/censor_audio.py` builds a clip's filter; `render_clip(censor=)`
  runs it after the cuts and before loudnorm; render_clip_row and previews
  use it (the preview key includes it). `polish.rendered_words` masks
  captions/SRT. `GET/PUT /api/censor-words` (`api/censor.py`).
- Verification: `uv run pytest backend/tests/pipeline/test_censor.py
  backend/tests/pipeline/test_censor_render.py backend/tests/api/test_censor_api.py -q`
  -> `18 passed in 6.22s`. Measured (astats RMS, 4 s quiet 440 Hz tone, cut 0.2-0.6 s,
  censored word at 1.1-1.6 s of the render): beep word -13.47 dB vs
  outside -37.01 dB; beep + loudnorm -14 LUFS: -11.81 vs -35.36 dB; mute
  word -inf vs outside -37.01 dB.
- `make check` (exit 0): `3476 passed, 14 skipped in 584.26s`; vitest
  `Tests  520 passed (520)`; frontend build `✓ built in 218ms`.

## 2026-11-01: TASK-95 Transcript and subtitle downloads (T33g)

- `pipeline/transcript_files.py` (`source_cues`, `clip_cues`, `format_cues`,
  `vtt_time`), `export.caption_cues` (build_srt now uses it),
  `GET /api/projects/{id}/transcript.{txt,srt,vtt}` and
  `GET /api/clips/{id}/transcript.{txt,srt,vtt}` in `api/clip_files.py`.
- Verification: `uv run pytest backend/tests/api/test_transcript_downloads.py
  backend/tests/api/test_clip_files.py -q` -> 7 + existing passed.
- `make check` (exit 0): `3491 passed, 14 skipped in 531.58s (0:08:51)`;
  vitest `Tests  520 passed (520)`; frontend build `✓ built in 159ms`.

## 2026-11-02: TASK-120 Find B-roll spots (LLM) + cutaway/PiP insert (T40b)

- `pipeline/broll.py` (sentences, LLM picks, spot windows, items),
  `prompts/broll.md`, `api/broll.py` (providers, search, spots, insert,
  replace, remove), `BrollProps.mode` cutaway/pip rendered by
  `timeline_graph._placement`, `api/timeline.store_tracks`.
- Verification: `uv run pytest backend/tests/pipeline/test_broll_spots.py
  backend/tests/api/test_broll_api.py -q` -> 18 passed; affected timeline/
  sfx/v1/gen_types suites -> `376 passed in 130.38s`.
- `make check` (exit 0): `4109 passed, 12 skipped in 1016.21s (0:16:56)`;
  vitest `Tests  666 passed (666)`; frontend build `✓ built in 254ms`.

## 2026-11-02: TASK-121 B-roll review UI (T40c)

- `components/BrollPanel.tsx` (rail panel "B-roll"), `components/broll/`
  (`SpotCard`, `StockResult`, `PlacedBroll`), `api/broll.ts`, `lib/broll.ts`.
- Verification: `npx vitest run src/pages/EditorBroll.test.tsx` -> `5 passed`;
  `npx playwright test -c e2e broll.spec.ts` -> `1 passed (30.3s)`;
  screenshot `.agent/screenshots/TASK-121-1.png`.
- `make check` (exit 0): `4137 passed, 12 skipped in 954.67s (0:15:54)`;
  vitest `Tests  679 passed (679)`; frontend build `✓ built in 285ms`.

## 2026-11-02: TASK-136 Export v2 up to 4K + platform presets (T45a)

- `clip_export.export_clip`, `export_presets`, `clip_render` (shared with `clips.render_clip_row`); sources and dates of the platform limits in `docs/decisions.md`.
- Verification: `cd backend && uv run pytest tests/pipeline/test_export_4k.py -q` -> `18 passed` (a 3840x2160 source exports 16:9 as 3840x2160, probed; no upscale of a 1080p source; caption extents 1:2 between 1080p and 4K). Screenshot of a 4K export frame: `.agent/screenshots/TASK-136-1.png`.
- `make check` (exit 0): `4213 passed, 12 skipped in 925.42s (0:15:25)`; vitest `Tests  727 passed (727)`; frontend build `✓ built in 272ms`.

## 2026-11-03 — TASK-152 Collections + collection zip export (T51a)

- Backend: migration 030 (`collection`, `collection_item`), `clip_collections.py`,
  `collection_export.py`, `api/collections.py` (also in `/api/v1` and as MCP
  tools), models `Collection*`; types regenerated.
- Tests: `tests/api/test_collections.py`, `tests/api/v1/test_collections_api.py`,
  `tests/unit/test_migration_v2_collections.py`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 300
  source files`; `4287 passed, 12 skipped in 997.10s (0:16:37)`;
  vitest `Tests  764 passed (764)`; frontend build `✓ built in 239ms`.

## 2026-11-03 — TASK-153 Library full-text search with FTS5 (T51b)

- Backend: migration 031 (`search_fts` FTS5 table, `search_state`), package
  `clipforge/search/` (`fts.py`, `query.py`, `moment.py`, `rows.py`),
  `api/search.py` (`GET /search`, `POST /search/clips`; also in `/api/v1` and
  as MCP tools), index hooks in `process.run_step` and
  `vocabulary.replace_everywhere`; types regenerated.
- Tests: `tests/search/test_fts.py`, `tests/api/test_search_api.py`,
  `tests/api/v1/test_search_public_api.py`,
  `tests/unit/test_migration_v2_search.py`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 306
  source files`; `4328 passed, 12 skipped in 917.68s (0:15:17)`;
  vitest `Tests  764 passed (764)`; frontend build `✓ built in 250ms`.

## 2026-11-03 — TASK-156 Library, collections and storage UI + project filters and reprocess (T51e)

- Backend: migration 032 (`project.archived_at`), `storage.py`, `reprocess.py`,
  `clip_crop.py`, `api/storage.py` (`GET /storage`, `POST /projects/{id}/cleanup`,
  `.../archive`), `POST /projects/{id}/reprocess`, archived guards; types regenerated.
- Frontend: `LibraryPage`, `CollectionsPage`, `StoragePage`, `components/library`,
  `components/collections`, `components/storage`, `ui/confirm-dialog.tsx`,
  project status chips, "Process again", gallery "Add to collection".
- e2e: `npx playwright test -c e2e library.spec.ts` -> `1 passed (37.8s)`;
  screenshots `.agent/screenshots/TASK-156-1..5.png`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 310
  source files`; `4347 passed, 12 skipped in 1033.88s (0:17:13)`;
  vitest `Tests  797 passed (797)`; frontend build `✓ built in 254ms`.

## 2026-11-02 — TASK-170 Notifications: in-app, desktop, SMTP email (T57a)

- Backend: migration 033 (`notification`), `notifications.py`,
  `notification_delivery.py`, `notification_rows.py`, `api/notifications.py`
  (`GET /notifications`, `/channels`, `POST /test`, `/read-all`,
  `/{id}/read`, `DELETE /{id}`), SMTP/desktop/quota settings in `config.py`;
  hooks in `process`, `reprompt`, `clips`, `posts`, `post_queue`, `jobs`;
  types regenerated.
- Tests: `tests/test_notifications.py`, `tests/test_notification_delivery.py`
  (a real SMTP conversation with `tests/smtp_fakes.py`),
  `tests/api/test_notifications_api.py`; every test turns email/desktop off.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 314
  source files`; `4384 passed, 12 skipped in 1061.85s (0:17:41)`;
  vitest `Tests  797 passed (797)`; frontend build `✓ built in 289ms`.

## 2026-11-02 — TASK-171 Settings v2: engines, keys, connections, defaults, caps, storage paths, language (T57b)

- Backend: `settings_edit.py` `SettingsView`/`SettingsUpdate` take `smtp_host`,
  `smtp_port`, `smtp_user`, `smtp_password` (write-only; `smtp_password_set`),
  `smtp_from`, `notify_email_to`, `desktop_notifications`,
  `quota_warn_percent`; types regenerated.
- Frontend: Settings sections Defaults for new projects, Platform connections,
  Notifications, Storage paths (plus the existing model, rendering,
  transcription, posting, usage and engines sections); `NotificationBell` in
  the top bar.
- Tests: `tests/api/test_settings_notifications.py`, `pages/SettingsV2.test.tsx`,
  `components/notifications/NotificationBell.test.tsx`, `lib/notifySettings.test.ts`,
  `e2e/settings.spec.ts` (screenshots `.agent/screenshots/TASK-171-1.png`, `-2`).
- `make check` (exit 0): ruff/mypy clean; `4392 passed, 12 skipped in 1044.65s (0:17:24)`;
  vitest `Test Files  128 passed (128)`, `Tests  810 passed (810)`; frontend build
  `✓ built in 257ms`. e2e: `e2e/settings.spec.ts` 1 passed.

## 2026-11-02 — TASK-177 T58b.2 Submission tracker, copy for submission, campaign accounts, bulk schedule

- Migration 034 (`campaign_account`, `submission`); `submissions.py`, `campaign_accounts.py` and their APIs
  (`/submissions`, `/campaigns/{id}/accounts`, `/campaigns/{id}/bulk-schedule`).
- Campaigns page: Submissions section (Copy for submission, submitted tick, board answer, views, payout, notes).
- `make check` (exit 0): ruff/mypy clean; `4438 passed, 12 skipped in 965.46s (0:16:05)`;
  vitest `Test Files  130 passed (130)`, `Tests  818 passed (818)`; frontend build
  `✓ built in 247ms`. e2e: `npx playwright test -c e2e/playwright.config.ts e2e/submissions.spec.ts` 1 passed.
- No third-party API used (internal only).

## 2026-11-02 — TASK-180 T58d.1 Autopilot settings + Draft/FeedbackEvent model

- Migration 035 (`autopilot_settings`, `draft`, `feedback_event`); models `AutopilotSettings(Update)`, `Draft`, `FeedbackEvent`; `autopilot/settings.py` (`get_settings`, `save_settings`) and `GET|PUT /api/campaigns/{id}/autopilot`.
- `make check` (exit 0): ruff/mypy clean; `4484 passed, 12 skipped in 1039.38s (0:17:19)`;
  vitest `Test Files  130 passed (130)`, `Tests  818 passed (818)`; frontend build
  `✓ built in 291ms`.
- No third-party API used (internal only).

## 2026-11-02 — TASK-181 T58d.2 Autopilot draft pipeline

- `autopilot/pipeline.py`: Auto Import makes a campaign upload the autopilot's way (`import_settings`); when its process job is done the best rendered clips (up to `max_clips_per_source`) become drafts, pending or needs_fix with the rule results (`make_drafts`, hooked in `process._finish`). Never posts, schedules or submits.
- Tests: `uv run pytest tests/autopilot -q` -> `43 passed in 3.13s`.
- `make check` (exit 0): ruff/mypy clean; `4499 passed, 12 skipped in 1059.14s (0:17:39)`;
  vitest `Test Files  130 passed (130)`, `Tests  818 passed (818)`; frontend build
  `✓ built in 221ms`.
- No third-party API used (internal only).

## 2026-11-02 — TASK-182 T58d.3 Autopilot safety stops, draft expiry, global pause

- `autopilot/safety.py`: stops (global pause, missing permission, paused/ended campaign, end date passed, daily quota) with a daily `autopilot_stopped` alert; 3 failed uploads in a row turn the campaign's autopilot off with an alert; drafts expire after `draft_ttl_days` (Auto Import tick). Migration 036 (`autopilot_pause`), `GET /api/autopilot/status`, `PUT /api/autopilot/pause` (resume is human-only).
- Tests: `uv run pytest tests/autopilot tests/api/test_autopilot_pause_api.py -q` -> `60 passed in 9.27s`.
- `make check` (exit 0): ruff/mypy clean (`Success: no issues found in 325 source files`); `4519 passed, 12 skipped in 1048.41s (0:17:28)`;
  vitest `Test Files  130 passed (130)`, `Tests  818 passed (818)`; frontend build
  `✓ built in 287ms`.
- No third-party API used (internal only).

## 2026-11-03 — TASK-183 T58d.4 Human-only approval enforcement

- Approval Inbox API (`autopilot/inbox.py`, `api/drafts.py`, also `/api/v1` and MCP): list/get/create drafts and review notes (migration 037 `draft.notes`) for agents; approve (queue to the autopilot's accounts in the next free slot), reject and approve-all are human-only: route-level `require_human` -> 403 `human_only` for any API key, on `/api` and `/api/v1`, and no MCP tool. Campaign bulk-schedule with `queue=true` now checks `require_human` first.
- Tests: `uv run pytest backend/tests/autopilot -q` -> `69 passed`; `tests/api/test_approval_auth.py`, `tests/api/test_drafts_api.py` (`7 passed`), `tests/api/v1/test_mcp_tools.py` + `test_contract.py` passed.
- `make check` (exit 0): ruff/mypy clean (`Success: no issues found in 327 source files`); `4574 passed, 12 skipped in 1133.54s (0:18:53)`;
  vitest `Test Files  130 passed (130)`, `Tests  818 passed (818)`; frontend build
  `✓ built in 1.07s`.
- No third-party API used (internal only).

## 2026-11-03 — TASK-184 T58e.1 Approval Inbox UI + keyboard (A/R/E/J/K) + approve-all confirm

- Approval inbox page `/inbox`: draft cards (autoplay preview, copy, campaign + rate, score, rule results, source + freshness, notes), Approve / Edit (editor with a back arrow to the inbox) / Reject with reason chips, Needs fix tab, campaign filter, approve-all with a confirm; keys A/R/E/J/K/Esc.
- Tests: `npx vitest run src/lib/drafts.test.ts src/lib/editorBack.test.ts src/pages/ApprovalInbox.test.tsx src/routes.test.tsx` pass; e2e `npx playwright test -c e2e/playwright.config.ts e2e/inbox.spec.ts` -> `1 passed`.
- `make check` (exit 0): ruff/mypy clean (`Success: no issues found in 327 source files`); `4574 passed, 12 skipped in 1133.42s (0:18:53)`;
  vitest `Test Files  133 passed (133)`, `Tests  842 passed (842)`; frontend build
  `✓ built in 250ms`.
- No third-party API used (internal only).

## 2026-11-03 — TASK-186 T58e.3 Ready-to-submit list + daily digest notification

- "Ready to submit" page `/submit`; daily `digest` notification (`autopilot/digest.py`, `digest_time` setting, migration 038 `submission.answered_at`).
- Tests: `uv run pytest backend/tests/autopilot/test_digest.py -q` -> 8 passed; `npx vitest run src/pages/ReadyToSubmit.test.tsx src/routes.test.tsx` pass; e2e `npx playwright test -c e2e/playwright.config.ts e2e/ready-to-submit.spec.ts` -> `1 passed`.
- `make check` (exit 0, second run; the first failed only on `test_migration_v2_submissions.py` comparing columns with the newer `answered_at`, fixed): ruff `All checks passed!`; mypy `Success: no issues found in 328 source files`; `4586 passed, 12 skipped in 1099.18s (0:18:19)`;
  vitest `Test Files  134 passed (134)`, `Tests  849 passed (849)`; frontend build
  `✓ built in 246ms`.
- No third-party API used (internal only).


## 2026-11-03 — TASK-187 T58.1 E2E flow 1: v1 full flow still passes on v2

- The v1 flow `e2e/flow.spec.ts` runs unmodified on v2: `npx playwright test -c e2e e2e/flow.spec.ts` -> `✓ 1 [chromium] › e2e/flow.spec.ts:86:1 › upload, get clips, edit one, render it and download the mp4 (25.5s)` / `1 passed (31.3s)`.
- Screenshot `.agent/screenshots/TASK-187-1.png`.
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 328 source files`; `4586 passed, 12 skipped in 1135.04s (0:18:55)`;
  vitest `Test Files  134 passed (134)`, `Tests  849 passed (849)`; frontend build `✓ built in 240ms`.
- No third-party API used (internal only).

## 2026-11-03 — TASK-191 T58.5 E2E autopilot: upload -> drafts -> approve 2, reject 1 -> 2 scheduled -> API key approve 403

- `npx playwright test -c e2e e2e/v2-autopilot.spec.ts e2e/inbox.spec.ts` -> `✓ 1 [chromium] › e2e/inbox.spec.ts:50:1 › approve, reject and fix the autopilot's drafts in the Approval inbox (25.8s)` / `✓ 2 [chromium] › e2e/v2-autopilot.spec.ts:85:1 › a new upload becomes drafts; the owner approves 2 and rejects 1, an API key gets 403 (18.7s)` / `2 passed (51.7s)`.
- `uv run pytest backend/tests/api/test_testmode_routes.py backend/tests/api/test_testapp.py -q` -> `11 passed`.
- Screenshots `.agent/screenshots/TASK-191-1.png` (3 drafts), `-2.png` (inbox empty, toasts), `-3.png` (2 posts in the calendar).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 329 source files`; `4590 passed, 12 skipped in 1148.42s (0:19:08)`;
  vitest `Test Files  134 passed (134)`, `Tests  849 passed (849)`; frontend build `✓ built in 248ms`.

## 2026-11-03 — TASK-192 T58.6 E2E campaign: create -> fresh upload -> preset clips -> rule check -> schedule -> submitted -> payout -> dashboard

- `npx playwright test -c e2e v2-campaign.spec.ts` -> `✓  1 [chromium] › e2e/v2-campaign.spec.ts:80:1 › campaign: create, fresh upload, preset clips, rules, schedule, submit, payout, earnings (21.9s)` / `1 passed (28.1s)`.
- `uv run pytest backend/tests/api/test_testmode_routes.py -q` -> `6 passed`; `npx vitest run src/lib/earnings.test.ts src/components/SubmissionTracker.test.tsx src/pages/Campaigns.test.tsx` -> `Tests  13 passed (13)`.
- Screenshots `.agent/screenshots/TASK-192-1.png` (campaign saved), `-2.png` (fresh-upload project with the campaign), `-3.png` (Rules panel: all pass), `-4.png` (submission approved, Earnings $30.86 / $30.00).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 329 source files`; `4592 passed, 12 skipped in 1073.49s (0:17:53)`;
  vitest `Test Files  135 passed (135)`, `Tests  854 passed (854)`; frontend build `✓ built in 255ms`.
- No third-party service API used (internal only).


## 2026-11-03 — TASK-193 T58.7 README v2 (engines setup, platform developer-app setup)

- `uv run pytest backend/tests/unit/test_readme_setup.py backend/tests/unit/test_engines.py -q` -> `20 passed, 6 skipped in 2.82s` (the skips are engines not installed here).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 329 source files`; `4598 passed, 12 skipped in 1077.52s (0:17:57)`;
  vitest `Test Files  135 passed (135)`, `Tests  854 passed (854)`; frontend build `✓ built in 257ms`.
- Official doc links were fetched 2026-11-03 (all HTTP 200); see decisions.md. No screenshot (documentation task).

## 2026-11-03 — TASK-194 T58.8 parity.md complete + final make check

- `uv run python scripts/check_parity.py` -> `docs/parity.md covers every bullet of SPEC-v2 section 3`; `uv run pytest backend/tests/unit/test_check_parity.py -q` -> `5 passed in 0.02s`.
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 330 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4603 passed, 12 skipped in 1070.45s (0:17:50)`;
  vitest `Test Files  135 passed (135)`, `Tests  854 passed (854)`; frontend build `✓ built in 253ms`.
- `make check-engines` (exit 0): `================ 9 passed, 7 skipped, 4599 deselected in 10.04s ================` (skips: ollama server, demucs, mflux, realesrgan, coqui-tts, sentence-transformers not installed).
- No third-party service API used (docs and a stdlib script only).

## 2026-11-03 — TASK-201 V3-01 Migrations: clip variants, Pro Edit tables, audio asset fields, campaign/autopilot flags

- `uv run pytest backend/tests/unit/test_migrations_v3.py backend/tests/unit/test_db.py backend/tests/unit/test_models.py backend/tests/unit/test_migrations.py -q` -> all passed (10 new migration tests).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 333 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4628 passed, 12 skipped in 1095.93s (0:18:15)`;
  vitest `Test Files  135 passed (135)`, `Tests  858 passed (858)`; frontend build `✓ built in 265ms`.
- No third-party service API used (internal schema only). No screenshot (database task).

## 2026-11-04 — TASK-203 V3-03a EDL schema + validation

- `uv run pytest backend/tests/unit/test_edl_schema.py backend/tests/pipeline/test_proedit_isolation.py -q` -> `all passed` (68 new EDL tests; the golden isolation test stays green).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 341 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4726 passed, 12 skipped in 1088.18s (0:18:08)`;
  vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 340ms`.
- No third-party service API used (Pydantic models only). No screenshot (backend task).

## 2026-11-04 — TASK-204 V3-03b EDL snapping + intensity budgets

- `uv run pytest backend/tests/unit/test_edl_snap_budget.py backend/tests/unit/test_edl_budgets.py backend/tests/unit/test_edl_schema.py backend/tests/pipeline/test_proedit_isolation.py -q` -> `116 passed in 13.47s` (47 new snapping/budget tests; the golden isolation test stays green).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 344 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4773 passed, 12 skipped in 1111.73s (0:18:31)`
  vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 254ms`.
- No third-party service API used (stdlib + Pydantic only). No screenshot (backend task).

## 2026-11-04 — TASK-205 V3-04a Signals adapter (reuse v1/v2 analysis)

- `uv run pytest backend/tests/unit/test_proedit_signals.py backend/tests/pipeline/test_proedit_isolation.py -q` -> all passed (10 new signals tests; the golden isolation test stays green inside `make check`).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 348 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4783 passed, 12 skipped in 1055.24s (0:17:35)`;
  vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 247ms`.
- No third-party service API used beyond the existing pipeline modules. No screenshot (backend task).

## 2026-11-04 — TASK-206 V3-04b Music beat grid + shared feature extractors

- `uv run pytest backend/tests/unit/test_features_basic.py -q` -> `17 passed in 6.86s` (beats/BPM/downbeats/drops of 120 and 150 BPM click tracks, cuts, zoom ramp/punches, shake, B&W, flashes on ffmpeg fixtures; stable over 3 runs).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 355 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4800 passed, 12 skipped in 1219.78s (0:20:19)`;
  vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 264ms`.
- librosa 0.11.0 / OpenCV 5.0.0 / ffmpeg 9.0.2 APIs verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-04 — TASK-207 V3-05a Renderer core (EDL -> filter graph, grade/vignette/grain/B&W, proxy + final)

- `uv run pytest backend/tests/unit/test_proedit_render_graph.py backend/tests/pipeline/test_proedit_render_core.py -q` -> `21 passed` and `8 passed in 4.26s` (exact B&W frames, dark/desat/vignette/grain measured on frames, identical frame hashes twice, ffprobe 540x960/1080x1920 h264 yuv420p + aac ±0.2 s, cut/final test with libx264 and h264_videotoolbox).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 361 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4829 passed, 12 skipped in 1148.56s (0:19:08)` (golden isolation test green);
  vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 254ms`.
- ffmpeg 9.0.2 filters `hue`, `eq`, `vignette`, `noise` verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-04 — TASK-208 V3-05b Renderer core (freeze, flash, LUT looks, normalize, skin protection)

- `uv run pytest backend/tests/unit/test_proedit_luts.py backend/tests/unit/test_proedit_render_graph.py backend/tests/pipeline/test_proedit_render_fx_basic.py backend/tests/pipeline/test_proedit_render_core.py backend/tests/unit/test_edl_schema.py -q` -> `119 passed in 12.42s` (freeze frames 30-44 bit-identical in a lossless render, flash peak on frame 60 / black dip on frame 90, teal_orange colors within 5 levels of `LOOKS`, protected skin within the cap, normalize stretches levels and evens channels).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 364 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4851 passed, 12 skipped in 1177.96s (0:19:37)`; vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 256ms`.
- ffmpeg 9.0.2 filters `freezeframes`, `normalize`, `lut3d`, `eq` (eval=frame), `huesaturation`, `colorbalance`, `colortemperature` verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-04 — TASK-209 V3-06a Renderer motion (zoom punch/push/out-reveal, pan, eased keyframes, face-safe crop)

- `uv run pytest backend/tests/unit/test_proedit_motion.py backend/tests/unit/test_proedit_face_path.py backend/tests/unit/test_proedit_render_graph.py backend/tests/pipeline/test_proedit_render_motion.py backend/tests/pipeline/test_proedit_render_core.py backend/tests/pipeline/test_proedit_render_fx_basic.py backend/tests/pipeline/test_proedit_isolation.py -q` -> all passed (render-measured zoom scale of all 120 frames within 0.22 % of plan, tolerance 3 %; the red face box whole inside every zoomed frame, ≥ 8 px from the edges; 40 randomized face-inside checks; golden isolation test green).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 368 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4924 passed, 12 skipped in 1155.99s (0:19:15)`; vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 245ms`.
- ffmpeg 9.0.2 `scale` (eval=frame) and `crop` verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-04 — TASK-210 V3-06b Renderer motion (shake, speed ramp, slow-mo)

- `uv run pytest backend/tests/unit/test_proedit_motion_time.py backend/tests/unit/test_proedit_face_path.py backend/tests/unit/test_proedit_render_graph.py backend/tests/unit/test_proedit_motion.py -q` -> `109 passed`; `uv run pytest backend/tests/pipeline/test_proedit_render_speed.py backend/tests/pipeline/test_proedit_render_motion.py backend/tests/pipeline/test_proedit_render_core.py backend/tests/pipeline/test_proedit_render_fx_basic.py backend/tests/unit -k proedit -q` -> all passed (slow-mo window within ±1 frame at speed 0.5±0.05, ramp content positions within POSITION_FRAMES, frames outside the windows in sync, flash vs beep < 40 ms, shake spans found by the affine extractor in each window only).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 369 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4942 passed, 12 skipped in 1160.69s (0:19:20)`; vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 251ms`.
- ffmpeg 9.0.2 `setpts`, `settb`, `trim`, `minterpolate`, `tpad`, `overlay`, `atempo` verified locally (docs/decisions.md). No screenshot (backend task).


## 2026-11-05 — TASK-211 V3-07a Renderer FX (glitch, RGB split, transitions)

- `uv run pytest backend/tests/pipeline/test_proedit_render_*.py backend/tests/pipeline/test_transitions.py backend/tests/unit/test_proedit_fx_glitch.py backend/tests/unit/test_proedit_render_graph.py backend/tests/pipeline/test_proedit_isolation.py -q` -> `114 passed in 44.25s` (frames changed vs a clean render == the items' windows exactly, 120 frames; RGB split found red (8,0)/blue (-8,0) and (0,-6)/(0,6) in its windows only; glitch frames/stutter match `glitch_window`; crossfade progress 0 -> 0.5 at the cut -> 1; flash white before the cut; zoom inside its window).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 373 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `4990 passed, 12 skipped in 1186.74s (0:19:46)` (golden isolation test green); vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 262ms`.
- ffmpeg 9.0.2 `rgbashift`, `geq`, `shuffleframes`, `xfade` (fade/hblur/zoomin/fadewhite/pixelize), `tpad`, `overlay` verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-05 — TASK-212 V3-07b Overlays (procedural skull/skeleton, emoji/arrow/circle, screen/face/object anchored)

- `uv run pytest tests/unit -k proedit tests/pipeline/test_proedit_render_core.py tests/pipeline/test_proedit_render_motion.py tests/pipeline/test_proedit_overlays.py tests/pipeline/test_proedit_isolation.py -q` (backend/, ffmpeg-full PATH) -> `239 passed, 1928 deselected in 35.64s`.
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 377 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `5044 passed, 12 skipped in 1179.69s (0:19:39)`; vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 258ms`.
- ffmpeg 9.0.2 `movie` (f=image2), `settb`, `setpts`, `overlay` (eof_action/repeatlast/enable), `format` (color_ranges) and Pillow 13.0.0 drawing/text verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-05 — TASK-213 V3-08 Kinetic captions (pop/bounce/shake/glow/single-word, emoji pops)

- `uv run pytest backend/tests/unit/test_kinetic_captions.py backend/tests/pipeline/test_proedit_kinetic_render.py backend/tests/pipeline/test_proedit_isolation.py backend/tests/pipeline/test_caption_animation.py backend/tests/pipeline/test_caption_styles.py backend/tests/pipeline/test_render_captions.py backend/tests/unit/test_captions.py backend/tests/unit/test_captions_format.py backend/tests/unit/test_caption_style.py backend/tests/unit/test_caption_layout.py backend/tests/test_caption_templates_v2.py -q` (ffmpeg-full PATH) -> `217 passed in 46.42s` (existing templates' ASS digest unchanged; only the active word has \t/glow/shake tags; loud word found by RMS shakes; libass frames: pop 70 % -> overshoot -> settled, neon halo around the word, emoji pop).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 381 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `5070 passed, 12 skipped in 1117.78s (0:18:37)` (golden isolation test green); vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 251ms`.
- libass `\t`, `\frz`, `\3c`/`\bord`/`\blur` and `\alpha` verified by test renders (docs/decisions.md). No screenshot (backend task).

## 2026-11-05 — TASK-214 V3-09a Audio: SFX placement engine + whoosh matching

- `PATH=/opt/homebrew/opt/ffmpeg-full/bin:$PATH uv run pytest backend/tests/unit/test_proedit_*.py backend/tests/pipeline/test_proedit_*.py backend/tests/unit/test_sfx*.py backend/tests/pipeline/test_sfx*.py -q` -> `460 passed, 2 failed` then, after updating the graph test for `[pro_a]` and the speech assertion, `38 passed in 8.30s` for the two fixed files (RMS onset of every planned SFX within +-1 frame; stretched whoosh = item length +-20 ms with rubberband, +-50 ms with atempo; 6 dB duck under speech; placed whooshes silent (< -70 dB) on the punchline word).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 385 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `5139 passed, 12 skipped in 1207.13s (0:20:07)` (golden isolation test green); vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 243ms`.
- ffmpeg 9.0.2 `atempo`, `asetrate`, `apad`, `adelay`, `amovie`, `amix`, `rubberband` verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-05 — TASK-215 V3-09b Audio: music bed + ducking, riser, silence-before-drop, bass drop, audio fx

- `cd backend && uv run pytest tests/pipeline/test_music_bed.py tests/pipeline/test_sfx_render.py tests/unit/test_music_bed_fx.py tests/unit/test_sfx_mix.py tests/unit/test_proedit_render_graph.py tests/unit/test_edl_*.py -q` -> `9 passed in 6.93s` (music bed pipeline: 12.0/6.0 dB dip under speech +-1 dB, silence frames < -60 dB before the drop, drop onset at the plan +-1 frame with a > 3 dB spike, music continuous across the silence, bass boost/reverb tail/lowpass sweep/stutter only in their window), `160 passed in 4.01s` (sfx render, sfx mix, render graph, EDL), `15 passed in 0.05s` (new unit tests).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 390 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `5163 passed, 12 skipped in 1193.43s (0:19:53)` (golden isolation test green); vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 341ms`.
- ffmpeg 9.0.2 `amovie` loop, `aloop`, `aecho`, `bass`, `lowpass`, `asendcmd`, `aeval`, `aformat`, `volume` eval verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-05 — TASK-216 V3-09c Audio: dialogue EQ/compression/de-ess + final loudness -14 LUFS, true peak <= -1 dBTP

- `uv run pytest backend/tests/pipeline/test_proedit_mix.py backend/tests/unit/test_music_bed_fx.py backend/tests/unit/test_proedit_render_graph.py backend/tests/pipeline/test_music_bed.py backend/tests/pipeline/test_sfx_render.py backend/tests/pipeline/test_proedit_render_core.py -q` -> `79 passed in 27.92s` (rendered sources of 0.02/0.2/0.95 amplitude, a peaky source and a source with a music bed all measure -14.0 +-0.1 LUFS integrated, true peak <= -2 dBTP; dialogue chain gains measured on sines).
- `make check` (exit 0): ruff `All checks passed!`; mypy `Success: no issues found in 390 source files`; parity `docs/parity.md covers every bullet of SPEC-v2 section 3`; pytest `5175 passed, 12 skipped in 1196.96s (0:19:56)` (golden isolation test green); vitest `Test Files  136 passed (136)`, `Tests  865 passed (865)`; frontend build `✓ built in 254ms`.
- ffmpeg 9.0.2 `highpass`, `equalizer`, `acompressor`, `deesser`, `loudnorm` verified locally (docs/decisions.md). No screenshot (backend task).

## 2026-11-05 — TASK-217 V3-10 Licensed audio library: Freesound integration + license filter + attribution

Added `proedit/audio/{licenses,freesound,credits}.py` and `api/proedit_audio.py` (status, search, download, clip credits). Only CC0 and CC BY are accepted (checked in the query filter and again on every returned sound); CC BY credits are appended to the clip description. Tests use recorded-shape fixtures, no network.

```
$ uv run pytest backend/tests/unit/test_freesound.py backend/tests/api/test_proedit_audio_api.py -q
61 passed (unit) + 11 passed (api)
$ uv run python scripts/gen_types.py --check
exit 0
$ make check
All checks passed!
Success: no issues found in 394 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5247 passed, 12 skipped in 1236.11s (0:20:36) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 245ms
exit 0
```

## TASK-218 V3-11 Pixabay audio import, own uploads with rights, auto-tagging, starter pack (2026-11-06)

Verification (real output):

```
$ make check
All checks passed!
Success: no issues found in 401 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5308 passed, 12 skipped in 1123.63s (0:18:43) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 246ms
exit 0
$ uv run python scripts/gen_types.py --check   # exit 0
$ uv run python scripts/fetch_starter_sfx.py   # no key: prints "Add a Freesound key..." , exit 1
```

## TASK-219 V3-12a Presets x6 (YAML) + rule-based director (2026-11-06)

Six YAML presets (`proedit/presets/`, loaded by `preset_defs.py`) and the offline rule-based Director (`director_rules.rule_plan` + `director_{build,moves,skull,moments,music}.py`). Valid, in-budget plans for every preset x intensity, with and without a bed; the Skull Moment sequence (freeze, B&W, skull on face, punch, shake, impact + bass drop, 1-2 s hold, snap-back whoosh) at Extreme.

```
$ uv run pytest backend/tests/unit/test_rule_director.py backend/tests/unit/test_preset_defs.py -q
72 passed
$ make check
All checks passed!
Success: no issues found in 408 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5383 passed, 12 skipped in 1195.38s (0:19:55) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 242ms
exit 0
```

## TASK-220 V3-12b Phonk Edit / Pro style-trait acceptance test (2026-11-06)

`backend/tests/pipeline/test_phonk_traits.py` renders the fixture clip at Phonk Edit / Pro (rule-based Director, generated 140 BPM bed, proxy libx264) and measures it with `proedit/features`. All five SPEC-v3 2.1 traits hold. To get there, presets gained `beat_lengths` (Phonk punches/shakes snap back on the next beat), and beat rules count their phase from the first downbeat.

```
$ PATH=/opt/homebrew/opt/ffmpeg-full/bin:$PATH uv run pytest backend/tests/pipeline/test_phonk_traits.py -q -s
Phonk Edit / Pro traits: Traits(mean_interval_s=0.8, punches_per_3_s=1.3333, on_beat_share=1.0, flashes_or_shakes_per_5_s=1.1111, output_luma=0.258, source_luma=0.4967)
5 passed in 12.39s
$ uv run pytest backend/tests/unit -q -k "director or preset or budget or snap or edl"
350 passed, 2089 deselected in 2.36s
$ make check
All checks passed!
Success: no issues found in 408 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5392 passed, 12 skipped in 1216.23s (0:20:16) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 244ms
exit 0
```

## TASK-221 V3-13 LLM Director: prompt, schema, retries, post-processing, cost estimate + usage meter (2026-11-06)

`proedit/director_llm.director_plan` asks the LLM for a plan (`director_prompt.py` messages, `prompts/proedit_director.md`), validates it (Pydantic, preset kinds, `plan_problems`, asset catalog), retries twice with the problems, post-processes it and falls back to the rule-based plan with a reason. `director_cost.py` gives the estimate shown before a run and the Pro Edit monthly cap (`ProEditCapExceeded`); calls are metered as usage kind `proedit` with `cost_usd` (tokens x `proedit.usd_per_million_tokens`).

```
$ PATH=/opt/homebrew/opt/ffmpeg-full/bin:$PATH uv run pytest backend/tests/unit/test_llm_director.py backend/tests/unit/test_director_cost.py -q
.............                                                            [100%]
13 passed in 0.40s
$ make check
All checks passed!
Success: no issues found in 412 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5405 passed, 12 skipped in 1202.44s (0:20:02) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 242ms
exit 0
```

## TASK-222 V3-14a Critic: capability check, frame/audio sampling, scoring (2026-11-07)

`proedit/critic/`: `capability.check_vision` probes the configured model once with a red PNG (refused or not seen -> "Pro Edit runs the Director only (no critic)."); `vision.complete_with_images` sends images per provider (OpenAI-compat, Copilot with `Copilot-Vision-Request`, Anthropic, Ollama); `sample.sample_frames` picks each EDL item's first/last frame + a 1 fps baseline under `proedit.critic_max_frames` and `extract_frames` reads them in one ffmpeg pass; `audio_summary.summarize_audio` gives LUFS/true peak, clipping, a 0.5 s loudness curve and speech/music/SFX levels; `score.critique` asks for the 9-point checklist (`prompts/proedit_critic.md`), validates, retries, caps and meters the calls as `proedit`.

```
$ PATH=/opt/homebrew/opt/ffmpeg-full/bin:$PATH uv run pytest backend/tests/unit/test_critic_score.py backend/tests/unit/test_critic_vision.py backend/tests/unit/test_critic_sample.py backend/tests/pipeline/test_critic_media.py ... -q
86 passed, 3 skipped in 11.48s
$ make check
All checks passed!
Success: no issues found in 419 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5444 passed, 12 skipped in 1208.57s (0:20:08) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 238ms
exit 0
```

## TASK-223 V3-14b Critic revisions loop: EDL changes, rounds, early stop, cost cap (2026-11-07)

`proedit/critic/`: the critic's reply carries EDL changes (`changes.py`: add / remove / modify by item id); `apply.revise_plan` applies them one at a time with the plan's validation (unknown id, user item, kind not in the preset, new overlaps/params/clip-end problems, unknown asset -> ignored with the reason), post-processes the revision like the Director's and stores "what changed" on the round; `revise.critic_loop` runs at most `proedit.critic_max_rounds` (2, 0..3) rounds, stops early when every score reaches `critic_threshold`, and stops when the monthly cap blocks the next round.

```
$ uv run pytest backend/tests/unit/test_critic_loop.py backend/tests/unit/test_critic_score.py backend/tests/unit/test_critic_vision.py backend/tests/unit/test_critic_sample.py backend/tests/unit/test_llm_director.py backend/tests/unit/test_director_cost.py backend/tests/unit/test_migrations_v3.py backend/tests/proedit -q
77 passed in 4.28s
$ make check
All checks passed!
Success: no issues found in 422 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5459 passed, 12 skipped in 1206.68s (0:20:06) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 295ms
exit 0
```

## TASK-224 V3-15 Pro Edit API + jobs + progress/ETA integration (2026-11-07)

Pro Edit runs end to end: `POST /proedit/clips/{id}/runs` makes a new variant clip (`parent_clip_id`, `variant: pro_edit`) and queues a `proedit` job (plan -> proxy -> critic rounds -> final, on the shared progress/ETA); on a variant the runs, plan versions, PATCH plan (changed items become manual), reset to v1, regenerate, critic and render; `GET .../estimate` prices a run without calling the LLM. The renderer now draws kinetic captions. Agents may use it all via `/api/v1` + MCP; posting stays human-only.

```
$ uv run pytest tests/api/test_proedit_api.py -q
18 passed in 8.07s
$ uv run pytest tests/api/test_proedit_job_api.py -q
5 passed in 7.38s
$ make check
All checks passed!
Success: no issues found in 429 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5537 passed, 12 skipped in 1268.66s (0:21:08) =================
 Test Files  136 passed (136)
      Tests  865 passed (865)
✓ built in 264ms
EXIT 0
```

## TASK-225 V3-16 Pro Edit dialog + progress view + gallery/inbox variant cards (2026-11-08)

The Pro Edit dialog opens from the editor top bar, every gallery card and the inbox: preset cards with looping previews, intensity (capped by the campaign), caption recipe, music, the critic toggle with a live cost estimate and a warning when the campaign does not allow (or does not say) heavy edits. Run turns it into a progress view (Plan, Proxy, Critic round n/N, Final render). Variants sit right after their original in the gallery with a Pro Edit badge and a link to the original; the inbox shows a draft's variants with Approve Pro Edit / Approve both. Backend: `GET /proedit/clips/{id}/choices`.

```
$ uv run pytest backend/tests/api/test_proedit_choices_api.py -q
4 passed
$ npx playwright test -c e2e proedit-dialog proedit-entry
  2 passed (1.1m)
$ make check
All checks passed!
Success: no issues found in 430 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5545 passed, 12 skipped in 1275.13s (0:21:15) =================
 Test Files  139 passed (139)
      Tests  884 passed (884)
✓ built in 248ms
EXIT=0
```


## TASK-226 V3-17a Pro Edit editor: side-by-side preview + EDL lanes (2026-11-08)

`/clips/{original}/proedit` is now the Pro Edit editor: the original (muted) and the Pro Edit video side by side, played and sought together, and the plan's items on 8 EDL lanes under a ruler with the plan's beats. Items move/trim by drag or arrow keys, snapping to word starts, beats, other items' edges and the playhead, then to frames; a dashed guide and "Snaps to …" show what they snap to; a drop PATCHes the next plan version, and "Render plan vN" renders it.

```
$ uv run pytest backend/tests/api/test_proedit_editor_api.py -q
4 passed
$ npx vitest run src/features/proedit
 Test Files  7 passed (7)
      Tests  43 passed (43)
$ npx playwright test -c e2e proedit-editor proedit-entry
  ✓  1 [chromium] › e2e/proedit-editor.spec.ts:58:1 › edit a Pro Edit variant's plan on its EDL lanes (40.8s)
  ✓  2 [chromium] › e2e/proedit-entry.spec.ts:25:1 › the editor opens a clip's Pro Edit dialog, which links to its page (17.3s)
  2 passed (1.1m)
$ make check
All checks passed!
Success: no issues found in 432 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5549 passed, 12 skipped in 1279.74s (0:21:19) =================
 Test Files  141 passed (141)
      Tests  903 passed (903)
✓ built in 268ms
EXIT 0
```


## TASK-227 V3-17b Pro Edit editor: inspector, regenerate/critic/reset, plan versions (2026-11-08)

Under the EDL lanes the editor now has "Regenerate with Director", "Run critic again" and "Reset to plan v1", an inspector with a form per selected item's params (Apply stores the next plan version), the plan version history with the diff of a chosen version, and the critic's scores per round with "what changed". Frontend only; the endpoints came with TASK-224.

```
$ npx vitest run src/features/proedit
 Test Files  10 passed (10)
      Tests  64 passed (64)
$ npx playwright test -c e2e proedit-plan-tools proedit-editor
  ✓  1 [chromium] › e2e/proedit-editor.spec.ts:24:1 › edit a Pro Edit variant's plan on its EDL lanes (41.4s)
  ✓  2 [chromium] › e2e/proedit-plan-tools.spec.ts:24:1 › inspect an item, read the plan versions and critic, reset to v1 (38.3s)
  2 passed (1.4m)
$ make check
All checks passed!
Success: no issues found in 432 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5549 passed, 12 skipped in 1212.84s (0:20:12) =================
 Test Files  145 passed (145)
      Tests  924 passed (924)
✓ built in 239ms
EXIT 0
```

## TASK-228 V3-18a Style learning: links, limits, rights confirm, download + guaranteed delete (2026-11-08)

A style recipe is made from 1-5 links and a rights confirmation (none -> 422); analyzing downloads each link with the ingest yt-dlp module (<= 3 min, <= 720p) into `data/work/style_<reference id>/`, measures its features and deletes the media in a `finally` block (tests assert the directory is gone after a success, a failed download, a refused video and an analyzer exception). Backend only.

```
$ uv run pytest tests/unit/test_style_fetch.py tests/api/test_proedit_style_api.py -q
28 passed
$ make check
All checks passed!
Success: no issues found in 436 source files
docs/parity.md covers every bullet of SPEC-v2 section 3
================ 5577 passed, 12 skipped in 1293.37s (0:21:33) =================
 Test Files  145 passed (145)
      Tests  924 passed (924)
✓ built in 252ms
EXIT 0
```

## TASK-229 V3-18b Style learning: cut/motion/color/flash features on references (2026-11-08)

- `proedit/style/analyze_video.py` (rhythm vs the reference's own beats, zoom/shake summaries, vignette/grain, glitches), shared extractors `proedit/features/look.py` and `features/spikes.py`, `measure_video(on_frame=)`; `store.measure_features` stores it per reference.
- Affected tests: `uv run pytest tests/unit/test_style_video_features.py tests/unit/test_features_basic.py tests/api/test_proedit_style_api.py tests/pipeline/test_phonk_traits.py -q` -> `47 passed in 43.85s`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 439 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5593 passed, 12 skipped in 1308.83s (0:21:48)`; `Test Files  145 passed (145)`, `Tests  924 passed (924)`; `built in 312ms`.

## TASK-230 V3-19a Style learning: caption OCR + audio/structure features (2026-11-08)

- `proedit/features/glyphs.py` + `features/ocr.py` (Tesseract 5.5.4 TSV), `proedit/style/analyze_captions.py`, `analyze_audio.py` (YAMNet speech/music, BPM, drops, silence before drop, SFX onsets off the beat grid, loudness curve), `analyze_structure.py` (first effect, hook, 5 s density, loop/hard-cut ending), `analyze.py`; `store.measure_features` stores them.
- Affected tests: `uv run pytest tests/unit/test_style_caption_audio.py tests/unit/test_style_video_features.py tests/api/test_proedit_style_api.py -q` -> `38 passed` (13 new).
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 445 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5606 passed, 12 skipped in 1336.75s (0:22:16)`; `Test Files  145 passed (145)`, `Tests  924 passed (924)`; `built in 259ms`.

## STEERING fix(proedit): original preview in the Pro Edit editor (TASK-226) (2026-11-08)

- `ComparePreview` original `<video>` (`previewUrl` -> `GET /clips/{id}/preview`, rendered on first request) now preloads, shows `PreviewStatus` until `loadeddata`, and follows the Pro Edit via `useSyncedPair` (late load / drift > 0.25 s re-seeks).
- Affected tests: `npx vitest run src/features/proedit/ComparePreview.test.tsx` -> `5 passed`; `npx playwright test -c e2e/playwright.config.ts proedit-editor.spec.ts` -> `1 passed (45.9s)`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 445 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5606 passed, 12 skipped in 1329.63s (0:22:09)`; `Test Files  146 passed (146)`, `Tests  929 passed (929)`; `built in 250ms`.

## TASK-231 V3-19b Recipe aggregation, style-match score, recipe editor/import/export (2026-11-08)

- Backend: `proedit/style/metrics.py` (28 metrics + readers), `recipe.py` (aggregate, describe via LLM/rules, `style_match` score, export), `match.py` (measure/cache a variant's match), `store.refresh_targets/update_recipe/import_recipe`; API `GET /proedit/style-recipes/metrics`, `PATCH .../{id}`, `GET .../{id}/export`, `POST .../import`, `GET|POST /proedit/clips/{id}/style-match`; Director reads the target summary.
- Frontend: `/proedit/style-recipes` (`StyleRecipes.tsx`, `StyleRecipeForm.tsx`, `RecipeEditor.tsx`, `RecipeTargets.tsx`), `StyleMatchPanel.tsx` in `PlanTools`, "Manage style recipes" link in the Pro Edit dialog.
- Affected tests: `uv run pytest backend/tests/unit/test_style_recipe.py backend/tests/api/test_proedit_style_recipe_api.py backend/tests/api/test_proedit_style_api.py backend/tests/unit/test_llm_director.py -q` -> `41 passed in 19.76s`; `npx vitest run src/features/proedit/` -> `Test Files  14 passed (14)`, `Tests  82 passed (82)`; `npx playwright test -c e2e proedit-style-recipes` -> `1 passed (8.3s)`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 449 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5632 passed, 12 skipped in 1331.26s (0:22:11)`; `Test Files  149 passed (149)`, `Tests  942 passed (942)`; `built in 244ms`.

## TASK-232 V3-20 Campaign/autopilot integration: Pro Edit variant switch, allow_heavy_edits, both variants in inbox (2026-11-09)

- Backend: `autopilot/proedit.py` (`wants_variants`, `variant_options`, `start_variants`) hooked into `pipeline.make_drafts`; variants only for new pending drafts when `proedit_enabled` and `allow_heavy_edits == "true"`, within usage caps. Approval stays human-only.
- Frontend: `CampaignProEdit.tsx` + `campaignApi.ts` on the Campaigns page.
- Affected tests: `uv run pytest backend/tests/unit/test_autopilot_proedit.py -q` -> `14 passed`; `npx vitest run src/features/proedit/CampaignProEdit.test.tsx src/lib/campaignForm.test.ts` -> all passed; `npx playwright test -c e2e proedit-campaign` -> `1 passed`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 450 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5646 passed, 12 skipped in 1265.76s (0:21:05)`; `Test Files  150 passed (150)`, `Tests  946 passed (946)`; `built in 246ms`.

## TASK-233 V3-21a Retention/pacing extras: pattern interrupts, J/L cuts, reaction holds, loop ending (2026-11-09)

- Backend: `proedit/pacing.py` (J/L audio cuts by intensity, reaction holds after punchlines), `proedit/retention.py` (pattern interrupt fill for rule and LLM plans, loop-friendly ending item), `proedit/render/loop_end.py` (loop blend + audio crossfade); `render_graph.cut_graph/clip_graph(audio_spans=...)`; `ProEditOptions/DirectorRequest.loop_ending`, recipe `loop_ending` median >= 0.5.
- Frontend: "Loop-friendly ending" switch in the Pro Edit dialog (`LoopField`), `loop` transition type in the param fields.
- Affected tests: `uv run pytest backend/tests/unit/test_retention.py backend/tests/unit/test_pacing.py backend/tests/pipeline/test_proedit_retention_render.py -q` -> `53 passed`; proedit pipeline/API + phonk traits -> `144 passed in 124.60s`; vitest proedit -> `85 passed`; `npx playwright test -c e2e proedit-loop-ending.spec.ts` -> `1 passed (49.2s)`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 453 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5699 passed, 12 skipped in 1382.18s (0:23:02)`; `Test Files  150 passed (150)`, `Tests  946 passed (946)`; `built in 267ms`.

## TASK-234 V3-21b Subject cut-out (segmentation): subject in front of text, background blur/swap (2026-11-09)

- Backend: `proedit/segment.py` (MediaPipe SelfieSegmenter, VIDEO mode, confidence masks; `segmenter_problem` install check, `download_segmenter`, `person_masker`, `write_masks` lossless FFV1 gray), `proedit/render/cutout_pass.py` (mask pre-pass over `graph.PRE_CUTOUT_STAGES`; `prepare_cutout` skips with `subject cut-out skipped: <reason>`), `proedit/render/cutout.py` (alphamerge subject layer, gblur/color background, subject redrawn after captions); `ProEditOptions.subject_front/background/background_color`; engine `segment` (`engine_segment` marker, README, `scripts/download_models.py`); `frame_stream.stream_raw`.
- Frontend: `CutoutField.tsx` ("Subject cut-out": "Subject in front of text", Background Keep/Blur/Swap for a color + color) in the Pro Edit dialog.
- Verification: `uv run pytest backend/tests/unit/test_segment.py backend/tests/pipeline/test_proedit_cutout_render.py -q` -> `17 passed`; engine/model/CLI/isolation tests -> `51 passed, 6 skipped`; `npx vitest run src/features/proedit` -> `85 passed (85)`; `npx playwright test -c e2e proedit-cutout` -> `1 passed (1.0m)`. Screenshots `.agent/screenshots/TASK-234-1.png`, `TASK-234-2.png`.
- `make check` (exit 0): `All checks passed!`; `Success: no issues found in 456 source files`; `docs/parity.md covers every bullet of SPEC-v2 section 3`; `5717 passed, 12 skipped in 1403.34s (0:23:23)`; `Test Files  150 passed (150)`, `Tests  946 passed (946)`; `built in 248ms`.
