# ClipForge v3 — "Pro Edit" — Specification

Companion documents: `.agent/prd/PRD-v3.md` (product), `.agent/prd/SUMMARY-v3.md` (loop summary). v1 rules (`SPEC.md`) and v2 rules (`SPEC-v2.md`) remain in force; this document adds to them.

Do not start any v3 task until every v1/v2 task in `.agent/tasks.json` passes and `make check` is green.

---

## 0. Rules

0.1 Never invent library APIs, CLI flags, ffmpeg filters/options, model names, endpoints, quotas or config keys. Verify each one by reading installed source / `help()` / `ffmpeg -h filter=<name>` or the provider's current official documentation, and record URL or command + date in `docs/decisions.md`.
0.2 Never invent package versions; uv/npm lockfiles pin them; record them in `docs/stack.md` (with license).
0.3 No stubs, placeholders, fake data, TODOs or hard-coded demo results in delivered code. If something cannot be built, leave it out and explain it in `docs/questions.md`.
0.4 A task is DONE only when its verification commands ran and passed in the same iteration; paste the real output tail into `docs/progress.md`.
0.5 Never weaken, skip or delete tests. Mock only external boundaries (LLM HTTP, Freesound/Pixabay HTTP, yt-dlp network, model downloads). Tests never call real external services.
0.6 Ambiguity: choose the simplest option consistent with this document, log it in `docs/decisions.md`, continue.
0.7 External blocker (missing key, model that will not install): log the exact error in `docs/questions.md`, mark the task BLOCKED, continue with the next independent task.
0.8 Stay inside the project directory. Never commit `.env*`, tokens, model weights, user media, downloaded audio, reference media or `data/`.
0.9 Schemas: single source of truth in `backend/clipforge/models.py`; regenerate frontend types (`scripts/gen_types.py`); DB changes only via new numbered migrations in `migrations/` (next free number after `038_…`).
0.10 Each iteration: read `docs/HANDOFF.md` first, then progress/decisions/task list; do ONE task; run `make check`; commit with the task id. Never push.
0.11 SELF-HANDOFF: before any compaction/reset, at the end of an iteration and after finishing or blocking a task, overwrite `docs/HANDOFF.md` (< 150 lines) with: Updated; Current task + status; Done so far; Next exact step; Last verification; Open problems; Gotchas learned; Do NOT.
0.12 Do not break v1/v2. All existing tests keep passing. Existing modules are reused, extended or wrapped, never removed, and their behavior in the normal pipeline never changes.
0.13 **Scope isolation (the most important v3 rule).**
- Pro Edit is a separate, opt-in feature. When Pro Edit is not invoked, the normal pipeline, its defaults, presets, renders and outputs are byte-for-byte unchanged.
- Pro Edit always creates a new variant clip `"<title> — Pro Edit"` linked by `Clip.parent_clip_id` and `Clip.variant = "pro_edit"`. The original clip and its files are never modified.
- Backend code lives in `backend/clipforge/proedit/` (API router `backend/clipforge/api/proedit.py`, tests in `backend/tests/proedit/`); frontend code in `frontend/src/features/proedit/` (a new folder; the rest of the app uses `pages/` and `components/`, which only receive small wiring changes such as a button or badge).
- Pro Edit may call existing modules (see 0.14) but must not change their default behavior. New parameters are keyword-only with defaults that reproduce the old output exactly.
- A golden regression test (TASK for V3-02) renders the v1 fixture through the normal pipeline and asserts identical ffprobe stream parameters, identical frame hashes at fixed timestamps and an identical audio RMS profile against a golden file captured before any v3 code change. Every later v3 task must keep it green.
- Feature flag `proedit.enabled` (config, default `true`) only controls UI availability. Nothing runs unless the user presses the button or turns on the per-campaign switch.

0.14 **Real module map** (prompt name → module in this repository). Reuse these; do not duplicate them.

| Prompt name | Real module(s) |
|---|---|
| auto_zoom | `pipeline/auto_zoom.py` |
| zoom_graph | `pipeline/zoom_graph.py`, `pipeline/zoom_transition.py` |
| sfx | `pipeline/sfx.py` (bundled pack, search, placement), `api/sfx.py` |
| music | `pipeline/music.py` (`music_filters`, `duck_filter`), `api/music.py` |
| transitions | `pipeline/transitions.py` |
| hooks | `pipeline/hooks.py`, `hook_theme.py` |
| motion_graphics | `pipeline/motion_graphics.py`, `pipeline/text_overlay.py` |
| caption_effects | `pipeline/caption_effects.py`, `caption_emphasis.py`, `caption_cues.py`, `captions.py` |
| render_graph / timeline_graph | `pipeline/render_graph.py`, `pipeline/timeline_graph.py`, `pipeline/render.py` |
| timeline | `timeline.py` (top level) + `pipeline/timeline_graph.py` |
| loudnorm | `pipeline/loudnorm.py`, `pipeline/loudness.py` |
| faces / tracking / object tracking | `pipeline/faces.py`, `face_cache.py`, `tracking.py`, `object_tracking.py`, `smoothing.py` |
| signals / audio events | `pipeline/signals.py`, `signal_merge.py`, `audio_events.py`, `audio_analysis.py`, `yamnet.py`, `level_events.py` |
| scene cuts | `pipeline/scene_cuts.py`, `frame_cuts.py`, `scenes.py` |
| motion energy | `pipeline/motion.py` |
| cleanup / dead air | `pipeline/cleanup.py`, `auto_cut.py` |
| stock / pixabay | `stock/pixabay.py`, `stock/base.py` (video/image stock; audio is new) |
| vlm engine | `engines/vlm_ollama.py` |
| yt-dlp module | `pipeline/download.py` (`download`, `probe`, `ytdlp_options`), `pipeline/ytdlp_session.py` |
| encoders | `encoders.py` (VideoToolbox detection) |
| usage meter | `usage.py` (`record`, `caps_of`), `models.UsageRecord` |
| LLM provider | `llm.py`, `llm_http.py`, `llm_anthropic.py`, `llm_claude_code.py`, `llm_replies.py` |
| autopilot / approval inbox / drafts | `autopilot/` (`pipeline.py`, `inbox.py`, `settings.py`, `safety.py`), `api/autopilot.py`, `api/drafts.py` |
| campaigns | `campaigns.py`, `campaign_rules.py`, `api/campaigns.py` |
| assets / media library | `assets.py`, `asset_rows.py`, `media_library.py`, `models.Asset` |
| jobs / progress / ETA | `jobs.py`, `job_progress.py`, `worker_pool.py`, `ffmpeg_progress.py` |
| clip variants | `clip_versions.py` (history of one clip; Pro Edit variants are separate clips) |

---

## 1. Legal and safety rules (mandatory)

1.1 Clean room: no scraping, crawling or reverse engineering of OpusClip or any other editor (SPEC-v2 1.1 still applies).
1.2 Audio sources are limited to (a) Freesound API sounds licensed CC0 or CC BY (attribution stored; CC BY-NC and Sampling+ rejected), (b) Pixabay audio — via the official API only if it verifiably serves music/SFX, otherwise a manual import of a file the user downloaded with source URL + license entered by the user, (c) the user's own uploads with a required rights field. Never download audio from YouTube, TikTok, Spotify, SoundCloud or any non-licensed source. Every audio asset stores `license`, `attribution`, `source_url`, `downloaded_at`.
1.3 Visual overlays (skull/skeleton, emoji, arrows, circles, glitch textures) are generated in code (SVG/vector/procedural), drawn by the user, or CC0 with the license stored. No meme images/GIFs from random sites. Emoji glyphs come from an open-licensed font already bundled or added with a LICENSES.md row.
1.4 Style learning downloads only the links the user pastes (max 5 per recipe, max 3 min each, max 720p) with the existing yt-dlp module into `data/work/style_<id>/`, analyzes locally, and deletes the media immediately after analysis (tests assert deletion). Only numeric/text recipe data is stored. Reference footage/audio is never used in output. The UI shows: "Downloading videos may break the site's terms; use only references you have the right to analyze." and requires a confirmation checkbox per recipe.
1.5 Campaigns get `allow_heavy_edits: true | false | unknown` (default `unknown`, treated as false by autopilot). Pro Edit autopilot runs only when it is `true`; the manual button warns when it is false/unknown.
1.6 Director and Critic spend LLM credits: every call is recorded in the usage meter (SPEC-v2 2.4) under a `proedit` category; a per-clip cost estimate is shown before running and a monthly cap blocks new runs. Before enabling the critic, verify the configured provider/model accepts image input; if not, fall back to "Director only" with a clear UI message.

---

## 2. Product decisions (fixed by the owner)

- Entry points: "Pro Edit" button on every clip (gallery card, editor top bar, approval inbox card) and a per-campaign/autopilot switch "Also make a Pro Edit variant" (default OFF).
- Audio sources: Freesound (CC0/CC BY), Pixabay, own uploads only.
- Style learning: the user pastes links; ClipForge downloads, analyzes and deletes.
- Critic: the LLM provider ClipForge already uses (vision-capable model required).
- Six original presets: Clean Pro, Dark Edit, Phonk Edit, Cinematic, Skull Moment, Glitch.
- Intensity slider: Clean → Standard → Pro → Extreme, chosen per run, capped per campaign.

### 2.1 Owner style references (target look and feel)

The owner wants Pro Edit to reach the look of heavy, high-retention edits made from movie scenes and streamer/YouTuber moments. Reference channels named by the owner:

- https://www.youtube.com/@FaziEdits
- https://www.youtube.com/@Ayxamv
- https://www.youtube.com/@limeeditss
- https://www.youtube.com/@FrayzzShorts

Target moves, in our own words: rapid cuts locked to the music's beats; sudden scale-ups on the subject's face; camera jolts on hits; single bright frames between beats; crushed, desaturated or monochrome grading; large glowing one-word captions; a heavy, bass-driven instrumental bed with a hard drop; swishes on every move and deep hits on key moments; and "caught" moments where the picture freezes, turns monochrome and gets a skeleton graphic.

Rules for these references:
- They define the target style of the presets (especially Phonk Edit, Dark Edit, Skull Moment, Glitch) and the Director's defaults at Pro/Extreme. Never copy their names, logos, text, music, overlays or footage into code, presets, assets or docs beyond the URLs listed here.
- The loop must not crawl or bulk-download these channels (1.1/1.4). Style Learning analyzes only individual video links the owner pastes into a StyleRecipe in the app, with the rights confirmation, and then deletes the media.
- **Acceptance (measurable traits):** a fixture-based test edit at Phonk Edit / Pro must show, measured by the same extractors used for Style Learning (section 4.3):
  - mean interval between cuts or zoom changes ≤ 1.5 s;
  - ≥ 1 zoom punch per 3 s of clip;
  - ≥ 60 % of cuts/zooms within one frame of a music beat;
  - ≥ 1 flash or shake per 5 s;
  - mean output luma lower than mean source luma.

---

## 3. Pro Edit engine

### 3.1 Edit Decision List (EDL)

`ProEditPlan {id, clip_id, preset, intensity, style_recipe_id | None, version, items: list[EdlItem], rationale, created_by: "director" | "rule_director" | "user" | "critic_revision"}`

`EdlItem {id, t_start, t_end, kind, params: dict, reason: str, source: "auto" | "manual"}`

Kinds and their track (items on the same track may not overlap unless the kind is marked stackable):

| Track | Kinds |
|---|---|
| zoom | `zoom_punch`, `zoom_push`, `zoom_out_reveal`, `pan` |
| fx | `shake`, `flash`, `glitch`, `rgb_split`, `freeze_frame`, `speed_ramp`, `slowmo`, `transition` |
| grade | `grade_change` (bw / dark / desat / lut), `vignette`, `grain` |
| overlay | `overlay` (asset, anchor screen/face/object, position, scale, rotation, animation), `text_pop`, `emoji_pop` (stackable, max 3 concurrent) |
| captions | `caption_style` (kinetic per-word) |
| sfx | `sfx` (asset, gain_db) (stackable, max 2 concurrent) |
| music | `music_bed` (asset, gain_db, duck), `silence_before_drop` |
| audio_fx | `audio_fx` (bass_boost, reverb_tail, lowpass_sweep, stutter) |

Each `params` dict has a per-kind Pydantic model (discriminated by `kind`). Validation: `0 ≤ t_start < t_end ≤ clip duration`; non-overlap per track; intensity budgets (3.4); `reason` non-empty. Every item's reason is shown in the UI.

**Intensity budgets** (defaults; presets may lower, never raise):

| Intensity | SFX density max | Pattern interrupt target | Effect items per 5 s max |
|---|---|---|---|
| clean | 1 per 6 s | none | 1 |
| standard | 1 per 4 s | none | 2 |
| pro | 1 per 2 s | every 2–4 s | 4 |
| extreme | 1 per 1 s | every 2–4 s | 8 |

**Snapping** (code, after any planner): times snap to the clip frame grid (`round(t * fps) / fps`); items marked `snap="word"` snap to the nearest word start within 0.25 s; items marked `snap="beat"` snap to the nearest beat within 0.12 s (else the word/frame rule applies). SFX never overlaps the punchline word span (moved to end at the word start minus one frame, or dropped).

### 3.2 Signals

`proedit/signals.py` builds a compact `ProEditSignals` object, reusing existing analysis stored for the clip and computing only what is missing: word timestamps and emphasis words (`caption_emphasis.py`), punchlines (laugh peaks from `audio_events.py`/`yamnet.py`, LLM-marked moments if stored), loudness peaks (`level_events.py`/`audio_analysis.py`), scene cuts (`scene_cuts.py`), face boxes/tracks (`faces.py`, `face_cache.py`, `tracking.py`), speaker turns (`speaker.py`), silence gaps (`cleanup.py`), sentence boundaries, motion energy (`motion.py`), and for the chosen music asset the beat grid, downbeats and drops (`librosa.beat.beat_track`, `librosa.onset.onset_strength`/`onset_detect` — verify signatures in the installed librosa per 0.1).

### 3.3 Core pro moves (auto and manual)

- **Zoom**: punch-in 110–130 % on emphasis words and punchlines (instant or 2–4 frame ease); slow push-in during setup (e.g. 100 → 112 %); zoom-out reveal after the payoff; centered on the face track; easing options ease-in-out, back, elastic; the face box never leaves the crop (asserted in tests).
- **Whoosh** on every zoom, transition, text pop-in and B-roll cut; whoosh length matched to the motion duration; pitch-shift variants (`asetrate`/`atempo` or `rubberband` if present — verify).
- **SFX auto placement**: whoosh, swoosh, pop, ding, impact/boom, bass drop, riser, record scratch, camera shutter, glitch, a deep "boom hit" (original or licensed only), typing, cash register, crowd laugh/gasp. Frame-accurate on the visual event; ducked under speech; never masks the punchline word; density per intensity (table above).
- **Retention**: pattern interrupt every 2–4 s at Pro and Extreme (zoom change, crop/angle change, B-roll, caption emphasis, SFX); dead-air removal via `cleanup.py`; hook within the first 1–2 s via `hooks.py`; optional loop-friendly ending (last 0.3 s of audio/video crossfades into the first frame's look).
- **Pacing**: cut on beat, cut on action, J/L cuts (audio leads/trails video by 2–8 frames), reaction hold 0.5–1.0 s after punchlines, speed ramps (slow-mo into the key moment, snap back).
- **Kinetic captions**: per-word pop, bounce, shake on loud words, scale on emphasis, neon glow, single-word mode, emoji pops — new Pro Edit caption styles in `proedit/captions.py`; existing caption templates unchanged.
- **Sound design and mix**: dialogue EQ (high-pass ≈ 80 Hz, presence boost), compression, de-ess; music bed with sidechain ducking; riser before drops; silence before drop 100–300 ms; impact on the drop; final loudness -14 LUFS integrated, true peak ≤ -1 dBTP via `loudnorm.py` (verify filter params).
- **Color**: auto exposure/white-balance normalization first (verify `eq`, `colorbalance`, `normalize`, `colortemperature`), then the preset grade (curves/eq or `lut3d` with bundled original `.cube` files), skin-tone protection (limit saturation change in the skin hue range).
- **Motion**: keyframed pan/zoom (Ken Burns for stills), overlays/text/emoji attached to face/object tracks (`tracking.py`, `object_tracking.py`), optional subject cut-out (MediaPipe selfie/image segmentation — verify the installed mediapipe 0.10.33 API) for "subject in front of text" and background blur/swap.

### 3.4 Presets

Original YAML definitions in `backend/clipforge/proedit/presets/*.yaml`, loaded into a `ProEditPreset` model. Each declares: allowed kinds, intensity budgets (≤ the global table), default music mood and BPM range, caption style, grade, overlay set, and Director rules (which signals trigger which kinds).

- **Clean Pro**: light correction grade, subtle punch-ins on emphasis words, whoosh on transitions, clean kinetic captions, optional music bed, no heavy FX.
- **Dark Edit**: darker exposure, higher contrast, desaturated, vignette, light grain, slow push-ins, low riser and impacts, neon single-word captions.
- **Phonk Edit**: Dark Edit look plus a strong-beat music bed (BPM 120–160 default); cuts/zooms/shakes on downbeats; bass drop on the punchline; speed ramps; higher SFX density.
- **Cinematic**: filmic teal/orange-style curves (original LUT), optional 2.39:1 letterbox inside 9:16, slow-mo on the key moment, soft whooshes, ambient riser, minimal captions.
- **Skull Moment**: at the punchline / "caught" moment: freeze frame → instant B&W/dark grade → shake + zoom punch on the face → procedural skull/skeleton overlay (optionally face-anchored) → boom/bass drop → 1.0–2.0 s hold → snap back to color with a whoosh.
- **Glitch**: flashes, RGB split, digital glitch frames and stutter at transitions and emphasis words; glitch SFX; datamosh-style look only if a verified ffmpeg filter chain produces it.

### 3.5 Director

- Input: compact JSON of signals (3.2), transcript with word times, preset rules, intensity, optional style recipe (4), campaign constraints, asset catalog (ids + tags only). The v2 "user feedback history" input is omitted because feedback learning (T58e.2) was deferred by the owner.
- Output: `ProEditPlan` JSON validated by Pydantic; up to 2 retries with the validation errors fed back; then deterministic post-processing (snapping, budgets, punchline protection — 3.1).
- Rule-based director (`proedit/rule_director.py`): produces a valid plan from preset rules and signals alone, deterministically, for all 6 presets × 4 intensities. Used when the LLM is unavailable, errors, or the cap is reached, so Pro Edit always works offline.

### 3.6 Renderer

- `proedit/render/` builds one ffmpeg filter graph from the EDL, following the patterns of `render_graph.py`, `timeline_graph.py` and `zoom_graph.py`.
- 540p proxy first, then the final at source resolution (up to 4K) with `encoders.py` (VideoToolbox when available).
- Deterministic: the same EDL and assets give the same output; fixed seeds for grain/glitch (`noise` `all_seed`, verify).
- ffprobe-verified output: size, codecs, duration ±0.2 s, loudness within ±1 LU of -14 LUFS.

### 3.7 Critic loop

- After the proxy render: sample frames at each EDL item start/end plus a 1 fps baseline, capped at 24 frames (configurable); audio summary (loudness curve, speech/music/SFX levels, clipping); transcript; EDL.
- Checklist, each scored 0–10 with a reason: hook strength (first 2 s), dead air, caption sync/readability, crop/face errors, effect overuse/underuse vs intensity, audio balance (speech over music/SFX), punchline clarity, loop ending, preset faithfulness.
- Output: JSON list of EDL changes (`add` / `remove` / `modify` with item ids), applied by code with validation; max 2 rounds (configurable 0–3); stop early when all scores ≥ threshold (default 7).
- Cost guard: estimate tokens and images first; respect the monthly cap (1.6); UI shows scores and a "what changed" diff.

### 3.8 Pro Edit UI

- Dialog: preset cards with a looping preview, intensity slider, optional style recipe, music choice (auto by mood/BPM or pick), "Use critic" toggle with a cost estimate, Run; warning when the campaign's `allow_heavy_edits` is not `true`.
- Progress view: plan → proxy → critic round n/N → final, using the shared progress/ETA system (`job_progress.py`).
- Editor (route `/clips/:id/proedit`): side-by-side original vs Pro Edit preview; EDL lanes (zoom, fx, overlays, captions, sfx, music) with draggable items and their reasons; inspector for params; "Regenerate with Director", "Run critic again", "Reset to plan v1"; plan version history.
- Gallery and approval inbox: Pro Edit variant as a linked card with a "Pro Edit" badge; approve the original, the Pro Edit, or both.
- Campaign settings: "Also make a Pro Edit variant" (default OFF), preset, max intensity, `allow_heavy_edits`.

---

## 4. Style learning from links

4.1 A StyleRecipe has a name, 1–5 reference links and a rights confirmation (1.4).
4.2 Per reference: temp dir `data/work/style_<id>/` → download (`pipeline/download.py`, ≤ 3 min, ≤ 720p, verified yt-dlp format selectors) → analyze → store features → delete media (assert the directory is gone). Deletion runs in a `finally` block even when analysis fails.
4.3 Features (all numeric/text; verify every library call). These extractors live in `proedit/features/` and are also used to measure Pro Edit output (2.1 acceptance, style-match score):
- cut rhythm: shot lengths (`scene_cuts.py`), cuts-per-second curve, % of cuts on beat;
- zoom/motion: scale changes and shake from frame-to-frame affine estimation (`cv2.estimateAffinePartial2D` on tracked features — verify), counts per minute, typical amplitudes/durations;
- color: mean luma, contrast (luma std), saturation, % B&W frames, hue histogram summary, vignette strength, grain estimate;
- flashes/glitches: frame-difference spikes, near-white frames, channel-offset (RGB split) heuristic;
- captions: OCR on sampled frames (Apple Vision via pyobjc or tesseract — verify an engine that installs on macOS arm64) → words per line, size ratio, position, color, uppercase ratio;
- audio: music presence, BPM, loudness curve, drop positions, SFX density (onsets not on beat or speech), silence-before-drop occurrences;
- structure: time to first effect, hook duration, effect density per 5 s window, ending type (loop / hard cut).
4.4 Aggregation: medians + ranges across references + a short LLM-written description (rule-based text when the LLM is unavailable). The Director uses the recipe as targets; the style-match score (0–100) compares Pro Edit output features to the recipe ranges.
4.5 Recipes are editable (sliders mirror the numbers), exportable/importable as JSON and never contain media or media paths.

---

## 5. Licensed audio library

5.1 Freesound: official APIv2 (verify current auth — token vs OAuth2 —, text search endpoint, `filter` syntax for `license`, and whether original downloads need OAuth2 while previews work with a token). Tag search (whoosh, riser, impact, bass drop, glitch, pop, ding, scratch, shutter, crowd laugh/gasp); license filter CC0/CC BY only (re-checked on the returned metadata); downloads respect rate limits; attribution text stored. If only previews are available with a token, document it and store the preview with the same license data.
5.2 Pixabay audio: verify whether the official API covers music/SFX. If yes, integrate with `PIXABAY_API_KEY`; if not, an "Import Pixabay file" form (file + source URL + license confirmation).
5.3 Own uploads: drag-and-drop with a required rights field; same tagging.
5.4 Auto-tagging: duration, BPM (music), key (optional), loudness (LUFS), energy curve, onset sharpness, mood/energy class (heuristics; optional LLM tag from filename/metadata), category (whoosh/impact/riser/...).
5.5 `scripts/fetch_starter_sfx.py` builds a recommended CC0-only starter set from Freesound once the user has a key; nothing is downloaded at install time; only generated `LICENSES.md` rows may be committed, never the audio.
5.6 Attribution: CC BY assets used in a clip are appended to the clip description and export JSON automatically.

Bundled original SFX: the existing bundled pack (`assets/sfx`, `pipeline/sfx.py`) is reused so Pro Edit works without any key.

---

## 6. Data model (migrations `039_…` onward)

- `Clip.parent_clip_id: int | None`, `Clip.variant: "original" | "pro_edit"` (default `"original"` for all existing rows).
- `ProEditPlan`, `EdlItem` (3.1) stored as a plan row with versioned JSON items.
- `ProEditRun {id, clip_id, plan_id, status, rounds, critic_scores, cost_estimate, cost_actual, started_at, finished_at, error}`.
- `StyleRecipe {id, name, description, features: dict, reference_count, created_at}`; `StyleReference {id, recipe_id, url, analyzed_at, deleted_at, rights_confirmed_at}`.
- `Asset` audio fields: `bpm, key, loudness_lufs, energy_curve, category, mood, license, attribution, source_url, downloaded_at`.
- `Campaign.allow_heavy_edits: "true" | "false" | "unknown"` (default `unknown`); `AutopilotSettings.proedit_enabled` (default false), `proedit_preset`, `proedit_max_intensity`.
- Config: `proedit.enabled` (true), `proedit.critic_max_rounds` (2), `proedit.critic_threshold` (7), `proedit.critic_max_frames` (24), `proedit.monthly_cap_usd` (unset = no cap).

---

## 7. Testing and acceptance

- Isolation regression (0.13), kept green by every v3 task.
- EDL: schema validation; budgets/density per intensity; frame/word/beat snapping with exact numbers; no face cropped out during zooms; SFX never overlaps the punchline word; rule-based director valid for all 6 presets.
- Renderer: ffprobe + frame-hash checks per kind on a short fixture (zoom scale at a timestamp within tolerance; freeze frame = identical consecutive frames; B&W = near-zero saturation in the window; flash = luma spike; SFX/drop = RMS spike at the planned time; ducking = music RMS drop under speech; loudness -14 ± 1 LUFS).
- Critic: mocked LLM (respx); max rounds respected; cost cap blocks; no image capability → director-only.
- Style learning: mocked downloads of ffmpeg-generated fixture "references" with known cuts/zooms/flashes/B&W segments → features within tolerance; media deleted; recipe contains no media.
- Audio library: recorded Freesound/Pixabay responses; license filter; attribution; no network in `make check`.
- Autopilot: variant only when the switch is ON and `allow_heavy_edits` is true; originals untouched; both variants in the inbox.
- Phonk Edit / Pro trait test (2.1).
- Playwright: clip → Pro Edit (Skull Moment, Pro) → progress → side-by-side → move one EDL item → re-render → approve variant; create a StyleRecipe from 2 fixture links (mocked download) → apply → style-match score shown.
- `make check` green after every task; HANDOFF updated per 0.11.

---

## 8. Task order

V3-01 migrations · V3-02 package skeleton + flag + isolation golden test · V3-03 EDL schema/validation/snapping/budgets · V3-04 signals + beat grid · V3-05 renderer core · V3-06 renderer motion · V3-07 renderer FX/overlays · V3-08 kinetic captions · V3-09 audio engine · V3-10 Freesound · V3-11 Pixabay/uploads/tagging/starter pack · V3-12 presets + rule director · V3-13 LLM director · V3-14 critic · V3-15 API/jobs · V3-16 dialog/progress/cards · V3-17 editor · V3-18 style learning A · V3-19 style learning B · V3-20 campaign/autopilot · V3-21 retention extras · V3-22 e2e + README + parity.

Large steps are split into sub-tasks (a/b/c) in `.agent/tasks/TASK-201.json` onward; see `.agent/tasks.json` for the execution order. The shared feature extractors needed by the Phonk Edit trait test (V3-12) are built early in V3-04b and extended in V3-18/19.

---

## 9. Assumptions (prompt gaps resolved by the planner)

1. `.agent/tasks/TASK-195..200` (and 196b/198b) exist as spec files but are not in `.agent/tasks.json`; v3 tasks do not depend on them and numbering continues at TASK-201 so no id collides.
2. The prompt's `frontend/src/features/proedit/` folder does not exist yet; it is created as a new folder (the rest of the app uses `pages/` and `components/`).
3. Module names in the prompt are mapped to real modules in 0.14 (e.g. "timeline" → `timeline.py` + `pipeline/timeline_graph.py`; "stock/pixabay" is video/image stock only, so Pixabay audio is a new client).
4. The Director's "user feedback history" input is omitted (T58e.2 deferred).
5. Created-by gains `"rule_director"` so the UI can say which planner made a plan.
6. Beat alignment for the 2.1 acceptance counts a cut/zoom as on-beat when within one frame (1/fps) of a beat; "grade darker than source" means mean output luma < mean source luma over the clip.
7. The Phonk trait test needs the output-measuring extractors before Style Learning; the cut/zoom/flash/luma extractors are therefore built in V3-04b and reused by V3-18.
8. A music fixture with a known BPM is generated in tests with ffmpeg (`sine`/`aevalsrc` click track, see `pipeline/click_track.py`) — no third-party music in the repo.
9. Per-campaign "max intensity" caps the slider; when unset, max is Extreme.
10. Monthly cap is in USD using the usage meter's existing cost fields; when the provider reports no price, tokens/images are counted and the cap is checked on the estimate.
