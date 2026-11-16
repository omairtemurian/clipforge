# Decisions

## 2026-11-03 — TASK-202 Pro Edit skeleton, `proedit.enabled`, golden isolation

- Flag: `Settings.proedit: ProEditConfig{enabled: bool = True}`, also in
  `config.yaml`. Off = every `/api/proedit/*` route answers 404
  `proedit_disabled` (router-level dependency read per request), so the
  status endpoint is gated too: the UI treats any failure as "off". The
  normal pipeline never imports `clipforge.proedit` (only the API router).
- UI entry: an outline "Pro Edit" link in the editor top bar (original
  clips only) to `/clips/:clipId/proedit`, a page inside the app shell that
  lists the clip's variants (TASK-226 turns it into the Pro Edit editor).
  The route is always registered and guarded (skeleton while the status
  loads, redirect to the clip when off) instead of conditional
  registration, which would bounce deep links to Home while loading.
- Golden isolation test: one real normal job on `sample.mp4`
  (`num_clips=1`, recorded transcript, `FakeLLMClient`) compared with
  `tests/fixtures/golden_normal_pipeline.json`: clip title/start/end,
  ffprobe stream keys, SHA-256 of decoded yuv420p frames at 1/5/10 s and
  duration-0.5 s, and RMS dBFS per 0.5 s window (tolerance 0.05 dB). The
  encoder is pinned to libx264 (VideoToolbox is machine-dependent and not
  bit-exact); libx264 + AAC decode were deterministic across repeated runs
  here. Regenerating (`CLIPFORGE_REGENERATE_GOLDEN=1`) needs a decision
  entry. Proofs: auto_zoom default flipped -> frame hashes differ;
  `config.yaml` `target_lufs: -15` -> 61/61 RMS windows differ (max
  4.19 dB). Changing only the class default of `target_lufs` is not caught
  because `config.yaml` sets it (the yaml is what users run).
- Verified by reading pydantic-settings `YamlConfigSettingsSource` (source
  order), ffprobe `-show_streams` JSON and ffmpeg `-f rawvideo` usage.

## 2026-11-02 — TASK-200 Light theme (default) + dark toggle, Poppins, Phosphor

- Light is the default (`:root` in `src/index.css`); the grey dark theme is
  `.dark`. Choice Light/Dark/System is saved in localStorage
  `clipforge.theme` (junk or missing = Light). The inline `#theme-init`
  script in `index.html` sets `.dark`, `color-scheme` and the
  `theme-color` meta before the app module loads, so there is no flash;
  `lib/theme.ts` holds the same rules (a unit test runs the script against
  them). System follows `prefers-color-scheme` live (`useTheme` store).
- Contrast (WCAG AA, checked by `lib/themeTokens.test.ts`): white on ember
  `#ff6b35` is only 2.84:1, so text on ember fills is dark
  (`--primary-foreground` `#1c0b03`) in both themes, and ember-coloured text
  uses a new `--primary-ink` token (`#b23a0c` light, `#ff8a5c` dark) via
  `text-primary-ink`. The ember fill stays `#ff6b35`.
- New tokens: `--field` (input/search fill), `--scrim` (dialog overlay),
  `--elevation-*` (soft card/popover shadows, `shadow-card`,
  `shadow-card-hover`, `shadow-popover`). Radius 0.75rem; buttons are pills.
- Poppins (OFL) is bundled in `frontend/public/fonts`, not `assets/fonts`:
  the caption font picker lists every TTF in `assets/fonts` and backend tests
  pin that set. Its sha256 rows are in `assets/fonts/LICENSES.md`.
- Icons: `@phosphor-icons/react` 2.1.10 (MIT, checked on npm 2026-11-02),
  `XxxIcon` exports; active nav icons use `weight="fill"`. lucide-react and
  Geist were removed (a TS-AST codemod renamed every import). Each Phosphor
  icon ships its six weights, so the JS bundle grew 816 -> 1,130 kB (gzip
  237 -> 302 kB); fine for a localhost app (the >500 kB warning predates it).
- Layout unchanged: only tokens, type, icons and shared component styles.
  No calendar page exists yet (TASK-149), so it has no screenshot.

## 2026-11-02 — TASK-120 T40b Find B-roll spots (LLM) + cutaway/PiP insert

- No new library or third-party endpoint: stock search/download is the
  TASK-119 client (`stock.provider`, `download_clip`; Pexels/Pixabay docs
  verified 2026-11-02, see below); the PiP window uses the ffmpeg `scale` +
  `overlay` filters the overlay track already uses (ffmpeg filters docs,
  https://ffmpeg.org/ffmpeg-filters.html, checked 2026-11-02).
- PiP is a B-roll item with `BrollProps.mode = "pip"` (x/y = window centre,
  width = share of the frame width, like overlays) instead of an overlay item:
  the spot and its replace/remove stay on the B-roll track, and the cutaway
  default keeps old timelines unchanged.
- Sentences: split at `.`/`!`/`?`/`…`, a pause >= 0.8 s, or 40 words. Sentence 0
  is the hook and is never offered; picks next to another pick are rejected
  (the LLM retries with the problems, 3 tries) so cutaways do not merge.
- Spot window: the sentence, clamped to 1.5-5 s and the clip; shorter or
  overlapping spots are dropped. Results ask for clips at least as long as
  the spot, portrait for a 9:16 cutaway, landscape for PiP.
- Spots are not stored: "regenerate" = call `/broll/spots` again (LLM + one
  search per spot, metered). A failed search marks only that spot (`error`).
- A stock clip is downloaded on insert (not on search), so only used clips
  land in `data/stock`. Replace keeps time, mode and placement, offset 0.

## 2026-11-02 — TASK-119 T40a Stock B-roll clients (Pexels, Pixabay)

- Verified 2026-11-02 against the official docs (no API key here, so the
  recorded answers in `backend/tests/fixtures/stock/` are built from the
  documented example responses, not captured live):
  - Pexels: https://www.pexels.com/api/documentation/ - `GET
    https://api.pexels.com/v1/videos/search?query&orientation&per_page`
    (max 80), key alone in the `Authorization` header (no "Bearer");
    `video_files[]` has `file_type`, `width`, `height`, `link` (the HLS
    entry has null size); 200 requests/hour, 20,000/month, 429 over the
    limit. API terms: show a visible link to Pexels and credit the
    videographer. License https://www.pexels.com/license/ (summarised on
    help.pexels.com): free for personal and commercial use, editing allowed,
    no attribution required; not allowed: selling unaltered copies, implying
    endorsement, showing identifiable people badly, reselling on stock sites.
  - Pixabay: https://pixabay.com/api/docs/ - `GET
    https://pixabay.com/api/videos/?key&q&per_page` (3-200); `hits[]` with
    `pageURL`, `duration`, `tags` (comma list), `user`, `user_id` and
    `videos.{large,medium,small,tiny}` `{url,width,height,thumbnail}`
    (a size can come with an empty url); 100 requests/60 s per key; results
    must be cached 24 h; hotlinking images is not allowed (store videos on
    our side). License https://pixabay.com/service/license-summary/: free
    use and editing, no attribution required; not allowed: selling or
    distributing unaltered content, misleading or illegal use, trademarks.
- Both licenses allow B-roll in a posted clip. Attribution is kept on the
  Asset anyway ("Video by <creator> on <Provider> (<page url>)") because the
  Pexels API terms ask for credit and the UI shows it.
- A missing key is not an error at startup: the client constructor raises
  `ProviderDisabled` ("Pexels is off: set PEXELS_API_KEY in .env ...") and
  `provider_statuses()` lists both providers with that message for the UI.
- File choice: the mp4 with the smallest short side >= 1080 px, else the
  largest (a full-screen cutaway in a 1080 x 1920 clip stays sharp without
  downloading 4K).
- Usage: each search request (also a failed one, the provider counts it) is
  one `api_calls` record for the current `usage.recording()` project; a
  Pixabay answer from the 24 h cache is not a call. Downloads go to the CDN,
  are not API calls and do not carry the key. Cost is None (free tiers).
- Pixabay has no orientation filter for videos: it is applied to the chosen
  file's size. Pexels filters on its side.

## 2026-11-02 — TASK-118 T39d Audio panel (music, SFX; voiceover UI removed per scope cut)

- No third-party library or endpoint is new: the panel calls the API of
  TASK-115/116/117 (`GET /api/music`, `/api/sfx`,
  `POST /api/clips/{id}/auto-sfx`; types from
  `scripts/gen_types.py`). The browser plays previews with the standard
  `Audio` element (MDN, HTMLAudioElement, checked 2026-11-02).
- One rail panel "Audio" (not three): music and sound effects
  share the audio tracks and the "render again to hear it" note.
- Music and manual SFX are edits of the clip's tracks (`edits.setLayer`),
  saved with the other edits and undone with them. The AI "Suggest sound
  effects" changes the saved clip, so
  it is disabled while there are unsaved edits or a save/render runs
  (like Cleanup); the clip an answer holds replaces the editor's.
- Choosing music puts one item over the whole clip (the file loops) with
  volume 50 %, 1 s fades and ducking on; choosing another track swaps the
  asset of the current item and keeps its settings. The panel edits the
  selected music item, else the first.
- The credit shown for a music track is the asset's attribution, plus its
  license if the attribution does not already name it.
- Voiceover UI: removed again per the owner's scope cut (steering item 1);
  the voiceover backend (`/voices`, `/clips/{id}/voiceover`) and its tests stay.

## 2026-11-02 — TASK-116 T39b Auto SFX

- Pack: no third-party sound is downloaded. Seven new effects (pop, ding,
  boom, riser, click, sparkle, rimshot) are original, synthesized by
  `scripts/make_sfx.py` and dedicated CC0 1.0; with the two whooshes and the
  CC0 crowd laugh already bundled the pack has 10 sounds, each with tags in
  `pipeline/sfx.BUNDLED_SFX` and `assets/sfx/LICENSES.md` (a test keeps
  the two in step with the files and their lengths).
- Generate-by-prompt: not available. Checked 2026-11-02 on the Hugging Face
  model API (https://huggingface.co/api/models/<id>, `cardData.license`):
  `stabilityai/stable-audio-open-1.0` is `other` (stable-audio-community,
  gated), `declare-lab/tango2` and `cvssp/audioldm2` are cc-by-nc-sa-4.0,
  `facebook/audiogen-medium` and `facebook/audio-magnet-medium` are
  cc-by-nc-4.0. None is open-licensed for commercial use (SPEC-v2 1.3), so
  the pass searches the bundled pack by tag. (A web search summary claimed
  MIT/Apache for some; the model cards above are the source used.)
- How it works: code lists the moments (cuts that join parts, spoken words,
  in render time); the LLM picks moments and describes each sound with tags
  from the pack (`prompts/sfx.md`, reply `SfxReply`); `search_sfx` takes the
  sound with most matching tags, avoiding sounds already placed. Rules
  (checked, errors sent back like bad takes): at most `max_items` (default
  5, max 8), 2 s apart, tags the pack has. A cut gets the sound centred on
  it (lead at most 0.4 s), a word from its start. Items are
  `auto-sfx-<n>` on the sfx track at volume 0.6; a rerun replaces them and
  keeps the owner's items. `POST /api/clips/{id}/auto-sfx`, `GET /api/sfx`.
  No UI yet.

## 2026-11-02 — TASK-107 T36d Overlays/transitions/media library UI

- Three new editor rail panels (rail now: Captions, Layout, Sections,
  Transitions, Brand, Text, Text layers, Media, Score, Rules; it scrolls
  if the window is short): "Media" (library grid, kind filter, upload,
  drag a tile onto a track or press + to add it at the playhead),
  "Text layers" (up to 5 text items: add, select, edit text and style,
  delete) and "Transitions" (one for all jump cuts, one per section cut,
  "Use the first for all", length slider 0.1-1 s).
- The media kind travels in the drag MIME type
  (`application/x-clipforge-media-<kind>`; the library id is the data),
  because the data itself can only be read on drop while the type list is
  visible during dragover; so a track highlights and accepts only kinds it
  can play (video: B-roll, Overlays; image/logo: Overlays, B-roll; audio:
  Music, SFX, Voiceover).
- A dropped item starts at the clip time under the pointer (preview time,
  after cuts), lasts the file's duration (stills 3 s), clamped to the
  rendered clip; ids are `<kind>-<n>` unique across the timeline. Items,
  text layers and transitions go through the same edit history as other
  edits (undo/redo, autosave, "Save changes": `PATCH /tracks` and
  `PATCH /api/clips/{id}` `transitions`).
- Text layer selection is shared with the timeline's selected item, so
  pressing a text item on the timeline opens it in the panel and vice versa.
- Third-party APIs checked 2026-11-02:
  - HTML drag and drop `DataTransfer.setData` / `types` (data is writable in
    dragstart, readable only on drop; types are visible in dragover)
    (https://developer.mozilla.org/en-US/docs/Web/API/DataTransfer/setData,
    https://html.spec.whatwg.org/multipage/dnd.html#drag-data-store-mode).
  - Playwright `locator.dragTo(target, { targetPosition })`
    (https://playwright.dev/docs/api/class-locator#locator-drag-to; matches
    the installed playwright-core types).

## 2026-11-02 — TASK-106 T36c Transitions: crossfade, zoom punch, whip, slide

- Stored per clip as `transitions` (`models.ClipTransitions`, JSON column,
  migration `024_v2_clip_transitions`; v1 clips get none): `auto` is the
  transition at every jump cut (a cut inside a section: the clip's cut
  ranges, the auto cut's included); `sections[i]` is the manual one at the
  cut from the i-th section to the next in play order (null: hard cut).
  Positional on purpose (simplest, SPEC-v2 0.6): reordering sections keeps
  the transition at the same boundary; entries past the last boundary are
  kept but unused. If a whole section is cut away, the cut after it uses the
  entry of the last section before it that plays. Set with
  `PATCH /api/clips/{id}` `{transitions}`; it is part of `ClipState`, so it
  has versions/undo; the preview key includes it.
- Kinds and xfade names: crossfade = `fade`, zoom punch = `zoomin`, whip =
  `hblur` (sideways blur, like a whip pan), slide = `slideleft`. Duration
  0.1-1 s (default 0.3).
- Length is kept: the transition is centred on the cut; the part before is
  padded with its last frame and the part after with its first frame
  (`tpad` clone, half the transition each, in whole frames) and `xfade`
  starts half the transition before the cut. Captions, layer items and the
  sound therefore keep their times; the sound stays a hard cut (no audio
  crossfade). A transition is cut to half of each part it touches, so two
  never overlap; less than a frame per side means a hard cut.
- Hard cuts next to transitions are joined by `concat=v=1:a=0`; every piece
  gets `settb=AVTB` first, because xfade refuses inputs whose time bases
  differ (probed: "First input link main timebase (1/1000000) do not match
  the corresponding second input link xfade timebase (1/30)" after concat).
- Third-party APIs checked 2026-11-02 against the installed ffmpeg 9.0.2
  (`ffmpeg -h filter=xfade`, `ffmpeg -h filter=tpad`) and
  https://ffmpeg.org/ffmpeg-filters.html#xfade /
  https://ffmpeg.org/ffmpeg-filters.html#tpad: xfade `transition` (fade,
  zoomin, hblur, slideleft among 58), `duration`, `offset` (relative to the
  first input); tpad `start`/`stop` (frames), `start_mode`/`stop_mode` clone.
  Probed: 1 s + 1 s + 1 s parts with 0.4 s and 0.2 s transitions rendered 90
  frames / 3.000 s for each of the four kinds.

## 2026-11-02 — TASK-105 T36b Text overlays (up to 5 layers) with animations

- "Up to 5 layers" = at most 5 items on a clip's text track
  (`MAX_TEXT_LAYERS`, `pipeline/text_overlay.py`), whether or not they
  overlap: a 6th is 422 from `PUT`/`PATCH /api/clips/{id}/tracks`
  ("text track: 6 text overlays, at most 5 allowed"). Older timelines stored
  with more are not migrated; the render draws only the first 5 and logs the
  rest.
- `TextProps` gained `stroke` (color or null), `stroke_width` (times the font
  size, 0-0.3, default 0.08), `box_opacity` (0-1), `animation_in` /
  `animation_out` (`none`, `fade`, `slide_up`, `slide_down`, `slide_left`,
  `slide_right`, `pop`) and `in_seconds` / `out_seconds` (0-3 s, default
  0.4). Every animation but `none` also fades; a slide moves the text 15% of
  the frame; `pop` scales the font from 60%. The progress eases out
  (1 - (1 - p)^2). When in + out are longer than the item, both shrink in
  proportion. New fields have defaults, so stored v1/v2 text items still
  validate (no migration).
- Third-party APIs checked 2026-11-02 against the installed ffmpeg 9.0.2
  (`ffmpeg -h filter=drawtext`) and https://ffmpeg.org/ffmpeg-filters.html#drawtext:
  `alpha`, `x`, `y` and `fontsize` are expressions (string options) that
  drawtext evaluates on every frame — probed: `fontsize='10+t*60'` drew 352
  px of text at t=0.1 and 5520 px at t=0.9, the same as fixed 16 and 64;
  `alpha` also fades the box. `borderw` (int px) + `bordercolor` draw the
  stroke; `boxcolor=0xRRGGBB@a` sets the box opacity; `clip(x,min,max)` and
  `pow` are ffmpeg expression functions (https://ffmpeg.org/ffmpeg-utils.html#Expression-Evaluation).
  Expressions with commas are single-quoted in the graph, as `enable` is.

## 2026-11-02 — TASK-104 T36a Media library uploads

- Third-party APIs checked 2026-11-02 against the installed ffmpeg 9.0.2
  (`ffmpeg -filters`, and the tests run each command for real) and
  https://ffmpeg.org/ffmpeg-filters.html: `showwavespic=s=WxH:colors=C`
  (audio in, one picture out; used with `-frames:v 1` for the waveform
  thumbnail of audio) and `scale=w='min(320,iw)':h=-2` (never upscales, keeps
  the ratio). `ffprobe -show_format -show_streams -of json` gives
  `codec_type`, `disposition.attached_pic` (cover art is not video),
  `format.duration`, `width`, `height`.
- Endpoints are under `/api/library` (not `/api/media`, which serves a
  project's source video): `GET` (filters `kind`, `tag`), `POST`, `PATCH
  /{id}`, `DELETE /{id}`, `GET /{id}/file` (Range) and `/{id}/thumbnail`.
  They live in `api/media.py` as the task asks.
- No migration: an upload is an `Asset` tagged `media-library` (the owner's
  tags are the other tags; `media-library`, `uploaded` and `bundled` are
  reserved). What does not fit the Asset (name, MIME, size, duration, size in
  pixels, thumbnail name) is `info.json` (`MediaMeta`) next to the file in
  `{data_dir}/media/<first 16 hex of the SHA-256>/`, with `file.<ext>` and the
  thumbnail. The client's file name is only shown, never a path.
- The MIME type and the format come from the first bytes (`media_sniff.py`),
  never the Content-Type or the name; ffprobe must then read a picture
  (image) or a stream with a length (video/audio). A container with video
  is a video, one with audio only is audio. Kinds: image (or logo if asked),
  video, audio; a `kind` that does not fit the file is 422.
- Size limits: image 25 MB, audio 300 MB, video 2 GB (checked while copying
  and after ffprobe says what it is).
- The same bytes twice are 409 (the directory is named by the hash).
- Delete is 409 while a clip's current timeline plays the asset. Older
  versions of a clip are not checked: restoring one that plays a deleted file
  fails the timeline check (422), as for any missing asset.
- Thumbnails: PNG for images and logos (keeps transparency), a JPEG frame at
  min(1 s, half the length) for video, a PNG waveform for audio.

## 2026-11-02 — TASK-103 T35c Section ops UI

- No third-party API is new (React, lucide icons and the browser's HTML5
  drag and drop events, which the section list uses; MDN
  `HTMLElement: dragstart event`, checked 2026-11-02), so nothing else was
  checked against docs.
- The ops live in a "Sections" panel of the editor rail (`SectionMenu`, with
  `SectionList` and `SectionPicker`), not on the timeline: the timeline
  shows source time, while sections play in their own order.
- The ops act on the saved clip, so they are disabled while the editor has
  unsaved edits or a save/render runs (the autosave saves within 2 s). The
  clip an op answers replaces the editor's (`edits.reset`), as a history move
  does.
- Rearranging: drag a row onto another, or its arrows (keyboard); it sends
  `POST .../sections/reorder`. Duplicate and split-into-two-clips are clip
  ops (T35b); "Split section in two" is the section op (T35a). All splits use
  the playhead and need it at least 0.1 s inside a section.
- The add-section picker lists the source's transcript lines (the 50 nearest
  to the clip, narrowed by a search box); a line that overlaps a section is
  disabled; the added section plays last. New `GET
  /api/projects/{id}/transcript` serves the transcript (the same
  `Transcript` model as `transcript.json`; 409 if it is missing).
- After a duplicate or split a link to the new clip shows in the panel; the
  editor stays on the clip.

## 2026-11-02 — TASK-102 T35b Duplicate clip + split one clip into two

- No third-party API is new (SQLModel rows and pydantic copies only), so
  nothing needed checking against docs. The code is in `clip_split.py`, not
  `clip_edit.py` (that file is at the 300-line limit); `api/clip_copies.py`
  serves `POST /api/clips/{id}/duplicate` (201, the copy) and `POST
  /api/clips/{id}/split` `{at}` (201, `[first, second]`).
- Duplicate: a new `candidate` clip, no render, title "<title> (copy)",
  everything else copied; layer items get new ids (`<track>-<hex>`), the
  video items keep `video-<n>`.
- Split takes a source time (like section split), snapped to the nearest
  frame counted from the clip's start (`frame_at`), so the parts' lengths
  add up to the clip's. It must be inside a section (the section is cut in
  two) or on the edge between two sections in play order. The clip keeps the
  sections that play before (its id, status and render stay, as for the other
  section ops: render again); a new `candidate` clip gets the rest, with no
  hook and the title "<title> (part 2)".
- Cut ranges are cut at the split; caption overrides and marks go by their
  start (`[start, end)` of a section); zoom and crop keyframes by `[start,
  end]` (one on the split goes to both, so both ends keep their value);
  scenes are refitted to each part's span; layer items (timed in the
  rendered clip) are cut at the time the first part lasts, the second part's
  moved to 0, with an audio/video asset's `offset` advanced for an item that
  starts before the split; items under one frame are dropped.
- Lengths add up exactly when the sections are in source order without
  gaps; with gaps or a new order each part rounds its cuts to frames from its
  own start, so the sum can differ from the clip by up to a frame.
- A split that leaves either part without any frame (cuts over it) is 422,
  as is a time outside every section; nothing is changed then.

## 2026-11-02 — TASK-101 T35a section ops backend

- A clip's `segments` are its sections in play order (no overlaps, gaps
  allowed); `start`/`end` stay the earliest start and latest end. The render,
  preview, clip length and captions now follow them (`pipeline/sections.py`):
  the gaps between sections are cut like cut ranges and the kept parts play in
  section order. One section gives exactly the v1 kept spans (frame-rounded
  the same way), so v1 clips render unchanged.
- Captions are retimed onto the cut timeline in source order, then each word
  moves with the kept part holding its start (`reorder_words`; its end is
  clamped to that part).
- Ops (`clip_edit.py`, `api/clip_sections.py`, each a clip version):
  trim/extend `PUT /clips/{id}/sections/{i}` clamps to `[0, duration]` and to
  the neighboring sections in source time (no overlap); add `POST
  /clips/{id}/sections` `{start, end, index?}` clamps its end to the source,
  appends without `index`, and refuses an overlap or `index > len` (422);
  split `POST .../sections/split` `{at}` takes a source time inside a
  section (sections are found by source time, so the editor need not map
  output time); `POST .../sections/reorder` `{order}` needs a permutation;
  `DELETE .../sections/{i}` refuses the only section (422). A missing
  section index is 404, a rendering clip 409. A section is at least one frame.
- After an op, cut ranges outside every section are dropped and ones
  crossing a section edge are clipped (`fit_cuts`); the video track is rebuilt
  from the sections; scenes are refitted when the span changed. An op whose
  cuts would leave nothing is refused (422).
- `PATCH` start/end (`respan`) now moves the earliest section's start and the
  latest section's end, keeping the play order.
- The preview cache key hashes the segments (order matters) instead of
  start/end.
- Cut math moved from `pipeline/polish.py` to `pipeline/frame_cuts.py`
  (polish was over 300 lines); shared test flashes helpers to
  `tests/flashes.py`.
- Third-party API check (2026-11-02, https://ffmpeg.org/ffmpeg-filters.html#trim,
  https://ffmpeg.org/ffmpeg-filters.html#concat, local ffmpeg 9.0.2 `ffmpeg -h filter=concat`: options n, v, a): no new
  filters; `trim`/`atrim` + `setpts=PTS-STARTPTS`/`asetpts` per kept part and
  `concat=n=N:v=1:a=1` join the segments in input order, so rearranged parts need
  no graph change. Verified by `tests/pipeline/test_section_render.py`
  (ffprobe duration and flash/beep onsets in rearranged order).

## 2026-11-01 — TASK-96 captions v2 editor UI

- The spec lists a per-word "color" but `CaptionMark` had none: added
  `CaptionMark.color` (nullable). The spoken word keeps the highlight color;
  otherwise a marked color beats the emphasis and speaker colors.
- The components live in `components/editor/` (`CaptionsPanel.tsx`,
  `WordEditor.tsx` and smaller pieces of at most 300 lines), next to the other
  editor panels, not in `components/CaptionPanel.tsx`/`WordEditor.tsx`.
- Library check (2026-11-01, installed source `node_modules/radix-ui` 1.8.1,
  `@radix-ui/react-dropdown-menu` types): `Popover` (Root/Trigger/Portal/
  Content) for the word popover, `DropdownMenu` (`modal`, `Item asChild`) for
  the transcript download links.
- The live preview is the server's PNG (`POST /caption-templates/{name}/
  preview`, debounced 300 ms) with the template fields only; while it loads or
  fails the client sample shows. Replace everywhere is blocked while the clip
  has unsaved edits, and the edits are re-based on the saved clip after it.

## 2026-11-01 — TASK-199 caption styles and fonts

- New looks are new `animation` values, not new template fields: the template
  schema is closed (`extra=forbid`) and a test pins its field set.
- "Colors saved into presets" is `ProcessingSettings.caption_colors`, applied
  to each new clip's `caption_style`. A color equal to the chosen template's is
  stored as unset, so changing template still brings that template's colors.
  Per-clip colors already worked through PATCH `caption_style`.
- Fonts come from google/fonts at a pinned commit; only OFL and Apache 2.0
  files are bundled, and a test fails for any font without its own license
  file and `LICENSES.md` row (with SHA-256).

## 2026-10-31 — TASK-41 clips gallery

- "Remove" needed an API that did not exist: new `DELETE /clips/{id}` (204;
  deletes the row, its jobs by cascade, and the rendered mp4, SRT, metadata
  and previews; 409 while the clip renders). The browser asks `confirm()`
  first (no dialog component yet).
- The 2-line snippet is the clip's `description` (the LLM summary), not the
  transcript: the API has no transcript text for a clip.
- Search, sort and min score run in the browser on one `GET
  /projects/{id}/clips` (the list is small), with the same rules as the
  endpoint's query parameters; sort "Shortest" counts the length without cut
  ranges.
- Clips are candidates until rendered. The download button of a candidate
  queues `POST /clips/{id}/render` and shows a spinner while a render job of
  the clip is queued or running (the project's jobs are polled every 2 s then,
  and the clips reload when that set changes); a rendered clip links to
  `/clips/{id}/download`. "Download all" links to `download.zip` once every
  clip is rendered, else it renders the clips that are not.
- The score breakdown is a click popover (docs/ui-layout.md) with Hook, Flow,
  Value, Trend bars and the reason, not an inline expansion (it would move
  the cards of its row).
- The hover preview is `GET /clips/{id}/preview` (the first request after an
  edit renders it, so it may take a moment), over the project's thumbnail as
  a placeholder. "Edited" = the clip has cut ranges or reworded captions.
- Left out for v1: grid/list toggle, multi-select with bulk bar (SPEC 8.4 has
  neither). "Edit" links to `/clips/{id}`, the editor route of TASK-45+; until
  then it lands on Home. Columns: auto-fill, 10.5 rem minimum (6 at 1440 px).

## 2026-10-31 — TASK-40 processing view

- The seven listed steps map onto the job's steps: Analyze audio = signals +
  enrich, Score = score + snap, Captions = render (it burns the captions in).
  Every listed step weighs the same in the overall bar.
- The live log shows one line per change of listed step or status, built in
  the browser from the SSE events; there is no log endpoint, so a page opened
  later starts with the current state only. Elapsed time counts from the
  project's `created_at` (the job has no timestamps) and is hidden for a job
  that was already over when the page opened.

## 2026-10-30 — Repository scaffold

- Keep the backend package under `backend/clipforge` and add it to the wheel
  configuration. This follows the repository layout in SPEC 3 without
  introducing placeholder modules before their tasks.
- Use uv dependency groups for development tools, leaving application
  dependencies separate.
- Select TensorFlow Hub or ONNX for YAMNet only when the audio-analysis task
  verifies installation on macOS arm64, as required by SPEC 2.

## PRD section 11 decisions

- Add `GET/PUT /api/settings` and `POST /api/settings/test-llm` because SPEC 8.7
  needs settings operations omitted from SPEC 7; this is the smallest coherent
  API extension.
- Keep TASK identifiers as the execution list and preserve SPEC T-identifiers
  in titles.
- Complete one task per iteration, run `make check`, and commit with the task
  identifier; maintain `docs/HANDOFF.md` between iterations.

## 2026-10-30 — TASK-3 frontend scaffold

- Initialize shadcn/ui with its Vite template, Radix base, and Nova preset.
  Tailwind CSS v4 uses its Vite plugin and CSS-first configuration, so no
  separate Tailwind config file is needed.
- Use the PRD section 8 palette: ember orange `#ff6b35` accent on zinc-950/900
  surfaces, with the Geist Variable font. (Corrected 2026-10-30: the first
  scaffold used violet; the PRD does define the colors.)
- Keep the app in React 18.3.1 and TypeScript 5.9.3. TypeScript 7 did not meet
  the installed `typescript-eslint` peer range.

## 2026-10-30 — TASK-5 configuration defaults

- Use `Credit: {channel}` as the default credit template so project and channel
  attribution can be rendered without hardcoding a specific creator.
- Apply SPEC 13.1's Copilot amendment to configuration defaults and the
  environment example: Copilot is the default provider, with OpenAI-compatible
  and Ollama options retained.

## 2026-10-30 — TASK-6 data models

- `Project.status` reuses the job status values `queued|running|done|failed`:
  SPEC 5 names the field without values, and a project's status mirrors its
  processing job.
- Add `Clip.emphasis_words: list[str]`. SPEC 6.9 highlights a clip's
  `emphasis_words` in its captions, but SPEC 5's `Clip` omits them, and
  captions run after snap has stored the clips.
- Length presets: `lt30` keeps clips with 0 < length < 30 s; `30_60`, `60_90`,
  `90_180`, and `auto` (`clip_min_s`..`clip_max_s`) are inclusive at both
  ends. Lengths are rounded to milliseconds before comparison so float noise
  (42.3 - 12.3 = 29.999999999999996) cannot drop a valid clip.
- Fractions use 0..1: `SignalEvent.intensity` (SPEC), `Scores.laugh`,
  `Scores.energy`, `Job.progress`, and `BrandTemplate.logo_opacity`.
  `Scores.overall` and the hook/flow/value/trend scores are integers 0..99,
  matching the SPEC 6.6 formula and the `ClipCandidate` limits.
- `ProcessingSettings` defaults: genre `auto`, length preset `auto`, aspect
  `9:16`, caption template `karaoke_bold` (first SPEC 6.9 template), fillers
  kept, optional fields `None`, and `num_clips` from config
  `default_num_clips` (validated 1..30). Timeframe bounds must be >= 0, and
  the end must be after the start (which defaults to 0).
- `BrandTemplate.name` must be non-empty and `primary_color` must be
  `#RRGGBB`. Path fields are strings, like SPEC's `output_path: str|None`.
- Stored entities (`Clip`, `Project`, `Job`, `BrandTemplate`) have no field
  defaults; create/update payload models will be added with the endpoints
  that need them.

## 2026-10-30 — TASK-7 database

- The schema lives in numbered SQL files under `migrations/` at the
  repository root (located relative to `db.py`). `migrate()` creates and owns
  `schema_version`, applies each pending file and its `schema_version` row in
  one transaction, and stops at the first failure. Migration files must not
  contain BEGIN/COMMIT/ROLLBACK.
- Foreign keys are switched off while migrating (so a future table rebuild
  cannot cascade deletes), and `PRAGMA foreign_key_check` must pass before a
  migration commits.
- Deleting a project cascades to its clips and jobs, and deleting a clip
  cascades to its render jobs, through `ON DELETE CASCADE` in the database
  rather than ORM relationships, so raw SQL deletes cascade too.
- Ids use AUTOINCREMENT, so a deleted row's id is never reused and leftover
  `data/work/<job_id>/` or `data/output/<project_id>/` files cannot attach to a
  new row.
- Nested model fields (`settings`, `hashtags`, `emphasis_words`, `scores`,
  `caption_overrides`, `cut_ranges`) are JSON text columns validated by their
  Pydantic types on write and parsed back on read. They are not queried by
  SQL, so no JSON1 queries or extra tables are needed.
- New rows default to their initial lifecycle state: project and job
  `queued`, clip `candidate` with no cut ranges, caption overrides, or output;
  `created_at` is now (stored as UTC). Other fields are required.
- `brand_template_id` stays inside the project settings JSON rather than
  becoming a foreign key, so deleting a template never touches projects;
  rendering must handle a template that no longer exists.
- `sqlalchemy` is a direct dependency because `db.py` imports it (it was
  already locked at 2.1.6 through sqlmodel).
- The table is named `job`, matching the task and the other singular table
  names (SPEC 2 says "jobs table").

## 2026-10-30 — TASK-8 fixture

- The script writes `expected.json` from the same shell constants it uses
  to build the media, so the two cannot drift. The fixture files are
  committed; tests read them and never regenerate them.
- Video: testsrc2 with `gblur=sigma=2` (its per-frame random noise made an
  unblurred file 23 MB), libx264 `-preset slower -crf 28`, giving a 2.8 MB
  fixture. The face overlay is added after the blur, so it stays sharp.
- Face: drawn with `geq` (skin-tone head ellipse with shading, hair, brows,
  eyes, nose, mouth) as one 240x300 RGBA frame repeated by `overlay`
  (`eof_action=repeat`); its centre moves linearly from x=200 to x=1080 at
  y=360. A throwaway check with mediapipe 1.2.0 (Tasks API FaceDetector,
  `blaze_face_short_range.tflite`) detected it in 30/30 frames sampled every
  2 s (score 0.74-0.95), so no OFL/CC0 face image is needed; TASK-22 should
  still verify detection with the version it locks.
- Audio: mono 48 kHz AAC 64 kb/s. Speech is a 120-180 Hz phase-integrated
  FM tone with two harmonics and a 4 Hz syllable envelope at about -28 dBFS
  RMS; laughs are seeded pink noise (`anoisesrc`) at about -16.5 dBFS
  (replaced by real CC0 laughter: "TASK-16 fixture laughs" below). Bursts
  have 30 ms linear fades and digital silence between them.
- Timeline: phrases of 2.2-2.8 s separated by 0.55-0.8 s pauses (some over
  0.6 s for filler-pause removal), three 0.35-0.4 s bursts reserved for the
  filler words of TASK-9, and three laughs (2.5 s, 2 s, 3 s) each starting
  0.3 s after a phrase ends: 3 laughs per minute, above the 1 per minute at
  which genre "auto" selects the comedy prompt.
- Determinism: fixed noise seed, `-threads 4`, `-fflags +bitexact` and
  `-flags:v/-flags:a +bitexact`, so reruns with the same ffmpeg build
  produce identical bytes. Title tag "ClipForge sample fixture" lets ingest
  tests check metadata.

## 2026-10-30 — TASK-9 transcript and LLM fixtures

- Canonical transcript form, which TASK-12 must normalize faster-whisper
  output to: word `text` has no whitespace but keeps attached punctuation
  ("says," "floor?"); `segment.text` is the word texts joined by single
  spaces; segment ids are 0-based and sequential; one segment per sentence
  (only its last word ends with . ? or !); segment start/end are its first
  word's start and last word's end.
- The transcript is an original stand-up set written for the fixture. Word
  times fill each speech burst of `sample.mp4` exactly (first word starts
  at the burst start, last word ends at the burst end, 0.04-0.12 s gaps
  inside a burst), so audio-based and word-based checks agree.
- Fillers (SPEC 6.10): "Um," (6.75-7.15), "Like," (23.25-23.6) and "Uh,"
  (42.1-42.45) each fill a short burst alone, with at least 0.55 s of
  silence on each side ("Like,": 0.80 s before, 0.70 s after). "like" in
  "It watches me like a hawk." is part of a phrase and must be kept.
- Snap starts (SPEC 6.7): segments 1 and 12 start mid-burst (a segment
  start with no silence before it), and 7 words follow a pause of at least
  0.35 s without starting a segment ("so" 7.7, "why" 11.1, "it" 24.3, "we"
  30.65, "it" 43.0, "and" 46.4, "recalculating" 49.35).
- Candidates in `llm_response.json` (average = mean of hook, flow, value,
  trend):
  - 0 "D" 1.5-32.9 (31.4 s, average 64.0): weaker cut of A, listed first.
  - 1 "A" 0.5-35.2 (34.7 s, average 82.0): yoga + fridge bits.
  - 2 "B" 16.9-54.9 (38.0 s, average 73.5): fridge + car bits.
  - 3 "C" 35.8-59.5 (23.7 s, average 68.0): car bit + sign-off.
  - 4 "E" 0.5-16.3 (15.8 s, average 75.0): yoga bit only.
- Only D and A overlap with IoU > 0.5 (0.905; the next highest pair is
  0.457). D is listed first so that a dedupe keeping the first of a pair,
  instead of the higher LLM average, fails. No two averages are equal.
- Expected curate result with default settings (preset `auto`, 20-75 s):
  validation drops E ("length 15.8s is outside the auto range (20-75s)"),
  dedupe drops D, leaving A, B and C. Preset `lt30` keeps C and E; `30_60`
  keeps D, A and B; `60_90` and `90_180` keep none.
- Laugh windows ([end - 3, end + 2], TASK-20): A, B, D and E overlap a
  laugh; C overlaps none.
- The fixture loaders (strict `model_validate_json(..., strict=True,
  extra="forbid")`) live in `test_fixtures_valid.py`; move them to a shared
  `backend/tests/conftest.py` when a second test module needs them.

## 2026-10-30 — TASK-10 ffmpeg wrapper

- `MediaInfo` has exactly the fields of `expected.json` `media` (duration,
  width, height, fps, video_codec, pix_fmt, audio_codec, sample_rate,
  channels, title), so `asdict(probe_media(sample.mp4)) == media`.
- width/height are the displayed size: a rotation of ±90/270 in the
  stream's display matrix swaps them, matching the frames ffmpeg decodes
  (autorotate is on by default). fps is `avg_frame_rate` (falls back to
  `r_frame_rate`): for variable-rate phone video the base rate can be far
  from the real rate (test clip: avg 20.7 vs r 30).
- `probe_media` raises `FFmpegError` for files without a usable video
  stream (cover art with `attached_pic` does not count), without a
  duration (still images) or without a frame rate. Audio fields are None
  when there is no audio; title is None when the tag is missing or empty.
- `run_ffmpeg` always passes `-nostdin -hide_banner -nostats -loglevel
  <level> -y`; the default level `error` keeps stderr empty on success.
  It returns the `CompletedProcess` (stdout and stderr bytes) so callers
  can pipe raw output and read info-level reports such as loudnorm's
  JSON (TASK-28 passes `loglevel="info"`).
- Path arguments become absolute paths, so names like `-clip.mp4` are
  never read as options. Strings pass through unchanged (filters, `-`).
- `FFmpegError` keeps the command and the last 20 stderr lines (at most
  2000 characters) and ends its message with them. A missing binary
  raises `FFmpegError` ("ffmpeg not found on PATH; install it with `brew
  install ffmpeg`"), not FileNotFoundError.
- The helpers write straight to `dst` (no temp file + rename); pipeline
  steps own skip/atomicity (e.g. TASK-11 writes meta.json last). No
  timeout parameter yet (nothing needs one).
- `extract_frame` seeks on the input (`-ss` before `-i`) and saves the
  first frame at or after the time; JPEGs use `-q:v 2`. A time past the
  last frame fails with ffmpeg's "Nothing was written into output file"
  error, so no extra existence check is needed. `extract_audio_wav` takes
  the first audio stream (`-map 0:a:0`) and has no start/duration options
  yet (TASK-12 may add them).
- Shared test fixtures `sample_mp4` and `expected` moved to
  `backend/tests/conftest.py`; the strict transcript/LLM loaders stay in
  `test_fixtures_valid.py` until another module needs them.

## 2026-10-31 — TASK-11 ingest step + `clipforge step` CLI

- Steps follow SPEC 6: module `clipforge.pipeline.<name>` with
  `run(job_dir, settings, *, force=False) -> Path` (main output path).
  `StepSettings` (frozen dataclass in `pipeline/step.py`) carries `source`
  (URL or path), `processing` (the project's `ProcessingSettings`), `cfg`
  (app `Settings`, read lazily) and `on_progress`. `load_step(name)`
  imports only the requested module, so one step never loads another
  step's heavy libraries; `STEP_NAMES` grows as steps land.
- Job work dir is `{data_dir}/work/{job_id}/` (SPEC 3); `Job.progress` is
  the current step's fraction 0..1 (TASK-31 may map it to overall).
- Ingest outputs: `source.mp4`, `audio.wav`, `thumb.jpg`, `meta.json`
  (`SourceMeta`, in `models.py`). meta.json is written last (via
  `meta.json.tmp` + `os.replace`) and is the skip marker; a forced or
  interrupted rerun deletes it first. source.mp4 goes through
  `source.tmp.mp4` too.
- Codec rules, per stream: h264 with 8-bit 4:2:0 (`yuv420p`/`yuvj420p`,
  what browsers play) and aac are copied; other video is encoded with
  libx264 `-crf 18 -pix_fmt yuv420p` (default preset) after an even-size
  scale, other audio with ffmpeg's aac (default bitrate). An MP4-family
  file (ffprobe `format_name` contains `mp4`; this includes .mov) whose
  streams both qualify is copied byte for byte (a download is moved).
  Only the first video (`0:V:0`, which skips cover art) and first audio
  stream are kept; a video without audio is a StepError (needs speech).
  The container check uses an extra `ffprobe_json` call instead of a new
  `MediaInfo` field, because `MediaInfo` mirrors `expected.json`.
- URLs: yt-dlp with SPEC's exact format `bv*[height<=1080]+ba/b[height<=1080]`
  and `merge_output_format: mp4`, saved as `download.<ext>` in the job dir
  then moved or converted to source.mp4. `noplaylist` plus
  `extract_flat: in_playlist`: a playlist is rejected (StepError) after
  extraction and before any download. yt-dlp messages go to the
  `clipforge.pipeline.download` logger (`color: never`, `noprogress`);
  `YoutubeDLError` becomes `StepError("download failed: ...")`.
  Known limit: SPEC's format needs a height, so direct file links without
  height info fail with "Requested format is not available".
- Timeframe is stored in meta.json, not cut: start defaults to 0, end to
  the duration; an end past the video is clamped (logged); a start at or
  after the end of the video is a StepError.
- Title: yt-dlp title, else the file's title tag, else the file name stem.
  `channel`/`channel_url` (uploader fallback) are kept for the SPEC 6.12
  credit line; None for local files.
- Progress: download 0..0.6 (per file, never decreasing), source ready 0.7,
  audio 0.85, thumbnail 0.95, meta 1.0. The CLI saves it rounded to 0.01,
  only on change.
- CLI: argparse, `clipforge step <name> <job_id> [--force]`, installed as
  a `[project.scripts]` entry. Prints the output path; exit 1 with
  `clipforge: error: ...` for a missing job or a StepError/FFmpegError,
  2 for bad arguments. It sets `Job.step`/`Job.progress` only; status,
  error and log_path belong to the job runner (TASK-31), and copying
  title/duration/thumbnail to the project row to the API tasks.
- `types-yt-dlp` (typeshed stubs) is a dev dependency so mypy strict
  checks the yt-dlp calls; `_YoutubeDLOptions` is imported only under
  `TYPE_CHECKING` (it is a stub-only TypedDict).

## 2026-10-31 — TASK-12 transcribe step (faster-whisper, chunked)

- Model files live in the project: `Settings.models_dir` (default
  `models`, git-ignored), whisper in `models/whisper/<name>` (a repo id
  `org/name` becomes `org--name`). `scripts/download_models.py` (run by
  `make setup`) fetches it with `huggingface_hub.snapshot_download`
  (`local_dir`, faster-whisper's file patterns) instead of
  `faster_whisper.download_model`, which always hides progress bars.
  HF_HOME defaults to `models/huggingface`, so the Hub's own metadata and
  caches stay in the project too. An existing model is skipped unless
  `--force`.
- The transcribe step never downloads: a missing model is a StepError
  that names the download command, so a pipeline run needs no network.
  A broken model (CTranslate2 RuntimeError) is a StepError too.
- `WhisperModel(dir, device="auto", compute_type="int8")` (SPEC 2); on
  the Mac it runs on the CPU as int8_float32. `cpu_threads` stays at
  faster-whisper's default (4): on the M4 Max 8 threads were only 13%
  faster on 60 s of speech (6.8 s vs 7.9 s) and 12 threads were slower.
- `transcribe(..., word_timestamps=True, vad_filter=True)`. The VAD
  filter (Silero, bundled) is not in SPEC; without it the small model
  turned 5 s of digital silence into garbage text ("nn" language) and
  tiny into "You". faster-whisper maps the times back to the chunk's
  time (`restore_speech_timestamps`).
- Chunks: only the meta.json timeframe is transcribed, in chunks of
  `chunk_minutes` that overlap by `chunk_overlap_s` (the last one may be
  shorter), each cut from audio.wav with ffmpeg `-ss`/`-t` into a temp
  dir inside the job dir. The language is detected in the first chunk
  with words and passed to the later chunks (Whisper itself also detects
  once per file); with no words at all, the first detection is kept.
- Overlap dedupe (`transcript_merge._splice`): consecutive chunks are
  spliced at a word both heard (texts equal after casefold and dropping
  punctuation, starts at most 1 s apart, aligned with difflib), the pair
  closest to the middle of the overlap; words near a chunk edge (where
  Whisper may cut or invent) are therefore never used. Without a common
  word the cut is at the middle of the overlap; if one chunk heard
  nothing in the overlap, the other's words are kept. Times are then
  made monotonic (each end <= the next start).
- Segments are sentences, like the fixture transcript: a word ending in
  `. ? ! …` (or CJK `。！？`, maybe before closing quotes) ends one, except
  common abbreviations (Mr., Dr., e.g., ...); unpunctuated speech is cut
  at a Whisper segment end once it lasts 20 s. Word text is stripped;
  segment text keeps Whisper's spacing (so CJK has none). Times and
  probabilities are rounded to 3 decimals.
- `Transcript.duration` is the whole video's duration (meta.json), not
  the timeframe's; word times are source times.
- Diarization is not built: pyannote is not installed (it would add
  PyTorch), its model is gated behind an HF token we do not have,
  and its API cannot be verified here (SPEC 0.1). Every word is "S0"; if
  HF_TOKEN is set the step logs a warning. See docs/questions.md.
- `write_json` (atomic tmp + `os.replace`, used by ingest too) and
  `load_meta` moved to `pipeline/step.py` with the job file names
  (`SOURCE`, `AUDIO`, `THUMB`, `META`), since every later step needs them.
- `make lint` now also checks `scripts/` (ruff) and
  `scripts/download_models.py` (mypy strict).

## 2026-10-31 — TASK-13 LLM clients (T06a)

- `backend/clipforge/llm.py`: the `LLMClient` protocol
  (`complete_json(system, user) -> str`), `CopilotClient` (default),
  `OpenAICompatClient`, `OllamaClient` and `create_client(cfg=None, *,
  transport=None)`, which picks the client by `LLM_PROVIDER`. The HTTP part
  (`post_json`, `LLMError`, `join_url`) is in `llm_http.py` to keep both
  files under 300 lines; `LLMError` is re-exported from `clipforge.llm`
  through `__all__` (mypy strict allows no implicit re-exports).
- HTTP library: httpx 0.28.1 (added; the SPEC names none). A new
  `httpx.Client` per request: no client lifecycle to manage, safe across
  threads, and the connection setup is negligible next to model latency.
  Timeout: 300 s, 10 s to connect (curating a long window on a local model
  can take minutes).
- Copilot (SPEC 13.1): POST https://api.githubcopilot.com/chat/completions
  with `Authorization: Bearer <token>`, `Copilot-Integration-Id:
  vscode-chat`, `Editor-Version: clipforge/<version>` and the OpenAI body.
  The token is GITHUB_COPILOT_TOKEN, else `gh auth token -u omairtemurian
  -h github.com`, run on the first request (building a client never runs
  gh) and kept for the client's life. The gh account and host are
  constants, not settings: SPEC 13.1 fixes them.
- OpenAI-compatible: no Authorization header when OPENAI_API_KEY is empty
  (local servers need none). URLs are joined with exactly one slash and
  keep the base's path (`/inference`, `/v1`).
- Bodies: model, the system and user messages, and JSON mode
  (`response_format: {"type": "json_object"}`; Ollama `format: "json"`,
  `stream: false`). No temperature or max_tokens: SPEC sets none, and some
  reasoning models reject them.
- The reply text is returned as it is: curate (TASK-14) parses and
  validates it and sends the errors back to the model. Only the envelope
  is checked (OpenAI `choices[0].message.content` must be a string, Ollama
  `message.content`); a missing or null content (a refusal) or a body that
  is not JSON is an LLMError "unexpected reply" naming the field.
- Errors: `LLMError(message, status_code=None)`. Messages start with the
  provider and include the URL; HTTP errors add the status and the body on
  one line, cut to 500 characters ("…" when cut, "(empty body)" when
  empty). The credential is replaced by `***` wherever the server's text
  is quoted and is never logged: one INFO line per call, "<provider>
  <model> replied in <s>s". The pydantic ValidationError is dropped from
  the chain (`from None`) because its message quotes the reply. gh
  failures read "copilot: no token: <gh's stderr>; set
  GITHUB_COPILOT_TOKEN or run `gh auth login -h github.com` as
  omairtemurian".
- No model listing (GET /models): nothing needs it yet.
- Test doubles live in `backend/tests/fakes.py` (outside the package;
  `backend/tests` is on the pytest pythonpath): `FakeLLMClient(*replies,
  repeat_last=False)` returns str or Path replies in order (a Path is read
  when its turn comes), returns `fixtures/llm_response.json` forever when
  given none, records prompts in `.calls`, and raises AssertionError when
  the replies run out; `FakeLLMServer` is an `httpx.MockTransport` that
  records requests, with `openai_reply`/`ollama_reply` bodies. Tests mock
  only the HTTP server and `subprocess.run` (gh).
- Live tests carry the `live` marker; the root conftest skips them unless
  the `-m` expression names "live" (`uv run pytest -m live`), so `make
  check` lists them as skipped and needs no network or credentials.

## 2026-10-31 — TASK-14 curate (T06b)

- Input: SPEC 6.5 splits enriched.txt, but enrich (TASK-18) comes later and
  TASK-15 runs ingest -> transcribe -> curate -> render. Until then curate
  formats transcript.json itself as SPEC 6.4 lines without markers:
  `[mm:ss.s-mm:ss.s] S0: text`, one per segment, whitespace collapsed,
  empty segments left out. TASK-18/19 switch the input to enriched.txt
  and the prompt to `curate_<genre>.md`.
- Time format: rounded to 0.1 s with Python `round`; minutes keep
  counting past 59 ("62:05.0"). The prompt shows how to turn mm:ss.s into
  seconds, because ClipCandidate times are seconds.
- Windows reuse transcribe's `plan_chunks` over the meta.json timeframe
  (0-1500 s with 10 min / 60 s -> [0,600], [540,1140], [1080,1500]). A
  line belongs to every window whose half-open range [start, end) holds
  its start, so lines in an overlap go to both windows and lines that
  start outside the timeframe to none. A window without lines is not
  sent.
- Prompt (`prompts/curate_base.md`, own wording): `string.Template`
  placeholders (`$length_rule`, `$keyword_section`, `$schema`), so the
  JSON braces need no escaping. The schema is
  `json.dumps(ClipCandidate.model_json_schema(), indent=2)`. In live runs
  gpt-4.1 often proposed the fixture's 12-16 s jokes despite the length
  rule, so the final wording states the rule ("20 to 75 seconds", "under
  30 seconds" for lt30) three times, works out a clip length in an example
  and tells the model to join a short joke with the sentences around it;
  with it, 3 of 6 runs on the 60 s fixture kept a clip. The keyword
  section is added only for a non-blank keyword_prompt.
- Reply contract: `CandidateList` (`{"clips": [ClipCandidate]}`, pydantic
  lax mode, extra keys ignored) is both the reply model and the
  candidates.json format. A reply wrapped in a ```json block is unwrapped
  before parsing (some models do that even in JSON mode); that costs no
  retry.
- Retries: only for replies that fail to parse/validate, up to 2 per
  window (3 calls). The retry is single-turn: the same system prompt and
  the window's lines, plus "Your previous reply for this transcript was
  not valid:" and the errors as "- clips.0.title: <msg>" lines ("reply"
  for invalid JSON; at most 20, then "... and N more errors"). Inputs and
  URLs are left out of the errors, so the bad reply is never echoed into
  prompts or logs. After the last failure the window is skipped with a
  WARNING and no exception; if every window fails, candidates.json is
  `{"clips": []}` (WARNING "kept 0 of ..."). An `LLMError` (unreachable,
  4xx/5xx, no token) is not retried: it becomes StepError "the LLM
  request failed: ...", since retrying cannot fix configuration.
- Clip lengths outside the preset are dropped, not retried: SPEC 6.5
  makes `validate_candidate` a filter, and a retry per bad clip would cost
  a full LLM call per window.
- Selection order: `fit_timeframe` (prompt times are rounded to 0.1 s, so
  a start or end up to 0.05 s outside the timeframe is moved onto it) ->
  `validate_candidate` (duration, length preset) -> inside the timeframe
  -> dedupe -> cap. Each drop is logged at INFO with the title and reason.
- Dedupe: greedy, by LLM average (mean of hook, flow, value, trend)
  highest first; equal averages keep the order they were proposed in; a
  candidate is kept unless its IoU with an already kept one is > 0.5. IoU
  rounds overlap and union to milliseconds, so float noise cannot turn an
  exact 0.5 into a duplicate. Then the best `max_clips_from_llm` are kept.
- The LLM client comes from `StepSettings.llm` (tests inject
  FakeLLMClient), else `create_client(settings.cfg)`.
- `load_json(path, model, step)` in step.py replaces load_meta's body so
  every step reports a missing input the same way ("... not found; run
  the transcribe step first"). `TRANSCRIPT` moved to step.py.

## 2026-10-31 — TASK-15 minimal render + `clipforge run` (T07)

- Output path: SPEC 6.11 and the task say
  `data/output/<project_id>/<clip_id>.mp4`; SPEC 3's tree shows
  `output/<job_id>/`. The clip's own path wins (a project can be
  reprocessed by later jobs; its clips stay in one directory).
- Render is not in STEP_NAMES: it runs once per clip and writes outside the
  job's work directory, so `clipforge step render` would have no single
  output. `process.run_process_job` renders after the steps, with
  `Job.step = "render"` and progress = clips done / clips.
- Crop: the largest centered window of the aspect's shape, its size and
  offsets rounded down to even pixels (yuv420p; ffmpeg's crop would floor
  them silently), then scaled to the exact SPEC size with `setsar=1`.
  `fps=` runs first, so crop and scale only process output frames.
- Verification: ffprobe must report the SPEC size, h264 yuv420p, aac and a
  duration within 0.2 s of end - start, compared to the millisecond. The
  file is written as `<clip_id>.tmp.mp4` and renamed only after the check,
  so a failed clip has no file (a bad `-preset` leaves an empty one). The
  AAC bitrate and crf are not checked by ffprobe (AAC bitrates are
  approximate); the pipeline test reads `crf=20.0` from the x264 SEI.
- Pass-through ordering until score/snap (T10a/T10b): the candidates of
  candidates.json are ranked by their LLM average (stable: ties keep the
  curate order) and the best `num_clips` become clip rows. overall = the
  average rounded with Python `round` (73.5 -> 74), hook/flow/value/trend
  from the LLM, laugh = energy = 0 (not measured yet), layout "fill",
  caption_template from the project's settings, status candidate.
  Superseded: score ranks the clips (TASK-20), snap moves their times onto
  words (TASK-21).
- A clip that fails to render is `failed` with no output_path and a
  WARNING, but the job and project are still `done`: the other clips are
  usable. `clipforge run` then prints "N of M clips failed to render
  (ids: ...)" and exits 1. A video without clips is done and exits 0
  (WARNING "job N found no clips in the video").
- Orchestration lives in `process.py` (`create_job`, `run_process_job`,
  `run_step` moved from cli.py), clip rows and their rendering in
  `clips.py`, so the T15a job worker can reuse them; cli.py only parses
  arguments and prints. The project's title, duration and thumbnail are
  copied from meta.json right after ingest. job.log
  (`Job.log_path = work/<job_id>/job.log`) gets the run's `clipforge.*`
  log records through a FileHandler, at the level the logging setup lets
  through (INFO for the CLI).
- Test mode (task note): `CLIPFORGE_TEST_MODE=1` plus
  `--fixtures-dir DIR`, both required; either one alone is a usage error
  (exit 2), and only the value "1" turns it on. DIR/transcript.json is
  copied into the work directory, so the real transcribe step skips its
  work, and curate gets `RecordedLLM`, which answers every prompt with
  DIR/llm_response.json. Everything else (ingest, curate's validation,
  render) is the real code. The package only reads files: no fake
  classes (test_fakes.py). The AC's "LLM_PROVIDER pointing to test mode"
  is this switch; LLM_PROVIDER keeps its three real values.
- `--num-clips` is validated by `ProcessingSettings` (1-30) inside
  argparse, so a bad value is a usage error before anything is written.
- The DB test fixtures (`data_dir`, `blank_engine`, `engine`, `rows`)
  moved from tests/unit/conftest.py to tests/conftest.py, so pipeline
  tests can use them.

## 2026-10-31 — review after TASK-15 (Hermes)

- OPENAI_BASE_URL default is https://api.openai.com/v1; GitHub Models
  (models.github.ai) was retired on 2026-07-30 (found in TASK-13).
- Diarization not built in v1 (SPEC 2 optional/off); all words speaker "S0".

## 2026-10-31 — TASK-16 signals: YAMNet laugh/applause (T08a)

- YAMNet backend: ONNX on onnxruntime 1.31.1, not TensorFlow Hub. Both were
  installed on this Mac (arm64, Python 3.11.15, uv 0.11.26):
  - TF Hub: tensorflow 2.21.0 installs (a 1.4 GB venv; a cold
    `import tensorflow` takes 19.9 s), but `import tensorflow_hub` (0.16.1)
    fails with `ModuleNotFoundError: No module named 'pkg_resources'`
    (setuptools 84.2.1 dropped it); it works only with `setuptools<81`.
  - ONNX: `audiomagic/yamnet-onnx` (Hugging Face) at revision
    f25b741c2f0bdc6d7e6db24b5fddda23347dbafd, a tf2onnx conversion of the
    official TF Hub archive (its README). On the fixture its 521 scores per
    frame match the official TF model within 2.4e-05. onnxruntime was
    already locked (faster-whisper's VAD); the model is 15 MB and scores
    60 s of audio in under 1 s on the CPU. `zeropointnine/yamnet-onnx` at
    ac2ca3bd45d12ec1f19f1144205ea529b4e9dedf matched too (a fallback).
  - `scripts/download_models.py` fetches it into `models/yamnet`, pinned by
    revision and sha256 (`model_files.YAMNET_SHA256`); a file with another
    sha256 is deleted and is an error. The step never downloads.
- Frames on the time line: YAMNet frame i reads [0.48 i, 0.48 i + 0.96] s
  and stands for its middle hop, [0.48 i + 0.24, 0.48 i + 0.72], so the
  frames tile time. With the defaults one inactive frame (a 0.48 s gap) is
  bridged and two (0.96 s) are not; one active frame lasts 0.48 s >= 0.4,
  so min duration only drops events cut by the timeframe's end. Whole
  windows would overlap by 0.48 s, so the gap and minimum would not mean
  what they say. In the hand check 11 of 12 first events started 0.17 s
  before to 0.32 s after the clip's sound. The model's float32 extra frame
  (38640 samples give 5, not 4) is dropped: frames = 1 + ceil((n - 15600)
  / 7680), at least 1 (`yamnet.frame_count`).
- Merge (pure `signal_merge.merge_active_frames`): active means score
  > 0.3; an active frame joins the event before it if the gap is <=
  laugh_merge_gap_s (1e-6 s tolerance); events shorter than
  laugh_min_duration_s are dropped. An event's mean class score is that of
  its active frames only (bridged inactive frames do not lower it).
- Classes: AudioSet "Laughter" (laugh) and "Applause" (applause), looked up
  by display_name in the model's class map (indexes 13 and 62 there). Baby
  laughter, Giggle, Snicker, Belly laugh, "Chuckle, chortle", Clapping,
  Cheering and Crowd are not used: SPEC 6.3 names laughter and applause.
- Loudness (`pipeline/loudness.py`, for TASK-17's silence and energy too):
  librosa RMS of 25 ms frames every 10 ms (YAMNet's STFT framing),
  center=False, in dBFS (ref 1.0), floor -100 dB. An event's level is the
  power mean of the frames centered in it; its baseline is the median of
  the frames centered in the 30 s around its middle, cut at the ends of the
  analyzed audio (the timeframe). intensity = score * clamp((level -
  baseline) / 12, 0, 1), rounded to 3 decimals like the times. Events of
  intensity 0 are kept (they were heard, just not louder).
- Only the meta.json timeframe of audio.wav is analyzed, in chunks of 125
  frames (60 s) that overlap by 7920 samples; that equals one pass (scores
  within 1.2e-7, identical RMS; tested with 7-frame chunks). Event times
  are source times.
- TASK-16 delivers `signals.detect_laughs_and_applause(job_dir, settings)
  -> list[SignalEvent]`; TASK-17 adds silence/energy/scenes, the step's
  `run` (signals.json) and its STEP_NAMES entry, as its task says. So
  `clipforge run` does not run YAMNet yet.
- The fixture is not changed: its pink-noise "laughs" are not laughter to
  YAMNet (questions.md); the expected.json laugh test is a strict xfail.
  Superseded by the owner's option B: "TASK-16 fixture laughs" below.

## 2026-10-31 — TASK-17 signals: silence, energy peaks, scene cuts

- One audio pass: `signals.detect_audio_signals` runs `analyze_audio` once
  (YAMNet scores + the 10 ms RMS envelope) and derives laughs/applause,
  energy peaks and silences from it (`pipeline/level_events.py`); scene
  cuts come from source.mp4 (`pipeline/scene_cuts.py`). The `signals` step
  runs between transcribe and curate (STEP_NAMES) and writes signals.json
  = `SignalList` (a JSON array of SignalEvent) sorted by (start, kind), in
  source seconds within the timeframe; times and intensities are rounded
  to 3 decimals.
- Frames on the time line: envelope frame k (25 ms, every 10 ms, centered
  at start + 0.0125 + 0.01 k) stands for the 10 ms around its center; the
  first frame reaches back to the timeframe start and the last forward to
  its end, so runs of frames tile the timeframe. A 0.5 s pause between
  tones is found as 1.0075-1.4875 s (frames that touch a tone are loud).
- Silence: a maximal run of frames below -40 dBFS lasting >= 0.35 s (1e-6 s
  tolerance); intensity 1 (it is there or not). Runs are never merged.
- Energy peak, SPEC "RMS z-score > 2 over a 10 s window", read as the
  z-score of a frame's RMS amplitude (10^(dB/20)) among the frames
  centered within 5 s of it (fewer at the timeframe's ends). Not dB: next
  to a silence the -100 dB frames dominate the spread. Two guards, found
  by trying speech (macOS `say`), tones and noise: a peak frame also needs
  at least 2x the window's mean RMS (+6 dB), since steady pink noise
  otherwise gave ~22 peaks (20 s) in 60 s, and must not be silent (at
  least -40 dBFS).
  Peak frames <= 0.5 s apart are merged and events < 0.2 s dropped, or a
  burst is a flicker of 10 ms events. Intensity = clamp((level - 30 s
  median level) / 12, 0, 1), as for a laugh of score 1. The fixture's
  peaks are its three laughs (the 3 s one in two parts: a long burst
  lowers its own z-scores); speech alone, tones, steady noise and silence
  have none.
- Scene cuts: PySceneDetect 0.7.2 `ContentDetector(threshold=27)` (default
  min_scene_len 15 frames: no cut in the first 0.5 s of the timeframe),
  used through `open_video` + `SceneManager`, which `scenedetect.detect`
  wraps (checked with help() and its source), so that the timeframe is
  read in 30 s slices with progress after each. The slices keep the
  detector's state and find the cuts of one pass (tested). A cut is an
  instant: start = end = the time of the new scene's first frame,
  intensity 1. Backend OpenCV (passed explicitly; also the default): 60 s
  of 1080p30 in 0.82 s, PyAV in 4.61 s. The library's `pyscenedetect`
  logger is set to WARNING (it logs "Detecting scenes..." per slice).
- Progress: the audio is the first 20 % of the step and the video the rest
  (10 min of 720p30: audio 1.1 s with the model load, video 5.0 s).
- opencv-python 5.0.0.93 (a scenedetect dependency) bundles its own FFmpeg
  (libavdevice 61) beside PyAV's (62), so macOS prints "objc[pid]: Class
  AVFFrameReceiver is implemented in both ... This may cause spurious
  casting failures and mysterious crashes." (and AVFAudioReceiver) in a
  process that loads both. Those are libavdevice's AVFoundation capture
  (camera/microphone) classes, which reading files never uses; scenedetect
  imports cv2 with either backend, so it stays, unsuppressed. TASK-22's
  mediapipe depends on opencv-contrib-python, which also provides `cv2`:
  keep only one, e.g. `[tool.uv] override-dependencies = ["opencv-python;
  sys_platform == 'never'"]`, and rerun the scene-cut tests.
- Whole-pipeline tests (`clipforge run`, the process job) now run YAMNet:
  they are `slow`, use `yamnet_cfg` (skipped without the model), and the
  `data_dir` fixture points models_dir at the project's models/.

## 2026-10-31 — TASK-18 enrich -> enriched.txt

- Enrich is its own step (`pipeline/enrich.py`), in STEP_NAMES between
  signals and curate, so `clipforge step enrich <job_id>` reruns it and
  `clipforge run` runs it. It owns the SPEC 6.4 line format
  (`PromptLine`, `timestamp`, `enriched_lines`, moved from
  curate_prompt.py). Until TASK-19 makes curate read enriched.txt, curate
  formats transcript.json with `enriched_lines(segments, [])`: the same
  lines, without markers.
- Lines: one per segment that starts in [timeframe_start, timeframe_end),
  as curate's windows, in transcript order; segments without text get no
  line. "[mm:ss.s-mm:ss.s] SPEAKER: text": start and end rounded to 0.1 s
  (Python's round, half to even), minutes past 59 for long videos;
  whitespace in the text collapsed to single spaces. Every line ends in
  "\n". Without speech in the timeframe the file is empty and a WARNING
  is logged: the step is done, and curate decides what no lines mean.
- Markers only for laugh, applause and scene_cut, the three that SPEC 6.4
  names. Silences and energy peaks stay out (the fixture alone has 20
  silences and 4 peaks a minute, which would bury the text); score and
  snap read them from signals.json. "[LAUGH 2.1s 0.85]" and
  "[APPLAUSE 3.0s 0.70]" give end - start with 1 decimal and the
  intensity with 2, as in SPEC's example; a scene cut is an instant:
  "[SCENE CUT]".
- Placement: a marker goes right after the last piece of text that starts
  before its event (`bisect_left` over the pieces' start times). So a
  laugh in the pause after a punchline ends the punchline's line, where
  the LLM reads it as the reaction to it; an event at a word's start goes
  before that word; one before the first word opens the first line and
  one after the last word ends the last line. Markers at one place are in
  order of (start, kind). Events have no place without lines and are left
  out.
- Pieces are the whitespace-separated parts of Segment.text, not the
  words: faster-whisper splits words at tokens with a leading space and
  glues them into the text, so "twenty-five" is the words " twenty" and
  "-five" (also " 50" "%", " well" "-known"; checked with the
  `models/whisper/small` tokenizer). A piece starts with its first word;
  if the words do not spell the pieces exactly, or there are none, the
  segment's whole text is one piece from the segment's start. Markers
  never split a piece, and a line's text is Segment.text with its
  whitespace collapsed and the markers added.
- Files are written atomically by the new `step.write_text` (path.tmp,
  then os.replace), which `write_json` now uses too.

## 2026-10-31 — TASK-19 genre prompts + auto genre

- Prompt layout: `curate_base.md` keeps what every genre shares (transcript
  format, marker legend, rules for each clip, keyword request, reply
  format) with a `$genre_rules` slot; `curate_<genre>.md` holds only "## The
  video" and "## Good clips" for comedy, podcast, talk and interview. Four
  full copies of the ~45 shared lines would drift apart. A genre file is a
  string.Template filled with the base's fields (write "$$" for "$").
- Comedy (SPEC 6.5): every clip is setup -> punchline -> laugh, starts at
  the start of a sentence before the setup and ends after the laugh
  marker. Lines carry no time for the marker itself, so the prompt says
  how: add the laugh's seconds to the end of the line it ends, but not past
  the next line's start, with a worked example. Live gpt-4.1 on the
  fixture with its expected laughs did exactly that (ends 13.5+2.5,
  32.8+2.0, 51.6+3.0).
- Podcast and talk (SPEC 6.5): strong first sentence hook, one complete
  idea, a satisfying end. SPEC has no interview rule; interview gets the
  same three read as question + answer (the hook may be the question),
  without relying on speaker labels (all S0 until diarization).
- Auto (SPEC 6.5 "laugh events > 1/min"): laugh events only (not
  applause) that start in [timeframe_start, timeframe_end), per minute of
  that timeframe (the part that is curated); strictly more than 1 is
  comedy, so exactly 1 per minute is podcast.
- The resolved genre is not stored: `genre.job_genre(job_dir, processing,
  meta)` recomputes it from signals.json (cheap, same answer) for curate
  now and score/snap later. signals.json is read only for "auto".
- Curate reads enriched.txt (`enrich.parse_line` takes the start from the
  "[mm:ss.s-" prefix) instead of transcript.json. Starts are rounded to
  0.1 s (half to even), so a line that starts at timeframe_start can show
  up to 0.05 s before it: the first window takes every line before its end
  and the last window every line after its start; inner windows are
  unchanged. Enrich already limits the file to the timeframe.
- `ContentGenre` is the four genres with a prompt and `Genre` is "auto" +
  ContentGenre: the same values, JSON schema enum and DB column as before.

## 2026-10-31 — TASK-20 score -> scored.json

- Laugh window (SPEC 6.6 "within [end-3s, end+2s]"): a laugh counts if its
  event overlaps the closed window, so one that starts before end-3 s and
  is still going counts (laughs are a signal over time, not points).
  Times are compared to the millisecond: 32.2 - 3 is 29.200000000000003
  in floats and must not drop a laugh that ends at 29.2. Applause does
  not count: SPEC names laughs only.
- Energy is the union of the energy peaks within the clip over its length,
  so overlapping peaks count once; the cap at 1 then only guards rounding.
- Weights: `cfg.score_weights` are always scaled to sum to 1 (the SPEC
  defaults already do), so a config like llm 3, laugh 1, energy 1 means
  60/20/20. For non-comedy genres laugh weighs 0 and the others are scaled
  up (0.8/0.2 by default). Unknown names, negative or non-finite weights,
  and no weight on the genre's components are a StepError. A name left
  out weighs 0 in `component_weights`, but pydantic-settings deep-merges
  the dict with config.yaml's, so in practice drop a component by
  setting it to 0.
- Stored scores: laugh and energy are measured (3 decimals) and kept in
  Scores for every genre, also when laugh weighs 0, so the UI can show
  them; overall is computed from the stored values and Python's round
  (half to even), so scored.json is self-consistent.
- Ties keep the order of candidates.json (stable sort), which dedupe
  leaves by LLM average.
- scored.json is `{"clips": [...]}` of ScoredCandidate (a ClipCandidate
  plus `scores`), best first, already cut to num_clips; the genre is not
  stored (`job_genre` again). `clips.save_clips` no longer ranks: it
  saves what it is given, in order; since TASK-21 that is snapped.json.
- `CANDIDATES` and `SCORED` live in step.py so score does not import
  curate (and its LLM stack). Signals only cover the timeframe, so score
  does not filter events by it.

## 2026-10-31 — TASK-16 fixture laughs: real CC0 laughter (owner option B)

- The owner answered questions.md (TASK-16) with B: the three laughs of
  sample.mp4 are now cut from a real recording instead of SPEC 9.1's pink
  noise, which YAMNet heard as Waterfall (Laughter <= 0.001), so the SPEC
  9.3 laugh check could not pass.
- Clip: `assets/sfx/crowd_laugh.flac` = 1.40-5.20 s of "crowd_laugh.wav" by
  moxobna, Freesound 76693,
  https://freesound.org/people/moxobna/sounds/76693/, license CC0 1.0
  (https://creativecommons.org/publicdomain/zero/1.0/) as stated on that
  page, checked 2026-10-31. Taken from the page's public HQ preview MP3
  (the WAV needs a login); mono, 48 kHz, 16-bit FLAC, 195 KB. The exact
  ffmpeg command (reproduces the file bit for bit) is in
  assets/sfx/LICENSES.md.
- Choice: 18 recordings, each verified as CC0 on its page (17 on
  Freesound, one on Wikimedia Commons), were scored with the project's
  YAMNet; most audience/sitcom laughs score mostly as Speech. 76693 is
  strong Laughter at 1.2-7 s. A simulation of
  each laugh slot (the fixture's speech + a gated excerpt at -16.5 dBFS,
  the frame merge of signals.py) picked offsets whose first and last
  active frames give event ends within 0.5 s, with the frames outside
  inactive. One short excerpt serves all three laughs (<500 KB budget).
- The laugh times stay 13.8-16.3, 33.15-35.15 and 51.85-54.85, so
  expected.json (unchanged bytes), transcript.json and llm_response.json
  stay valid. Laugh k starts at offset 1.00/1.32/0.48 s of the clip with
  gain -1.5/-2.4/-0.9 dB (about -16.5 dBFS RMS, the old pink noise level)
  and keeps the 30 ms gate fades.
- Graph: asplit; per laugh atrim(start) + volume + adelay (integer ms:
  ffmpeg 9.0.1's adelay reads "13.8s" as 13.8 ms, its "s" suffix only
  takes integers) + asetpts=N/SR/TB + atrim(end); amix normalize=0; apad
  to 60 s; asetpts=N/SR/TB; aeval's input. adelay and amix emit frames
  without timestamps, from which aeval computes t = NaN (the AAC encoder
  then fails: "Input contains (near) NaN/+-Inf"); renumbering them with
  asetpts fixes it. The laugh track equals the clip's excerpts (to 4e-8)
  and is digital silence elsewhere; reruns give identical bytes.
- Result on the real pipeline: laughs 14.16-16.08 (intensity 0.758),
  33.36-34.8 (0.847), 52.08-54.48 (0.738). Laughter is the top class of
  every frame inside a laugh (0.62-0.95) and <= 0.001 elsewhere; the laughs
  are 16.1-16.4 dB above the 30 s median level; AAC peaks reach -0.37
  dBFS. Energy peaks: one per laugh (14.647-15.878, 33.688-34.908,
  53.218-54.448); still 20 silences, no scene cut.
- Consequences: genre auto -> comedy (3 laughs a minute); enriched.txt has
  three LAUGH markers; scores A 71 (llm 0.83, laugh 0.85, energy 0.07),
  B 63, C 42, same order (were podcast 68/61/56). test_run_minimal pins
  A's new scores; the waterfall test became "YAMNet hears laughter in the
  laughs and nowhere else".

## 2026-10-31 — TASK-21 snap -> snapped.json

- Silence (SPEC 6.7 "follows a silence >= 0.35s"): the gap between the end
  of the word before and the start of the word in transcript.json,
  compared to the millisecond (4.6 - 4.25 is 0.34999999999999964 and
  counts), the reading of the fixture design (TASK-7). signals.json's
  silence events (below -40 dBFS for >= 0.35 s) are not used: they
  measure the audio level, not the gap between words, and their edges do
  not line up with word starts.
- Start: of the words that start in [start - 0.3 s, end), the first that
  begins a segment or follows such a pause; if none does (a clip inside
  one long phrase), the first of them, so the clip still starts on a word.
  The 0.3 s edge counts and is compared to the ms (36.1 - 0.3 is
  35.800000000000004).
- End: "the last word before end" is the last word that starts before
  end. The LLM reads times rounded to 0.1 s, so an end of 51.5 for a clip
  ending on "choices." (51.04-51.55) keeps the word instead of ending on
  "life" (51.0).
- Tail: +0.3 s; for comedy, until the laugh after the last word ends,
  capped at +1.5 s. A laugh counts if it ends after the word's end and
  starts at most 1.5 s after it; applause does not (SPEC names laughs);
  without one, comedy gets +0.3 s too. Every tail stops where the next
  word starts (SPEC "never cut mid-word") and at timeframe_end; the last
  word itself is never cut, even if it runs past timeframe_end.
- Words: only the segments that start in the timeframe (enrich's
  `timeframe_segments`, the speech the LLM saw).
- A clip in which no word starts (e.g. only a laugh) is dropped with a
  WARNING. So no snapped clip starts or ends inside a word (property test:
  1000 random clips per genre on the fixture words).
- Snapped times are rounded to the ms. Lengths are not checked again
  against the preset (SPEC 6.7 asks for no check) and scores are not
  recomputed: score ran on the LLM's times, which the clip ranking keeps.
- Output: snapped.json (`ScoredList`, same order and scores), so the step
  keeps the one-file, idempotent contract. `run_process_job` saves its
  clips as clip rows (status candidate) after the steps; `clipforge step
  snap` never writes the DB, so reruns cannot duplicate clips.
- Fixture (auto -> comedy): A 0.5-35.2 -> 0.5-34.35 ("cheese." ends at
  32.85, + 1.5 s inside the 33.36-34.8 laugh), B 16.9-54.9 -> 16.9-53.05,
  C 35.8-59.5 -> 35.8-59.8; as podcast A ends at 33.15 and B at 51.85.

## 2026-10-31 — TASK-22 reframe -> crop_<clip_id>.json

- Library: mediapipe 0.10.33 exactly. mediapipe 0.10.35, 1.x and 1.2.0
  link Google's Clearcut usage logging (`play.googleapis.com/log` and
  Clearcut symbols in `libmediapipe.dylib`); SPEC 1 forbids telemetry.
  0.10.33 has neither string, and a run under a DYLD connect() interposer
  made no network call. <= 0.10.21 are pybind wheels that need numpy 1 /
  protobuf 4. A test fails if the library ever gains the strings back.
  mediapipe needs opencv-contrib-python, which clashes with
  opencv-python (both install `cv2`): `[tool.uv] exclude-dependencies =
  ["opencv-python"]` keeps only contrib (PySceneDetect imports `cv2`
  and works with it).
- API (verified in the installed source): 0.10.33 has the Tasks API only
  (no legacy `mp.solutions`): `vision.FaceDetector` in IMAGE mode with
  `min_detection_confidence` 0.5 (the default); `mp.Image(
  image_format=mp.ImageFormat.SRGB, data=uint8 HxWx3)`;
  `Detection.bounding_box` (int origin_x, origin_y, width, height) and
  `categories[].score`. The C library's errors are plain Exceptions:
  load errors become StepError.
- Model: BlazeFace short-range (SPEC 2), float16 version 1 from
  storage.googleapis.com (Apache-2.0 per its model card), pinned by
  sha256 and downloaded by `scripts/download_models.py` with httpx, like
  the other models (steps never download). It is made for faces within
  about 2 m of the camera: wide stage shots may show no face, and then
  the window holds or centers.
- Frames: ffmpeg decodes 5 fps slices of 50 samples (`-ss` before `-i`,
  `-t count/5`, `fps=5`, scaled to <= 640 px; the model sees 128x128),
  so a 3-minute clip needs 18 short ffmpeg runs and ~35 MB at a time.
  Samples are start + k/5 s while < end; a sample ffmpeg does not return
  (end of the video) has no faces. Boxes are stored in source pixels.
- Subject: the largest face (diarization is not built, so the "nearest
  speaker" rule has no speaker yet). Two similar faces can swap; the
  dead-zone damps it.
- Dead-zone: 8% of the frame width, centered on where the window aims
  (+-4%). While the subject stays inside it the aim holds; when it leaves,
  the aim moves to the subject. EMA: center += 0.15 * (aim - center) at
  each 5 fps sample. Hard reset (window jumps to the subject) at the
  clip's first sample and at the first sample at or after each scene_cut
  of signals.json.
- Gaps: SPEC "no face > 1 s: hold the last position" read as the simplest
  rule: any gap holds the last subject (a short gap needs no other
  rule). In a shot, the samples before its first face take that face; a
  shot without faces holds the previous subject, or the frame center if
  none was seen ("no face at all: center"). Subjects nearer an edge than
  half the window are aimed at as if they were not, so the window stays
  inside the frame.
- Output: only x is tracked; width, height and y are render's
  center_crop for the aspect (full height for a wider source), x is even
  (yuv420p). crop_<clip_id>.json (`CropPlan`: clip_id, start, end, aspect,
  width, height, y, keyframes[t (source seconds), x, faces largest first])
  keeps the faces of each sample for TASK-23's split layout. Without
  faces x is center_crop's x (1280x720 9:16: 438).
- Pipeline: reframe needs clip ids, which exist only once snap's clips
  are saved, so it is not a STEP_NAMES step: `run_process_job` saves the
  clips, then runs `reframe_clips` (Job.step "reframe", progress = clips
  done) before render. The face model is loaded once per job and only if
  a plan is missing; existing plans are skipped (force redoes them).
  Render still center-crops until TASK-23 reads the plans.
- Schemas: SPEC 0.9 keeps schemas in models.py, which would pass 300
  lines, so the candidate rules (`PRESET_LENGTH_RANGES`, `length_range`,
  `validate_candidate`) moved to `clipforge/candidate_rules.py`.

## 2026-10-31 — TASK-23 layouts fill/fit/split in render

- Crop method: one crop `x` expression per window, evaluated by crop at
  every frame, not sendcmd. Evidence (ffmpeg 9.0.1): `ffmpeg -h
  filter=crop` lists `x <string> ..FV.....T. set the x crop area
  expression (default "(in_w-out_w)/2")`, and the ffmpeg-filters manual
  says x and y are evaluated for each frame, with `t` the timestamp in
  seconds and `n` the frame number. `ffmpeg -h filter=sendcmd` has only
  `commands`/`c` and `filename`/`f`: sendcmd sets a value at given
  times, so x would jump at every 0.2 s keyframe (or need an expression
  per command anyway) and need a second escaped command list. The
  expression moves x linearly from keyframe to keyframe and holds before
  the first and after the last one:
  `x0 + (x1-x0)*clip((t-t0)/(t1-t0),0,1) + ...` (terms with x1 == x0
  are dropped). With input `-ss`, `t` starts at 0 at the clip's start
  (checked on a lossless ffv1 gbrp gradient with `-ss 10` and
  `-ss 10.5`), so keyframe times are written relative to the clip start.
- ffmpeg refuses (EINVAL, "Failed to configure input pad on
  Parsed_crop_0", exit 234) a flat sum of 98 or more terms:
  libavutil/eval.c (release/8.0 and master) has `#define MAX_DEPTH 100`
  (checked in make_eval_expr and for function calls) and parse_expr
  allows 100 nested parentheses. The terms are therefore summed as a
  balanced tree, `(first half)+(second half)`, about log2(n) deep: a
  3-minute clip (900 keyframes) gives a 28.7 KB expression that works,
  5000 keyframes work, and the window is within 0.5 px of the keyframe
  line (test_layouts checks 59 s against 300 random keyframes, frame by
  frame, within 1 px). Keyframe x are even, as yuv420p crop needs.
- Graphs (`layouts.layout_graph`, `-filter_complex` from `[0:V:0]`, the
  first real video stream like `-map 0:V:0`; `-map [v] -map 0:a:0`):
  every layout starts with `fps=30` and ends with `setsar=1`.
  - fill: crop the fill window, scale to the output size.
  - fit (SPEC 6.8 "scaled source over a blurred, scaled-to-fill copy"):
    `split`; the back copy is scaled to fill a quarter-size frame
    (`force_original_aspect_ratio=increase`, crop), blurred with
    `boxblur=luma_radius=10:luma_power=2` and scaled to the output size;
    the front is scaled to fit (`force_original_aspect_ratio=decrease:
    force_divisible_by=2`) and overlaid centered (`x=(W-w)/2:y=(H-h)/2`).
    Blurring at quarter size took 0.89 s instead of 3.53 s for 20 s of
    video and looked the same.
  - split: `split`; each copy is cropped by its split window, scaled to
    the output width and half its height, then `vstack=inputs=2`.
  Options checked with `ffmpeg -h filter=` scale, boxblur, overlay,
  split, vstack, fps and setsar.
- Split trigger (SPEC 6.8 "two faces stacked top/bottom when 2 faces
  persist > 60% of the clip"): a 5 fps sample counts if the detector
  finds two or more faces; split when strictly more than 3/5 of the
  samples count (`Fraction(3, 5)`, no float error: 60/100 -> fill,
  61/100 -> split, 3/5 -> fill, 4/5 -> split). Split is chosen only when
  the fill window is narrower than the frame (16:9 of a 16:9 source
  already shows both faces). Reframe never chooses fit; the user can in
  the editor (SPEC 8, Layout tab).
- Split windows: each has the shape of half the output frame and is the
  largest one in half the source's width (center_crop of width/2 x
  height): 1280x720 -> 640x568 for 9:16, 640x320 for 1:1, 640x180 for
  16:9. The top window follows the left and the bottom one the right of
  the two largest faces of each sample, with fill's tracking (dead-zone,
  EMA, scene-cut resets) over the whole frame; samples with fewer than
  two faces hold, and before the first pair the windows aim at the
  centers of the frame's halves. A window's y centers the median height
  of its faces (even, inside the frame), else the center_crop's y.
- Flow: plan_crop writes `layout` and `split` into crop_<clip_id>.json;
  the process job copies each plan's layout to its clip row
  (`clips.set_planned_layouts`) and render frames the clip in the row's
  layout, so a layout the user picks later wins. Render no longer probes
  the source: the plan holds the windows. Crop plans written before
  TASK-23 have no layout or split and fail validation (StepError); rerun
  reframe with force for such a job.
- The tracking primitives moved from reframe.py to
  `pipeline/tracking.py` (300-line limit) and track_centers generalizes
  track_subject to any window and default aim.

## 2026-10-31 — TASK-24 caption templates, fonts, emoji map

- Fonts (PRD: Montserrat ExtraBold + Inter Bold, OFL, in assets/fonts
  with their OFL license files): static `Montserrat-ExtraBold.ttf` 9.000
  (JulietaUla/Montserrat master, weight 800) and `Inter-Bold.ttf` 4.001
  (Inter 4.1 release, `extras/ttf`, weight 700), plus Noto Emoji 3.002
  (google/fonts `ofl/notoemoji`, monochrome, variable wght 300-700),
  renamed from `NotoEmoji[wght].ttf` to `NotoEmoji-VariableFont_wght.ttf`.
  Sources, sha256 and copyrights: `assets/fonts/LICENSES.md`; none has a
  Reserved Font Name.
- A template's `font` is the name libass selects the font by. libass
  (ass_fontselect.c, master) reads the Windows (platform 3) name records
  ID 1 (family) and ID 4 (full name) and the PostScript name; a family
  match is scored by weight and italic, a full-name or PostScript match
  is taken at once (case-insensitive). Montserrat-ExtraBold.ttf has
  family and full name "Montserrat ExtraBold" (its ID 16 "Montserrat" is
  not read). Inter-Bold.ttf has family "Inter" and full name "Inter
  Bold": templates say "Inter Bold", which picks the bundled file even if
  the system has Inter, while family "Inter" with Bold 0 asks for weight
  400 and could get a system Inter Regular. So the AC's "font family
  names match the template font field" is tested as: the font is the
  family or full name of exactly one bundled file (fontTools), whose OS/2
  weight is 800 or 700. A libass-enabled ffmpeg (outside the project,
  read-only probe) logged `fontselect: (Montserrat ExtraBold, 400, 0) ->
  Montserrat-ExtraBold` and `(Inter Bold, 400, 0) -> Inter-Bold`.
- Emoji: libass found no fallback for emoji ("Glyph 0x1F602 not found",
  "failed to find any fallback") and dropped them. With `{\fnNoto
  Emoji}😂{\fn}` it logs `(Noto Emoji, 400, 0) -> NotoEmoji-Regular` and
  draws the glyph in the line's colors and outline; all 207 distinct
  emoji of the map drew that way (no "Glyph ... not found" at -v debug).
  TASK-25 must wrap each emoji in `\fn` + `clipforge.fonts.EMOJI_FONT`.
- libass loads every file of fontsdir and warns "Error opening memory
  font 'Inter-OFL.txt'" (also for the other license files and
  LICENSES.md). It is an AV_LOG_WARNING, hidden at run_ffmpeg's default
  `-loglevel error`, and harmless; the licenses stay next to the fonts as
  the PRD asks.
- Size: `size` is the ASS Fontsize in pixels of the output frame (TASK-25
  sets PlayRes to the output size; every output is at least 1080 px
  wide). libass makes the font's OS/2 winAscent + winDescent that tall
  (Montserrat 1109 + 453 per 1000 units, Inter 1984 + 494 per 2048),
  consistent with a probe: Montserrat at 96 drew "THAT IS HILARIOUS"
  about 640 px wide, Pillow measured 631 px. Sizes keep a full line
  inside 1080 px: Montserrat 100 "THAT IS HILARIOUS" 662 px, Inter 64
  "nobody understands the problem" 864 px. A probe render of all six
  templates on 1080x1920 (ad-hoc ASS styles) fitted every line.
- Templates: karaoke_bold (default of ProcessingSettings; Montserrat 100,
  white, yellow spoken word, middle, 3 words), minimal (Inter 64, grey,
  white spoken word, bottom, 4), boxed (Montserrat 80 on an opaque box;
  with box, outline is the box padding as in ASS BorderStyle 3), neon
  (cyan/magenta/green, emoji), comic (yellow, heavy outline and shadow,
  emoji), clean_subtitle (Inter 60, all colors white: no highlight).
  Outline and box colors are not template fields in SPEC 6.9; TASK-25
  picks them.
- Schema: `CaptionTemplate` (extra="forbid") has exactly the SPEC 6.9
  fields; outline and shadow are floats (ASS allows fractions). The name
  is the file stem, not a field, so they cannot disagree. It lives in
  `clipforge/captions_templates/__init__.py` (the SPEC 3 directory made a
  package, so the YAMLs ship in the wheel like prompts/), not in
  models.py (292 lines), as `config.Settings` lives in config.py; TASK-36
  must export it too. Loaders raise ValueError naming the file ("is not a
  valid caption template", "is not valid YAML", "font 'X' is not in
  <dir>") chained from the error like `step.load_json`; local files hold
  no secrets (the no-chaining rule is for LLM replies). `FONTS_DIR` is
  the repo's assets/fonts (like `db.MIGRATIONS_DIR`).
- Emoji map: 266 lowercase one-word keys (`^[a-z]+$`) -> 207 distinct
  emoji, grouped by theme; everyday words (think, look, time, work,
  okay, yes, no) are left out so emoji stay rare. A value is one
  non-ASCII character plus an optional U+FE0F, so no ZWJ sequences,
  keycaps or flags. All 266 are fully-qualified per Unicode's
  emoji-test.txt 18.0 (checked once; not a test) and in the Noto Emoji
  cmap (tested). Unquoted YAML 1.1 keys on/off/yes/no load as booleans
  and fail validation; PyYAML keeps the last of duplicate keys, so a test
  counts the raw key lines.
- Dependencies: fonttools 4.68.0 (already locked through matplotlib)
  became direct for `clipforge.fonts` (no py.typed: mypy override);
  types-PyYAML 6.0.12.20261030 (dev) because captions_templates is the
  first module that imports yaml under mypy --strict.
- Homebrew ffmpeg 9.0.1_1 has no libass (no `subtitles`/`ass` filter),
  which TASK-26 needs: asked in docs/questions.md.

## 2026-10-31 — TASK-25 ASS captions

- Two modules (300-line rule): `pipeline/caption_lines.py` (which words,
  their lines, emphasis and active spans; no ASS) and
  `pipeline/captions.py` (the ASS file). Captions are written per clip,
  like crop plans, by `write_captions(job_dir, clip, frame)` into
  `<job>/captions_<clip_id>.ass` (`step.write_text`): not a STEP_NAMES
  step and not called yet (TASK-26 burns them in). It takes the frame
  size, not the aspect, so captions does not import render (render will
  import captions; the other way round would be an import cycle).
- Times are integer milliseconds from the clip start (render seeks its
  input there and vf_subtitles renders at the frame pts). A word belongs
  to the clip if it starts in [start, end); its end is cut at the clip
  end. ASS times are centiseconds rounded half up; an event that rounds
  to zero length is dropped.
- Caption words are the whitespace pieces of the segment text
  (`enrich.piece_words`, as the LLM read them), so Whisper's "twenty" +
  "-five" is one word; if the words do not spell the text, each word
  stands alone. caption_overrides (a Word list, SPEC 5) replace the text
  of the transcript word with the same start and end to the millisecond
  (an edit keeps the word's times); a blank override hides the word; an
  override that matches no word is ignored.
- Lines: at most max_words_per_line words; a line ends after a word that
  ends with . , ! ? ; : … or — (closing quotes or brackets may follow)
  and before a pause of more than 300 ms (exactly 300 ms does not break:
  SPEC says "pause > 0.3s").
- Active word: one Dialogue per word that shows its whole line with the
  word in highlight_color. It stays active until the next word starts
  (also across lines, so the captions never blink between words) unless
  a pause of more than 300 ms comes first; then until its own end.
- Emphasis: emphasis_words entries may be phrases; a phrase matches
  consecutive words by key (lowercase, punctuation around it removed).
  Emphasis words are always 110% (`\fscx110\fscy110`) and in
  emphasis_color, but in highlight_color while active (the spoken-word cue
  wins). Override runs end with `{\r}` (back to the style).
- Emoji: with emoji on, a word whose key is in emoji_map.yaml is followed
  by a space and its emoji in `{\fnNoto Emoji}...{\fn}` (libass has no
  font fallback; `\fn` without a name returns to the style's font).
- Styles: Caption at the template position (bottom: alignment 2 with
  MarginV 15% of the height, clear of the platforms' bottom UI; middle:
  alignment 5, where libass ignores MarginV), left/right margins 5% of the
  width, opaque black outline, 50% black shadow (templates have no
  outline or shadow color, SPEC 6.9). A box template uses BorderStyle 3,
  an opaque box per glyph in OutlineColour (black). Bold is off: the
  fonts are bold faces. Hook: 70% of the caption size, top center
  (alignment 8), MarginV 10% of the height, the same colors, from
  0:00:00.00 to 0:00:02.50 on layer 1, because libass moves colliding
  events only within one layer; no Hook event if hook_text is blank;
  uppercase if the template is.
- Script Info: PlayResX/Y = the output frame (the subtitles filter runs
  after the layout, so one ASS pixel is one video pixel), WrapStyle 0,
  ScaledBorderAndShadow yes, "YCbCr Matrix: None" (vf_subtitles then
  draws the colors in the video's own color space; without the header
  libass assumes BT.601 TV and colors shift on BT.709 video).
- Text escaping: whitespace runs become one space; `{` and `}` become
  `\{` and `\}`; a U+2060 WORD JOINER follows each backslash so that text
  such as "\N" shows as written (libass has no escape for a backslash).
- Verification without a libass ffmpeg in the project: Homebrew ffmpeg's
  ASS demuxer parses the files (syntax), and the libass ffmpeg outside the
  project drew the six templates once as a read-only probe
  (`.agent/screenshots/TASK-25-1.png`).

- 2026-10-31: ffmpeg-full 9.0.2 (Homebrew, keg-only) is the required ffmpeg; plain `ffmpeg` lacks libass/freetype. Makefile exports PATH with /opt/homebrew/opt/ffmpeg-full/bin first. README must say `brew install ffmpeg-full`.

## 2026-10-31 — TASK-26 burn captions in render

- `render_clip` takes the clip's ASS file as an optional keyword
  (`captions=`); without it the graph is the layout graph alone, as
  before. `clip_graph` writes the layout to the label `[framed]` (the new
  `out` parameter of `layout_graph`) and draws the ASS on it with
  `subtitles=filename=<ass>:fontsdir=<assets/fonts>` into `[v]`. Captions
  come after the layout because the ASS is in output pixels (PlayResX/Y =
  the output frame), and before the brand overlay and loudness pass still
  to come (SPEC 6.11 order: cuts, layout, ASS, brand, loudnorm), which can
  chain on the same way.
- Captions are written at render time by `clips.render_clip_row`
  (`write_captions`, before the clip turns "rendering"), not by a step: a
  render always shows the clip's current caption_overrides, template and
  hook text, and the file is overwritten each time. If they cannot be
  written (no transcript.json: StepError; unknown template: ValueError),
  the error propagates and the clip keeps its status and output, as with
  a missing crop plan; the process job then fails with that message. An
  ASS file that is missing when ffmpeg runs is an FFmpegError ("Unable to
  open <path>"), so that clip is marked failed.
- Filter option values are escaped by `ffmpeg.filter_value`, a generic
  helper next to `run_ffmpeg`: a backslash before `\ ' :` and whitespace
  (option level), then before `\ ' [ ] , ;` and whitespace (graph level).
  Backslashes rather than '...' quotes, because a quoted string cannot
  hold a quote. Paths are made absolute first, so they are never read as
  protocols.
- fontsdir is `clipforge.fonts.FONTS_DIR` (assets/fonts). libass falls
  back to a system font silently if a font is not found, so the tests
  read libass's "fontselect" lines for each template instead of trusting
  the exit code.
- ffmpeg-full is required (owner, docs/questions.md): the missing-binary
  error now says `brew install ffmpeg-full`; plain Homebrew ffmpeg fails
  with "No such filter: 'subtitles'". The render log line is unchanged.

## 2026-10-31 — TASK-27 filler removal + caption re-timing

- Fillers are found in caption words (`caption_lines.word_groups`: the
  enrich pieces, else single Whisper words), not in raw Whisper words, so
  "Um-hmm," is one piece and never loses its "Um". The filler set is
  um/uh/erm/ah (lowercased, punctuation stripped by `word_key`).
- "like" counts as a filler only when standalone: at least 0.35 s of
  silence before and after it, the same pause as `snap.PAUSE_S` (SPEC 6.3
  defines a silence gap as 0.35 s). A missing neighbour counts as silence;
  neighbours come from the whole transcript, not just the clip. The
  fixture's "Like," has 0.80 s / 0.70 s around it and goes; "like a hawk"
  stays.
- A pause (a gap of more than 0.6 s between kept words or a clip edge)
  shrinks to 0.3 s, keeping 0.15 s on each side, rather than going whole:
  Whisper word edges are imprecise, and speech without breath sounds
  jarring. A cut of fillers in a pause covers the fillers too; a filler
  outside a pause is cut from its start to its end (merged when several).
  The clip edges are zero-length anchors under the same rule.
- A gap that a laugh or applause overlaps is never shrunk: in comedy the
  reaction is the content (snap extends clips for laugh tails; scores
  reward laughs). Fillers inside it are still cut.
- Cuts never enter a kept word: with overlapping Whisper words, a cut is
  clamped to the gap, leaving part of a filler rather than eating a kept
  word.
- Cuts are computed when clips are saved: `clips.save_clips` takes the
  job's work dir (required, so no call site can forget it) and, when the
  project's `remove_fillers` is on, stores them as absolute source seconds
  in the clip's `cut_ranges` (the field the editor's PATCH sets in
  TASK-34). The transcript and signals must exist (StepError otherwise).
- Captions are re-timed when they are written (`write_captions`), from the
  clip's current `cut_ranges`, so editor changes show at the next render.
  Times are int ms: `cut_spans` makes merged spans relative to the clip
  start, `output_ms` subtracts the cut time before a point, a word inside
  a cut is dropped and a word partly cut keeps its kept part.
- Render does not cut yet (TASK-28), and `remove_fillers` defaults to
  false with no CLI flag, so until then default renders are unchanged.

## 2026-10-31 — TASK-28 loudnorm two-pass + cut_ranges render

- Cuts use trim+concat, not select/aselect (SPEC 6.11 leaves the choice):
  each kept part is `trim`/`atrim` + `setpts`/`asetpts=PTS-STARTPTS` of a
  `split`/`asplit` copy, joined by `concat`. aselect keeps or drops whole
  decoded audio frames (1024 samples: 0.51 s came out 0.512 s), so audio
  would drift from video at each cut; atrim is sample-exact.
- Inner cut edges snap to the nearest frame of the render fps
  (`polish.frame_ms`); the clip's own start and end never move, so the
  ffprobe check still expects end - start minus the cuts. Each kept part
  is then whole frames and exactly n x 1600 samples at 30 fps / 48 kHz, so
  concat pads no audio and picture and sound stay in step. Cuts that
  snap to nothing disappear.
- Captions are re-timed with the same snapped spans (`write_captions`
  takes the render fps), so burnt-in words never drift from the picture.
- Graph order: layout first, then the cuts, then the captions. The crop
  plan (keyframes, split windows) is timed from the uncut clip start:
  cutting first would move each crop change after a cut earlier by the
  time cut before it. The ASS times are on the cut timeline, so captions
  come after the cut. Audio: cut, then loudnorm.
- `-t` is now an input option (`-ss start -t length -i source`): both
  loudnorm passes share the same input options, so pass 1 measures
  exactly the audio that pass 2 renders.
- Loudness: pass 1 runs only the audio part of the graph into
  `loudnorm=print_format=json` (`-f null`); pass 2 feeds its measurement
  back with `linear=true`. TP -2 dBTP and LRA 7 LU are loudnorm's own
  defaults (SPEC sets only target_lufs); loudnorm itself falls back to
  dynamic mode when one gain cannot reach the target within them (most
  speech, clip A included). dual_mono stays off, as in ebur128.
- loudnorm outputs 192 kHz: always `aresample=48000` after it, then
  `asetpts=N/SR/TB+STARTPTS`, since loudnorm's own timestamps are wrong
  after concat and at the end of every stream (the mp4 got 1-sample
  packets and +83 ms). STARTPTS keeps a source's audio start offset.
- A silent clip (loudnorm reports -inf) renders without normalization
  (info log); a missing report is an FFmpegError, and cuts that leave
  nothing a RenderError, so either marks the clip failed.
- `render_clip(target_lufs=None)` means no loudnorm, so direct callers
  and older tests render as before; `clips.render_clip_row` always passes
  `settings.target_lufs` (default -14).
- The graph builders moved to `pipeline/render_graph.py`: with them,
  render.py would have had 320 lines (limit 300).

## 2026-10-31 — TASK-29 export: SRT, metadata JSON, zip

- SRT cues are the caption lines that the render burns in: the same words
  (`polish.rendered_words`: `clip_words` with the caption_overrides, then
  re-timed by the frame-snapped cuts), in lines of the clip template's
  `max_words_per_line` (`caption_lines.group_lines`). A cue runs from the
  line's first word's start to `active_end` of its last word, so SRT and
  ASS lines come and go together. Cue text keeps the transcript's case
  (uppercase is template styling) and has no emoji or hook; whitespace is
  collapsed onto one line. Lines that would show for no time get no cue;
  numbering stays 1, 2, 3, ...
- Format: `index\nHH:MM:SS,mmm --> HH:MM:SS,mmm\ntext\n\n` for every cue,
  the last one included, in UTF-8 (no BOM) with LF: what ffmpeg's srt
  muxer writes (round trip byte-identical, tested).
- The SRT belongs to the rendered mp4: `render_clip_row` writes it right
  after a successful render, and `export_project` zips it as it is (it only
  writes a missing one). Edits of start/end/cut_ranges/caption_overrides
  (TASK-34 PATCH) reach the SRT with the next render, as they reach the
  video. Before rendering, a clip's old srt/json are removed, so a failed
  clip has no exports, as it has no mp4.
- The metadata JSON holds exactly title, description, hashtags (as stored:
  without "#") and credit. It is written after each render and again by
  `export_project`, because text edits and credit_template changes need no
  re-render.
- credit_template may use `{channel}`, `{channel_url}` and `{title}` (the
  source video's title), from meta.json as they are; `{{`/`}}` are literal
  braces. Settings rejects other fields, conversions, format specs and
  stray braces (`config.credit_fields`), so a saved template never fails
  at export. The credit is null when a field it uses is unknown (a local
  file has no channel) or the line is blank. channel_url is yt-dlp's
  channel_url (else uploader_url), e.g. https://www.youtube.com/channel/UC...,
  so SPEC's example "youtube.com/@SampleComedian" is not reproduced verbatim;
  the default template stays "Credit: {channel}".
- Zip: `{data_dir}/output/{project_id}/clips.zip` (`clips.ZIP_NAME`) with
  `<clip_id>.mp4`, `.srt`, `.json` for each rendered clip whose mp4
  exists, best overall score first (ties by id); mp4 stored (already
  compressed), srt/json deflated; written to `.tmp`, then renamed. No
  rendered clips: an empty zip. `clipforge run` does not zip; TASK-34's
  GET /projects/{id}/download.zip calls
  `clips.export_project(engine, project_id, work)`.
- `rendered_words` lives in polish (captions and export share it):
  caption_lines must not import polish (polish imports caption_lines).

## 2026-10-31 — TASK-30 Premiere FCP7 XML (xmeml v4)

- The XML lives in a new `pipeline/premiere.py` (export.py would pass 300
  lines); `clips.export_premiere(engine, project_id, work)` writes it to
  `{data_dir}/output/{project_id}/premiere.xml` (`clips.PREMIERE_NAME`).
  `clipforge run` does not write it; TASK-34's GET
  /projects/{id}/premiere.xml calls export_premiere.
- Document: `<xmeml version="4">` holds one `<project>`, named after the
  source video's title, with one `<sequence>` per clip of the project,
  whatever its status (the XML needs no render), best overall score first
  (ties by id), named "01 <clip title>" (two digits or more). A sequence
  starts at frame 0 (timecode 00:00:00:00, NDF) and lasts the clip; its
  clipitems play frames in = round(start * fps) to out = round(end * fps)
  of the source.
- The source is the job's `work/source.mp4` (pathurl
  `file://localhost/<percent-encoded absolute path>`, as Premiere writes
  it): clip times are on its timeline, and it exists for URL sources too
  (`Project.source_path` is empty for them). The full `<file id="file-1">`
  (rate, duration, size, sample rate, channels) appears once, in the first
  clipitem; all other clipitems refer to it by id, as Premiere does.
- fps is the rate the XML declares: timebase round(fps), ntsc when fps is
  nearer timebase * 1000/1001 (29.97, 23.976, 59.94). For the usual rates
  that is meta.fps; for a variable-rate average it keeps frames on the
  declared timeline (no drift).
- Audio follows Premiere's own exports (and auto-editor's): a mono source
  gets one audio track; a source with 2 or more channels a stereo pair of
  mono tracks playing channels 1 and 2 (`outputchannelindex` 1/2); a 5.1
  source's other channels are left out. Each clipitem links the
  sequence's video and audio clipitems (audio: groupindex 1), so they move
  together. Sample rate and channels come from ffprobe of source.mp4
  (meta.json has neither); a source without audio is a StepError (ingest
  never makes one).
- Not represented: cut_ranges, layouts/reframing, captions and the
  vertical frame; sequences have the source's frame size. The XML is an
  editor's starting point on the uncut source.
- Only elements of Apple's xmeml v4 DTD are written (no
  `numOutputChannels`/`premiere*` attributes), so the output validates
  against the DTD; control characters that XML 1.0 forbids are removed
  from all text (titles), since ElementTree escapes &, < and > but not
  those.
- The tests' DB row helpers (`add_project`, `add_clip`) moved from
  test_clips/test_clips_export into `tests/seed.py` for test_fcpxml.

## TASK-32 — API projects, upload, media Range (T15b)

- `POST /projects` takes a required http(s) `url` (SPEC 7 says `url|null`):
  a null url has nothing to process, and a local path must never be taken
  from a request, so files go through `POST /projects/upload` (form fields
  `file` and optional `settings`, the JSON of a ProcessingSettings). Both
  return 201 and the queued Project; the job is read via TASK-33's
  endpoints.
- Uploads are saved as `{data_dir}/uploads/<random id>/<file name>` (last
  path component only); DELETE removes that directory, the project's work
  dirs and `output/<id>`, and answers 409 while one of its jobs runs.
- `/media/{id}/source` serves `work/<job>/source.mp4` of the project's
  latest process job (the browser-playable ingest result), 404 until
  ingest has run. Range is Starlette's `FileResponse`; its 416 is plain
  text (no body JSON), the only error not in the {error, message} shape.
- Request models live in models.py (`ProjectCreate`, SPEC 0.9); the app is
  built by `create_app()`, tests pass `run_worker=False`.

## TASK-33 — API jobs + SSE events (T15c)

- SSE `message`: the Job model has no message field, so it is the error
  of a failed job, else "Waiting in the queue." / "Running <step>." /
  "Done.". Events are sent on change only, polled from the job row every
  0.5 s (the worker is a separate thread: no in-process pub/sub), with a
  `: keep-alive` comment after 15 s of silence.
- The test module is `tests/api/test_job_endpoints.py`, not `test_jobs.py`
  (TASK-33 spec): tests have no `__init__.py`, so a second `test_jobs.py`
  would clash with `tests/unit/test_jobs.py`.

## TASK-34 — API clips (T15d)

- `sort=score` is overall score descending, `sort=duration` shortest
  first (ties by id). `q` is a case-insensitive substring match on title,
  hook_text, description and hashtags (not the transcript).
- PATCH validates (end > start, cuts inside the clip and not covering it,
  known caption template; 422) and leaves status/output alone: the mp4
  and SRT change only with POST /clips/{id}/render. PATCH answers 409
  while the clip renders. An explicit null keeps the field. Edited
  hashtags may be 0..8 (the LLM output needs 3..8).
- POST render returns the clip's queued render job if there is one
  (no duplicate jobs). A project without a process job -> 409.
- Preview: half size (540x960 for 9:16), libx264 veryfast crf 28, 96k
  audio, no loudnorm; cached in `output/<pid>/previews/<clip>-<hash>.mp4`
  by a hash of everything that changes the picture; one preview renders
  at a time (global lock); older previews of the clip are deleted.
- Regenerate-text rewrites only title, description and hashtags (from the
  clip's kept words); an LLM failure -> 502 `llm_error`.
- Download and SRT need a rendered clip (404); the SRT is written if
  missing. download.zip needs one rendered clip (409); premiere.xml needs
  one clip (409).
- models.py grows past 300 lines (344): SPEC 0.9 keeps every schema there.
- Test modules: `test_clip_endpoints.py` / `test_clip_files.py` (the
  basename `test_clips.py` is taken by tests/unit).

## TASK-35 — API brand templates, caption templates, settings (T15e)

- Brand create is multipart (`name`, `logo`, optional `logo_position`
  `logo_opacity` `font` `primary_color` `intro` `outro`); the logo is
  required. PUT is multipart too and changes only what is sent
  (`remove_intro` / `remove_outro` drop a video). Intro/outro are uploads,
  not local paths (like POST /projects). The logo type is read from its
  first bytes (PNG, JPEG, WebP; at most 5 MB); `font` must be a bundled
  font. Files live in `data/brand/<id>/`; uploads are staged and
  validated first, so a rejected request changes no file. Deleting a
  template does not touch projects that name it in `brand_template_id`
  (render must ignore a missing template).
- Caption template previews: one 540x960 PNG per template drawn by libass
  from the real ASS builder at startup (`create_app(caption_previews=)`),
  cached by content hash in `data/caption_previews/`, drawn on demand if
  missing. `GET /caption-templates` -> `[{name, template, preview_url}]`.
- Settings are saved in `.env.local` (cwd): Settings already reads it
  before config.yaml, so nothing else changes and config.yaml keeps its
  comments. API keys are write-only (`*_set` flags). `data_dir` is shown
  but cannot be changed (the database is open in it). An environment
  variable of the same name wins over `.env.local`: such a PUT is 409 and
  the file is restored. The saved values replace `config.settings` at once
  (jobs and LLM requests read it per use).
- POST /settings/test-llm sends one small chat request with the saved
  settings, or with the settings in the body (not saved). A failure is a
  200 with `ok: false` and the reason; keys are replaced by `***`.

## TASK-36: type generation
- Types come from the Pydantic JSON schemas (serialization mode) of all
  models, not from the OpenAPI document: it leaves out models the API does
  not return (Transcript, CropPlan) and splits others into -Input/-Output.
  Every property of a response model is required (a default is always
  serialized); `ProjectCreate`, `ClipPatch` and `SettingsUpdate` keep their
  optional fields. `ProcessingSettings` is therefore complete: a client
  that sends part of it uses `Partial<ProcessingSettings>`.

## 2026-10-31 — TASK-37 frontend shell

- Toasts are a 40-line store (`lib/toast.ts`) plus `Toaster.tsx` instead of a
  new dependency (sonner); `apiFetch` shows the server's `message` itself, so
  every caller gets the toast unless it passes `silent`.
- Sidebar follows docs/ui-layout.md: group label "Create" (Home, Projects,
  Brand templates), Settings and Help (README link) at the bottom, collapsible
  to icons. Left out: Media library (not built), Publish group (v2).
- Top bar (inner pages only): breadcrumb from the path and the search field
  (cmd+K); submitting goes to `/projects?q=...`, which the projects page reads
  in its task. The notification bell waits for the job events UI.
- The app is dark only (`dark` class set in `main.tsx`); no theme toggle.

## 2026-10-31 — TASK-38 Home page

- "Get clips" on Home creates the project with default settings at once
  (POST /projects, or /projects/upload for a file); the new project shows in
  the grid as Queued. TASK-39 puts the settings panel (SPEC 8.2) between a
  valid link/file and this call; the Processing view (TASK-40) adds the link
  from a card.
- The thumbnail is served by a new `GET /media/{id}/thumbnail` (the API had
  no way to show `thumb.jpg`); the clip count is `GET /projects/{id}/clips`
  per card, asked only for done projects (no `clip_count` field in `Project`).
- Any http(s) link is accepted, not only YouTube (yt-dlp handles many sites);
  a link typed without a scheme gets `https://`.
- Left out of the Home layout: tool chips (no feature behind them in v1),
  Google Drive (v2) and the card's kebab menu (the API has no rename).

## 2026-10-31 — TASK-39 settings panel

- The panel needs a link's title, duration and thumbnail before a project
  exists: new `POST /sources/probe` (yt-dlp metadata only, no download).
  The thumbnail is the site's URL (loaded with `referrerPolicy=no-referrer`),
  not a copy. A file's duration and frame are read in the browser.
- New `GET /processing-defaults` so the panel starts from the server's
  defaults (`default_num_clips` from settings) instead of copies in the UI.
- "Get clips" stays enabled while the probe is loading, but is disabled when
  it failed (a playlist or an unreadable page would fail ingest the same way).
- Genre and brand template are native `<select>`s (no new dependency);
  timeframe and filler switch use radix `Slider`/`Switch`.
- The timeframe is sent as null on a side that is at the video's edge (whole
  video by default); it is hidden when the duration is unknown.
- A minimal project page at `/projects/:id` (name, status) is where "Get clips"
  lands; TASK-40 builds the Processing view on that route.

## 2026-10-31 — TASK-42 editor player + timeline

- The editor is a full-screen route `/clips/:clipId` outside `AppShell` (the
  gallery's Edit button already links there); it waits for the clip and its
  project (duration bounds the timeline, `settings.aspect` sizes the player).
- The player plays the saved clip's proxy (`/clips/{id}/preview`). Its time
  has the cut ranges removed, so the playhead is mapped to source time with
  the saved cuts (`previewToSource`/`sourceToPreview`); "current / total"
  is shown on the trimmed clip being edited.
- The timeline shows the saved clip with 30 s of source on each side
  (inside the video). The handles keep at least 1 s of clip (`MIN_CLIP_S`);
  arrow keys move a focused handle 0.1 s, shift 1 s, Home/End to the window
  edges. Cut ranges outside the trimmed clip are trimmed or dropped
  (`fitCuts`), as the API requires cuts inside the clip.
- Handle moves stay local until Save (TASK-45) / PATCH (TASK-52); the preview
  shows the saved clip until then.
- The transcript editor (TASK-43) needs a transcript endpoint that does not
  exist yet, so the left column shows the clip's In/Out/Length/Cuts (they
  follow the handles), hook, description and hashtags until then. The right
  rail starts with "Score" (score bars + reason); Captions, Layout, Brand and
  Text join it with TASK-44/45. Undo/redo, Save and Export come with their
  tasks (no disabled placeholders).

## 2026-10-31 — TASK-43 transcript editing

- The transcript editor lives in `components/editor/TranscriptEditor.tsx`
  (next to the other editor parts, where TASK-53 extends it) instead of
  `components/TranscriptEditor.tsx` named in the task file.
- `GET /clips/{id}/transcript` returns caption words (the Whisper words of
  one piece of segment text joined, as captions show them) as `Word`s in
  source seconds, prob = the lowest of the group; no new schema.
- Click a word = play from it and select it; drag or shift+click selects a
  run; Delete/Backspace cuts it (`[first.start, last.end]`, trimmed to the
  clip, merged with touching cuts). A click on a struck word restores the
  whole cut it is in. Clicking a gray context word offers "Extend to here"
  (start = its start before the clip, end = its end after it).
- Undo/redo covers the clip span and cuts; a whole handle drag is one step
  (gesture id); arrow-key nudges are one step each. Cuts outside a trimmed
  span are kept in the history and shown again when the span grows back.
- Space does not toggle playback while a button or slider has the focus
  (Space is theirs). Pause pills, the selection toolbar, the "Extend a
  clip" toggle, speech cleanup and the playing-word highlight are TASK-53.

## 2026-10-31 — TASK-44 caption style and crop offset

- Per-clip caption look lives in `clip.caption_style` (JSON, optional size,
  colors, position, uppercase, emoji; null = the template's value) next to
  `caption_template`; the template YAML is never edited. Choosing another
  template resets the style. Migration 002 adds the column and `crop_offset`.
- `crop_offset` is a fraction (-1..1) of the fill window width; the render
  and preview shift the crop plan's fill keyframes by it (`nudge_plan`), so
  it needs no source size and works with face tracking. It applies to the
  fill layout only; TASK-54 adds a manual crop keyframe on top.
- Panel edits are local until Save (TASK-45); the editor shows a CSS
  caption sample instead of re-rendering the preview on every change.

## TASK-54 — Player crop frame (T21c)

- A clip's editor framing is one JSON column (`Clip.framing`, migration
  003): `aspect` (null = the project's), `background` (blur/black, fit),
  `scale` (crop window size 0.25-1 of the planned window, one per clip:
  ffmpeg evaluates crop w/h once), `points` (keyframes: the window center
  at a source time, in fractions of the frame) and `tracker`.
- Render and preview use `framing.framed_plan`: replan for the clip's
  aspect from the plan's stored faces (no new face pass), then the crop
  offset nudge, then the crop tool, then the background. Tracker on: the
  window follows the plan, shifted to pass through each keyframe
  (interpolated shifts); off: it stays at the keyframes (or the first
  planned window). `CropKeyframe.y` (optional) lets keyframes move the
  window vertically.
- The crop tool draws the source video (`/media/{id}/source`) at the
  playhead with the window from `GET /clips/{id}/crop?aspect=`; the
  frontend mirrors the backend math in `lib/cropFrame.ts`.

## TASK-45 — Editor Brand and Text panels, Save/Render/Download (T21b)

- The brand template is a project setting (`ProcessingSettings.
  brand_template_id`), not a clip field, so the Brand panel saves at once
  with the new `PATCH /projects/{id}` (`ProjectPatch`, 422 for an unknown
  template) and says it applies to every clip of the project. Per-clip
  brands would need a new clip column and a way to clear it; the render
  pass that uses the brand is a later task (TASK-134).
- "Render" saves unsaved edits first (a render job reads the saved row),
  then queues the job; "Save changes" is enabled only while the edits differ
  from the saved clip (`ClipEdits.dirty`). The top bar's "Render" replaces
  ui-layout's "Export"; "Download" appears once the clip is rendered.
- The "progress toast" is the Render button's own label ("Rendering 40%",
  from the job's SSE events) plus toasts when the job starts and ends; the
  toast store has no updating toasts and adding one is not worth it.
- Texts keep the API's limits (title 70, hook 60, description 300: inputs
  stop at the limit; hashtags 3-8: Save and Render are disabled with a
  message). Regenerate with AI saves on the server (the endpoint does), so
  its texts are applied to the edits as one undo step and are no longer dirty.


- E2E (TASK-48): Playwright is a root devDependency (`package.json`), so
  `npx playwright test -c e2e` works from the repo root; `make setup` runs
  `npm ci` and `playwright install chromium`. `make e2e` is not part of
  `make check` (it starts servers on 8000/5173 and needs the browser).
  The test server is a factory (`--factory`), not a module-level `app`, so
  importing it never starts test mode; it needs both env switches.

## TASK-49 — Full e2e flow (T23b)

- `make check` still does not run the e2e suite; `make e2e` (or `npx
  playwright test -c e2e`) is the separate command (needs ports 8000/5173
  free, the chromium build and `models/`). The flow takes ~35 s.
- The pipeline renders every clip, so the editor shows "Download" before
  the test renders: the test waits for its own job's toast ("The clip is
  rendered. Download it now.") and checks the downloaded mp4's duration
  (`mvhd`) equals the editor's Length, so it is the edited render.
- The flow keeps the default processing settings ("settings" step = the
  Clip settings panel opens with the server defaults and is submitted).
- The test backend reads the models from the repo's `models/`
  (`MODELS_DIR` in the webServer env), never downloads them.
- The flow deletes its project in `afterEach`, so specs do not depend on
  their order on the shared server.

## 2026-10-31 — TASK-50 README (T24a)

- The task asks for a "GitHub Models option" in the `.env` section; GitHub
  Models was retired on 2026-07-30 (decisions, TASK-13), so the README says so
  and names Copilot (`GITHUB_COPILOT_TOKEN` or `gh auth login`) as the GitHub
  route. No provider was added.
- SPEC 10 says `brew install ffmpeg`; plain ffmpeg has no libass and the
  render fails, so the README says `brew install ffmpeg-full` (the keg
  ClipForge's `default_tool` looks for).

## 2026-10-31 — TASK-55 V2-PRE prerequisites and engines

- The staging SPEC-v2.md and out/PRD-v2.md (../clipforge-v2-staging) are
  byte-identical (`cmp`) to `.agent/prd/SPEC-v2.md` and `PRD-v2.md` (committed
  in 306f443), so nothing was copied and both files are unchanged.
- `scripts/check_prereqs.py` lists the 20 v2 credential names from the task
  (the v1 names in `.env.example` are not repeated). "Present" means a
  non-empty value in the environment, `.env` or `.env.local`; it prints names
  only and always exits 0. `HF_TOKEN` stays where v1 had it in
  `.env.example`.
- Engine test markers are `engine_<name>` for the ten engines with a probe
  (list in `docs/stack.md`); gaze, outpainting and text-to-video get their
  marker in the task that picks the model. `make check-engines` selects them
  with an explicit `-m "a or b ..."` (pytest `-m` has no wildcard); a unit
  test fails if a probe's marker is missing from pyproject.toml or the
  Makefile. `conftest` skips an engine test only when its probe says the
  engine is missing, with the reason; an installed engine runs `verify()`
  (import, `--help`, or Ollama `/api/tags` + `/api/show`), so a broken install
  fails. Engine tests also run in `make check` (skips allowed).
- Ollama probe (SPEC-v2 0.1): `GET {OLLAMA_HOST}/api/tags` lists models and
  `POST /api/show {"model": name}` returns `capabilities`, which contains
  `"vision"` for a vision model (checked against the running server, which
  returned `vision` for qwen3.5-35b-128k, and
  https://docs.ollama.com/api, 2026-10-31).
- Import names are the packages' own: `df` (deepfilternet), `kokoro_onnx`
  (kokoro-onnx), `demucs`, `mflux`, `TTS` (coqui-tts), `sentence_transformers`;
  they are confirmed by `verify()` the first time an engine task installs
  them. Nothing was installed in this task.

## 2026-10-31 — TASK-56 T25a timeline model (Clip.segments + Clip.tracks)

- `Clip.segments` (list of `[start, end]` source seconds, at least one,
  `0 <= start < end`) and `Clip.tracks` (`Timeline` with the seven SPEC-v2 4
  tracks) replace the `start`/`end` columns. `Clip.start`/`Clip.end` stay as
  read-only pydantic `@computed_field` properties: the earliest segment start
  and the latest segment end (the span v1 stored). They are serialized in
  every API response (so v1 clients and the editor are unchanged) and appear
  in the serialization JSON schema with `readOnly` (so types.ts keeps them),
  but are not inputs. `ClipPatch` still takes `start`/`end`: they move the
  first segment's start and the last one's end (`timeline.respan`), and the
  video track is rebuilt from the segments; other tracks are kept.
  Checked against the installed pydantic 2.14.2 (`computed_field` +
  `model_json_schema(mode="serialization")`) and
  https://docs.pydantic.dev/latest/concepts/fields/#the-computed_field-decorator
  (2026-10-31).
- Track item kinds: only `"source"` exists (a section of the source video,
  start/end in source seconds, `asset_id` null); later tasks add kinds as
  their features land (no unused values). Video item ids are `video-<index>`
  in both `timeline.py` and the migration.
- Migration 004 rebuilds the clip table (create/copy/drop/rename, the
  documented way to drop columns: https://www.sqlite.org/lang_altertable.html
  "Making Other Kinds Of Table Schema Changes", 2026-10-31). The runner already
  turns foreign keys off, so dropping `clip` keeps jobs. The `sqlite_sequence`
  row of `clip` is copied to the new table (https://www.sqlite.org/autoinc.html:
  sqlite_sequence may be changed with ordinary INSERT/UPDATE/DELETE), so ids
  of deleted clips are never reused.
- Floats in the migrated JSON are written with `json(printf('%!.17g', x))`:
  `json_array(x)` of a REAL rounds to 15 digits in SQLite 3.53.1 (the
  version in the project venv: `0.30000000000000004` became `0.3`) but not in
  3.53.4, and `%!.17g` round-trips every double (checked on 20 000 random
  values with both versions; https://www.sqlite.org/printf.html, 2026-10-31).

## 2026-10-31 — TASK-57 T25b assets, rights and usage records

- SQLite `ALTER TABLE ... ADD COLUMN` adds the three project columns in
  place (NOT NULL needs a non-NULL default, so `credit_line` defaults to '');
  https://www.sqlite.org/lang_altertable.html, 2026-10-31. No table rebuild.
- "Rights not set" is `source_rights IS NULL`, exposed as the read-only
  computed field `Project.rights_set`; the publishing guard comes with the
  publishing tasks. `campaign_id` has no foreign key until the campaign table
  exists.
- The migration registers brand files from `brand_template` in SQL. The
  bundled fonts live in `assets/fonts`, which SQL cannot list, so
  `assets.register_bundled_fonts` registers them (by file name, with the
  font's own copyright notice and license OFL-1.1) every time `init_db` runs;
  a moved project directory updates the paths instead of adding rows.
- `AssetRow`/`UsageRecordRow` live in `asset_rows.py`, not `db.py`, to keep
  `db.py` from growing (it imports `assets` lazily in `init_db`: assets
  imports db).
- `usage_record.project_id` is `ON DELETE SET NULL`: spend history (monthly
  caps) must survive deleting a project.

## 2026-10-31 — TASK-58 T25c source rights + credit line in the API and Home

- No new third-party API: FastAPI `Form()` takes the `SourceRights` Literal
  (checked by `test_upload_rejects_a_bad_enum`: 422 `validation_error`).
- `ProjectCreate` and the upload form take `source_rights` (optional) and
  `credit_line` (max 200). The API stays usable without rights (the CLI and
  v1 clients); the Home panel requires the select (native `required`), since
  publishing is refused without rights (`rights.rights_ok`, used by the
  publishing tasks).
- `ProjectPatch` fields are all optional now; `model_fields_set` tells what
  to change, `{}` is still 422, `source_rights: null` unsets the rights.
  `ProjectPatch` joined `REQUEST_MODELS` in `gen_types.py` so its fields stay
  optional in `types.ts`.
- `SettingsPanel.onSubmit(settings, rights)`: `ProcessingSettings` is
  unchanged (rights belong to the project, not to the processing settings).

## 2026-10-31 — TASK-59 T26a job worker pool

- The claim is one `UPDATE job SET status='running' ... WHERE id = (SELECT id
  ... ORDER BY priority DESC, id LIMIT 1) RETURNING id, kind, project_id,
  clip_id`. RETURNING exists since SQLite 3.35.0 (venv: 3.53.1) and all
  changes happen in the statement's first step, inside its write
  transaction; https://www.sqlite.org/lang_returning.html, 2026-10-31.
  SQLAlchemy 2.1.6 `update(...).returning(...)` emits it for SQLite. A
  single write statement, so two connections (threads or processes) never
  claim the same job (`test_two_workers_never_claim_the_same_job`, 8
  engines, 150 jobs, lockstep rounds).
- Priority is a plain integer column (migration 006, default 0, so v1 jobs
  keep their oldest-first order); higher runs first. `enqueue_process`,
  `enqueue_render` and `process.create_job` take `priority=0`; no caller
  sets another value yet (simplest option).
- Settings: `workers` (default 2), `job_concurrency` (default `process: 1,
  render: 2`), `gpu_job_kinds` (default `[process]`: Whisper, MediaPipe and
  YAMNet run in the process job; render is ffmpeg libx264 on the CPU). A
  kind with no limit is capped only by `workers`. Unknown kinds or a value
  below 1 are a ValueError when the pool is built (config cannot import
  `models.JobKind`: models imports config).
- The per-kind slots and the GPU lock are in-process (`WorkerPool`), taken
  under the pool's mutex in the same step as the claim. One app process runs
  the pool; the CLI runs its pipeline in-process without the pool.
- `JobWorker` is replaced by `worker_pool.WorkerPool` (same start/wake/stop
  API); `jobs.run_next` stays (claim + run one job). The new tests live in
  `backend/tests/unit/test_worker_pool.py` (the task listed `tests/`; unit
  tests are in `tests/unit/`). The job body in the pool tests is a recording
  runner (the pool's own scheduling is what is tested).

## 2026-10-31 — TASK-60 T26b resumable jobs

- Resume = stage markers: `steps/<name>.done` in the job's work directory,
  written (atomic `write_text`) by `process.run_step` after a step returns,
  and by `process_clips` after the clips are saved (`clips`) and the layouts
  planned (`reframe`). A marked stage is not called at all on a restart (the
  old output-exists check only lived inside each step and did not cover
  steps with several outputs). A clip that is `rendered` with its mp4 on disk
  is not rendered again. `run_step` does not rewrite an existing marker unless
  `force` (so `clipforge step` without `--force` changes nothing on disk).
- The clips of a process job are deleted only while the `clips` marker is
  absent (moved from `jobs.run_claimed` to `process_clips.clear_unsaved_clips`
  at the start of `run_process_job`), so resumed clips keep their ids and
  their crop plans. Clip ids are AUTOINCREMENT, so a re-save never reuses an
  old `crop_<id>.json`.
- Attempts: migration 007 `job.attempts INTEGER NOT NULL DEFAULT 0`; v1 jobs
  that are not queued get 1 (a worker started them once). `claim_next` adds 1
  in its atomic UPDATE (`SET attempts = job.attempts + 1`, SQLAlchemy 2.1.6
  compiles `col(JobRow.attempts) + 1` to that; checked with
  `update(...).compile()`, 2026-10-31).
- Poison job = a job that was running when the app stopped at each of
  `job_max_attempts` (default 3, setting `JOB_MAX_ATTEMPTS`) attempts:
  `reset_stale_jobs` fails it (and its project for a process job, and its
  clips still `rendering`) instead of queueing it. A job that raises an
  exception still fails at once (v1 behavior; those errors are user-fixable,
  such as a bad source), so attempts only count starts. Simplest option.
- The kill test runs a real worker subprocess (`backend/tests/resume_worker.py`)
  whose `signals` step waits forever, and kills it with `Popen.kill()`
  (SIGKILL on POSIX: "Kill the process with SIGKILL", CPython 3.11
  `subprocess.Popen.kill` source, checked 2026-10-31). The test file is
  `backend/tests/unit/test_job_resume.py` (the task listed `tests/`; unit
  tests live in `tests/unit/`).
- `process.py` was near 300 lines: the clip stages moved to
  `process_clips.py` and the job-row helpers to `job_rows.py`.

## 2026-10-31 — TASK-61 T26c engines framework

- Facts checked 2026-10-31: Ollama `GET /api/version` returns
  `{"version": "0.34.4"}` on the local server (curl); `/api/tags` and
  `/api/show` as in docs/stack.md. PyPI JSON (https://pypi.org/pypi/<name>/json)
  for the README install lines: deepfilternet 0.5.6 (MIT), kokoro-onnx 0.6.1,
  demucs 4.1.0 (MIT), mflux 0.24.0 (MIT, Python >=3.11), coqui-tts 0.28.0
  (MPL-2.0), sentence-transformers 6.2.0 (Apache-2.0), piper-tts 1.8.0
  (GPL-3.0-or-later; https://github.com/OHF-voice/piper1-gpl).
- An engine is detected without importing or running it: `find_spec` for a
  package, `shutil.which` for a program, the Ollama API and the YAMNet files.
  The pytest `verify` (import / `--help` / load) stays in the engine tests, so
  a broken install fails there while a missing one skips. Simplest option.
- The result of each check is cached in the process (`install_status`);
  `GET /api/engines?refresh=true` runs them again. No TTL: the Settings page
  has a "Check again" button.
- `GET /api/engines` returns a list of `EngineStatus` (the flag is
  `installed`); the response models live in `engines/base.py` (like the other
  API models) and are a gen_types source. The task listed
  `backend/tests/test_engines.py`; the tests are `tests/unit/test_engines.py`
  (existing file) and `tests/api/test_engines_api.py`.
- The README link of "see setup" is `https://github.com/omairtemurian/clipforge#engine-<name>`
  (GitHub heading anchors); a test checks each anchor has a README heading.

## 2026-10-31 — TASK-62 T26d usage meter

- Facts checked 2026-10-31: the OpenAI chat completion has
  `usage.{prompt_tokens, completion_tokens, total_tokens}`
  (https://github.com/openai/openai-openapi/blob/master/openapi.yaml);
  Ollama `/api/chat` (stream false) has `prompt_eval_count` (prompt tokens)
  and `eval_count` (reply tokens)
  (https://github.com/ollama/ollama/blob/main/docs/api.md). Copilot's chat API
  takes the OpenAI shape. An answer without `usage` records nothing.
- Kinds are `compute` (seconds per job, recorded by `jobs.run_claimed` even
  when the job fails), `llm_tokens` (one record per LLM answer) and
  `api_calls` (for the later stock/TTS tasks; nothing records it yet, so it
  totals 0). An LLM call is not also counted as an API call. `cost_usd` stays
  NULL for tokens: prices differ by model and plan, and Copilot is flat-rate.
- The client finds its project through a `ContextVar` (`usage.recording`) so
  the `LLMClient` protocol and the pipeline steps did not change; a call
  outside a job (the connection test, regenerate-text) opens its own context.
- Caps are three flat settings (`usage_cap_compute_hours`,
  `usage_cap_llm_tokens`, `usage_cap_api_calls`; 0 = none) so they use the
  existing `.env.local` writer. A month is the UTC calendar month. Once any
  kind's total reaches its cap, `POST /projects`, `POST /projects/upload` and
  `POST /clips/{id}/render` answer 409 `usage_cap_exceeded`; a running job is
  never stopped, and regenerate-text is not a job so it is not blocked.
- Metering never fails a job: a record that cannot be written is logged.
- `GET /api/usage?month=YYYY-MM` returns the totals per kind and per project.
  The tests are `tests/unit/test_usage.py` and `tests/api/test_usage_api.py`
  (the task listed `backend/tests/test_usage.py`).

## 2026-10-31 — TASK-63 T27a generic video URL import

- Facts checked 2026-10-31 in the installed yt-dlp 2026.10.26 (source and
  `yt_dlp.extractor.list_extractor_classes()`; docs
  https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md): Vimeo is
  `extractor/vimeo.py` `VimeoIE` (`vimeo`), Zoom recordings are
  `extractor/zoom.py` `ZoomIE` (`zoom`, `*.zoom.us/rec/play|share/<id>`; some
  recordings need a passcode or email sign-in and then fail with yt-dlp's own
  message), Dropbox is `Dropbox`. Every URL also matches `GenericIE`.
- A link is supported when a non-generic, working (`_WORKING` true)
  extractor's `suitable(url)` is true, or when its path ends in a video,
  audio or manifest extension (`MEDIA_EXTENSIONS`), which the generic
  extractor downloads as it is. Any other page is 422 `unsupported_source`
  with a message naming the host: yt-dlp's generic extractor would only
  guess at embedded players. The list is read from the installed yt-dlp, no
  site is hardcoded. `POST /projects`, `POST /sources/probe` and the ingest
  step (`download`, `probe`) all call `extractors.require_supported`.
- Found by the real-generic-extractor test: a direct media link has no
  `height`, so `YTDLP_FORMAT` (`[height<=1080]`) matches nothing ("Requested
  format is not available"). Direct links use `DIRECT_FORMAT = "bv*+ba/b"`;
  `YTDLP_FORMAT` itself is unchanged.
- yt-dlp refuses `file://` URLs unless `enable_file_urls` is set, so the
  end-to-end tests run the real generic extractor on a local file by
  swapping the URL inside a test `YoutubeDL` subclass; no network is used.
- Existing API tests used `https://example.com/watch?v=abc`; they now use a
  YouTube URL because example.com has no extractor.

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

## 2026-10-31 — TASK-13 Copilot Responses API (STEERING item 2)

- Some Copilot models are served only at `/responses`: GET
  https://api.githubcopilot.com/models (same headers as chat) lists
  `supported_endpoints: ["/responses", "ws:/responses"]` for gpt-6-luna and
  gpt-5.6-luna; gpt-4.1 has no such field and POST /responses refuses it
  (`unsupported_api_for_model`). `CopilotClient.complete_json` fetches the
  list once per token (module cache in `clipforge/llm_responses.py`, keyed by
  URL and a sha256 of the token, never the token itself) and posts to
  `/responses` when the model lists `/responses` but not
  `/chat/completions`; every other model (also unlisted ones) keeps
  `/chat/completions`. A failed list fetch logs a warning, uses chat
  completions, and is retried on the next call (failures are not cached).
- Request and reply shapes checked against
  https://developers.openai.com/api/reference/resources/responses/methods/create
  (2026-10-31) and a recorded Copilot reply (gpt-5.4-nano): body `{model,
  input: [{role: system}, {role: user}], text: {format: {type:
  json_object}}}`; the reply text is the joined `output_text` parts of the
  `type: "message"` items of `output` (reasoning items may come first);
  `usage.total_tokens` goes to the usage meter. No output text (status
  `incomplete`, refusal) is an `LLMError`.
- The system prompt is an input message, not `instructions`: Copilot
  answered 400 "Response input messages must contain the word 'json' in some
  form to use 'text.format' of type 'json_object'" when the only "JSON" was
  in `instructions`, and 200 with system + user input messages.
- `llm.py` stayed under 300 lines by moving the chat reply models to
  `llm_replies.py`; `llm_http.get_json` is the GET twin of `post_json` (same
  errors and redaction). `FakeLLMServer` answers GET /models apart
  (`models=`, `.model_requests`) so the one-request asserts still hold; an
  autouse fixture clears the model cache around each test.
- Live: gpt-6-luna is refused (`model_not_supported`) on this machine, so the
  default model stays gpt-4.1 (docs/questions.md).

## 2026-10-31 — TASK-15 hardware H.264 encoding (VideoToolbox, STEERING item 3)

- Setting `video_encoder` (`VIDEO_ENCODER`, config.yaml, Settings page
  "Rendering" select): `libx264` or `h264_videotoolbox`. Unset (empty), it
  is `h264_videotoolbox` when `ffmpeg -hide_banner -encoders` of the
  ffmpeg in use lists it, else `libx264` (`clipforge/encoders.py`, asked
  once per binary). The Settings API lists the encoders ffmpeg has
  (`video_encoders`) and refuses (422) one it lacks.
- `ffmpeg -h encoder=h264_videotoolbox` (ffmpeg-full 9.0.2) has no -crf or
  -preset; it takes `-q:v` (constant quality 1-100 on Apple Silicon),
  `-b:v`, `-profile`, `-allow_sw` and others. Renders use
  `-c:v h264_videotoolbox -q:v (120 - 2.5 * crf)` within 1-100 (crf 20 ->
  70, preview crf 28 -> 50); libx264 keeps `-preset` and `-crf`. Both keep
  `-pix_fmt yuv420p`, the fps filter, AAC and `+faststart`; VideoToolbox's
  output is H.264 High profile, yuv420p.
- The mapping was picked by SSIM: on the 60 s fixture at 1080x1920, libx264
  crf 20 scored 0.99887 and VideoToolbox q 50/60/65/70 scored
  0.99642/0.99778/0.99809/0.99858, so q 70 is the closest.
- Timing, one 30 s 1080x1920 clip (fill layout, two-pass loudnorm) of the
  owner's preview source 3 (1920x1080 29.97 fps, 600-630 s), Apple M4 Max,
  `render_clip`, two runs each:

  | encoder | time | size | SSIM vs crf 4 reference |
  |---|---|---|---|
  | libx264 (medium, crf 20) | 12.1 s, 12.3 s | 24.9 MB | 0.99177 |
  | h264_videotoolbox (q 70) | 3.3 s, 3.3 s | 31.0 MB | 0.99131 |

  About 3.7x faster at the same quality, files about 25% bigger.
- Previews use the same `video_encoder` (at crf 28). The ffprobe-checked
  render tests (captions, cuts + loudnorm, layouts, crop tool, `clipforge
  run`) run once per encoder (`encoder` / `render_settings` fixtures in
  tests/pipeline/conftest.py; an encoder ffmpeg lacks is skipped). libx264
  writes its options into the stream (`crf=20.0`); VideoToolbox does not, so
  the run test checks that only for libx264. The test of a failing render
  (bad libx264 preset) pins `video_encoder="libx264"`.

## 2026-10-31 — TASK-24/TASK-25 smaller lower-third captions (STEERING item 4)

- Owner feedback on real clips: the captions were too big and sat in the
  middle of the frame. All six templates now default to `position:
  lower_third` and 3 words a line; `CaptionPosition` is `top | middle |
  lower_third | bottom` (SPEC 6.9 listed bottom|middle; middle and bottom
  keep their old placement). No migration: stored `caption_style.position`
  values stay valid.
- Sizes are about 62% of the old ones, outline and shadow scaled alike
  (outline at least 1.5 so thin text keeps an edge):

  | template | size | outline | shadow | before |
  |---|---|---|---|---|
  | karaoke_bold | 62 | 3.7 | 1.9 | 100, 6, 3 |
  | comic | 62 | 5 | 3.7 | 100, 8, 6 |
  | neon | 57 | 2.5 | 0 | 92, 4, 0 |
  | boxed | 50 | 8.8 (box padding) | 0 | 80, 14, 0 |
  | minimal | 40 | 1.5 | 1.2 | 64, 2, 2 |
  | clean_subtitle | 37 | 1.9 | 1.2 | 60, 3, 2 |

  The owner's target "cap height ~5-6% of frame width per line" is read as
  the line height (the template size, which libass makes the font's
  winAscent + winDescent): 62 px is 5.7% of 1080. Taken as the capital
  letters' height it would need Montserrat at size 120-145 (its cap height
  is 0.448 of the size, OS/2 sCapHeight 700 / (1109 + 453); Inter's 0.601),
  larger than before, which contradicts "60-65% of today". Scaling every
  template by the same factor keeps the Inter templates' capitals (minimal
  24 px, clean_subtitle 22 px) close to karaoke_bold's (28 px), as before.
- Placement (`CAPTION_PLACES` in pipeline/captions.py; alignment, vertical
  margin as a share of the frame height): top 8 / 0.18 (below the hook at
  0.1), middle 5, lower_third 2 / 0.22, bottom 2 / 0.15. Measured with
  libass on 1080x1920 (tests/pipeline/test_caption_placement.py): a
  karaoke_bold line covers rows 1451-1480 (75.6-77.1%), two wrapped lines
  1389-1480 (72.3-77.1%), so the block sits in 70-78%, above the bottom
  ~12% where the platforms draw their buttons and text.
- At most two lines: an event shows one caption line of at most 3 words;
  at these sizes libass wraps three long words ("Unbelievable extraordinary
  performance") into two lines, never three.
- The active word only changes color (100% size, within the owner's
  <= 105%); emphasis words keep 110%.
- Template preview PNGs are cached by a hash of their ASS text, so they are
  redrawn with the new values on first request. The editor's Captions panel
  already had the size slider; its position chips are now Top, Middle,
  Lower third, Bottom.
- Visual check on the owner's preview source 3 (600 s + 2.85 s, 9:16
  center crop): .agent/screenshots/fix-captions-1.png (left before, right
  after); fix-captions-2.png is the new karaoke_bold preview.


## 2026-10-31 — TASK-27 auto cut silences (STEERING item 5a)

- New processing settings `auto_cut` (default **on**, owner request) and
  `auto_cut_min_pause_s` (default 0.5, 0.2-3). A new clip's `cut_ranges`
  take out each silence longer than the min pause: between two spoken
  caption words of the clip (`polish.spoken_pieces`, so never inside a
  word; a word that overlaps the next leaves no gap), and between the
  clip's start or end and its first or last word. Each cut keeps 0.12 s
  of silence after the word before it and before the word after it
  (`auto_cut.PADDING_MS`), so a 0.5 s pause becomes a 0.26 s cut.
- Gaps during a laugh or applause event are kept (as polish does): the
  audience's reaction is part of the joke. A gap is compared with the
  threshold by its length in ms (`> min pause`), so a 0.5 s gap stays.
- Separate from `remove_fillers`: either, both or neither may be on;
  `auto_cut.new_clip_cuts` merges their cuts (`merge_ranges`), and
  `save_clips` reads the transcript and signals only if one is on.
- The cuts are ordinary cut ranges: the editor shows them in the
  transcript and timeline and restores them one by one. The clip stores
  `auto_cut` (migration 008, `BOOLEAN NOT NULL DEFAULT 0`: older clips have
  none). The Layout panel's "Auto cut silences" switch asks
  `GET /clips/{id}/auto-cuts?start&end` (the project's min pause, the
  editor's unsaved span) and, in one undo step, adds those cuts (on) or
  takes out what they cover (off, `subtractCuts`): a user cut that
  overlaps an auto cut keeps only its parts outside it.
- The cleanup-suggestions endpoint moved with it to `api/clip_cuts.py`
  (same route and behavior).
- On the fixture's clip A (0.5-34.35 s) auto cut takes 9 cuts, 3.44 s:
  the 33.85 s clip renders as 30.5 s (`clipforge run` test).

## 2026-10-31 — TASK-23 auto zoom punch-ins (STEERING item 5b)

- New processing setting `auto_zoom` (default **on**, owner request). A new
  clip stores `auto_zoom` and `zoom_keyframes: [{t, scale}]` (source
  seconds, scale 1-2; migration 009, `BOOLEAN NOT NULL DEFAULT 0` and
  `TEXT NOT NULL DEFAULT '[]'`). Keyframes are made only when the setting
  is on; the editor's "Auto zoom" switch (Layout panel) asks
  `GET /clips/{id}/auto-zooms?start&end` and sets them when turned on;
  turning it off keeps them (the render ignores them), so the keyframes
  can be edited later (v2 timeline).
- Triggers (`pipeline/auto_zoom.py`): emphasis words (runs of
  `mark_emphasis` over the clip's caption words) at 1.15x, laugh /
  energy_peak starts at 1.13x, new sentences at 1.12x. A new sentence is
  the end of each auto-cut silence (`auto_cuts`, computed even when
  `auto_cut` is off), so the zoom is fully in on the first word after the
  cut. Selection is by priority (larger scale first, then time) so
  emphasis words are not crowded out by earlier sentence triggers: a
  trigger is kept if it is >= 3 s from every kept one, its 0.2 s ramp-in
  starts inside the clip, and it can hold >= 1.5 s before end - 0.5 s.
  Each punch-in: (t-0.2, 1), (t, s), (t+hold, s), (t+hold+0.5, 1), hold =
  min(2 s, room left). Ramps are linear (piecewise `ramp_expr` in
  layouts.py, also used by the crop window).
- ffmpeg method (verified on ffmpeg 9.0.2, `ffmpeg -h filter=scale` / `crop`):
  `scale=w='2*trunc(W*(Z)/2)':h='2*trunc(H*(Z)/2)':eval=frame` then
  `crop=w=W:h=H:x=..:y=..`, `setsar=1`, where Z is the ramp expression in
  `t`. crop's `iw`/`ih` keep the first frame's size when the input grows
  per frame, so `(iw-ow)/2` zooms toward the top-left; the scaled size is
  written out again in crop's x/y expressions. Odd x/y are rounded by
  crop for chroma. zoompan was not used: it makes `d` output frames per
  input frame and its expressions count frames (`in`/`on`), not
  timestamps, so scale+crop with `t` fits the source-time keyframes.
- The zoom runs on the framed stream right after the layout
  (`[unzoomed]` label in `render_graph.clip_graph`), in source time,
  before the cuts and captions: captions and the brand do not zoom.
  Center (`zoom_graph.subject_center`): in fill, the first face of the
  nearest crop keyframe relative to the crop window (respects user
  nudges); fit/split zoom on the frame center. The crop window is
  clamped so the frame never shows outside the scaled image.
- Preview keys include `auto_zoom` and `zoom_keyframes`.
- On the fixture's clip A (0.5-34.35 s) 7 punch-ins (2.53, 6.63, 12.99
  "floor?", 19.24, 23.13, 27.53, 30.53): zoomed about 70% of the time,
  which may be busy on real clips; constants live in `auto_zoom.py`.

## 2026-10-31 — TASK-22 reframe tracker quality (STEERING item 6)

- Detection (`pipeline/detectors.py`): MediaPipe BlazeFace **full-range**
  (verified on mediapipe 0.10.33: same `FaceDetector` Tasks API, model
  `blaze_face_full_range/float16/1`; Apache-2.0) instead of short-range.
  On 48 frames (640x360) of the owner's project 3 source, short-range found
  faces in 9, full-range in 26; on the fixture shrunk to 400x225 in a
  1280x720 frame (a ~75 px face), short-range 0 of 40 samples, full-range
  32-34. Where no face is found, the EfficientDet-Lite0 object detector's
  "person" boxes (score >= 0.4) stand in (`FaceBox.kind = "person"`; found
  in 36 of the 48 frames); people count for the subject, never for split.
  Sampling is 10 fps (`SAMPLE_FPS`), so plans have twice the keyframes.
- Mouth opening: the face landmarker (`face_landmarker/float16/1`) run on a
  1.5x crop of each of the 4 largest faces, scaled to 256 px (the full
  frame's faces are too small for it: on 3x crops it measured 47 of 58
  faces). Opening = inner-lip gap (landmarks 13/14) / forehead-chin height
  (10/152), in `FaceBox.mouth`.
- Identity (`pipeline/identity.py`): greedy nearest-center matching
  (distance < 1 width of the wider box, same kind), a track ends after
  > 10 unseen samples (1 s) and at every scene cut. Stored in
  `FaceBox.track`.
- Subject (`pipeline/speaker.py`): mouth activity = population std-dev of a
  track's openings within +-0.5 s that fall in transcript speech (no
  transcript.json: all samples count). Leader = most active track if
  >= 0.01 (ties: larger face, then older track). A shot starts on the
  leader, else the largest face. A challenger takes over after leading at
  >= 1.5x the subject's activity for 19 samples in a row: the 1 s of
  STEERING plus the +-0.5 s window its activity spreads over (minus one);
  checked exactly: 0.9 s of talk does not switch, 1.0 s does. Since the
  whole clip is known, the switch is backdated to where the talk started.
  A subject unseen for 1 s gives way to the leader / largest face,
  backdated to just after it was last seen. `FaceBox.subject` marks it, so
  `replan` (other aspects) and auto zoom (`zoom_graph.subject_center`) use
  the same subject without re-choosing.
- Smoothing (`pipeline/smoothing.py`, `tracking.follow`) per shot:
  forward + backward EMA (alpha 0.3, padded with 20 copies of each end so
  the ends do not sag; a filtfilt-style zero-lag filter in pure Python, so
  scipy is not needed), then the 8% dead-zone (the aim jumps to the path
  when it is more than 4% away), then a speed limit of 25% of the frame
  width a second, applied forward and backward and averaged so the pan is
  centered on the move (starts before, ends after) instead of lagging.
  Hard reset at scene cuts. Gaps: < 1 s holds the subject's last center,
  longer gaps interpolate; when the subject changes within a shot, the
  samples between the old one's last center and the new one's first take
  the new one's (not a detection gap; the window heads there at once).
- Visual check on project 3 clips 3 and 5 (.agent/screenshots/
  fix-tracker-1..3.png, red = before, green = after): samples with a
  subject 28/81 -> 147/161 and 40/75 -> 149/149; the old window sat on
  empty background or the wrong person in all three frames. Reframing the
  two clips (31 s) took 1.4 s before, 5.1 s after.
- Known trade-offs: a 2-shot speaker change pans at 25%/s (a 400 px move
  takes ~1.6 s), as STEERING asks; full-range also finds small audience
  faces in crowd shots, which makes `wants_split` (> 60% of samples with
  two faces) more likely there. Models: ~19 MB in `models/face/`.

## 2026-11-01 — TASK-54 per-scene reframe modes (STEERING item 7)

- Storage: `Clip.scene_reframes` (migration 010), a list of
  `SceneReframe {start, end, mode auto|track|fixed, layout, crop_keyframes,
  scale, track_seed}` covering the clip's span in order. Empty (the
  default) means "framed as `layout` throughout", so old clips and clips
  whose scenes are all auto in one layout keep the old render and preview
  keys. The editor stores scenes only when they differ
  (`lib/scenes.compactScenes`). `GET /clips/{id}/scenes` gives the source's
  scene cuts (signals.json) and the clip's scenes (stored, or split at the
  cuts that are >= 0.5 s from the clip's ends and each other).
- PATCH validates scenes (contiguous and covering start..end, within
  1 ms; each has end > start) and snaps their edges to the span and to
  each other; a span change without new scenes stretches/drops the stored ones
  (`pipeline/scenes.fit_scenes`). Keyframe times are not validated: they
  hold before the first and after the last, as in the crop tool.
- Render (`pipeline/scene_framing.scene_parts`, `scene_graph.py`): each
  scene gets its own plan: auto = the clip's framed plan (crop offset,
  tracker, crop tool keyframes as before), fit/split = that plan in that
  layout, fixed/track = a plan with one keyframe per crop keyframe (window
  size = scale x the clip's fill window), linear between keyframes and held
  outside, so nothing interpolates across a scene edge. Neighbouring scenes
  with the same plan and layout are merged; more than one part becomes
  `split` + per-part `trim`/`setpts` + the layout graph + `concat`. Zoom
  keyframes still apply to the whole clip after the parts.
- A fixed scene without keyframes holds the clip's window at its start.
- Splitting a scene with keyframes (timeline split) gives both halves a
  keyframe at the split, where the window is then.
- "Apply to all scenes": auto/fit/split copy the choice; fixed or track
  makes every other scene fixed at the current window (one keyframe at its
  start), since tracking is per scene.
- The crop position nudge (clip-wide offset) only applies to auto fill
  scenes; the crop tool edits the scene's keyframes in a fixed scene and
  the clip's framing otherwise.

## 2026-11-01 — TASK-54 click-to-track subject (STEERING item 7b)

- Tracker: OpenCV CSRT. Verified on this machine 2026-11-01:
  `opencv-contrib-python` 5.0.0 has `cv2.TrackerCSRT.create()` and
  `cv2.TrackerKCF.create()` (init(frame, (x, y, w, h)), update(frame) ->
  (ok, box)); a synthetic square moving 120 px/s is followed within 0.05 of
  the frame. `pipeline/click_track.opencv_tracker` takes CSRT, else KCF;
  if the build has neither, `DetectorTracker` follows the face/person box
  (pipeline/detectors) nearest the last one (lost beyond 2 box widths).
- Seed: a dragged box is tracked as drawn; a click (seed width = height =
  0) takes the smallest face/person box around the click on the seed frame,
  else a square of 15% of the frame height centered on it. The resolved box
  is returned and stored as the scene's `track_seed`.
- Frames: the scene sampled at 10 fps (faces.sample_times), scaled to 320
  px on the longer side, decoded 50 at a time; one tracker runs forward from
  the seed frame and one backward (slices decoded in reverse), so a long
  scene never sits in memory.
- Smoothing: box centers, held where the tracker lost the subject
  (tracking.fill_gaps), go through item 6's `tracking.follow` (zero lag,
  8% dead zone, 25%/s speed limit) for x and y; the keyframes keep only the
  samples a straight line misses by more than 0.005 of the frame
  (Ramer-Douglas-Peucker), about 1-2 per second for a moving subject.
- API: `POST /clips/{id}/scenes/track {start, end, seed}` ->
  `{keyframes, seed}`; synchronous (a 34 s scene tracks in ~3 s here). 422
  if the scene is not inside the clip or the seed not inside the scene,
  409 if the source or meta.json is missing.
- UI: "Track" in the Layout panel; a track scene without keyframes (or
  after "Pick another subject") shows the source frame to click or box the
  subject; the result makes the scene `track` at the returned keyframes and
  saves the clip at once, and the preview URL carries a hash of the saved
  clip (`lib/previewUrl`) so the 540p proxy reloads (at the same time) after
  every save. This fixes the old "preview keeps its URL after Save" problem.

## 2026-10-31 — TASK-13 copilot_account, fenced JSON replies, default claude-sonnet-5.5 (STEERING 8)

- Probe results (Hermes, 2026-10-31, direct calls to api.githubcopilot.com
  with each account's `gh auth token`): account omairtemurian can use only
  gpt-4.1 (/chat/completions) and gpt-5.4-nano (/responses); claude-haiku-4.5,
  kimi-k3-copilot and gpt-6-luna answer 400 `model_not_supported`. Account
  <your-github-account> (owner approved): claude-sonnet-5.5 and claude-opus-5.5 work
  on /chat/completions, gpt-6-luna and gpt-6.1-sol on /responses, with
  Copilot-Integration-Id vscode-chat and copilot-developer-cli alike.
- New setting `copilot_account` (COPILOT_ACCOUNT; config.py, config.yaml,
  .env.example, Settings page "GitHub account" under GitHub Copilot): the
  account of `gh auth token -u <account> -h github.com` when
  GITHUB_COPILOT_TOKEN is empty (the token still wins). The Settings API
  accepts only a GitHub account name (letters, digits, `-`, `_`; not starting
  with `-`, as it is an argument of gh). The old constant `GH_USER`
  (omairtemurian) is gone.
- Defaults (owner decision 2026-10-31): `copilot_account` <your-github-account>,
  `llm_model` claude-sonnet-5.5; gpt-6-luna (Responses API) is the documented
  alternative (`LLM_MODEL=gpt-6-luna`). The owner's `.env.local` pinned
  `LLM_MODEL=gpt-4.1` (a copy of the old .env.example value), which would
  have kept the old model on this machine; that one line was changed to
  claude-sonnet-5.5.
- Claude models ignore `response_format: json_object` and may wrap the JSON
  in a Markdown fence ("```json\n{...}\n```"). `llm_replies.reply_json`
  (exported by clipforge.llm) strips one fence around the whole reply,
  with any language tag (json, JSON, json5, none), before validation; curate
  and regenerate-text both use it (it replaces curate's `CODE_BLOCK`, which
  only knew a `json` tag). A reply with text before or after the fence is
  left as it is, so it fails validation and the existing retry asks again.
- `test_settings_defaults_match_spec` now builds `Settings(_env_file=None)`:
  it read the owner's .env.local, so a local LLM_MODEL broke it.


## TASK-13: Anthropic API provider (STEERING 9a, 2026-10-31)

`LLM_PROVIDER=anthropic` calls the Anthropic Messages API directly with an
API key (`llm_anthropic.AnthropicClient`). Verified on 2026-10-31 against:

- https://platform.claude.com/docs/en/api/messages: `POST /v1/messages`
  with `model`, `max_tokens`, `system` and `messages`; the reply's
  `content` is a list of blocks, the text in `{"type": "text", "text": ...}`;
  `usage.input_tokens` / `usage.output_tokens`; `stop_reason`.
- https://platform.claude.com/docs/en/api/versioning: header
  `anthropic-version`; the latest is `2026-10-21`, which drops
  `temperature`/`top_p`/`top_k` (we send none). Pinned in
  `ANTHROPIC_VERSION`.
- https://platform.claude.com/docs/en/get-started: headers `x-api-key`,
  `anthropic-version`, `content-type: application/json`.
- https://platform.claude.com/docs/en/api/models/list: `GET /v1/models`,
  `limit` 1-1000 (default 20), reply `data[{id, type, display_name,
  created_at}]`, `has_more`, `first_id`, `last_id`.
- https://platform.claude.com/docs/en/about-claude/models/overview: current
  ids `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`,
  `claude-haiku-5-5`.

Choices:
- Separate `ANTHROPIC_MODEL` (default `claude-sonnet-5-5`) instead of
  `LLM_MODEL`: Copilot names models `claude-sonnet-5.5` (dots) and Anthropic
  `claude-sonnet-5-5` (dashes), so switching provider would otherwise give
  a wrong model name. `llm.model_of(cfg)` returns the model of the active
  provider (shown by Test connection).
- `max_tokens` 8192 (`MAX_TOKENS`): the Messages API requires it; a curate
  reply of 20 clips is well under it.
- Text blocks are joined and parsed by the shared `reply_json` (code fence
  stripped); tokens are recorded in the usage meter like other providers.
- `POST /settings/anthropic-models` lists models with one request
  (`limit=1000`, no paging) for the Settings "Load models" button; the
  form's unsaved key/URL may be sent and are not saved. Errors come back as
  `{models: [], error}` with the key redacted, not as an HTTP error.
- Not the default provider; the opt-in live test (`-m live`) skips without
  `ANTHROPIC_API_KEY`. No key exists on this machine, so the provider is
  verified with mocked HTTP only.

## TASK-13: Claude subscription provider via Claude Code (STEERING 9b, 2026-10-31)

`LLM_PROVIDER=claude_code` runs the installed Claude Code CLI with the
owner's Claude subscription (`llm_claude_code.ClaudeCodeClient`). Flags
checked with `claude --help` on Claude Code 2.1.284 (2026-10-31): `-p`,
`--output-format json`, `--model` (alias or full name), `--system-prompt`,
`--strict-mcp-config`, `--tools ""` (no tools), `--no-session-persistence`.

- argv: `claude -p <prompt> --output-format json --model <model>
  --system-prompt <system> --strict-mcp-config --tools "" --no-session-persistence`,
  cwd an empty temp dir (no project CLAUDE.md/hooks), stdin closed, 300 s
  timeout. The prompt follows `-p` directly because `--tools` takes a list.
- A prompt over 100 KB goes on stdin instead (macOS ARG_MAX ~1 MB; checked
  that `echo ... | claude -p ...` reads the prompt).
- Output: one JSON object; recorded real output (not logged in) in
  tests/fixtures/claude_code_not_logged_in.json: `type "result"`, `subtype
  "success"` even on failure, `is_error true`, `result "Failed to
  authenticate: OAuth session expired and could not be refreshed"`, `usage
  {input_tokens, output_tokens, ...}`. is_error raises LLMError; results that
  mention authentication/login/OAuth get "Claude Code is not logged in. Run
  `claude` in a terminal and log in, then retry." plus Claude's own words.
- Tokens: usage.input_tokens + output_tokens to the usage meter.
- `--json-schema` is not passed: the LLMClient protocol has no schema
  argument (curate, clip_text and test-llm share it), and the structured
  output field of a schema run cannot be verified without a login. The
  fence-stripping `reply_json` and curate's retry validate replies instead.
- Settings: CLAUDE_CODE_BIN (default `claude`, must be an executable when
  changed), CLAUDE_CODE_MODEL (default `sonnet`). Never the default provider.
- `ClaudeCodeEngine` ("Claude subscription (Claude Code)") in the engines
  registry: installed when `<bin> --version` answers, version is its first
  word; marker `engine_claude_code`. Login is only checked by a real call.
- The owner has no subscription today: the live test is opt-in (`-m live`)
  and not run; this is expected, not a blocker.

## TASK-39: Clip settings panel parity (STEERING 10, 2026-11-01)

The owner asked for the settings panel to match the reference tool's
functions (with ClipForge's own names, wording and look).

- Genres: auto, comedy, sports_commentary, faith, news, vlog, gaming,
  podcast, talk, interview, other; each new one has its own curate prompt
  (`prompts/curate_<genre>.md`, our own selection rules). Only comedy gets the
  laugh weight in score and the comedy snap tail.
- Lengths: `ProcessingSettings.length_presets` is a list (min 1, sorted in
  the literal's order, "auto" dropped when others are chosen; the v1
  `length_preset` is still read). A candidate is valid when it fits ANY
  chosen range (`candidate_rules.fits_preset`). New ranges 180_300, 300_600,
  600_900. "auto" is clip_min_s..180 s (`AUTO_MAX_S`) for validation and the
  prompt says "most often clip_min..clip_max": the panel labels it 0-3m.
- Curate windows grow for long clips: chunk = max(chunk_minutes*60,
  2 x longest chosen clip), overlap = max(chunk_overlap_s, longest), so a 15
  minute clip fits in one window.
- Migration 011: clip columns `auto_color` (0) and `show_captions` (1);
  project settings `length_preset` -> `length_presets` with json_set/json_remove.
- Auto headline off: clips are saved with hook_text "" (still editable).
- No captions: `ProcessingSettings.captions=False` -> `Clip.show_captions=False`;
  captions.write_captions then writes no word lines, but the hook still shows.
- Auto color: `render_graph.COLOR_FILTER` =
  `normalize=smoothing=30:independence=0:strength=0.5,eq=saturation=1.12,curves=preset=medium_contrast`
  on the framed video before zoom/captions. Filters and options checked with
  `ffmpeg -h filter=normalize|eq|curves` on ffmpeg-full 9.0.2 (normalize:
  blackpt, whitept, smoothing, independence, strength; eq: saturation;
  curves: preset medium_contrast). Measured on a washed-out copy of the
  fixture: luma spread 21.7 -> 26.9, saturation 117 -> 159 (8-bit RGB);
  tests/pipeline/test_auto_color.py asserts +10 % spread and +20 % saturation.
  normalize alone barely moved the dull test pattern, hence the eq/curves.
- Speech language: `ProcessingSettings.language` (a faster-whisper code or
  null = detect) is passed to Whisper for every chunk.
- SRT: uploaded first (`POST /subtitles`, UTF-8, <= 5 MB, must have cues) to
  `data/subtitles/<32 hex>.srt`; the project carries the token in
  `subtitles_id` (validated as 32 hex, so no path traversal). Transcribe then
  skips Whisper: each cue's words share its time in proportion to their
  length; `Transcript.approximate_times` is true and the language is the
  chosen one or "und".
- Captions only (`clipping: "captions_only"`, was "none" until TASK-69): curate writes one candidate covering the
  timeframe without the LLM (neutral scores, no hook) and snap keeps it as it
  is, so the clip is exactly the timeframe.
- Presets: the default and up to 50 named presets live in
  `data/processing_presets.json` (no DB table: they are app settings, not
  project data). Saved settings exclude timeframe_start/end and
  subtitles_id (they belong to one video). GET /processing-defaults returns
  the saved default or the built-in one, so the panel opens with it.
- Copyright notice: a note under the preview in our own words; it reads the
  panel's required Source rights choice and says which reason was confirmed.

## TASK-64 (T27b): Chunked resumable upload up to 30 GB (2026-10-31)

- Own protocol instead of tus (no new dependency; the app is local):
  `POST /api/uploads {filename, size}` -> `UploadSession{id, filename,
  size, offset}`; `GET /api/uploads/{id}`; `PATCH /api/uploads/{id}?offset=N`
  with the raw chunk and `X-Chunk-SHA256` (hex); `POST
  /api/uploads/{id}/complete` (body as ProjectCreate minus url) -> Project;
  `DELETE /api/uploads/{id}`. `POST /projects/upload` (one multipart
  request) stays for API users and v1 tests.
- Storage: `data/upload_sessions/<32 hex>/{meta.json,data.part}`; the
  offset is the size of data.part, so a restart of the server loses
  nothing. complete renames data.part to `data/uploads/<hex>/<name>` (same
  place as the multipart upload, so project delete still removes it).
  Abandoned sessions are not cleaned up automatically (DELETE does it).
- Limits: declared size 1 B..30 GiB (422), chunk <= 64 MiB (413
  chunk_too_large), offset must equal bytes received (409 offset_mismatch),
  chunk SHA-256 must match (422 checksum_mismatch, nothing written), no
  bytes past the declared size (422). Free-space preflight at create:
  `shutil.disk_usage(data/upload_sessions).free >= size + 512 MiB` else 507
  insufficient_storage (RFC 4918 11.5).
- Chunk writes of one session are serialized by a per-session
  threading.Lock; the body is read with Starlette `Request.stream()` (cap
  enforced while reading) and written in `run_in_threadpool`.
- Frontend `lib/chunkedUpload.ts`: 8 MiB chunks; SHA-256 with
  `crypto.subtle.digest` (localhost is a secure context); session id
  remembered in localStorage under name:size:lastModified so a retry of the
  same file resumes from the server's offset; a network error, 5xx,
  offset or checksum mismatch re-reads the offset and resends, up to 5
  failures in a row (linear backoff 1 s). Progress shows in the settings
  panel footer ("Uploading N%" + progressbar).
- Verified (2026-10-31): installed Python 3.11.15 `shutil.disk_usage`
  (https://docs.python.org/3.11/library/shutil.html#shutil.disk_usage),
  Starlette 1.10.0 `Request.stream()` and
  `starlette.concurrency.run_in_threadpool` (installed source), FastAPI
  0.162.0 `Header(alias=...)`; MDN SubtleCrypto.digest
  (https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest) and
  Blob.slice/arrayBuffer
  (https://developer.mozilla.org/en-US/docs/Web/API/Blob/slice), both also
  present in the Vitest jsdom environment.

## TASK-65 (T27c): Local inbox folder watch (2026-10-31)

- Polling, not OS file events (watchdog): no new dependency, works on any
  folder (network shares, cloud-synced folders) and the "size is stable
  across two polls" rule needs polling anyway. `INBOX_DIR` (empty: off) and
  `INBOX_POLL_S` (default 10) are Settings fields (env, `.env.local` or
  config.yaml); not in the Settings page yet (one folder, SPEC-v2 3.1 names
  "a folder").
- "Stable" = (size, st_mtime_ns) equal in two consecutive polls, so a
  copy that pauses with the same size but still rewrites keeps waiting only
  while the mtime moves. Empty files, hidden files, subfolders and
  extensions that are not video (`VIDEO_EXTENSIONS`; `.ts` left out: it is
  mostly TypeScript) are ignored.
- Imported files are recorded in table `inbox_import` (migration 012),
  key (absolute path, size, mtime_ns), project_id without a foreign key: a
  deleted project is not imported again, a changed or replaced file is.
  The row is written after the project is queued: a crash in between
  imports the file once more (a duplicate, never a loss).
- The project has default `ProcessingSettings` and rights unset (like any
  upload: the owner sets them before publishing). The source file stays in
  the inbox; ingest copies it. A used-up monthly usage cap keeps files
  waiting (retried each poll). A file that fails to import is retried each
  poll and logged.
- Verified APIs (2026-10-31, installed Python 3.11): `Path.stat().st_mtime_ns`
  (https://docs.python.org/3/library/pathlib.html#pathlib.Path.stat),
  `threading.Event.wait(timeout)`; SQLModel composite primary key by
  `Field(primary_key=True)` on several fields (SQLAlchemy composite PK),
  checked by test_migration_inbox_import against the migration.

## TASK-66 (T27d): Google Drive import (2026-10-31)

- Shared OAuth helper `clipforge/oauth.py` (reused by the publishers later):
  authorization-code flow with PKCE S256 and a random `state`; pending
  consents live in memory (one-time, 10 min TTL, lost on restart: the user
  presses Connect again). Tokens are stored by `token_ref` as 0600 JSON files
  in `data/oauth_tokens/` (`oauth_tokens.TokenStore`), not in the DB: no
  migration yet, and `SocialAccount.token_ref` (SPEC-v2 4) can point at the
  same store. Drive uses the fixed token_ref `google-drive` (one account).
  A token is refreshed 60 s before expiry and once after a 401; a refresh
  without a new refresh_token keeps the old one; `invalid_grant` on refresh
  forgets the token (Drive answers 409 drive_not_connected: connect again).
- Desktop app OAuth client ("installed app"): loopback redirect derived from
  the request (`/api/sources/gdrive/callback`, the vite proxy rewrites the
  host to 127.0.0.1:8000). The client secret is optional (sent when set).
  No `access_type=offline`: Google always returns a refresh token to
  installed apps. The callback answers a small HTML page ("you can close
  this window"), 400 for a denied consent or an unknown state; the dialog
  polls `GET /sources/gdrive` until connected.
- Scope `https://www.googleapis.com/auth/drive.readonly` (restricted: a
  public app needs Google's verification; fine for an owner-run local app).
  `drive.file` would need the Google Picker to grant per-file access.
- The project's `source_url` is the canonical Drive link
  `https://drive.google.com/file/d/<id>/view`; the process job downloads it
  with files.get `alt=media` (`supportsAllDrives=true`) into
  `download<ext>.part`, renamed when the size matches the metadata. A Drive
  link with Drive not connected (or not configured) still goes to yt-dlp
  (public links, v1 behavior). Folder links are refused (422
  invalid_drive_link); a non-video MIME type is 422 not_a_video; a file
  with `capabilities.canDownload=false` is 422 drive_file_not_downloadable.
  Resource keys of old shared links are not handled.
- Endpoints in `api/gdrive.py` (not `api/sources.py`, which keeps the link
  probe/SRT upload; one concern per file). Request/response models live
  next to their router like the other API modules (types generated).
- Disconnect only deletes the local token (no call to Google's revoke
  endpoint); README points to the Google permissions page.
- Tests use respx 0.23.1 (dev dependency) with recorded JSON responses in
  `backend/tests/fixtures/gdrive/`; nothing reaches the network.
- Verified docs (2026-10-31):
  - OAuth for installed apps (authorize/token endpoints, PKCE params,
    loopback redirect, refresh, `access_denied`, `invalid_grant`):
    https://developers.google.com/identity/protocols/oauth2/native-app
  - Downloads with files.get `alt=media`, `capabilities.canDownload`:
    https://developers.google.com/workspace/drive/api/guides/manage-downloads
  - files.get (`GET https://www.googleapis.com/drive/v3/files/{fileId}`,
    `supportsAllDrives`):
    https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get
  - File resource (`size` is an int64 string,
    `videoMediaMetadata.durationMillis`):
    https://developers.google.com/workspace/drive/api/reference/rest/v3/files
  - `fields` syntax (`capabilities/canDownload`):
    https://developers.google.com/workspace/drive/api/guides/fields-parameter
  - Scopes (`drive.readonly` restricted):
    https://developers.google.com/workspace/drive/api/guides/api-specific-auth
  - Error shapes (401 authError, 404 notFound):
    https://developers.google.com/workspace/drive/api/guides/handle-errors
  - PKCE S256 test vector: RFC 7636 appendix B
    (https://www.rfc-editor.org/rfc/rfc7636#appendix-B).

## TASK-67 (T27e): Dropbox import, optional (2026-11-01)

- Same shape as the Drive import: `sources/dropbox.py` (link parsing,
  metadata, download) and `api/dropbox.py` (`/sources/dropbox/*`: status,
  connect, callback page, disconnect, file, import) on the shared OAuth
  helper; fixed token_ref `dropbox`. Without `DROPBOX_APP_KEY` the status
  says `configured: false` and the other endpoints answer 412
  `needs_credentials`; a Dropbox link then goes to yt-dlp as before (its
  `Dropbox` extractor handles public links). No frontend dialog: the task
  lists backend files only; the API is usable by curl, the public API
  (`/api/v1` does not mount it yet) and a later UI task.
- Shared links only (`/s/...`, `/scl/fi/...` on dropbox.com): that is what
  Dropbox's "Copy link" gives, and it needs one scope (`sharing.read`) and
  two endpoints. Browsing the account's paths (`files/download`,
  `files.content.read`) is not done. Folder links (`/sh/`, `/scl/fo/`) are
  422 `invalid_dropbox_link`. The link is stored as the project's
  `source_url` (https, `www.dropbox.com`, query kept: `rlkey` is the access
  key of new-style links; fragment dropped).
- OAuth: authorization-code flow with PKCE S256 through the shared helper
  plus `token_access_type=offline` (an `authorize_params` entry) so Dropbox
  returns a refresh token (access tokens last 4 h). The app secret
  (`DROPBOX_APP_SECRET`) is not sent: PKCE replaces it, and Dropbox's own
  PKCE examples send either the verifier or the secret. The redirect URL
  (`http://127.0.0.1:8000/api/sources/dropbox/callback`) must be registered
  in the Dropbox app console exactly (README).
- Metadata has no media info: a video is recognised by the file extension
  (`VIDEO_SUFFIXES`), a folder by `.tag != "file"`. The size comes from the
  metadata and is checked after the download (`.part` file, as Drive).
- Errors: 401 -> 409 `dropbox_not_connected` (after the shared one-time
  refresh); 409 `shared_link_not_found` / `shared_link_access_denied` -> 404
  `dropbox_file_not_found`; `shared_link_is_directory` -> 422; 429 -> 429
  `dropbox_rate_limited`; anything else 502 `dropbox_error`. Dropbox 400
  bodies are plain text, so only the status is shown.
- Verified 2026-11-01 (the developer site renders client-side, so the
  machine-readable sources of the same docs were read):
  - API spec https://github.com/dropbox/dropbox-api-spec (`sharing.stone`:
    `get_shared_link_metadata` auth "app, user" scope `sharing.read` on the
    API host; `get_shared_link_file` style "download", host "content", scope
    `sharing.read`, argument = `GetSharedLinkMetadataArg` {url, path?,
    link_password?}; `FileLinkMetadata` has `size` UInt64 and `.tag` file;
    `SharedLinkError` tags shared_link_not_found / shared_link_access_denied
    / unsupported_link_type; `GetSharedLinkFileError` adds
    shared_link_is_directory).
  - Official SDK https://github.com/dropbox/dropbox-sdk-python
    (`dropbox/oauth.py`: `/oauth2/authorize` on www.dropbox.com,
    `/oauth2/token` on api.dropboxapi.com, `token_access_type`, `scope`,
    `code_challenge` + S256, `code_verifier` instead of `client_secret`;
    `session.py`: hosts api / content `.dropboxapi.com`).
  - OAuth guide https://developers.dropbox.com/oauth-guide and offline access
    https://dropbox.tech/developers/using-oauth-2-0-with-offline-access
    (refresh with `grant_type=refresh_token` + `client_id`, no secret).
  - HTTP conventions (download-style: POST, `Dropbox-API-Arg` header, the
    file as the response body):
    https://www.dropbox.com/developers/documentation/http/documentation
- Untested live (no `DROPBOX_APP_KEY`, docs/questions.md): the consent and
  redirect on a real app, the real error body of `get_shared_link_file`
  (assumed to be JSON like the RPC errors) and new-style links with a
  password.
- Tests: `tests/sources/test_dropbox.py` (28) and
  `tests/api/test_dropbox_api.py` (12) with recorded-shape JSON in
  `tests/fixtures/dropbox/` (respx; nothing reaches the network).

## TASK-70 (T28a): Auto Import, YouTube channel RSS watch (2026-10-31)

- Feed URL verified live on 2026-10-31:
  `https://www.youtube.com/feeds/videos.xml?channel_id=UCBR8-60-B28hp2BmDPdntcQ`
  answered 200 `text/xml; charset=UTF-8`, `cache-control: public,
  max-age=900`, no ETag/Last-Modified, an Atom feed with the 15 newest
  videos newest first; an unknown channel id answers 404. Each `<entry>` has
  `<yt:videoId>`, `<yt:channelId>` (full `UC...`; the feed-level one drops
  the `UC`), `<title>`, `<published>`/`<updated>` (RFC 3339 with offset)
  and `<link rel="alternate">` (a `/watch` or `/shorts` page). The
  recorded answer (cut to 3 entries) is backend/tests/fixtures/youtube_feed.
- Parsing with the stdlib `xml.etree.ElementTree` (no defusedxml): Python's
  "XML security" docs (https://docs.python.org/3/library/xml.html#xml-vulnerabilities,
  read 2026-10-31) say Expat >= 2.7.2 is not vulnerable to billion laughs /
  quadratic blowup and Expat never loads external entities; the venv's
  `pyexpat.EXPAT_VERSION` is `expat_2.8.1`. Answers over 2 MB are refused.
- A channel is given by its `UC...` id, a `youtube.com/channel/UC...` link
  or its feed URL. `@handle` and `/c/` links need a page scrape or the Data
  API to resolve: left to T28c (TASK-195), which owns handle resolution.
- The first feed read that works only records the videos already in the
  feed (project_id NULL): adding a channel does not import its back
  catalogue. "Read worked" is `last_checked_at` (NULL: never), not "has
  rows", so a channel with no videos imports its first upload. New videos
  are imported oldest first. A video that falls out of the 15-entry feed
  between two polls is missed (the poll interval keeps that unlikely).
- Dedupe: table `watched_video` keyed (watched_channel_id, video_id),
  project_id without a foreign key (a deleted project is not re-imported);
  the row is written after the project is queued (a crash in between
  imports once more: a duplicate, never a loss), like the inbox watch.
- `AUTO_IMPORT_POLL_S` default 300 s ("within minutes", SPEC-v2 3.18); the
  60 s cadence, WebSub push and ETag handling are T28c. A project is queued
  at priority 0 (campaign speed-first priority is T58b).
- `auto_schedule_drafts` is stored only (wired by T49). The importer always
  runs in the app (an idle poll with no channels reads only the DB).
- InboxWatcher and AutoImporter share `poller.Poller` (clock, interval,
  thread); the tests share `tests/fake_clock.py`.

## TASK-71 (T28b): Auto Import UI (2026-10-31)

- No third-party API is new: the page uses the TASK-70 feed reader only
  through the importer; the endpoints are ClipForge's own
  (`/api/auto-import/channels`, GET/POST list+add, GET/PATCH/DELETE one,
  `GET .../videos`).
- PATCH sends only the fields to change (`WatchedChannelPatch`,
  `extra="forbid"`, at least one); the channel id cannot change (remove and
  add instead). Adding a watched channel again is 409 `conflict`; an
  invalid id/link or default is 422; an unknown id is 404.
- Removing a channel deletes its `watched_video` rows (FK cascade) but not
  its projects. Adding it again starts over: the first read records the
  videos then in its feed without importing them.
- The page shows the projects as `watched_video` rows with a `project_id`
  ("new projects"); the videos that were in the feed when the channel was
  added are only counted as skipped. "Last seen" is `last_checked_at`.
- A new channel gets the saved default settings (`/processing-defaults`)
  and a required source rights choice (SPEC-v2 1.6), like Home's panel;
  everything else is edited in "Edit defaults" (the settings panel's
  fields without the timeframe slider and the SRT upload, which belong to
  one video). The queries poll every 15 s so last checked follows the
  importer; the videos use their own query key so removing a channel does
  not refetch (404) the videos of the removed one.
- `SourceRightsField` takes its element ids from `useId` (the page shows
  two of them at once: the add form and the defaults dialog).

## TASK-195 (T28c): fast creator watch (2026-10-31)

Official sources read on 2026-10-31 (no scraping, SPEC-v2 1.5):
YouTube push notifications
<https://developers.google.com/youtube/data/guides/push_notifications>
(hub `https://pubsubhubbub.appspot.com/subscribe`, topic
`https://www.youtube.com/xml/feeds/videos.xml?channel_id=UC...`); W3C
WebSub <https://www.w3.org/TR/websub/> (async intent verification with
`hub.challenge`, `hub.lease_seconds`, `X-Hub-Signature: sha1|sha256|
sha384|sha512=<hmac>` over the raw body, 410 to unsubscribe from the
subscriber side); Twitch EventSub webhooks
<https://dev.twitch.tv/docs/eventsub/handling-webhook-events> (HMAC-SHA256
of message id + timestamp + body, `webhook_callback_verification` answered
with the raw challenge as text/plain, revocation, 10 min replay window),
subscription types
<https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types>
(`stream.online` v1), Helix <https://dev.twitch.tv/docs/api/reference>
(Get Users, Get Streams, Create EventSub Subscription), app access token
(client credentials)
<https://dev.twitch.tv/docs/authentication/getting-tokens-oauth>; YouTube
Data API channels.list `forHandle`
<https://developers.google.com/youtube/v3/docs/channels/list>;
cloudflared ingress rules
<https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/>
(path is a Go regex matched on the raw path, forwarded unchanged); Kick
webhooks <https://docs.kick.com/events/introduction>.

- New `backend/clipforge/watch/` package; `AutoImporter` moved there
  (`youtube_watcher.py`), `auto_import.py` keeps the channel CRUD. Migration
  014 adds the push columns to `watched_channel` (existing rows `off`),
  `watched_streamer` and `watch_event` (UNIQUE platform+kind+external_id:
  an alert is recorded once even when push and poll race; the import also
  runs under a lock). `watched_video.seen_at` is kept; `watch_event` holds
  `published_at` vs `detected_at` (time-to-detect in the UI).
- Polling fallback: `AUTO_IMPORT_POLL_S` default 300 -> 60, `ge=30`; one
  `FeedSchedule` slot per feed/streamer (a new one is due at once), ±10 %
  jitter, backoff `min(interval·2^failures, 1800 s)`. Conditional GET with
  ETag/Last-Modified (`Validators`); the validators are stored only when
  every entry of the read was recorded, so a 304 never hides a video that
  failed to import or was capped. Entries with push get a 15 min safety
  poll instead.
- Push needs `PUBLIC_CALLBACK_URL` (HTTPS, never required). Secrets are
  HMAC-SHA256(master key, purpose) with a 0600 `data/watch_secret.key`
  (`websub:<channel>`, `twitch-eventsub`): nothing secret in the DB.
  Leases are renewed a day before expiry, a pending request is retried
  after 10 min, a failed one after 1 h. No explicit unsubscribe: a push for
  a removed or paused channel gets 410 (the hub drops it) and leases
  expire. A pushed entry older than the channel's `created_at` is recorded
  without a project (WebSub also pushes edits of old videos).
- Twitch: EventSub webhook transport only when `PUBLIC_CALLBACK_URL` is
  set, else Helix Get Streams polling (batches of 100 user ids). The
  WebSocket transport is not used: it needs a user access token, the app
  has only an app token. A 409 on Create Subscription means "already
  subscribed". Without `TWITCH_CLIENT_ID/SECRET` no request is made and the
  UI says "Needs Twitch app keys". Go-live only raises an alert; handing
  off to the live recorder waits for TASK-157 and the "fresh" project badge
  for TASK-176. Kick is deferred (its webhooks need an app and credentials).
- "@handle" channels are resolved once at add time with channels.list
  `forHandle` (`YOUTUBE_API_KEY`; 412 `needs_credentials` without it, 422
  for an unknown handle, 502 if YouTube fails); the stored ref is the UC id.
- New uploads are queued at `jobs.TOP_PRIORITY` (100).
- `create_app(run_watch=...)` (defaults to `run_worker`): API tests and
  the e2e test server (`run_watch=False`) never start the watcher threads,
  so no request leaves the machine; the push callbacks still answer.
- Alerts in the UI: `useWatchAlerts` in `AppShell` polls
  `/watch/events?after=<id>` every 10 s; the first answer is a baseline
  (old alerts stay quiet); each new one is a toast and, with permission, a
  browser `Notification`.
- The Twitch fixtures are the payloads from Twitch's docs (recording live
  answers needs credentials); the WebSub push fixture follows the feed
  format of the recorded YouTube feeds.

## 2026-10-31 — TASK-173 T58a.1 Campaign model, CRUD API, permission evidence

- Campaign has the fields of SPEC-v2 3.18 plus a nullable `end_date`
  (needed by the 3.19 safety stop "the end date passed"; open-ended when
  NULL). `Campaign` extends `CampaignCreate`, so its JSON starts with the
  editable fields; the set of fields is tested, not their order.
- `permission_checked_at` is set by the server (never sent by the client:
  `CampaignPatch` forbids it) whenever a permission source URL is saved
  (create or PATCH) or a screenshot is uploaded; clearing the URL clears
  the date. The date means "when the owner last saved evidence", not the
  date printed on the page.
- Evidence is complete (`Campaign.permission_complete`) only with the URL,
  the screenshot asset and the date. The screenshot is uploaded on its own
  (`POST /campaigns/{id}/permission-screenshot`, PNG/JPEG/WebP up to 5 MB,
  checked by its first bytes like brand logos), stored as
  `{data_dir}/campaigns/<id>/permission.<ext>` and registered as an `image`
  asset (license "user-provided", tag `campaign-permission`, the permission
  URL as its source); a new upload replaces the old asset and file.
- `allowed_platforms` is limited to `youtube`, `tiktok`, `instagram` (the
  publishers of T46/T47); `required_hashtags` are stored without "#" like
  `Clip.hashtags`; `platform_board` is a label only, never a URL to fetch.
- Guard: `campaigns.require_permission(engine, project_id)` and the FastAPI
  dependency `api.campaigns.require_campaign_permission` answer 409
  `permission_missing` naming what lacks. The publish and schedule endpoints
  do not exist yet (T46+), so the test mounts a stand-in route behind the
  dependency; TASK-138/177 must put the dependency on the real endpoints.
- `project.campaign_id` still has no foreign key (SQLite cannot add one to
  an existing column); deleting a campaign clears it in code and removes the
  screenshot. Setting a project's campaign comes with presets (TASK-174).
- No new third-party API: only SQLite `CREATE TABLE` (a plain DATE column),
  pydantic v2 validators and FastAPI `UploadFile`, as in earlier tasks. A
  test greps the package for Whop/Clip-OK/Discord hosts (none present).

## 2026-11-01 — TASK-174 T58a.2 Campaign presets + rule checker

- The campaign needs a caption template to preset one (SPEC-v2 3.18), so
  `Campaign.caption_template` (nullable, None: keep the project's) was added
  by migration `016_v2_campaign_preset.sql` (`ALTER TABLE ... ADD COLUMN`).
  Create/PATCH answer 422 for a template that `load_templates()` does not
  know; applying re-checks it.
- "Clip length range" maps to the existing `length_presets` (the presets
  whose range overlaps [min, max], strict overlap, e.g. 2-30 s -> `lt30`;
  15-60 s -> `lt30, 30_60`); no new processing field. No overlap (e.g. min
  1000 s) or no range keeps the project's presets. The exact min/max is
  enforced per clip by the rule checker.
- Applying (`PUT /projects/{id}/campaign {campaign_id}`) sets
  `project.campaign_id`, length presets, caption template, the project's
  credit line (= required credit line when set) and, for every clip: the
  caption template, the required hashtags first (then the clip's own up to
  8 in all, the editor's cap; required ones are never dropped) and the
  missing credit line / tags-mentions appended on their own lines after a
  blank line; the clip's own text is shortened with "…" so the whole fits
  300 characters (the editor's cap) when the additions alone fit. Clips a job
  saves later get the same (`process_clips._saved_clips` ->
  `preset_new_clips`). `campaign_id: null` leaves the campaign and undoes
  nothing. Source rights are never set by a campaign (SPEC-v2 1.6: the owner
  says it).
- Allowed platforms are not copied anywhere: they are read from the
  campaign when a clip is checked/published (the `platform` rule).
- Rules (in this order): campaign_status (active and today <= end_date,
  local date), permission (URL + screenshot + date), source_rights (set; the
  only rule for a project without a campaign), min_duration, max_duration
  (played length: segments minus merged cut_ranges, in ms), hashtags (in
  `Clip.hashtags` or "#tag" as a whole word in the description, any case),
  credit_line (in the description; case and white space aside), mentions
  (whole word in the description, a "#tag" mention may be a hashtag),
  platform (must be listed; an empty `allowed_platforms` fails: the owner
  must say where the campaign pays). Unset min/max/hashtags/credit/mentions
  pass with "no ... required".
- Publish guard: `api.campaign_rules.require_campaign_rules` (path `clip_id`,
  query/path `platform`) answers 409 `campaign_rules_failed` with
  `{"error","message","failed":[RuleResult]}`; `ApiError` got an optional
  `extra` dict merged into the body (all existing errors unchanged).
  `GET /clips/{id}/campaign-check?platform=` returns every rule for the UI
  (TASK-175).
- No new third-party API: SQLite `ALTER TABLE ADD COLUMN`
  (https://www.sqlite.org/lang_altertable.html, checked 2026-11-01: a new
  column is appended last, nullable without default is allowed), Python `re`
  lookarounds, pydantic/FastAPI as before.

## TASK-175 (T58a.3): campaign forms UI + rule check panel

- Lists are pasted text: hashtags and mentions split on spaces/commas,
  channel links one per line (the server tidies and dedupes). Hashtags are
  sent without "#" (what the API stores) so an unchanged field is not a diff.
- PATCH sends only the changed fields: the API resets `permission_checked_at`
  whenever `permission_source_url` is in the body, even if unchanged. A save
  with only a new screenshot sends no PATCH (GET + upload).
- The rule check shows in the editor rail ("Rules") for the saved clip (the
  API checks the stored clip, not unsaved edits; saving a clip refetches it)
  and the campaign is chosen per project in the gallery header: choosing
  applies the preset to its clips at once (PUT), no confirmation, as the
  toast says so. No per-card pass/fail badge (the panel is enough for now).
- No third-party API used: React/TanStack Query/lucide icons as before
  (`Megaphone`, `ListChecks`, `ShieldCheck` exist in the installed lucide).

## TASK-176 (T58b.1): campaign creator watch + fresh upload + priority

- A campaign's YouTube links (`source_channel_urls`: channel id, `/channel/UC…`
  or `/@handle` links) become Auto Import channels with `campaign_id`
  (migration 017). `sync_channels` runs on create, PATCH and screenshot
  upload of a campaign; a link that is not YouTube, or a handle that cannot
  be looked up (no `YOUTUBE_API_KEY`), is skipped and logged, never an
  error. Links removed from the campaign drop their channels; deleting the
  campaign removes all its channels. A channel the owner already watches is
  adopted (it gets the campaign id, so removing the link removes it too); a
  channel of another campaign is skipped.
- A campaign project is made with the campaign's preset at creation (settings
  via `preset_settings`, the campaign's credit line over the channel's,
  `campaign_id`), so its clips get the hashtags/description lines through the
  existing `preset_new_clips` when they are saved. Source rights are
  "permission" only while the permission evidence (URL, screenshot, date) is
  complete (else unset: the rule checker then fails the permission rule).
- Priority: `CAMPAIGN_PRIORITY = 200` > `TOP_PRIORITY = 100` > 0; the worker's
  existing "highest priority, then oldest" claim does the rest.
- "Fresh upload" = `Project.fresh_upload`, derived (read-only, like
  `rights_set`) from `source_published_at` (the feed's publish time) being
  within `FRESH_UPLOAD_HOURS = 48` of now and the project having a campaign.
  Chosen over a stored flag so the badge expires by itself; 48 h because
  fresh clips matter most in the first days (SPEC-v2 3.19 expires drafts
  after 3 days). The API only exposes it; no UI badge yet (backend task).
- Channels are enabled while the campaign is active and its end date is not
  past. An end date passes without a sync, so the importer re-checks it
  (`campaign_watch.is_watched`) before reading a feed or accepting a push.
- No new third-party API (YouTube handle lookup is T28c's,
  docs/decisions.md TASK-195); SQLite `ALTER TABLE ADD COLUMN` as in TASK-174.

## TASK-138 (T46a): publisher framework, social accounts, posts, token store

- Tokens: encrypted files, not the OS keychain (no new native dependency,
  works in tests and on any OS) and never the DB. `token_store.TokenStore`
  writes `data/oauth_tokens/<token_ref>.token` (0600, atomic replace) with
  `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256). Docs checked
  2026-11-01: https://cryptography.io/en/latest/fernet/ and the installed
  source of cryptography 50.0.2 (`Fernet(key)` takes 32 url-safe base64
  bytes; `encrypt(bytes)`; `decrypt(token, ttl=None)` raises
  `InvalidToken`). The key is `derived_secret("oauth-token-store",
  data_dir)` of the existing 0600 master key file (`watch/keys.py`), so a
  copied token folder or DB backup does not leak tokens; it does not
  protect against a local attacker running as the user. Deleting the master
  key makes stored tokens unreadable (load gives None: reconnect). The old
  plain `<ref>.json` files of TASK-66 (Drive) are encrypted on first read
  and removed. `Token` hides access/refresh tokens from repr.
- Several accounts per platform: `social_account` is unique by (platform,
  external_id); connecting the same account again updates it in place and
  keeps its token_ref (the new token overwrites the old one).
- Status machine (SPEC-v2 3.10 + guards): draft -> queued | canceled;
  queued -> draft (unschedule) | uploading | canceled; uploading ->
  published | failed | queued (retryable error); failed -> queued (manual
  retry) | canceled; published/canceled are final. An upload in progress
  cannot be canceled (the platform may already have it). Moves are one
  conditional UPDATE (status = old), so two workers cannot both start one.
- Disconnect is refused (409 account_busy) while the account has draft,
  queued or uploading posts; published/failed/canceled posts stay as
  history with `account_id` NULL (deviation: SPEC-v2 section 4 lists
  account_id as a plain FK; nullable keeps the history). Deleting a clip
  deletes its posts.
- `publishers.registry.ENTRIES` is empty in this task: each platform task
  (T46b+) adds its publisher. Unknown platform -> 501 not_supported,
  missing OAuth app settings -> 412 needs_credentials naming the env keys.
- The framework's publish run checks source rights (SPEC-v2 3.10), a
  rendered file and the account. Campaign guards (`require_campaign_permission`,
  `require_campaign_rules`) belong to the publish/schedule endpoints
  (TASK-147/177), which do not exist yet.
- OAuth redirect URI = `request.url_for("accounts_callback")` on the
  loopback server (as Drive); platforms that refuse http loopback redirects
  are handled in their own tasks.

## TASK-139 (T46b): YouTube publisher

Docs checked 2026-11-01:
https://developers.google.com/youtube/data/reference/rest/v3/videos/insert,
https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol,
https://developers.google.com/youtube/data/reference/rest/v3/thumbnails/set,
https://developers.google.com/youtube/data/reference/rest/v3/videos (video
resource limits, uploadStatus/rejectionReason/failureReason),
https://developers.google.com/youtube/data/reference/rest/v3/channels/list,
https://developers.google.com/youtube/v3/docs/errors,
https://developers.google.com/youtube/v3/getting-started#quota,
https://developers.google.com/youtube/v3/determine_quota_cost,
https://developers.google.com/youtube/v3/revision_history,
https://developers.google.com/identity/protocols/oauth2/web-server
(`prompt=select_account`).

- OAuth: the Google OAuth app of the Drive import (GOOGLE_OAUTH_CLIENT_ID /
  SECRET, Desktop app, loopback callback `/api/accounts/youtube/callback`),
  scopes `youtube.upload` (insert + thumbnails.set) and `youtube.readonly`
  (channels.list mine=true), `prompt=select_account` so several channels
  can be connected. No separate YOUTUBE_CLIENT_ID.
- Upload: resumable protocol (POST `uploadType=resumable` with the video
  resource, then PUT chunks of 8 MiB, a multiple of 256 KiB as required).
  An interrupted chunk (no answer, 500/502/503/504) waits 2^n s and asks
  `Content-Range: bytes */size`, then resumes after the 308 `Range`; after
  5 interruptions or a 404 (expired session) the post is queued again.
  Retryable: 429, 5xx, reasons quotaExceeded, rateLimitExceeded,
  userRateLimitExceeded, uploadLimitExceeded, uploadRateLimitExceeded; other
  4xx (forbiddenPrivacySetting, invalidTitle...) fail the post; a 401 after
  the session's token refresh asks to reconnect. A 200/201 with
  uploadStatus rejected/failed fails the post with YouTube's reason.
- Metadata (`YouTubePostOptions` in post.payload; other keys ignored):
  title <= 100 characters, description <= 5000 bytes, both without "<"/">"
  (removed); tags <= 500 characters counting commas and quotes around tags
  with spaces (later tags dropped); defaults from the clip (title,
  description + #hashtags, hashtags). `containsSyntheticMedia` and
  `selfDeclaredMadeForKids` are always sent (the owner's declarations).
- Scheduling: a public post with a future scheduled_at goes up private with
  `publishAt` (YouTube only accepts publishAt with private); unlisted or
  private posts ignore scheduled_at here (the scheduler of TASK-147 decides
  when they are sent).
- Quota (since 2026-06-01 videos.insert has its own bucket: 100 calls/day,
  1 unit each; every other method shares 10,000 units/day; reset at
  midnight Pacific Time): `publishers/quota.DailyQuota` sums the
  `usage_record` rows of its kind (`youtube_uploads`,
  `youtube_quota_units`) for the Pacific day and refuses (retryable
  `QuotaExceeded`, nothing sent) a call that would go over
  `YOUTUBE_DAILY_UPLOADS` / `YOUTUBE_DAILY_QUOTA_UNITS`. Units are recorded
  before the call (Google charges even failed calls). Only the initiating
  POST counts as the insert call; chunk PUTs do not. Metering works through
  `usage.recording` (ContextVar), which `publish_post` and the account
  callback open, so publishers need no engine; outside it nothing is
  metered.
- Thumbnail: thumbnails.set (50 units) after the upload; any failure (no
  units, 4xx/5xx, network) is logged and the post stays published, because
  failing it would upload the video again on retry.
- Restrictions shown on the account: the daily limits, the audit note (the
  2020 revision history locks unverified projects' uploads to private while
  the current videos reference no longer says so: we warn "may keep
  uploads private"), a channel without a linked identity
  (status.isLinked false) and long uploads not allowed
  (status.longUploadsStatus != allowed).
- `PublishBlocked` now has a global API handler (409 {error: code,
  message}) for the publish endpoints of TASK-147.

## TASK-140 (T47a): TikTok publisher

Docs checked 2026-11-01 (developers.tiktok.com/doc/... redirects to
developers.tiktok.com/docs/en/...):
https://developers.tiktok.com/docs/en/content-posting-api-get-started,
https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post,
https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide,
https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status,
https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info
(updated 2026-10-27),
https://developers.tiktok.com/doc/login-kit-desktop,
https://developers.tiktok.com/doc/oauth-user-access-token-management,
https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info,
https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit,
https://developers.tiktok.com/doc/tiktok-api-v2-error-handling,
https://developers.tiktok.com/docs/en/content-sharing-guidelines.

- OAuth (Login Kit for Desktop): `client_key` instead of `client_id` in the
  authorize URL, token request and refresh; scopes comma-separated
  (`user.info.basic,video.publish`); PKCE is required and its challenge is
  the HEX SHA-256 of the verifier (not base64url). The redirect is the
  loopback `/api/accounts/tiktok/callback` (TikTok allows localhost /
  127.0.0.1 with any port for desktop apps). `OAuthClient` gained
  `client_id_param`, `scope_separator`, `pkce_hex` and `granted()`
  (scopes split on spaces or commas); the token endpoint's 200 answers with
  an `error` and no access token are treated as refusals. Access tokens last
  24 h, refresh tokens 365 days (a refresh may return a new one; it is
  stored).
- Direct Post flow per post: creator_info/query (fresh, right before the
  post, as the UX guidelines require) -> checks (privacy level offered,
  clip's played length <= max_video_post_duration_sec, disabled
  interactions stay disabled) -> video/init (FILE_UPLOAD, post_info) ->
  chunked PUT -> status/fetch every 5 s, at most 24 times.
- Chunks: 10 MiB (rules: 5-64 MB, last chunk up to 128 MB holding the
  remainder, chunk count = floor(size / chunk), a file under the chunk size
  goes whole). PUT answers 206/201; no answer or 5xx is retried after 2^n s
  (5 times, then the post is queued again); 403 (link expired), 404 and 416
  re-queue the post (a new init), other 4xx fail it. Video checks before any
  call: MP4/MOV/WebM, <= 4 GB.
- Post settings (`TikTokPostOptions` in post.payload): caption (default
  title + #hashtags, cut to 2200 UTF-16 units), privacy_level (no default:
  the post fails until the user picks one, as TikTok's UX rules forbid a
  default), allow_comment/duet/stitch (off unless chosen), brand_organic,
  branded_content (never with SELF_ONLY), ai_generated (is_aigc),
  cover_timestamp_ms. TikTok has no cover upload: `Upload.thumbnail` is
  ignored (logged). The music-usage consent text is the UI's job
  (TASK-145).
- Outcome: PUBLISH_COMPLETE with `publicaly_available_post_id` (TikTok's
  spelling) -> that id and https://www.tiktok.com/@user/video/id; private
  posts never get a post id -> the publish_id, no URL. Still processing
  after the polls (or a status that cannot be read) -> published with the
  publish_id, because re-posting would make a duplicate. FAILED -> final,
  except `internal` and `spam_risk_too_many_posts` (retryable).
- Errors: HTTP 429, 5xx and codes rate_limit_exceeded,
  spam_risk_too_many_posts, internal_error are retryable; a 401 after the
  session's refresh asks to reconnect (scope_not_authorized names
  video.publish); everything else is final with TikTok's message.
  creator_info errors arrive with HTTP 200 and an error code.
- No daily quota counter (unlike YouTube): TikTok's limits are per token
  (creator_info 20/min, init 6/min, status 30/min) and per creator (about
  15 posts/24 h, reported as spam_risk_too_many_posts), both handled as
  retryable refusals.
- Account restrictions saved at connect: the unaudited-app note (until
  TikTok audits the app, posts can only be SELF_ONLY on private accounts,
  error `unaudited_client_can_only_post_to_private_accounts`), the daily
  post cap, the creator's privacy options, longest video and disabled
  interactions, and a missing video.publish grant. The audit guidelines
  reject "utility tools to upload to accounts you manage", so a personal
  ClipForge app is unlikely to pass: parity says "needs platform approval".

## TASK-141 (T47b): Instagram Reels publisher

Docs checked 2026-11-01 (developers.facebook.com/docs/... redirects to
developers.facebook.com/documentation/...; latest Graph API version v26.0):
https://developers.facebook.com/documentation/instagram-platform/content-publishing,
https://developers.facebook.com/documentation/instagram-platform/overview,
https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/get-started,
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media,
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-container,
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/error-codes,
https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow,
https://developers.facebook.com/docs/facebook-login/guides/advanced/oidc-token
(PKCE: code_challenge on the dialog, code_verifier on the exchange),
https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived,
https://developers.facebook.com/docs/facebook-login/facebook-login-for-business,
https://developers.facebook.com/docs/graph-api/guides/error-handling.

- API choice: the **Instagram API with Facebook Login for Business**
  (graph.facebook.com), not the Instagram API with Instagram Login: only
  apps on Facebook Login for Business may upload a local file
  (`upload_type=resumable` to rupload.facebook.com); the Instagram Login
  API takes public `video_url` links only, and ClipForge has no public
  server. It also shares the Meta app (META_APP_ID / META_APP_SECRET) with
  the Facebook Pages publisher (TASK-142). Accounts must be Instagram
  professional accounts (Business or Creator) linked to a Facebook Page.
- OAuth: dialog https://www.facebook.com/v26.0/dialog/oauth with
  comma-separated permissions `instagram_basic,instagram_content_publish,
  pages_show_list,pages_read_engagement`, PKCE and, when
  `META_LOGIN_CONFIG_ID` is set, `config_id` (a Facebook Login for Business
  configuration). The code is traded with a **GET** of
  graph.facebook.com/v26.0/oauth/access_token (`OAuthClient.token_method`)
  for a short-lived token (about 1 h, no refresh token, no scope).
  `Publisher.finish_sign_in` (new hook, called by the callback before
  `fetch_account`) trades it at once for a long-lived token (about 60
  days, `grant_type=fb_exchange_token`) and sets its scope from
  `/me/permissions` (granted rows; left empty if Meta does not answer).
  There are no refresh tokens: `OAuthClient.refresh_grant` makes the
  session's refresh (expiry or a 401) do the same exchange, which works
  only while the token is still valid; code 190 from the token endpoint ->
  `reconnect_required` (the user connects again). Meta's nested
  `{"error": {"message", "code"}}` token errors are parsed.
- Account: `/me/accounts?fields=id,name,instagram_business_account{id,
  username,name}`; the external id is the Instagram user id (passed to
  `upload` as the new `Upload.account_external_id`); several linked
  accounts -> the first by username is connected and the others are named
  in a restriction (one account per connection). No linked account -> the
  connection fails with a hint (switch to Business/Creator, link a Page).
- Restrictions saved at connect: Standard Access only serves people with a
  role on the Meta app (others need App Review + Business Verification for
  Advanced Access: parity says "needs platform approval" for other
  people's accounts), 100 API posts per 24 h, the Reels rules (no cover
  file), a declined `instagram_content_publish`, and the current
  `content_publishing_limit` use (or why it could not be read).
- Post flow: `content_publishing_limit` (used up -> retryable, nothing
  created; unreadable -> continue) -> POST /{ig-user}/media (REELS,
  resumable, caption, share_to_feed, collaborators, thumb_offset,
  audio_name, is_ai_generated, trial_params) -> POST the whole file to the
  container `uri` with `Authorization: OAuth <token>`, `offset: 0`,
  `file_size` (3 tries, 2^n s apart while `debug_info.retriable`, 5xx or no
  answer) -> GET /{container}?fields=status_code,status once a minute, at
  most 5 times (Meta's advice) -> POST /{ig-user}/media_publish
  (creation_id) -> GET /{media}?fields=permalink (failure -> no URL, still
  published). A publish call without answer checks the container: if it
  is PUBLISHED the post counts as published (container id kept, no URL)
  instead of being posted twice. Still IN_PROGRESS after 5 checks or
  EXPIRED -> retryable (a new container next time).
- Reel checks before any call: MP4/MOV, 1 byte..300 MB, played length 3 s
  to 15 min, caption <= 2200 characters / 30 hashtags / 20 @ tags, up to 3
  collaborators (usernames, "@" dropped), thumb_offset inside the clip.
  `cover_url` needs a public image URL, so `Upload.thumbnail` is ignored
  (logged) and `thumb_offset_ms` picks the cover frame.
- Errors (`meta_graph.graph_error`): code 190 or HTTP 401 -> final
  "connect again"; codes 10 and 200-299 -> final "permission missing";
  HTTP 429/5xx, `is_transient`, codes 1, 2, 4, 17, 32, 341, 368, 613,
  80001, 80002 and Instagram subcodes 2207001/3/8/20/32/42 (daily limit)/53
  -> retryable; everything else (e.g. 2207050 restricted account, 2207051
  spam, 2207026 format) -> final with Meta's user message. Container ERROR
  statuses map the subcode in `status` the same way.
- Localhost redirect URIs are accepted only while the Meta app is in
  Development mode (assumption from the Facebook Login settings, not
  re-verified on a page); a Live app needs an https redirect (README).

## TASK-142 (T47c): Facebook Pages reel publisher

Docs checked 2026-11-01 (Graph API v26.0):
https://developers.facebook.com/docs/video-api/guides/reels-publishing,
https://developers.facebook.com/docs/graph-api/reference/page/video_reels,
https://developers.facebook.com/docs/graph-api/reference/video/thumbnails,
https://developers.facebook.com/docs/pages-api/getting-started,
https://developers.facebook.com/docs/pages-api/manage-pages,
https://developers.facebook.com/docs/permissions.

- Reels are published **as the Page**, with a Page access token (not the
  user token). `GET /me/accounts?fields=id,name,access_token,tasks` with the
  long-lived user token returns one Page token per Page; the user needs the
  CREATE_CONTENT task. Permissions: `pages_show_list`,
  `pages_read_engagement`, `pages_manage_posts`. The Page token is read on
  each upload, so nothing besides the user token is stored.
- Reuses the Meta app (META_APP_ID / META_APP_SECRET /
  META_LOGIN_CONFIG_ID), the Facebook Login dialog and the long-lived token
  exchange of TASK-141 (`meta_graph.MetaPublisher`, `GraphSession`;
  `meta_upload.send_video` is shared with Instagram). Redirect URI:
  `/api/accounts/facebook/callback`.
- Flow: `POST /{page}/video_reels` upload_phase=start -> `{video_id,
  upload_url}`; POST the file to `upload_url` (rupload) with
  `Authorization: OAuth <page token>`, `offset: 0`, `file_size`;
  `POST /{page}/video_reels` upload_phase=finish, video_state=PUBLISHED,
  description, title, is_ai_generated; then poll `GET /{video}?fields=status`
  (video_status, phases with `status`/`error`; "complete" and "completed"
  are both accepted because the docs use both).
- Reel rules: MP4 (MOV accepted), 9:16, at least 540x960, 24-60 fps, 3-90 s.
  ClipForge checks type and length; Facebook's own errors 1363040
  (aspect), 1363127 (resolution), 1363128 (duration), 1363129 (fps) are
  final. Limit: 30 API-published reels per Page per 24 h, enforced at
  publish; no endpoint reports it, so it is only listed in the restrictions.
- After `finish` is accepted the post is never sent again (no double
  posts): a retryable failure first checks the status; a reel still
  processing after 12 polls (10 s apart) counts as accepted.
  Status/permalink/collaborator failures never fail a post.
- Several Pages: the first Page the user can create content on is
  connected; the others are named in the restrictions (choose one Page in
  Facebook's dialog). Collaborators: `POST /{video}/collaborators?
  target_id=`, up to 10 invitations per Page per 24 h, best effort.
- No custom thumbnail (the `/{video}/thumbnails` upload was not verified);
  left to TASK-148. No native Facebook scheduling: ClipForge's scheduler
  decides when a post goes out and always sends PUBLISHED.
- Standard Access serves only people with a role on the Meta app; other
  people's Pages need App Review plus Business Verification -> parity
  "needs platform approval".

## TASK-145 (T48c): Social accounts settings UI

- UI only, no third-party API (2026-11-01): it calls the TASK-138 `/accounts`
  endpoints. `GET /accounts/platforms` gained `settings_keys` (the env vars
  of the platform's developer app) so the UI can name them instead of
  hard-coding them.
- Placement: a "Publish" group in the sidebar with "Social accounts"
  (`/accounts`); the "Social account connections" modal (ref-5 tile style)
  opens from "Add account". The filter and modal list only platforms with a
  publisher (`supported`), so X and LinkedIn appear when their tasks
  register them (TASK-143/144 come later in tasks.json than this one).
- Connect opens a blank tab on the click (popup blockers), then sends it to
  the platform's sign-in, like the Drive dialog; the page polls
  `GET /accounts` every 2 s until a new account appears (the callback page
  tells the user to come back), then closes the modal and toasts.
- Remove asks first (inline confirm, as in the Watchlist); a 409
  `account_busy` shows as the API's message toast.
- README anchors `#<platform>-publishing` for "See setup" (the sections are
  named "<Platform> publishing").

## TASK-146 (T49a): bulk scheduler core (slots + allocation)

- Library checked (2026-11-01): Python's `zoneinfo`
  (https://docs.python.org/3.11/library/zoneinfo.html) and PEP 495 `fold`
  (https://peps.python.org/pep-0495/), verified with the installed Python
  3.11.15 + system tz database: `datetime(2026, 3, 29, 2, 30,
  tzinfo=ZoneInfo("Europe/Zurich"))` has offset +01:00 and converts to
  01:30Z = 03:30 CEST; `datetime(2026, 10, 25, 2, 30, ...)` with fold=0 is
  +02:00 (00:30Z), fold=1 is +01:00 (01:30Z). No new dependency (`tzdata`
  is already installed through python-dateutil for systems without a tz
  database).
- Rules schema: `models.ScheduleRules` {timezone (IANA key), times (1-24
  distinct wall-clock times, sorted), posts_per_day (default: all times;
  the earliest N times are used), skip_days (mon..sun, not all 7),
  start_date (default today; a past date means today)}. Simplest reading of
  "posts/day + time slots": the times are the slots, posts/day takes the
  first N of them (no evenly-spread generator).
- DST: a skipped wall-clock time moves forward by the gap (zoneinfo
  fold=0); when that lands on another slot of the day, the two merge (one
  slot fewer that day). A repeated time is used once, at its first
  occurrence. "A day" for per-day counts is the local calendar day in the
  rules' timezone.
- Bulk allocation: every clip goes to every selected account (several
  platforms at once); per account, the clips keep their order and each takes
  the account's next free slot. Cap per day = min(rules' posts/day,
  account max_per_day). Posts already scheduled (`busy`) count toward their
  local day and hold their exact instant for that account; other accounts
  may share the instant. Output sorted by (time, account id): deterministic
  regardless of the order of accounts given. No room within 731 days ->
  `NoFreeSlot`.
- The core is pure (now is a parameter; nothing reads the DB): TASK-147
  wires it to the posts table and the API; the per-platform max/day values
  come from the publishers' limits there.

## TASK-147 (T49b): post API (publish now / schedule / reschedule / cancel) + "Schedule post" modal

- Owner rule (2026-10-31): AI agents may draft posts and give drafts a
  time, but only the owner publishes. Publish now, queue (draft -> queued,
  incl. bulk schedule with `queue: true`) and any change to a queued post
  are human-only: `api.deps.require_human` answers 403 `human_only` when
  the request carries an `X-API-Key` or `Authorization` header or its path
  starts with `/api/v1/`. The local UI sends neither. TASK-164 (public API)
  and TASK-166 (MCP) MUST authenticate with one of these headers (or live
  under `/api/v1/`) so the rule holds; there is no auto-publish setting.
- Endpoints: `GET /posts` (filters clip/account/status), `GET /posts/{id}`,
  `POST /clips/{id}/posts` (one draft per target account, 201),
  `PATCH /posts/{id}` (text, scheduled_at = reschedule, thumbnail),
  `POST /posts/{id}/queue`, `POST /posts/{id}/publish` (queues with no
  time, then publishes in a background task), `POST /posts/{id}/cancel`,
  `POST /posts/bulk-schedule` (201). Reschedule/cancel/edit only in
  draft|queued: 409 `post_locked` otherwise; an illegal status move is 409
  `invalid_status`; a past time is 422.
- Checks before a post may be queued or published, in order: source
  rights, campaign permission, campaign rules (with the target platform:
  the campaign rule's platform type is widened to every social platform,
  so a Facebook post of a TikTok-only campaign fails), a rendered video
  (409 `clip_not_rendered`; drafts do not need one), the account, and the
  platform's own readiness (409 `post_not_ready`, e.g. TikTok without a
  privacy level: TikTok forbids a default). Publish now also needs the
  platform's developer app (412, registry). Bulk queue runs every check
  before anything is saved (all or nothing).
- Per-platform customization: `models.PostText` {title, caption, hashtags,
  link, privacy, collaborators, options} per target; `post_payload.py`
  builds the platform's native payload (the publishers' option models) and
  keeps the PostText under `payload["text"]` for editing. A field left
  None takes the clip's own text. TikTok/Instagram have no title: the title
  goes above the caption (`title: ""` drops it; the modal sends "" and
  shows the joined caption). Body = caption, link, hashtag line, separated
  by blank lines; YouTube tags = the hashtags. Over a limit (YouTube 5000-byte
  description / 500-char tags / no "<>", TikTok 2200 UTF-16 units,
  Instagram/Facebook option models) -> 422, never cut. Collaborators only
  on Instagram/Facebook; Instagram/Facebook are public only.
- Daily caps of the bulk scheduler (`post_schedule.DAILY_POSTS`): YouTube
  `YOUTUBE_DAILY_UPLOADS` (100), TikTok 15, Instagram 100 (API limit per 24
  h), Facebook 30 (reels per Page per 24 h). Busy slots = the accounts'
  draft/queued posts with a time. No free slot within 731 days -> 409
  `no_free_slot`.
- Modal: "Rewrite with AI" called `POST /clips/{id}/regenerate-text` until
  TASK-148 (see its section: tone/format/hashtags, nothing saved on the
  clip) and showed the clip's thumbnail (covers: TASK-148). Bulk schedule in the modal schedules the one clip in each
  chosen account's next free slot, in the browser's timezone. Queued posts
  with a time wait for the posting worker (TASK-150).

## TASK-148 (T49c): thumbnails/covers + AI post copy

- Limits verified from the official docs on 2026-11-01 (web_fetch):
  - YouTube `thumbnails.set` (https://developers.google.com/youtube/data/
    reference/rest/v3/thumbnails/set): JPEG or PNG, at most 50 MB, ~50
    quota units. Title <= 100 characters and description <= 5000 bytes were
    verified in TASK-139.
  - TikTok Direct Post (https://developers.tiktok.com/docs/en/
    content-posting-api-reference-direct-post): `title` (the caption) at
    most 2200 UTF-16 units; `video_cover_timestamp_ms` picks the cover
    frame; there is no cover image upload; unaudited clients are private
    only.
  - Instagram IG User Media (https://developers.facebook.com/documentation/
    instagram-platform/instagram-graph-api/reference/ig-user/media):
    caption at most 2200 characters, 30 hashtags and 20 @-tags; a Reel's
    cover is a JPEG of at most 8 MB, given as a public `cover_url` or as
    `thumb_offset` (ms into the video).
  - Facebook documents no title/description limit for reels. OUR choice:
    title <= 100, description <= 2200 characters (`post_copy_fit.STYLES`).
- `POST /clips/{id}/post-copy` (`post_copy.write_copy`) writes the title,
  caption and hashtags of ONE platform from the clip's transcript words,
  hook, current text and the project's credit line; it saves nothing (the
  modal's form holds the draft; the clip keeps its own text). Reply is
  validated (`PostCopyReply`), retried up to `MAX_RETRIES` times, then 502
  `llm_error`; no transcript/process job -> 409. Usage is recorded.
- The generator cuts, it never relies on the model: `post_copy_fit` cuts the
  title at a word boundary ending in "...", the caption within the platform
  budget less the hashtag line that `post_payload` appends to every
  payload, and the hashtag count to the platform (YouTube 3-5, TikTok 3-5,
  Instagram 5-10 and at most 30, Facebook 2-4). TikTok has no title, so its
  headline (<= 70) goes first in the caption like the modal does. YouTube
  measures bytes, TikTok UTF-16 units, the others characters.
- The project's credit line is appended by ClipForge to the description,
  not written by the LLM (so it is never reworded or cut off).
- "Rewrite with AI" menu, each option changes only its own fields:
  tone (casual, punchy, professional, funny) and format (short, list,
  story) rewrite title + caption and keep the hashtags; hashtags (more =
  platform's high count + up to 3 extra, fewer = one less than the low
  count and at least 1, none) change only the hashtags and re-cut the
  caption to fit; "none" needs no LLM call. The rewrite acts on the platform
  tab shown and is sent the form's current text, so a user's edits count.
- Opening the modal: the AI writes the platform of every connected
  account (in parallel, silent errors) and fills a platform unless the user
  has already typed in it; on failure the clip's own text stays and one
  notice is shown. ASSUMPTION: this is "per selected platform"; platforms
  without an account are not written (no wasted LLM calls).
- Covers (`thumbnails.py`): a frame of the RENDERED video at t seconds
  (`GET /clips/{id}/frame?t=` preview JPEG; `POST /clips/{id}/thumbnail`
  saves it as an image Asset under `output/{project}/covers/`, same time ->
  same Asset), or an uploaded JPEG/PNG (`.../thumbnail/upload`, raw body,
  magic bytes checked, at most 8 MiB = the strictest documented limit).
  `POST /clips/{id}/thumbnail/apply` sets the Asset on all the clip's draft
  and queued posts ("apply to all"); the modal sends it as
  `thumbnail_asset_id` on create, and after a bulk schedule applies it.
  `GET /thumbnails/{asset_id}` serves the image. A time past the end is
  422 (ffmpeg exits 0 without a frame there, so the duration is probed
  first); an unrendered clip is 409.
- The cover only reaches YouTube today (`thumbnails.set`); TikTok and
  Instagram publishers do not pass it yet (TikTok takes a cover TIMESTAMP,
  Instagram a public URL or offset) and Facebook reels have none.


## TASK-150 (T50a): posting worker

- Verified 2026-11-01 (SPEC-v2 0.1): no new external endpoint, scope or
  library call. The limits used are the ones verified and recorded with
  their URLs earlier in this file: TikTok upload init 6/min per user token
  and about 15 posts/24 h per creator (TASK-140,
  https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post),
  Instagram 100 API posts per 24 h (TASK-141,
  https://developers.facebook.com/documentation/instagram-platform/content-publishing),
  Facebook 30 reels per Page per 24 h (TASK-142,
  https://developers.facebook.com/docs/video-api/guides/reels-publishing),
  YouTube 100 videos.insert / 10,000 units per Pacific day (TASK-139,
  https://developers.google.com/youtube/v3/determine_quota_cost). Python
  3.11 `zoneinfo` wall-clock arithmetic (aware datetime + timedelta keeps
  the zone's wall time) checked with the spring-forward test
  (`test_a_quota_resets_at_the_next_local_midnight_across_dst`).
- `scheduler/post_worker.PostWorker` is a `Poller` (same thread pattern as
  the inbox watch / Auto Import) started in the app lifespan when
  `run_posting` (default: `run_worker`) is on; the e2e test server passes
  `run_posting=False`. "UI closed" = the browser is closed while the
  backend runs; there is no separate daemon (the backend is the process).
- New migration 019: `post.attempted_at` (start of the latest upload, the
  rate limits count them) and `post.next_attempt_at` (held back until then
  by backoff, a rate limit or a quota). Reusing `scheduled_at` for the
  backoff was rejected: it would move the post in the calendar and lose the
  user's time.
- Due = queued, `scheduled_at` null or <= now, `next_attempt_at` null or <=
  now; the longest-due first (null first, then coalesce(next_attempt_at,
  scheduled_at), then id). Posts are uploaded one at a time per poll.
- Order of checks per post: quota guard, then rate limits, then
  `publish_post` (rights, render, account, platform keys, upload).
- Quota guard: `PublisherEntry.quotas` (YouTube: `UPLOAD_QUOTAS` = one
  `UPLOADS` unit). Used up -> `next_attempt_at` = the quota's next reset
  (`DailyQuota.next_reset`, local midnight, DST-safe) and the error says it
  waits for the quota; no attempt counted. A `QuotaExceeded` raised inside
  an upload now carries `retry_at`; `publish_post` puts the post back to
  queued with its previous attempts and attempted_at (nothing was sent).
- Rate limits: rolling windows over the posts' `attempted_at` (each post's
  latest start; a retried post counts once - ASSUMPTION, platforms count
  posts). Per account: 1 per `post_account_gap_s` (60 s, under TikTok's
  6 inits/min) and `post_schedule.DAILY_POSTS` per 24 h; per platform
  (all accounts): `post_platform_hourly[platform]` per hour, none by
  default (no documented app-wide cap that a local app would hit). A held
  post gets `next_attempt_at` = when the window frees a start; its error is
  left as it was.
- Backoff: `RetryPolicy` base `post_retry_base_s` (60 s) doubling to
  `post_retry_max_s` (1 h), no jitter (one local client); the
  `post_max_attempts`-th (5) failed upload -> failed with
  "<platform error> (gave up after N attempts)". The publish-now path uses
  the same policy, so its retryable failure is picked up by the worker.
- `posts.queue_post` now resets `attempts` to 0 and `next_attempt_at`:
  attempts count the tries since the post was last queued, so queuing a
  failed post again gives it fresh attempts.
- A post that cannot be published (PublishBlocked, PublisherUnavailable)
  keeps status queued with the reason in `error`, retried after the
  backoff cap; the state machine is unchanged (queued -> failed stays
  illegal).
- On start the worker fails the posts left `uploading` (the platform may
  already have the video; never re-sent on its own) with
  `post_queue.INTERRUPTED`.
- Missed-while-offline: posts due while the app was off are posted late;
  the skip option and the history page are TASK-151.

## 2026-11-01 — TASK-164 Public REST API /api/v1 (T55a)

- Verified (installed FastAPI 0.162.0 / Starlette 1.10.0 source and
  `help()`, 2026-11-01): `APIRouter.include_router` can include the same
  router twice under different prefixes (the copies get their own
  operationIds); `include_router(dependencies=...)` applies only to that
  copy; `fastapi.security.APIKeyHeader(name, scheme_name, description,
auto_error=False)` and `HTTPBearer(auto_error=False)` return None when the
  header is missing (a non-Bearer Authorization too) and add the security
  schemes to OpenAPI; FastAPI adds its own 422 `HTTPValidationError` answer
  only when the operation documents none of 422, 4XX or default.
  https://fastapi.tiangolo.com/reference/security/ (2026-11-01).
- /api/v1 re-mounts the app's own routers (same handlers and models) behind
  `require_api_key` instead of copying endpoints: one implementation and the
  public API cannot drift from the UI's. Included: projects, uploads,
  sources, presets, jobs, clips, clip files, campaign rule check, brand and
  caption templates, post copy, covers, posts and a read-only GET /accounts.
  Left out: settings (secrets), account connect/disconnect, Drive, watch,
  engines, usage, the editor helpers (crop/scenes/auto cuts), media.
- Keys: `cfk_` + `secrets.token_urlsafe(32)` (256 bits), stored as the
  SHA-256 hex digest with the first 10 characters as prefix. Not argon2:
  a slow hash protects low-entropy passwords; for a random 256-bit key it
  only adds latency to every request and stops the lookup by digest.
  argon2 stays for LAN-mode passwords (TASK-167).
- Key management (`/api/api-keys`) is human only (`require_human`), so an
  agent cannot make itself keys. No UI yet (Settings v2, TASK-171): curl
  or /api/docs.
- Rate limit: in memory, per key, `api_rate_limit_per_min` (120) per rolling
  minute (`scheduler.rate_limits.RateLimit` reused); 429 `rate_limited` with
  `Retry-After` seconds. Resets on restart (one local process).
- Errors: `ApiError` takes `headers`. 401 adds `WWW-Authenticate: Bearer`.
  The v1 operations document 401, 429 and `4XX` as `ErrorBody` (new model,
  `{error, message}` + extra fields), replacing FastAPI's
  HTTPValidationError for 422 (our handler never sends that shape).
- Docs moved to `/api/docs` and `/api/openapi.json` (redoc off). The whole
  app is in the document; the public operations are tagged.
- "Draft or queued per the publish policy setting" (owner's request):
  no such setting exists, and the owner's rule of 2026-10-31 forbids
  auto-publish. Agents' posts are always drafts (with scheduled_at), and the
  owner queues them. ASSUMPTION; revisit with Autopilot (TASK-180).
- Contract tests: no schemathesis/jsonschema in the deps; a small validator
  (`tests/openapi_check.py`) checks the answers against the OpenAPI
  document's schemas, and the tests are parametrized over its /api/v1
  operations.

## 2026-11-01 — TASK-165 Webhooks (T55b)

- Verified (installed httpx 0.28.1 `inspect.signature`, Python `hmac` /
  `hashlib` stdlib, 2026-11-01): `httpx.Client.post(url, *, content=,
  headers=, timeout=...)`; `follow_redirects` defaults to False (kept, so a
  webhook cannot bounce a signed body to another host); `Response.is_success`
  is 2xx. n8n (docs.n8n.io Webhook node, 2026-11-01): the node has an
  "HTTP Method" (POST), a "Path" and an option "Raw Body"; the Code node
  reads binary data with `this.helpers.getBinaryDataBuffer` and `require`
  of `crypto` needs `NODE_FUNCTION_ALLOW_BUILTIN=crypto`
  (https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/,
  https://docs.n8n.io/code/cookbook/code-node/get-the-binary-data-buffer/).
  The example workflow JSON uses the long-standing node types
  `n8n-nodes-base.webhook` v2, `.if` v1, `.set` v2, `.noOp` v1; it was not
  imported into a real n8n here (docs/automation.md says so).
- SPEC 4 says `Webhook {id, url, events, secret_hash}`. HMAC signing needs
  the secret itself, so a hash cannot sign. The secret (`whsec_` +
  `token_urlsafe(32)`) is kept Fernet-encrypted (`secret_enc`, key derived
  from the data directory's master key, purpose `webhook-secrets`, the same
  scheme as the OAuth token store) and shown once on create. ASSUMPTION:
  encrypted-at-rest meets the intent of "not stored in the clear".
- Signature: `X-ClipForge-Signature: sha256=` + HMAC-SHA256(secret,
  `"<timestamp>.<raw body>"`), with `X-ClipForge-Timestamp` (Unix s of the
  attempt, so a retry is re-signed) like Stripe/Standard Webhooks, which
  gives receivers a replay window. Body: compact JSON, sorted keys, so the
  bytes are the same on every attempt.
- Delivery is an outbox: `emit` writes `webhook_delivery` rows (pending);
  a `WebhookWorker` (a `Poller`, started with the posting worker) sends them
  every 2 s. A slow endpoint never holds up a job or a post, and a restart
  loses nothing (at-least-once). Retry: `RetryPolicy(6, 30 s, 1 h)` as
  constants (no new settings): 30 s, 1, 2, 4, 8 min.
- Events come from the single places where the facts change:
  `process._finish` ("done"), `clips.render_clip_row` (rendered),
  `posts.move` and `post_queue.fail_interrupted` (published / failed); a
  failure to queue is logged, never raised (`webhook_events._never_raises`).
  `post.failed` is the final failure only (a retry moves back to queued).
- Webhook management is human only and not in `/api/v1`: an agent with a key
  could otherwise exfiltrate clip titles and post URLs to its own server.
  URLs may be http (n8n and scripts run on localhost); no SSRF filter since
  only the owner sets them.
- `data` holds ids and API paths, no disk paths.

## TASK-166 (T55c) MCP server

- SDK verified from the installed package (`mcp` 2.3.0, `uv add mcp`, read
  2026-11-01: `mcp/server/lowlevel/server.py`, `mcp/client/client.py`;
  docs at https://modelcontextprotocol.github.io/python-sdk/ not fetched).
  Facts: `mcp.server.Server(name, instructions=, on_list_tools=,
  on_call_tool=)` takes handlers `(ctx, params)`; types come from the
  separate `mcp_types` package (`Tool.input_schema`, `CallToolResult`
  `is_error`, `TextContent`); `stdio_server()` + `server.run(read, write,
  server.create_initialization_options())`; `mcp.Client(server)` connects
  in process (used by the tests). This is the 2.x API: v1's `FastMCP` and
  `types.Tool.inputSchema` do not exist in it.
- The low-level `Server` is used, not `MCPServer` decorators, because the
  tools are generated from the OpenAPI document (53 tools with JSON Schemas
  the API already defines), not written one by one.
- Separate process over HTTP (`clipforge-mcp`, stdio) rather than inside the
  app: it is a client of `/api/v1` with a key, so rate limits, key
  revocation and the human-only rule apply unchanged, and the app needs no
  MCP transport. The key comes only from `CLIPFORGE_API_KEY`.
- 1:1 with the API except: queue and publish (no tool; the API is 403 too),
  the `queue` field of `bulk_schedule` (hidden), chunked uploads and the job
  event stream (do not fit a tool call; `upload_project` takes a local file
  path instead), the raw cover upload. File answers are saved to
  `--download-dir` (default `~/clipforge-downloads`); a tool returns the path
  because MCP text results are the wrong channel for a video.

## TASK-68 (T27f) SRT and WebVTT upload

- WebVTT format checked 2026-11-01 against https://www.w3.org/TR/webvtt1/
  and https://developer.mozilla.org/en-US/docs/Web/API/WebVTT_API/Web_Video_Text_Tracks_Format:
  `WEBVTT` first line, then NOTE/STYLE/REGION blocks (skipped), cue blocks
  with an optional identifier line, timing `[hh:]mm:ss.ttt --> [hh:]mm:ss.ttt`
  plus cue settings after the end, `<v>`/`<c>`/`<00:00:01.000>` tags.
- One parser (`pipeline/subtitle_import.parse_subtitles`) for both formats
  (renamed from `srt_import`): hours are optional and `,` or `.` both work in
  either, so a slightly off file still imports. A fraction is read as digits
  (`,5` = 0.5 s). HTML entities are unescaped.
- Malformed means: a `-->` line that does not parse, a cue that ends before
  it starts, text outside a cue that is not a counter (SRT), a counter or
  identifier without a timing. The 422 `invalid_subtitles` message starts
  with `line N:` (`SubtitlesError.line`). A file with no cue at all has no
  line.
- Each word has `Word.approximate` (default false, so v1 transcripts load);
  `Transcript.approximate_times` stays. The editor's joined words are
  approximate if any part is.
- The file stays `<token>.srt` for both formats (format sniffed from the
  header) so tokens from TASK-39 keep working.
- Not done: attaching subtitles to a project after creation (the upload only
  sets `subtitles_id` for a new project's settings).

## TASK-69 (T27g) Captions/reframe-only mode, languages, import UI

- The mode already existed as `clipping: "none"` (TASK-39); it is renamed
  `captions_only` to match SPEC-v2 3.1. Settings saved with "none"
  (project settings, presets, the default) are read as `captions_only` by a
  `ProcessingSettings` before-validator, so no migration is needed (they are
  JSON, not columns).
- "Captions only" and "reframe only" are one mode: the one clip still gets
  captions (unless "No captions") and the reframe crop of its aspect ratio.
- Languages: nothing new. `languages.WHISPER_LANGUAGES` is faster-whisper's
  own list (a unit test compares it with `faster_whisper.tokenizer`);
  `language: null` is auto-detect and is the default.
- Home: the chip row is a toggle (Long video to shorts | Captions only); the
  chosen mode is passed to the settings panel as `initial`. A Subtitles
  button uploads an SRT/VTT before the video is chosen and its token also goes
  in `initial`; it is cleared once a project is created.

## TASK-72: Length presets 0-1m..10-15m, custom range (T29a, 2026-11-01)

No third-party API is used: only our own validation rules (nothing to verify
against external docs).

- New presets `0_60` (0-1m) and `60_180` (1-3m) join the existing `180_300`,
  `300_600`, `600_900` (3-5m, 5-10m, 10-15m) and the v1 ones; saved settings
  keep working (the literal only grew).
- Custom range: preset `"custom"` plus `ProcessingSettings.custom_length_min_s`
  and `custom_length_max_s` (seconds, both bounds inclusive). Rules: both
  required when "custom" is chosen, `0 <= min < max <= 900`
  (`models.CUSTOM_LENGTH_MAX_S`); each bound is checked even when "custom"
  is not chosen. They are JSON settings, so no migration. A custom range
  combines with other presets like any preset (a clip fits if it fits any).
- The range is not a literal-keyed constant, so `length_range`, `fits_preset`,
  `longest_clip`, `describe_range`, `validate_candidate` and
  `curate_prompt.length_rule` take an optional `custom=(min, max)`
  (`ProcessingSettings.custom_length`). `campaign_presets` only maps fixed
  presets, so a campaign never picks "custom" but may now pick `0_60` and
  `60_180` when their range overlaps its duration range.
- Timeframe and clip count were already enforced (curate drops candidates
  outside the timeframe; score keeps `num_clips`); T29a adds tests on the
  fixture transcript. The UI for the custom range is TASK-76.

## TASK-73: Prompt to clip and keyword search (T29b, 2026-11-01)

No third-party API is used: Python's own `str.casefold`/`str.isalnum`
(checked with `help(str.casefold)` in the project's Python, 2026-11-01) and
`string.Template.substitute` (substituted values are not scanned again for
`$`, so a request may hold "$").

- Prompt to clip is the existing `keyword_prompt` (the "Find moments
  about..." box): its section moved to `prompts/prompt_to_clip.md`
  (`curate_prompt.request_section`, placeholder `$request_section` in
  curate_base.md, was `$keyword_section`). It now asks for every matching
  moment of the window, allows other wording for the same topic, asks each
  reason to say how the clip matches, and for no clips if nothing does.
  The reply goes through the usual schema check/retries and score + snap.
  No rename of `keyword_prompt` (saved settings, UI and API keep it).
- Keyword search is a clipping mode, `clipping: "keyword_search"`, with
  `ProcessingSettings.search_terms` (<= 20 terms of <= 100 chars; tidied:
  whitespace collapsed, blanks and case-insensitive repeats dropped; at
  least one needed for the mode). No LLM is asked (`pipeline/keyword_search`).
- Matching: whole words, case and punctuation ignored (`normalize` keeps
  casefolded letters and digits), a phrase matches consecutive words even
  across segments, punctuation-only words skipped. No stemming ("fridge"
  does not match "fridges") and no matching inside words, so scripts
  without spaces (Chinese, Japanese) only match whole Whisper words.
- Windows: from the match's segment, add the neighbouring segment (after
  or before) that keeps the window shorter, the one after on a tie, until
  it reaches the shortest of the goal, never past the longest. Goal: the
  first chosen length preset's range ("auto": clip_min_s..clip_max_s;
  ranges from 0 aim for at least clip_min_s), its longest minus snap's
  0.3 s tail. A segment longer than the goal is grown by words. Matches
  inside a window join it; the next window cannot reach back into the one
  before, so windows never overlap and dedupe never drops a match.
- Candidate text without an LLM: title `"term" at mm:ss.s`, empty hook,
  description = the sentence of the first match, hashtags = terms (letters
  and digits) + video/clip/shorts (moved to `candidate_rules
  .DEFAULT_HASHTAGS`), emphasis = the matched words, reason lists terms and
  times, LLM scores 50 (signals then rank them in score). num_clips and
  max_clips_from_llm still cap the result.
- UI for search terms is TASK-76 (the mode is API-only for now).

## TASK-74 (T29c): reprompt without re-transcribing

- Third-party APIs: none new (SQLite, FastAPI, SQLModel as before).
- A reprompt is a new job kind, `reprompt` (`reprompt.py`), not a second
  process job, so the project's process job, its work directory (video,
  transcript, signals, enriched.txt, crop plans) and its step markers stay
  untouched. It runs curate, score and snap again (`force=True`) in the
  process job's work directory, with `keyword_prompt` = the prompt and
  `clipping` = "ai" (a captions-only or keyword-search project is asked
  with the LLM). Transcribe, signals and enrich are not run: tests assert
  the loaded steps are exactly curate, score, snap. The prompt is saved as
  `prompt.txt` in the reprompt job's own directory.
- Result sets: `Clip.result_set` and `Project.result_set` (migration 022,
  all existing rows 1). A reprompt saves its clips as set
  `project.result_set + 1` and switches the project to it only when the set
  is saved, reframed and rendered, and the project's settings take the new
  prompt then. Lists, zip, Premiere XML and `project.completed` show the
  current set; `GET /projects/{id}/clips?result_set=N` shows any set. The
  old clips, their renders and crop plans are kept (never deleted).
  A reprompt that finds nothing makes an empty current set (the old set
  stays reachable).
- Status: the endpoint answers 409 unless the project is `done` (checked and
  set to `queued` in one UPDATE, so two reprompts cannot both start), and
  409 if enriched.txt is gone. The project is `queued`/`running` meanwhile.
  A failed or poison reprompt deletes its unfinished clips and puts the
  project back to `done` with its old set; only the job is `failed`. A
  reprompt that restarts after a stop begins again at curate.
- Config: `job_concurrency` has `reprompt: 1`, and reprompt shares the GPU
  lock (`gpu_job_kinds`), as reframe runs face detection.
- `project.completed` is raised again when a reprompt finishes (with the new
  set's clips). The frontend (TASK-76) will show the sets.

## TASK-75 (T29d): topic chapters and clip by topic

- Third-party APIs: none new (the existing LLM clients and Pydantic only),
  so there is nothing to verify against external docs (SPEC-v2 0.1).
- Chapters are made on demand, not as a pipeline step: `POST
  /api/projects/{id}/chapters` runs `pipeline/chapters.make_chapters` in the
  request (sync, in FastAPI's thread pool) and saves `chapters.json` in the
  process job's work directory; `GET` returns it (`[]` if not made). A
  second POST replaces the chapters. Simplest option; a long video takes one
  LLM request per 30 minutes (`CHAPTER_WINDOW_S`), asked one after another.
  502 `llm_error` if the LLM fails or sends no valid reply
  (`ChapterLLMError`), 409 if there is no transcript.
- The chapters prompt (`prompts/chapters.md`) shows the sentences of the
  timeframe (transcript segments, not enriched.txt, so times are exact).
  A reply is valid when it parses, the chapters end after they start, do not
  overlap by more than 0.1 s and every sentence starts in a chapter; else it
  is sent back with the problems, up to `curate.MAX_RETRIES` times, then the
  endpoint fails (there is no way to skip a part without a gap).
- Snapping: each chapter start moves to the nearest sentence start (the
  earlier on a tie); chapters that snap to one sentence become one (the
  first kept); the first chapter of a part starts at the part's first
  sentence; each chapter ends where the next starts (a pause belongs to the
  chapter before it) and the last at the end of the last sentence. A topic
  that runs over the border of two 30-minute parts is split there.
- Clip by topic: `POST /api/projects/{id}/clip-by-topic` `{chapters: [ids],
  prompt?}` is a reprompt (TASK-74) with ranges: `enqueue_reprompt(...,
  ranges)` saves `ranges.json` next to `prompt.txt`, `run_step(ranges=)`
  gives them to `StepSettings.ranges` and `curate.run` asks each range apart
  (`plan_scopes`), keeping only clips inside one range, then ranks all clips
  together and caps them at `max_clips_from_llm`. Chosen chapters that follow
  each other are one range, so a clip may span them. The ranges are not part
  of `ProcessingSettings` (no schema/migration): they belong to the job. The
  prompt is optional; without one, `keyword_prompt` of the new result set is
  null (the old prompt is not carried over). 409 without chapters or if the
  project is not done, 422 for an unknown chapter id or an empty list.
- Not done: no UI (TASK-76); chapters are not removed when the project is
  reprocessed (a new process job has a new work directory, so they go with
  it); no editing of chapter titles or bounds.

## TASK-76 (T29e): clipping controls UI (reprompt, topics)

- Third-party APIs: none new (Radix Dialog, already used by the rename
  dialog; TanStack Query), so nothing to verify externally (SPEC-v2 0.1).
- The settings panel already had the presets, custom range, timeframe, count,
  prompt and genre controls (TASK-39/72/73); this task adds the gallery part.
- Gallery header has "Reprompt" (dialog with the prompt, prefilled with the
  project's `keyword_prompt`) and "Topics" (`ChaptersPanel`: "Find topics"
  POSTs the chapters, a checkbox per chapter with its time span and summary,
  optional prompt, "Clip selected topics"). Both are shown also when the
  project has no clips, since that is when a new prompt helps most.
- Both actions queue a `reprompt` job and the project becomes `queued`, so
  the project page switches to the processing view. `useProcessJob` now
  follows the newest `process` or `reprompt` job so that view (and the
  project card) shows the reprompt's steps instead of the finished process job.
- Once a project has more than one result set a "Result" select shows an
  earlier set (`GET .../clips?result_set=N`); it opens on the latest. The
  clips query key now includes the result set.
- Shared `components/ui/dialog-frame.tsx` for the two new dialogs; the rename
  dialog was left as is.

## TASK-77 (T30a): audio event classes as curation signals

- Third-party APIs verified (SPEC-v2 0.1, 2026-11-01): the installed class map
  `models/yamnet/yamnet_class_map.csv` (CSV `index,mid,display_name`, same as
  https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)
  has `Laughter` (13), `Cheering` (61), `Applause` (62) and `Music` (132);
  names are looked up in the loaded map (`Yamnet.class_index`), never by
  index, and a map without one is a `StepError`. No new library call.
- Same single audio pass, 4 columns instead of 2 (no extra model run). Per
  class: a per-second track (max score of the frames that overlap each second,
  from the timeframe start) in `audio_events.json` (`AudioEventList`,
  written before signals.json so signals.json implies it), and events in
  signals.json (new `SignalKind`s `cheer` and `music`, same 0.3 threshold and
  merge/min-duration settings as laugh/applause).
- Scoring: the energy component now also counts applause and cheer events
  (`signal_merge.CROWD_KINDS`), merged with energy peaks (overlaps count
  once). Music does not change the score (it is background more often than a
  highlight); it is stored for the curate prompt/search (TASK-79). No new
  score component, so no schema, migration or `score_weights` change.
- Side effect: YAMNet hears Music in the speech of the 60 s fixture, so
  signals.json of the fixture now has `music` events; nothing reads them yet
  (enriched.txt has no marker for them, so recorded LLM prompts are intact).
- Not done: jobs processed before this task have no audio_events.json (it is
  optional, nothing requires it); cheer events do not get a transcript marker.

## TASK-78 (T30b): VLM frame captions via Ollama

- Third-party APIs verified (SPEC-v2 0.1, 2026-11-01): Ollama's OpenAPI at
  https://docs.ollama.com/api/chat (https://docs.ollama.com/openapi.yaml):
  `POST /api/chat` `ChatRequest` has `model`, `messages[]` (`role`,
  `content`, `images`: list of base64 strings "for multimodal models"),
  `stream` (default true), `think` (bool or low/medium/high), `options`
  (`temperature`, `num_predict`); the reply's `message.content`,
  `prompt_eval_count`, `eval_count`. `GET /api/tags` (= `ollama list`),
  `POST /api/show` `capabilities`, `GET /api/version` (as in TASK-61).
  ffmpeg: `-f image2pipe -c:v mjpeg pipe:1` writes one JPEG to stdout.
- Feasibility on this Mac (arm64, Ollama 0.34.4, `ollama serve`): `ollama
  list` shows `qwen3.5-35b-128k:latest` (and `huihui_ai/qwen3.5-abliterated:35b`,
  its parent); `/api/show` lists `["completion", "vision", "tools",
  "thinking"]` for it. A 512 px frame of the fixture: 17.5 s with the model
  cold, 0.3-0.5 s warm. So the engine is usable (not BLOCKED).
- Model: `VLM_MODEL` (new setting, default empty) or else the first vision
  model `ollama list` shows (here `qwen3.5-35b-128k:latest`); a name without a
  tag means `:latest`. The install check now also fails when VLM_MODEL is set
  but not a pulled vision model. `think: false` because qwen3.5 is a thinking
  model (else it spends the token budget thinking). Temperature 0,
  num_predict 80, one-sentence prompt (original wording).
- Sampling: a frame 0.2 s after each scene cut of signals.json (so it shows
  the new scene; at the cut if that is past the timeframe end) plus one every
  `FRAME_CAPTION_INTERVAL_S` (default 10 s) from the timeframe start; an
  interval frame within 2 s of a scene-cut frame is dropped. Frames are
  scaled to 512 px wide JPEG in memory (no temp files).
- Not a pipeline step yet (not in STEP_NAMES): `frame_captions.run(job_dir,
  settings, *, force, captioner=None)` has the step signature and writes
  `frame_captions.json` (`FrameCaptionList`: model + captions with time,
  reason, caption). TASK-79 runs it when "clip anything" is on and feeds the
  captions into the curate prompt; running it on every job would add a 23 GB
  model load to plain speech projects.
- `OllamaVisionEngine` moved from engines/checks.py to engines/vlm_ollama.py
  (same name and registry entry `ollama_vlm`).

## TASK-79 (T30c): clip anything: motion + frame captions into curate

- Switch: `ProcessingSettings.clip_anything` (bool, default false; JSON in
  the project settings, so no migration). It only acts with clipping "ai"
  (simplest option: not a new ClippingMode, so prompt to clip, genres and
  reprompt work with it unchanged). Settings panel toggle "Clip anything".
- New step `visuals` in STEP_NAMES between signals and enrich
  (`pipeline/visuals.py`): a no-op unless clip anything; then motion.json
  and, only when the `ollama_vlm` engine is installed (`engines.is_installed`),
  frame_captions.json (TASK-78). Without the engine curate still gets motion,
  audio events and scene cuts. Reprompt runs visuals first, not forced, so a
  clip-anything reprompt of a project processed without it gets the files.
- Motion energy (`pipeline/motion.py`), verified 2026-11-01 with the
  installed ffmpeg 9.0.2 (`ffmpeg -h filter=fps`, `-h filter=scale`,
  `-h filter=format`, `-h muxer=rawvideo`; docs
  https://ffmpeg.org/ffmpeg-filters.html#fps-1): `-vf
  fps=4,scale=64:36:flags=area,format=gray -f rawvideo pipe:1`, then numpy:
  mean |frame - previous| / 255 per pair, per-second median (a scene cut is
  one pair, so it does not count as motion). ffmpeg, not OpenCV: no new
  dependency and the frames stream from one process. Measured: still picture
  0, talking-head fixture ~0.012, testsrc2 0.03-0.05; 60 s of the fixture in
  0.2 s.
- "High motion" spans: seconds >= max(0.02, 1.5 x the 25th percentile of the
  timeframe), joined over 1-s gaps; level = span mean / busiest second. The
  median was tried first: when most of the timeframe moves it hides all
  motion, the 25th percentile does not.
- Prompt: `prompts/clip_anything.md` (original wording) is the system
  prompt's `$anything_section`; the user message gets timeline lines
  between the transcript lines, by time: `[mm:ss.s] FRAME: caption`,
  `[mm:ss.s] SCENE CUT`, `[a-b] MOTION 0.77`, `[a-b] LAUGH|APPLAUSE|CHEER|MUSIC
  0.80`. Laugh/applause/scene cut are also inline markers in enriched.txt
  (kept as they were); the standalone lines are what a window without
  speech has.
- No speech: snap keeps a wordless clip at the LLM's times (it used to drop
  it) and auto cut takes nothing out with clip anything on (it would cut a
  wordless clip down to 0.24 s and cut action out of mixed clips). The
  settings panel shows "Auto cut silences" off and disabled while clip
  anything is on.

## TASK-80 (T31a): aspect ratios 4:5 and custom W:H

- No third-party API is new: ffmpeg `crop`/`scale`/`pad` filters were already
  used for any output size, so the render graph needed no change (checked
  against the installed ffmpeg by the real renders in
  `tests/pipeline/test_reframe_ratios.py`, 2026-11-01).
- `Aspect` is a `"W:H"` string (`clipforge/aspect.py`, pure) instead of a
  Literal: `^[1-9][0-9]{0,2}:[1-9][0-9]{0,2}$`, long side at most 4 x the
  short side (1:4 to 4:1), validated in models, the CLI and the crop API.
  Presets: 9:16, 1:1, 4:5, 16:9. Frontend type is `string`.
- Size: 1080 px on the shorter side, the longer side to match, rounded to an
  even number; a longer side over 1920 is capped there and the shorter side
  shrinks (21:9 -> 1920x822, 4:1 -> 1920x480). That gives 1080x1920,
  1080x1080, 1080x1350, 1920x1080 for the presets, as before for the old ones.
- `render.SIZES` stays as the presets' sizes (tests); code that renders uses
  `aspect.aspect_size(aspect)`, which also sizes a custom ratio.
- UI: 4:5 is in the settings and player aspect menus; a custom ratio from
  the API shows as "W:H custom" in the settings select. There is no
  free-text custom ratio field yet.

## TASK-81 (T31b): moving subject (object) tracking

- Tracker availability, verified 2026-11-01 on this machine (macOS arm64)
  with the installed `opencv-contrib-python` 5.0.0.93 (`help()` and a live
  probe): `cv2.TrackerCSRT.create()`, `cv2.TrackerKCF.create()` (also MIL,
  Nano, Vit, DaSiamRPN; Nano/Vit/DaSiamRPN need ONNX model files, not
  bundled, so unused). `init(frame, (x, y, w, h))` returns None;
  `update(frame)` returns `(ok, (x, y, w, h))`. Also used:
  `cv2.cvtColor(src, COLOR_RGB2GRAY)`, `cv2.GaussianBlur(src, ksize,
  sigmaX)`, `cv2.absdiff`, `cv2.threshold(src, thresh, maxval, type) ->
  (retval, dst)`, `cv2.getStructuringElement`, `cv2.morphologyEx`,
  `cv2.connectedComponentsWithStats(image, connectivity=8) -> (count,
  labels, stats, centroids)` (stats rows: left, top, width, height, area;
  row 0 is the background). Docs: https://docs.opencv.org/5.x/ (checked
  against installed docstrings, 2026-11-01). Test
  `test_this_opencv_build_has_the_csrt_tracker` records it.
- Fallback: CSRT, else KCF (`click_track.opencv_tracker`); with neither
  (an opencv build without contrib), `click_track.DetectorTracker` follows
  the moving region nearest the last box (the motion detector below acts as
  its detector). Tested with `make=lambda: None`.
- What is "the moving subject" (no click): the per-pixel median of up to 25
  gray samples of the shot is the background; pixels > 30 gray levels off
  it, opened 3x3 and closed 9x9, form regions; boxes of 0.2%-30% of the
  frame count. The largest one in the shot seeds the tracker, which runs
  forward and backward from it (frames at 320 px, 10 fps, like
  click-to-track). A tracked box that overlaps no moving region of its
  sample is "lost" (CSRT drifting onto background), so the window holds
  there. A shot needs a moving region in >= 30% of its samples and >= 5
  samples, else it has no moving subject.
- When: only in shots (between scene cuts) where no face and no person is
  detected; shots with people keep v1 behaviour exactly. Simplest option,
  no setting. Boxes are stored as `FaceBox(kind="object")` in the crop
  plan's keyframes so subject choice, smoothing, `replan` and the editor
  reuse them unchanged (score = share of the box a moving region covers).
- Limits: needs a mostly still camera (a pan or zoom makes the whole frame
  "move", the regions exceed 30% and the shot keeps the center crop); one
  subject per shot (the largest mover); a 30 s faceless 720p shot takes
  ~5 s (three 320 px decodes + CSRT).

## TASK-82 (T31c): manual subject tracking + genre reframe presets

- Manual tracking (click or box at a time t, followed forward and back
  through the scene) already shipped with STEERING 7b
  (`pipeline/click_track.py`, `POST /clips/{id}/scenes/track`; decisions
  TASK-54). This task adds `tests/api/test_manual_tracking_api.py`, which
  runs it on the moving-square video through the API, and the presets.
  No new third-party call: OpenCV CSRT facts are in TASK-81.
- Presets (`pipeline/reframe_presets.py`, table `PARAMS`): `podcast-2`
  (layout by faces, split at > 40% of samples with two faces instead of
  60%, no object tracking), `standup` (always fill, dead-zone 0.05, pan
  0.4 frame widths/s: the performer paces), `gaming` (always fit: the whole
  screen over a blurred copy, no object tracking), `vlog` (always fill,
  dead-zone 0.12, pan 0.3 against hand shake, objects tracked). Numbers
  are the simplest values that differ visibly from the defaults (dead-zone
  0.08, pan 0.25, split 60%); there is no reference to tune them against.
- "Gaming/screenshare" maps to the fit layout because the screenshare +
  facecam, gameplay + facecam and picture-in-picture layouts come with
  T32 (TASK-84+); this preset then changes there.
- Choice: `ProcessingSettings.reframe_preset` (None: the defaults; no
  automatic pick by genre, so existing projects frame exactly as before).
  `CropPlan.preset` keeps it so `replan` (other aspect) frames the same
  way. `GET /api/reframe-presets` lists the table for the editor UI
  (TASK-83); there is no per-clip override yet.

## TASK-83 (T31d): reframe v2 editor UI

- No third-party call: the UI uses `GET /api/reframe-presets` (TASK-82) and
  the existing track endpoint. Checked in the repo on 2026-11-01.
- Click on the preview to set the tracking target already existed
  (`PlayerTrackPick`, STEERING 7b); it is unchanged and its tests
  (`EditorTrack.test.tsx`) cover it.
- The reframe preset is a project processing setting that shapes the clips
  when they are found (reframe runs then), and there is no per-clip
  override or re-plan endpoint. So the preset select is in the settings
  panel (`ReframeStyleField`, "Automatic" = null) and the editor shows
  the project's style read-only in `ReframeControls`, instead of a select
  that would change nothing for the open clip.
- Custom ratio: a text field in the Layout tab, checked with the backend's
  rule (`lib/aspectRatio.ts`, two numbers of 1-3 digits, at most 4:1); the
  toolbar's aspect menu adds the clip's custom ratio as a checked item.
  The common ratios stay in the toolbar menu only.

## TASK-84 (T32a): three-speaker grid + picture-in-picture layouts

- Verified 2026-11-01 with the installed ffmpeg 9.0.2 (`ffmpeg -h
  filter=vstack|hstack|overlay|pad`; https://ffmpeg.org/ffmpeg-filters.html):
  `vstack`/`hstack` take `inputs` (needs equal widths / heights),
  `overlay` takes `x`/`y` expressions with `W`,`H` (main) and `w`,`h`
  (overlay), `pad` takes `w`,`h`,`x`,`y`,`color`. No other new API.
- New `Layout` values `grid` (three speakers) and `pip` (picture in
  picture). Reframe does not pick them yet (auto switching is T32c); the
  user sets them per clip or per scene (API now, UI in T32e).
- Grid: three cells, rows (`vstack`) when the output is taller than wide,
  else columns (`hstack`): 9:16 and 4:5 get rows, 1:1 and 16:9 columns
  (rows of 1:1 would be 3:1 strips). Even thirds, the last cell takes the
  rest. Each window follows the left/middle/right of the three largest
  faces, like split (generalized: `tracking.face_groups`,
  `layout_windows.side_windows`; `split_windows` moved there, same output).
- Pip: the fill window fills the output; a square inset, 36% of the
  shorter side, 4% from the top and right edges, white border 1/180 of the
  side, shows the "other speaker" (largest face that is not the subject),
  at 3x its median height (at most the frame height and half its width).
  No such face in the clip: the inset shows the whole frame, fitted. The
  inset follows switches like the fill window (pans, no jump). Simplest
  choice that fits podcasts and single speakers; manual inset choice can
  come with T32d/T32e.
- `CropPlan.grid` (list, empty in older plans) and `CropPlan.inset`
  (None = whole frame) default so v1 plans still load. `framing.planned`
  adds them (`layout_windows.add_layout_windows`, from the faces the
  keyframes hold; reads meta.json + signals.json) only when the clip or a
  scene uses grid/pip, so v1 renders read exactly what they did before.

## TASK-85 (T32b): screenshare + facecam, gameplay + facecam layouts

- Verified 2026-11-01 with the installed ffmpeg 9.0.2 (`ffmpeg -h
  filter=crop|scale`; https://ffmpeg.org/ffmpeg-filters.html): `crop`
  takes `w`,`h`,`x`,`y` expressions in `iw`,`ih` (so a box in fractions
  needs no frame size), `scale` takes `force_original_aspect_ratio`
  (`increase` = cover) and `force_divisible_by`; `null` passes frames
  through (used to start a chain from a split label). No other new API.
- New `Layout` values `screenshare` and `gameplay`. Two cells, rows when the
  output is taller than wide, else columns (like grid). Screenshare: the
  whole frame fitted in the first cell over the plan's background (blur or
  black, the fit graph), so the screen stays readable; the facecam cell
  (50% of the long side) second. Gameplay: facecam first (1/3), the middle
  of the frame scaled to cover the rest (2/3) and cropped, the usual
  gaming-shorts look. Simplest fixed shares; adjustable shares can come
  with the layout UI (T32e).
- Facecam box (`FrameBox`, fractions of the frame): auto = a square of 3x
  the median height of the subject's face (marked subject, else largest
  face; persons/objects ignored), centered on its median center, inside the
  frame, held still (a stream's facecam does not move). User box:
  `Framing.facecam` (PATCH /clips/{id} `framing`), which replaces the found
  one in `framing.framed_plan`. The cell shows the box scaled to cover it
  and cropped around its center (no stretching). No face and no box: the
  video takes the whole output (screenshare = fit, gameplay = center crop).
- `CropPlan.facecam` defaults to None, so v1 and TASK-84 plans load;
  `framing.planned` computes it from the keyframes' faces
  (`layout_windows.add_facecam`, needs meta.json) only when the clip or a
  scene uses a facecam layout, the plan has none and the user drew none.
- The gaming preset keeps `fit`: it covers screen recordings too, where
  gameplay's crop would cut the screen; picking a default layout is T32c.
- `layouts.py` would pass 300 lines: the crop expressions and the fit graph
  moved to `pipeline/layout_parts.py` (same output), the facecam graphs are
  in `pipeline/facecam.py`.

## TASK-86 (T32c): dynamic per-segment layout switching + default layout

- Verified 2026-11-01 with the installed ffmpeg 9.0.2 (`ffmpeg -h
  filter=concat`; https://ffmpeg.org/ffmpeg-filters.html#concat): `concat`
  takes `n`, `v`, `a`; every segment must have the same size and SAR (each
  layout graph ends in `setsar=1` at the output size). No other new API.
- Default layout: one processing setting `default_layout` = `auto` (v1:
  reframe's per-clip choice, preset included), `dynamic` (a layout per
  segment) or a `Layout` (every new clip). One field instead of a layout +
  a switch toggle, so the settings UI (T32e) is a single select. `auto` is
  the default, so v1 projects and tests are unchanged.
- Dynamic (`pipeline/layout_switch.py`): shots at the scene cuts
  (`scenes.default_scenes`), then within a shot a new segment where the
  per-sample layout changes for at least 2 s (shorter runs join their
  longer neighbour, deterministic). Segment layout: grid/split when 3/2
  faces persist (> the preset's split share, fill narrower than the frame,
  as `reframe.choose_layout`); someone seen in >= half the samples -> fill
  (preset layout; its facecam variant for fit, so gaming -> screenshare);
  a moving object -> fill (preset); nobody -> fit (preset). Pip and
  gameplay are never picked automatically (no reliable signal); the user
  picks them per scene.
- The segments are stored as the clip's `scene_reframes` (auto mode) only
  when their layouts differ; the clip's layout is the one shown longest.
  Manual override = PATCH `scene_reframes` (existing). A clip that already
  has scenes keeps them when the layouts are set again.
- `set_planned_layouts` moved from `clips.py` (at 300 lines) to the new
  `clip_layouts.py`. Zoom punch-ins now center on the subject of the scene
  (plan + layout) that holds each zoom keyframe (`zoom_graph.framing_at`),
  not on the clip's layout throughout.

## TASK-87 (T32d): keyframed manual reframe (drag/resize crop box)

- Already built under STEERING item 7 (TASK-54 commits): per-scene fixed
  crop keyframes (`SceneReframe.crop_keyframes`, migration 010), linear
  between keyframes, rendered per scene (`scene_framing.keyframed_plan`,
  `layout_parts.crop_window`). Not re-implemented.
- Added for T32d: `pipeline/keyframes.py` (set/delete one keyframe on a
  scene, scene at a time, `window_at` = the ramp the crop expression
  encodes) and `PUT`/`DELETE /api/clips/{id}/crop-keyframes`, so a keyframe
  can be set without sending every scene (agents, scripts). Semantics copy
  the editor's crop tool: keyframes within 0.1 s are one (frontend
  `POINT_GAP_S`), an auto scene turns fixed, a track scene stays track,
  only fill scenes take keyframes (422 otherwise). The routes live in a
  new `api/clip_keyframes.py`, not `api/clips.py` (256 lines; the 300
  line limit), and are not in `api/v1.PUBLIC_ROUTERS`, like the other crop
  endpoints of `api/clip_crop.py`.
- Verified 2026-11-01 against the installed ffmpeg 9.0.2 and
  https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_crop.c
  (`filter_frame`): per frame, crop evaluates x and y, rounds with
  `lrint`, clamps the window inside the frame, then (without `exact`)
  rounds down to the chroma subsampling (even pixels for yuv420p), and
  logs `n:%d t:%f x:%d y:%d x+w:%d y+h:%d` at loglevel trace. The test
  compares that log with `window_at` at every frame.


## TASK-88 (T32e): layouts + keyframe crop UI in the editor

- Most of T32e existed: the crop tool (drag/resize, keyframe at the
  playhead, STEERING 7a), the keyframes row and per-scene framing
  (`SceneChooser`). Added: `components/LayoutPicker.tsx` (a 3x3 tile radio
  group of every framing: Auto, Track, Fixed, Fit, Split, Grid, Picture in
  picture, Screenshare + facecam, Gameplay + facecam; constants in
  `components/layoutOptions.tsx` for react-refresh), the toolbar layout menu
  lists all 7 clip layouts (short visible names, full name in aria-label;
  the toolbar wraps instead of overflowing), `components/CropBoxEditor.tsx`
  (the drag/resize box, shape kept or free; `PlayerCrop` now uses it) and a
  "Default layout" select in the settings panel (`default_layout`).
- Facecam box (T32b had no UI): in a screenshare or gameplay scene the Crop
  button edits `framing.facecam` (one box per clip, as the backend stores
  it) with a free-shape box; "Use the found box" sets it back to null. To
  draw the found box, `CropTrack` (GET /clips/{id}/crop) now also returns
  the plan's facecam box (found from the plan's faces for older plans;
  `None` without a face, then the editor starts with a square in the
  middle). Simplest option: no new endpoint.
- The editor keeps editing scenes client-side and saves with PATCH (as
  before); the T32d keyframe endpoints stay for agents/scripts.
- Verified 2026-11-01 in the installed packages: lucide-react exports
  `Columns3`, `PictureInPicture2`, `ScreenShare`, `Gamepad2`
  (`node_modules/lucide-react/dist/lucide-react.d.ts`); pointer capture
  (`Element.setPointerCapture`) per
  https://developer.mozilla.org/en-US/docs/Web/API/Element/setPointerCapture
  routes later pointer events to the box element, so the box handles its
  own moves.

## TASK-89 (T33a): 10+ original animated caption templates + live preview

- Extended the v1 template system instead of a new one: `CaptionTemplate`
  gained `outline_color` (stroke/box color, default black as before),
  `max_lines` (1-2) and `animation` (none, pop, bounce, fade, reveal);
  `max_words_per_line` widened to 1-6. Every template field is also an
  optional `CaptionStyle` field, so a clip can override any of them
  (`font` must be a bundled font: `style_problems`, 422 validation_error).
  The six v1 templates keep their values and output (animation none,
  one line, black stroke).
- Seven new templates with original names (13 in all): pop_punch,
  spotlight, storyteller, soft_fade, ember_box, tidal_bounce,
  headline_duo. All stay in the lower third (owner rule TASK-24/25).
- Animations stay within the owner's size rules (active word <= 105%,
  emphasis 110%): pop grows each spoken word from 75% to its size in
  120 ms; bounce goes 85% -> size+5 points (90 ms) -> size (90 ms);
  fade fades a caption page in over 150 ms; reveal keeps the words after
  the spoken one transparent so the line never moves.
- Two lines: lines of a clip are grouped into pages of at most
  `max_lines` (owner: "at most two lines"); a page also ends at a pause
  (> 300 ms, the line rule). Lines of a page are joined with `\N`.
- Live preview: `POST /api/caption-templates/{name}/preview` with a
  CaptionStyle body returns the template's sample frame with the style
  applied (PNG, drawn per request, not cached: caching every slider
  position would fill the disk). The
  sample caption has 7 words now so two-line templates show two lines.
  Not in /api/v1 (as the GET preview).
- Verified 2026-11-01 at https://aegisub.org/docs/latest/ass_tags/:
  `\t(t1,t2,tags)` animates `\fscx`, `\fscy`, `\alpha`, `\c`, `\3c` from
  the event's start in ms; `\fad(in,out)` fades in/out in ms;
  `\alpha&HFF&` is fully transparent; `\3c` is the border color; `\r`
  resets to the style, ending earlier animation tags. Checked against
  libass in ffmpeg 9.0.2 (`--enable-libass`) by rendered pixels
  (tests/pipeline/test_caption_animation.py: pop 94 -> 126 px wide in
  120 ms, bounce peaks at 135 px then settles at 129 px).

## TASK-90 (T33b): AI emojis + keyword highlights per word + speaker colors

- Per-clip data lives in `CaptionStyle` (a JSON column that exists), not in
  new `Clip` columns: no migration, `PATCH /clips/{id}` and the editor's
  undo/preview key already carry it. `speaker_colors` (speaker label ->
  `#RRGGBB`) and `word_marks` (list of `CaptionMark`) have no template
  counterpart, so `CaptionTemplate.styled` skips them and the test that
  compares the two field sets excludes them. The frontend's reset to the
  template and template change keep them (`resetStyle`).
- A `CaptionMark` names a word by its start in source seconds (to the
  millisecond, like `caption_overrides`), so it survives cuts and trims.
  `emphasis` True/False pins the word's emphasis over the clip's
  `emphasis_words` phrases (None: phrases decide); `emoji` "" removes the
  keyword-map emoji, None leaves it. `source` "ai" or "user": a user mark
  beats an AI mark of the same word, and a new AI pass (`with_ai_marks`)
  replaces only AI marks, so editor changes are never lost.
- The LLM sees the clip's caption words numbered 0..n and answers
  `{"marks": [{"index", "emphasis", "emoji"}]}` (prompt
  `caption_emphasis.md`, JSON Schema of `WordMarks`, same retry loop as
  curate/clip_text). Indexes out of range are dropped with a warning; an
  emoji must be one character (+ optional VS16), else the reply is sent
  back. Emoji codepoint pattern moved to `models.Emoji` (shared with
  `emoji_map.yaml`).
- A marked emoji always shows (the user or AI asked for that word); the
  template's `emoji` switch only governs the keyword map. Colour order of a
  word: spoken word (highlight) > emphasis (emphasis color) > speaker color
  > template primary. Speaker colors do not split lines on a speaker change.
- No endpoint calls the LLM yet: the Captions panel (TASK-96) will need
  one (`POST /clips/{id}/caption-marks`-like); the backend function is
  `caption_emphasis.generate_marks`. Verified ASS tags (`\c`, `\fn`) 2026-11-01
  at https://aegisub.org/docs/latest/ass_tags/ (already used by T33a).

## TASK-91 (T33c) Custom font upload

- Verified 2026-11-01 (installed fontTools 4.68.0 and
  https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html): `TTFont(path,
  lazy=True)` reads tables on access, `font.sfntVersion` is `"\x00\x01\x00\x00"`
  (TrueType outlines) or `"OTTO"` (CFF), `font.getBestCmap()`, `"glyf" in font`.
  A TTC or a text file raises `TTLibError`; a truncated file raises it or
  `struct.error`/`KeyError` on first table access (all become `FontError`).
- libass takes ONE `fontsdir`. Uploads live in `{data_dir}/fonts/<sha256
  prefix>.ttf|.otf` (the client's name is never a path); while there are
  uploads `render_fonts_dir()` returns `{data_dir}/fonts-render`, a folder of
  symlinks to the bundled and uploaded fonts (resynced on every call, so a
  delete takes effect); with no uploads it is the bundled `assets/fonts`, so
  nothing changes for owners who upload nothing. Checked with ffmpeg 2026-11-01:
  libass loads fonts through symlinks (`Loading font file '.../fonts-render/..'`).
- Accepted: `.ttf`/`.otf` file name, a TrueType or CFF sfnt with head, hhea,
  hmtx, maxp, name, cmap, outlines, at least one mapped character and a
  Windows family or full name (libass selects by those; without them the font
  could never be chosen). Up to 20 MB. A name that a bundled or uploaded font
  already has is 409 (libass would pick one of the two arbitrarily).
- The font's license is asked for (form field `license`, default
  `user-supplied`: ClipForge cannot know it); attribution is the font's
  copyright notice. Uploaded fonts are asset rows (kind `font`, tag
  `uploaded`); `FontFile` (models.py) lists names and bundled/uploaded.
- Deleting is refused (409) for bundled fonts and for a font a brand template
  or a clip's caption style uses, so no render silently falls back to another font.
- Brand templates accept uploaded fonts (`/brand-fonts`, `_font`); the brand
  pass of render is still missing (v1 gap), so only validation uses it.

## TASK-92 (T33d) Caption translation + RTL

- Verified 2026-11-01: the local ffmpeg links libass 0.17.5 built with
  fribidi 1.0.17, HarfBuzz and libunibreak (`ffmpeg -buildconf`, libass log
  at `-loglevel info`). libass source
  https://raw.githubusercontent.com/libass/libass/0.17.4/libass/ass_shaper.c
  (`ass_resolve_base_direction`): a style's `Encoding` -1 gives the paragraph
  an automatic base direction (`FRIBIDI_PAR_ON`), any other value forces
  LTR. So a caption style gets `Encoding -1` only when its text has a
  right-to-left (bidi R/AL) character; every existing LTR caption keeps
  `Encoding 1` and the same ASS bytes.
- Shaping is libass's (HarfBuzz + fribidi); ClipForge never reorders or
  reshapes text itself. Tested by rendering: the logical text renders
  pixel-close to the same word written as LRO + visual-order presentation
  forms (joined letters, right to left) and far from unjoined or LTR order.
- Fonts: libass silently fell back to a system font when Montserrat lacked
  Arabic (renders would differ per machine). `fonts.covering_font` therefore
  picks a bundled script font for text the caption font cannot draw:
  Vazirmatn Bold v33.003 (Persian/Arabic/Urdu,
  https://github.com/rastikerdar/vazirmatn/releases/tag/v33.003) and Noto Sans
  Hebrew Bold v3.001 `full` build (https://github.com/notofonts/hebrew/releases/tag/NotoSansHebrew-v3.001;
  Vazirmatn has no Hebrew; the `hinted`/`unhinted` builds lack Latin). Both
  OFL 1.1, recorded in `assets/fonts/LICENSES.md`, registered as bundled
  assets like the others. A template font that covers the text (an uploaded
  Arabic font) is kept; emoji-only gaps keep the font (the emoji font handles them).
- Translation: the clip's transcript words are grouped into cues
  (`caption_cues.py`: sentence end, pause > PAUSE_MS, speaker change, max 14
  words); the LLM (prompt `caption_translate.md`, JSON Schema of
  `TranslatedCues`) gets the numbered cues and returns one text per index.
  Missing, duplicate or out-of-range indexes are sent back (same retry loop
  as curate/clip_text/caption_emphasis); an empty translation of a cue is
  not allowed (pattern `\S`). Each cue keeps its source start/end, so
  timings are preserved per cue (acceptance criterion), and its speaker.
- Storage: `CaptionStyle.translation` (language + cues, source seconds) in
  the clip's caption-style JSON, no migration (like TASK-90 marks). It is a
  clip-only field: excluded from `CaptionTemplate.styled`, from the
  frontend template-field set (`CLIP_FIELDS`) and kept by `resetStyle`.
- Rendering: `polish.rendered_words` returns the translated words when a
  translation is set: each cue's text is split on whitespace and its span is
  shared by character length (a language without spaces shows a cue as one
  piece); cuts are applied as for source words. Captions, SRT export and the
  title/description text (`clip_text`) all use those words. Word marks and
  per-word emphasis do not apply to translated words (they key on source
  words); speaker colors still do. Trimming/extending the clip or editing
  the transcript after translating keeps the old cues (words outside the
  clip are dropped): translate again.
- API: `POST /api/clips/{id}/caption-translation` `{language,
  source_language?}` -> Clip (502 `llm_error`, 409 no transcript), `DELETE`
  clears it. Not in `/api/v1` (UI-only for now); the Captions panel (TASK-96)
  gets the language picker.

## TASK-93 (T33e) Brand vocabulary

- Verified 2026-11-01 in the installed faster-whisper 1.2.1
  (`inspect.signature(WhisperModel.transcribe)`, `transcribe.py` source):
  `hotwords: Optional[str]` and `initial_prompt: Optional[str|Iterable[int]]`
  exist. `initial_prompt` is only the prompt of the FIRST window; `hotwords`
  is put into the prompt of every window (`get_prompt`: `sot_prev` + hotwords
  tokens, cut at `max_length // 2 - 1` = 223 tokens; "no effect if prefix is
  set", ClipForge sets no prefix). Decision: terms go to `hotwords` only
  (`vocabulary.hotwords_text`: ", "-joined, whole terms up to 600 characters,
  about 150 tokens), because chunks and later windows would lose an initial
  prompt. A test checks the signature and a slow test runs the real model.
- Storage: one global vocabulary in `{data_dir}/vocabulary.json` (no DB
  migration, like fonts in `{data_dir}/fonts`), the model is
  `models.Vocabulary` (`terms`, `corrections` {heard: correct}, each at most
  100 entries of at most 100 characters; terms unique and corrections unique
  case-insensitively). Simplest option; a per-brand-template vocabulary can
  follow with the brand kit (T44).
- Corrections run in `transcribe.run` after the transcript is built (also
  for uploaded SRT/VTT): `pipeline/transcript_correct.py` works on the
  whitespace pieces of a segment (`enrich.piece_words`), matches whole words
  by `caption_lines.word_key` (any case, punctuation around the match kept),
  the longest phrase first, only inside one segment. A corrected piece
  becomes one word per replacement word over the replaced words' time, the
  segment text is rebuilt so words still spell the text. Needs a new
  transcribe run to apply (existing projects use replace-everywhere).
- Replace everywhere (`vocabulary.replace_everywhere`, `POST
  /api/projects/{id}/replace-everywhere`): the same whole-word logic on the
  latest process job's transcript.json and on every clip of the project (all
  result sets): title, hook_text, description, reason, emphasis_words,
  hashtags (match with the spaces removed) and caption_overrides (only when
  the searched text is one word). Not changed: translated caption cues,
  post copy of queued posts, text overlays. A re-render shows the change.

## STEERING 2026-11-01: ingest H.264 preference, hardware transcode, progress

- Problem (owner): a 2 h YouTube live VOD came as AV1 + Opus; ingest
  re-encoded it with libx264 crf 18 for 30+ min while the job sat at
  "Download 60%".
- yt-dlp: `format_sort = ["vcodec:h264", "res", "acodec:m4a"]` (the Python
  form of `-S`; documented in `YoutubeDL.__doc__` of 2026.10.26). The format
  selector keeps the 1080p cap. Checked on canned formats with the installed
  yt-dlp (tests/pipeline/test_ingest_formats.py): without a sort it picks
  AV1 + Opus; with it H.264 1080p + AAC, H.264 720p over AV1 1080p (codec
  ranks above resolution, as the owner asked), VP9/AV1 + AAC only when no
  H.264 exists. A codec limit ranks the codec, then worse ones, then better
  ones (`FormatSorter._calculate_field_preference_from_value`).
- Transcode (`pipeline/transcode.py`, moved out of ingest.py): video is
  encoded with `Settings.video_encoder` (the render setting:
  h264_videotoolbox when ffmpeg has it, -q:v 75 = `video_quality(18)`),
  libx264 crf 18 preset medium as before when that is libx264 or when the
  hardware encode fails (FFmpegError, logged as a warning, progress starts
  again). Audio-only conversions stay as they were (video copied).
- Progress: `ffmpeg_progress.run_ffmpeg_progress` reads `-progress pipe:1`
  (`out_time_us` vs the probed source duration; stderr to a temp file so a
  full pipe cannot block ffmpeg; ffmpeg is killed if the callback raises).
  Logged as "Converting video to H.264: N%" once per whole percent.
- Sub-step without a DB migration: the ingest step's progress has fixed
  bands (download 0-0.5, conversion 0.51-0.9 starting with exactly
  CONVERT_START = 0.51, audio 0.95, thumbnail 0.98). The frontend
  (`processingSteps.subStep`, `INGEST_CONVERT_BAND`) shows "Converting
  video N%" under Download while an ingest event is in that band. An
  unchanged download never reports the band. Alternative rejected for now:
  a `job.detail` column (migration + model + types for one label); worth it
  once more steps need sub-steps.

## TASK-197 Apple Silicon GPU transcription: MLX Whisper backend

- Problem (owner: "use my Mac hardware"): faster-whisper (CTranslate2)
  transcribes on the CPU only on macOS.
- Verified (Apple M4 Max, 48 GiB, macOS 27.0.1, Python 3.11.x arm64):
  `uv add mlx-whisper` installs 14 packages without errors (mlx-whisper
  0.4.3, mlx and mlx-metal 0.32.4, torch 2.15.0, tiktoken, numba already
  there). Source read in `.venv/.../mlx_whisper/transcribe.py`:
  `transcribe(audio, *, path_or_hf_repo, word_timestamps=True, language=None,
  initial_prompt=None, hallucination_silence_threshold=None, ...)` takes a
  path or a float32 array and returns `{"text", "segments", "language"}`;
  each segment has `words: [{word, start, end, probability}]`. Word
  timestamps exist, so no BLOCKED.
- Licenses: mlx-whisper 0.4.3 is MIT (package METADATA); the weights
  `mlx-community/whisper-<size>-mlx` are OpenAI's Whisper (MIT) converted to
  MLX; the repo cards have no license field (SPEC 0.1: noted, not a blocker).
- Setting `transcribe_backend: auto | faster_whisper | mlx` (default auto).
  `pipeline/transcribe_mlx.choose_backend`: auto = MLX on Apple Silicon when
  `mlx_whisper` is importable (`find_spec`, nothing is loaded) and the MLX
  model is in `models/whisper-mlx/<whisper_model>`, else faster-whisper
  (silent off a Mac, a logged warning on a Mac when something is missing).
  `mlx` asks for it: it falls back with a warning when the machine or the
  package cannot run it, and a missing model is a StepError that says
  how to download it. `Settings` GET shows `transcribe_backend` and
  `transcribe_backend_active`; the Settings page shows "Running on: Apple GPU
  (MLX)" or "CPU (faster-whisper)".
- MLX model = the same whisper_model name mapped to the mlx-community repo
  (`whisper-<name>-mlx`, `large-v3-turbo` -> `whisper-large-v3-turbo`).
  Faster-whisper repo ids (Systran/...) and distil models have no MLX
  version: they stay on faster-whisper. `scripts/download_models.py` also
  downloads the MLX model on an Apple Silicon Mac with mlx-whisper.
- Output is normalised to the same `TimedWord` list, so chunking, overlap
  dedupe (`merge_chunks`) and `Transcript` are shared. `read_wav` gives
  mlx_whisper float samples (it would otherwise run `ffmpeg` from PATH).
  Hotwords become `initial_prompt`. No voice activity filter in MLX:
  `hallucination_silence_threshold=2.0` drops words made up over a 2 s
  silence. Progress is reported once per chunk (MLX has no segment callback).
- Found while testing on 10 min of speech: Whisper's alignment can give a run
  of words one time (34 of 1827 words at 30.72 s). They are spread over the
  time up to the next word instead of dropped (`_spread_collapsed`), so the
  text is complete and times keep rising.
- Dependency: `mlx-whisper` is a normal dependency with the marker
  `sys_platform == 'darwin' and platform_machine == 'arm64'`, so other
  machines do not install it. It pulls torch (~0.5 GB), which was absent
  before; the alternative, an optional extra, would not be installed by the
  plain `uv sync` that `make setup` runs and so never active.
- Benchmark (Apple M4 Max, model small, whole audio as one chunk, wall time
  of `transcribe._transcribe_chunk`, first call includes MLX start-up and
  second is warm):

| Input | faster-whisper (CPU, int8) | MLX (Apple GPU) |
| --- | --- | --- |
| backend/tests/fixtures/sample.mp4 (60 s, synthetic tones) | 14.7 s / 13.5 s | 4.1 s / 0.6 s |
| 607 s of speech (macOS `say`, 1827 words; no real recording in the repo) | 75.0 s / 78.4 s | 9.4 s / 8.7 s |

  MLX is about 8-9x faster on speech (65x real time), with the same words
  (1827 of 1827 spoken). On the tone fixture both only make up a few words
  (faster-whisper "mhm" x9 after its VAD, MLX "Hmm." x2): the fixture has no
  real speech, so it is a timing check only.
- Open: speaker is still S0 (no diarization); MLX has no per-segment
  progress; MLX output was checked against `say` speech only, not a real
  recording with music or crosstalk.

## TASK-198 Auto zoom-out moments (square_blur / fit)

- Scope: zoom-outs replace stretches of AUTO-mode FILL scenes only (default
  layout auto or dynamic, clips without manual scenes). Split/grid/pip and
  explicit default layouts are kept; manual scenes are never overwritten.
- Reasons per sample (10/s): two+ faces spread wider than the fill window;
  largest face under 12 % of the frame height; nobody seen and >= 50 % of
  the columns moving (64x36 grey frames at 4 fps, column mean abs diff >=
  0.04); nobody seen for > 1 s in a shot that shows someone elsewhere. No
  OCR rule: there is no OCR in the codebase.
- Layout: fit when at least half the wishing samples need the whole frame
  (motion, or faces spread wider than the frame's square), else square_blur.
  The square is min(W,H) of the source centered on the faces' midpoint,
  placed with its bottom at 0.66 H (top 186 px for 1080x1920) so lower-third
  captions stay over the blur.
- Smoothing: 1 s windowed share, enter 0.7 / exit 0.3, runs snapped back to
  the wishing samples, min 2.5 s (shorter runs join the longer neighbour),
  then a hard cap of 40 % of the clip (strongest, then longest first; a
  zoom-out that does not fit the remaining budget is skipped, not cut).
- Intensity f (subtle 0.5, balanced 1, frequent 1.5): max share x f, wide
  face height x f, lost time / f, still share of columns x f. Default
  balanced, per project and in presets (`zoom_out_moments`).
- Transition: 0.3 s smoothstep zoom from the fill window to the zoomed-out
  frame (and back), none at a scene cut (hard cut there).

## TASK-94 Auto censor (default + custom list, per word, beep or mute)

- APIs verified 2026-11-01 with the installed ffmpeg 9.0.2 (ffmpeg-full):
  `ffmpeg -h filter=aeval` (options `exprs`, `c`/`channel_layout`; "supports
  timeline through the 'enable' option"), `ffmpeg -h filter=volume`
  (`volume`, timeline `enable`), `ffmpeg -h filter=astats`
  (`measure_perchannel`, `measure_overall`, RMS_level). Docs:
  https://ffmpeg.org/ffmpeg-filters.html#aeval,
  https://ffmpeg.org/ffmpeg-filters.html#volume (checked 2026-11-01).
- Beep = `aeval=exprs=0.3*sin(2*PI*1000*t):c=same:enable='between(..)+..'`:
  replaces every channel with a 1 kHz sine only inside the windows (one
  filter, no extra source/amix). Mute = `volume=volume=0:enable='...'`.
- Windows: each censored word ±50 ms (Whisper word times are approximate),
  merged, in output time: computed from the transcript words retimed by the
  clip's cuts (`polish.spoken_words`), so the filter runs after the cut
  graph and before loudnorm (both loudnorm passes see the censored sound).
- Default list: written from scratch for ClipForge (no third-party list),
  English only (`assets/wordlists/censor_en.txt`); a `censor_<code>.txt`
  for the captions' language adds to it. Mild words (crap, damn) are not on
  it. Entries are single words; `word*` is a prefix. Multi-word phrases are
  not supported (simplest option).
- Custom list is global (`{data_dir}/censor_words.json`, like the
  vocabulary), not per clip; censoring is per clip (`caption_style.censor`,
  None = off) so it can differ between clips; default off for new clips.
- Per-word: `CaptionMark.censor` True/False overrides the lists; True works
  without `caption_style.censor` (beep). Masking keeps the first letter and
  punctuation ("Shit," -> "S***,"); it applies to rendered captions, SRT
  and the clip words the LLM reads (all from `polish.rendered_words`).
  Translated captions are masked by the lists of their language; their
  sound censor still comes from the transcript's words.
- A broken custom list file is a StepError (render/preview fails with the
  path) rather than silently rendering uncensored words.

## TASK-95 Transcript and subtitle downloads (T33g)

- Specs checked 2026-11-01: WebVTT, https://www.w3.org/TR/webvtt1/ (file
  starts with "WEBVTT" and a blank line; timestamps `HH:MM:SS.mmm`; cue text
  may not hold `&`, `<` or `>` unescaped, so they become `&amp;` `&lt;`
  `&gt;`); SubRip as in `pipeline/export.srt_time`. No third-party library.
- Two routes with the format in the path (`transcript.txt|srt|vtt`) rather
  than a `?format=` query: they download as plain links. An unknown format is
  a 422. The existing `GET /clips/{id}/srt` (the render's file) stays.
- Source files have a cue for each Whisper segment (no re-wrapping); clip
  files reuse the caption lines of the burnt-in captions (`caption_cues`),
  so they match the video, including masked censored words. Clip files do
  not need a rendered video. Source files are not censored (the raw
  transcript).
- txt: one line for each cue, no timestamps and no speaker labels (simplest
  option).

## TASK-97 Multi-track timeline backend (T34a)

- Verified 2026-11-01 against the installed ffmpeg 9.0.2 (`ffmpeg -h
  filter=<name>`; docs https://ffmpeg.org/ffmpeg-filters.html): `overlay`
  (x, y, eof_action, timeline `enable`), `drawtext` (fontfile, text,
  expansion, fontsize, fontcolor, box, boxcolor, boxborderw, x, y, `enable`),
  `amix` (inputs, duration=first, normalize), `adelay` (delays, all),
  `colorchannelmixer` (aa), `scale` force_original_aspect_ratio. A hand-run
  graph showed the overlay passes the main frames before the shifted asset's
  first frame and after it ends (eof_action=pass), and `filter_value`
  escaping keeps `: ' , [ ] ; %` in drawtext text (with expansion=none).
- Item kinds: `source` (video track only), `video`/`image` (broll,
  overlays), `text` (text), `audio` (music, sfx, voiceover). Image items take
  `image` or `logo` assets; audio items `audio`, `music` or `sfx` assets.
- Times of the non-video tracks are seconds of the rendered clip (after its
  cuts), 0..clip length; the video track stays in source seconds. Simplest
  for overlays that must line up with what the viewer sees. When later cuts
  shorten the clip, render clamps items to the new end and drops items that
  start after it (logged), rather than blocking the cut edit.
- Props are one strict model per track (`BrollProps`, `OverlayProps`,
  `TextProps`, `AudioProps`, extra keys refused) and stored with defaults
  filled in. B-roll always covers the full frame and is muted; overlays are
  `width` of the frame wide at center (x, y) with opacity; text is drawtext
  with a bundled/uploaded font (default Montserrat ExtraBold).
- Layer order: B-roll, overlays, text (later items of a track on top), all
  under the burned-in captions so captions stay readable. Sound layers are
  mixed after the censor and loudnorm of the clip's own audio (amix
  normalize=0, length of the clip), so their volume is what the user set;
  loudnorm measures the clip's speech only.
- `PUT /clips/{id}/tracks` replaces the timeline; its video track must equal
  the clip's (or be empty: kept), since segments are edited with
  `PATCH /clips/{id}` (and section ops later). `PATCH /clips/{id}/tracks`
  replaces only the tracks it sets. "Asset exists" means a library row of a
  matching kind whose file is on disk. Items whose asset was deleted after
  saving are left out of the render with a warning (not a failed render).
- Previews include the layers; the preview key hashes the tracks and the
  layer files.


## TASK-98 Clip version history: undo/redo, autosave, restore (T34b)

- Verified 2026-11-01 in the installed SQLAlchemy 2.1.6 source
  (`sqlalchemy/orm/session.py` `Session.flush`/`_flush`, `orm/events.py`
  `SessionEvents.before_flush`; docs
  https://docs.sqlalchemy.org/en/21/orm/session_events.html): `before_flush`
  runs with `_flushing` set (queries in it do not autoflush), objects added
  or deleted in it are part of the same flush, and listening on the
  `sqlalchemy.orm.Session` class covers sqlmodel's `Session` subclass.
  `AttributeState.history.has_changes()` tells which columns were set.
- "Every edit stores a version" is done with one `before_flush` hook
  (installed by `db.create_db_engine`) rather than calls in each endpoint:
  clips are edited from many places (PATCH, tracks, keyframes, caption
  translation, vocabulary replace, regenerate text, zoom-out re-planning),
  and a hook cannot be forgotten by later section ops. It fires only when a
  `ClipState` field changes; status/render/score writes store nothing, nor
  does writing the same values.
- `ClipState` = the clip's edit fields (segments, tracks, text, layout,
  captions, cuts, framing, zooms, scenes, color, show_captions); not
  status, output_path, scores, reason or result_set. Restore and undo set
  the state exactly, without re-validating it (assets deleted since are
  skipped by the render as before); the rendered video is not changed.
- History is linear: undo/redo move a `current` flag; an edit after an
  undo drops the undone versions. Restore copies an old version's state as
  a new `restore` version (with `restored_from`), so it can be undone.
  Version numbers grow per clip and are never reused.
- No v1 data migration: a clip's history starts at its next edit, which
  first stores the clip as stored (`original`). Processing steps that edit
  a stored clip (layout planning) also make versions; harmless and
  undoable.
- Autosave is the editor saving each change through the API (TASK-100);
  each save is a version. Retention: the latest `clip_versions_kept`
  (default 100, minimum 2) versions per clip; older ones are deleted.

## TASK-99 Timeline editor UI: tracks, playhead, zoom, snap (T34c)

- The six layer tracks are rows in the existing editor timeline (source
  time view, zoom, playhead, ruler) instead of a second timeline: Text,
  Overlays, B-roll above the video row (drawn over it in the render),
  Voiceover, Music, SFX below the audio row. Track names sit in a fixed
  gutter (`TrackLabels`) left of the scroller, so they never cover items
  or the playhead; its row heights share class constants with the rows.
- Layer item times are clip output seconds (TASK-97); the view maps them
  to source seconds with `sourceToPreview`/`previewToSource`, so items
  move with cuts. Drags and snapping work in clip time.
- Snapping (`lib/snap.ts`) is one routine used by segment handles and
  layer items: targets = word edges, segment/cut part edges, the playhead
  and the other items' edges; tolerance 8 px in the current zoom; a moved
  item snaps by whichever edge is nearer to a target. The toggle turns all
  of it off.
- Item ends are kept inside `safeLength` = clip length minus a frame per
  cut, because the server's length is frame-rounded per kept part and
  rejects items past it (422).
- Layer edits live in the editor's undoable edit state (one history entry
  per drag gesture) and are saved with "Save changes" through
  `PATCH /api/clips/{id}/tracks` after the clip PATCH (ClipPatch has no
  tracks).
- No new third-party APIs: only the browser Pointer Events API already
  used by `useDrag` (`setPointerCapture`, MDN
  https://developer.mozilla.org/en-US/docs/Web/API/Element/setPointerCapture,
  checked 2026-11-01) and existing React/Tailwind code.

## TASK-100 Keyboard precise editing + undo/redo + autosave in UI (T34d)

- Undo/redo routing (`hooks/useUndo.ts`): unsaved edits undo locally (the
  editor's `lib/history.ts` reducer); once the edits equal the saved clip,
  undo/redo call the server history (`POST /api/clips/{id}/undo`, `/redo`)
  and the editor's local history starts over from the answered clip. Redo
  prefers a local redo. This keeps one linear history with autosave: every
  autosave is a server version, so cmd+Z after a save steps to the version
  before it instead of re-saving an undone state as a new version.
- Autosave (`hooks/useAutosave.ts`): debounce 2000 ms after the last
  change; skipped while texts are invalid, a save/render/history move runs;
  a failed save is not retried until the edits change (no error loops). On
  by default; the top bar toggle stores `clipforge.autosave` = on/off in
  localStorage. Splits stay editor-only (not saved), as before.
- Restore is a server `POST .../versions/{n}/restore` (a new version, so
  cmd+Z goes back); it is disabled while edits are unsaved, so they are
  never dropped silently.
- Layer item selection: pressing/focusing an item selects it (one of
  segment / item / words at a time). Delete removes it; cmd+C / cmd+V copy
  it and paste a copy at the playhead on the same track with id
  `<id>-copy[-n]` (video ids are `video-N`, so they never collide; the
  server requires unique ids across the timeline). Copy/paste of transcript
  text is left to the browser when no item is selected or copied.
- Playback speed: < / > step through 0.25×–2× (`lib/playbackRate.ts`),
  plus a menu in the timeline control row.
- e2e specs that check explicit "Save changes" turn autosave off with
  `e2e/autosave.ts` (`addInitScript` sets the localStorage key);
  `e2e/timeline-keys.spec.ts` covers autosave.
- Third-party APIs checked 2026-11-01:
  - `HTMLMediaElement.playbackRate` / `defaultPlaybackRate`: the media load
    algorithm resets `playbackRate` to `defaultPlaybackRate` when a new
    source loads, so both are set
    (https://html.spec.whatwg.org/multipage/media.html#loading-the-media-resource,
    https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/defaultPlaybackRate).
  - `KeyboardEvent.key` gives the produced character ("<", ">" with shift)
    (https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key).
  - `structuredClone` for copying item props
    (https://developer.mozilla.org/en-US/docs/Web/API/Window/structuredClone).
  - Playwright `keyboard.press("ControlOrMeta+z")`
    (https://playwright.dev/docs/api/class-keyboard#keyboard-press) and
    `page.addInitScript` (https://playwright.dev/docs/api/class-page#page-add-init-script).

## TASK-108 Viral hook templates (T37a)

- A clip's hook is `Clip.hook: ClipHook | None` (template, text, duration
  2-3 s; migration 025, a JSON column at the end of `clip`), not timeline
  items: the hook is one unit the user applies, edits or removes, and the
  render expands it into its template's parts. So the hook's text layers do
  not count against the 5 user text layers, and an old clip (hook None)
  renders exactly as before.
- Templates are YAML files in `backend/clipforge/hooks_templates/` (like
  caption templates): label, description, duration, uppercase, wrapping
  (max chars per line, max lines), 1-3 `TextProps` layers with a `{text}`
  slot (existing text-overlay animations), an optional punch-in (scale,
  attack, release) and a whoosh from `assets/sfx`. Six original ones:
  slam_pop, boxed_drop, side_swipe, slow_push, echo_stack, neon_rise.
- The punch-in is applied in rendered-clip time right after the cuts
  (`render_graph.clip_graph(punch=)`, scale with `eval=frame` + centred
  crop), not as source-time zoom keyframes: the hook must cover the start of
  the render whatever sections/cuts the clip has.
- Text sources: `captions` takes the opening words up to the first
  sentence end (max 8 words, 60 chars); `theme` asks the LLM
  (`prompts/hook_theme.md`, JSON `{text}`, retried with errors like the
  other prompts); `text` is given. Dedicated endpoints (POST/PATCH/DELETE
  `/clips/{id}/hook`) because `ClipPatch` treats null as "unchanged" and
  could not remove a hook. Versions come from the clip version hook, so
  undo works with no extra code.
- While a clip has a hook, the v1 `hook_text` ASS line is not drawn (it
  would overlap the hook's text).
- The whooshes are synthesized from seeded noise by ClipForge itself and
  dedicated CC0 (commands in `assets/sfx/LICENSES.md`), so there is no
  third-party license to track.
- ffmpeg facts checked on 2026-11-02 against the installed ffmpeg 9.0.2
  (`ffmpeg -h filter=drawtext`, `ffmpeg -h filter=anoisesrc`) and
  https://ffmpeg.org/ffmpeg-filters.html#drawtext-1 :
  - drawtext `text_align` takes flags (`C` centres each line horizontally)
    and `line_spacing` sets extra pixels between lines;
  - a newline escaped with `filter_value` is drawn as a backslash; each line
    is escaped on its own and the lines are joined with a raw `\n`, which
    drawtext breaks on (verified by rendering);
  - `anoisesrc` has `color` (white/pink/brown/...), `amplitude`, `duration`
    and `seed`.

## TASK-109 T37b Auto headline + motion graphics (2026-11-02)

- Both are ordinary text-track items (`TextProps`), so the editor, the
  5-item limit (`MAX_TEXT_LAYERS`), versions/undo and the render need no new
  code paths. Ids: `headline` and `mg-<n>` (in time order), which is how
  regenerating finds and replaces them.
- Motion graphics are made on demand (`POST /clips/{id}/motion-graphics`),
  not as a processing step: an LLM call per clip at processing time would
  slow every project for a feature not every clip wants.
- The LLM quotes the words each graphic goes with; the quote is matched
  against the rendered clip's words (casefolded alphanumeric tokens), so
  times are word-snapped in output time (`caption_lines.rendered_words`).
  A quote that is not said is sent back as an error (retries like the other
  prompts); after the last try unsaid picks are dropped. A graphic shows
  from its first word for 2-3.5 s; same-template graphics may not overlap.
- Two original templates: lower-third (names, key phrases: white text on a
  brand-color box, slide right) and callout (numbers, dates: big brand-color
  text with a dark stroke, pop). Brand style = the project's brand template
  font (falls back to Inter Bold if the font is gone) and primary color;
  ClipForge defaults (Inter Bold, #FF6B35) without one.
- The auto headline at processing becomes a headline item only when the
  project has a brand template; otherwise the v1 ASS hook line is kept, so
  v1 renders are unchanged. While a headline item exists the captions do
  not draw `hook_text` (no double headline). `POST /clips/{id}/headline`
  sets both `hook_text` and the item; regenerating keeps an edited item's
  props and times and changes only its text. Editing `hook_text` via
  `PATCH /clips` does not change the item.
- `hook_theme.ask_line` is now the shared "one short LLM line" helper (hook
  theme and headline). `text_overlay.wrap_lines`/`fit_scale` are shared by
  hooks, headlines and motion graphics.
- No new third-party API: reuses ffmpeg drawtext as verified for TASK-105/108
  (ffmpeg 9.0.2, `text_align=C`, per-frame `alpha`/`fontsize`), checked
  again by real renders in `tests/pipeline/test_motion_graphics.py` on
  2026-11-02.

## 2026-11-02 — TASK-110 T37c Hooks/headline/motion graphics UI

- Two rail panels: "Hooks" (the hook plus the Headline group) and "Graphics"
  (motion graphics). The hook/headline/find/remove calls act on the saved
  clip server-side, so like the Sections panel they wait for unsaved edits
  and swap the editor onto the clip they answer (`edits.reset`). Editing or
  deleting a motion graphic changes the text track in the editor's edit
  history (saved with the other edits), since graphics are plain text items.
- The hook's template and length change at once (PATCH); its text is saved
  with "Save text". The slider commits on release/key (Radix
  `onValueCommit`, verified by the unit test on 2026-11-02, radix-ui as
  installed in `frontend/node_modules`); no new endpoint or library.
- Test mode's `RecordedLLM` answers every prompt with the clip list, so the
  e2e covers the non-LLM paths (captions hook, typed headline); the AI
  buttons and graphics are covered by unit tests with mocked responses.


## 2026-11-02 — TASK-111 T38a Speech cleanup

- Filler lists are YAML files per language in `clipforge/fillers/`
  (en, es, fr, de, it, pt, nl, ru, pl, tr, fa, ar), written from general
  linguistic knowledge (no third-party API or word list). `always` words are
  fillers anywhere; `alone` words (English "like", Spanish "este", ...) only
  between pauses or punctuation, as v1 did for "like". Every entry is quoted
  (YAML 1.1 reads a bare `no` as false). Drawn-out fillers match their entry
  (`filler_key` squeezes 3+ repeated letters to 2: "ummm" -> "umm").
  Languages without spaces between words (zh, ja, ko, th) have no list.
- The list is the transcript's language unless the request picks one; a
  language without a list falls back to English (the v1 behaviour). German
  leaves out "um" (a German word). English gains umm, uhh, uhm and a
  standalone "hmm"; new clips with `remove_fillers` use the transcript's
  language list, so English projects cut the same plus those variants.
- Pause threshold: 0.3-10 s (default 0.6 s = v1 `PAUSE_MS`); a cut pause
  still keeps `MARGIN_MS` (150 ms) of silence on each side, and laughs keep
  their gaps.
- Bad takes: the LLM sees the clip's words numbered in play order with
  `---` between sections (words already cut are left out) and answers
  `{"takes": [{"first", "last"}]}` (at most 20). A take is cut from its
  first word's start to the next kept word's start (or its last word's end
  at a section end). Invalid replies are sent back with their errors
  (`- takes.<i>: ...`) up to 3 tries; after the last try only usable takes
  of the last valid reply are kept; no valid reply is 502 `llm_error`.
- Preview and apply act on the saved clip (like section ops): preview never
  changes it; apply takes the preview's items plus the indexes the user
  unchecked, merges the checked ones with the clip's cuts (touching ranges
  merge, as in the editor) and saves through `apply_patch`, so a version is
  recorded and undo takes it back. Items already fully cut are left out of
  a new preview. A bad take's `text` is its words (no extra field, so the
  v1 `CleanupSuggestion` shape the editor reads is unchanged).
- `fit_cuts` moved from `clip_edit.py` to `pipeline/sections.py`, since
  `pipeline/*` must not import `clipforge.db`.

## 2026-11-02 — TASK-112 T38b Speech enhancement: ffmpeg fallback

- Verified in the installed ffmpeg 9.0.2 (`ffmpeg -h filter=afftdn`,
  `-h filter=arnndn`, `-h filter=highpass`, 2026-11-02): `afftdn` options
  `nr` (0.01-97 dB), `nf` (-80..-20), `rf` (-80..-20), `tn`; `arnndn`
  options `m` (model file), `mix` (-1..1; no bundled model); `highpass=f`.
  ffmpeg ships no `.rnnn` model.
- RNNoise model: `beguiling-drafter-2018-08-30/bd.rnnn` (Recording noise,
  voice signal) from https://github.com/GregorR/rnnoise-models at commit
  3eee541a283fd3b8f81b85b1748e3b9ccbefa04d (README, 2026-11-02: the models
  are not creative work, "none of it is subject to copyright"); pinned by
  sha256 ae3f7411...a98a17b, 299,693 bytes, downloaded by
  `scripts/download_models.py` to `models/rnnoise` (`enhance_model.py`).
  Without the file only afftdn runs.
- Strength is a 0-1 float (0 = off, no filter). `nr` = 6 + 24 * strength dB;
  `rf` = `nf` - 20 * strength; `arnndn mix` = strength; a 80 Hz highpass
  always goes first.
- `afftdn` needs `nf` near the real noise: measured with white noise at
  -35, -38 and -53 dBFS RMS, it removes the noise fully when `nf` is at
  least about 3 dB above the noise RMS and not at all when it is under it.
  So `nf` = the recording's quietest 50 ms (astats `RMS_trough`) + 6 dB,
  limited to -80..-20. `tn=1` (noise tracking) removed nothing on steady
  noise, so it is not used.
- Not wired into the render or the editor yet; `enhance_audio(src, dst,
  strength)` is the entry point for the engine/API tasks that follow.

## 2026-11-02 — TASK-113 T38c DeepFilterNet engine

- Verified 2026-11-02: pip `deepfilternet` 0.5.6 (latest, PyPI) requires
  `numpy (>=1.22,<2.0)`, `packaging (<24)` (its METADATA) and its
  `df/io.py` does `from torchaudio.backend.common import AudioMetaData`; in
  a scratch Python 3.11 venv with torch 2.15.0 / torchaudio 2.11.1 `import
  df` raises `ModuleNotFoundError: No module named 'torchaudio.backend'`.
  The project uses numpy 2.4.6, so the package cannot share `.venv`.
- Chosen instead (simplest working option): the official Rust program from
  https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6 (assets
  `deep-filter-0.5.6-aarch64-apple-darwin`, sha256 4601e7f4...4611081,
  27,877,081 bytes; `-x86_64-apple-darwin` d3be8400...b5b50f). The release
  lists no digests: the sha256 are of the downloads. It embeds the
  DeepFilterNet3 model. License: README "dual-licensed under either MIT or
  Apache 2.0" (2026-11-02).
- Flags from `deep-filter --help` (0.5.6): `-D/--compensate-delay`,
  `-a/--atten-lim-db` (0 = no reduction, 100 = no limit, default 100),
  `-o/--output-dir` (writes `<dir>/<input file name>`), `--pf`, `-m`.
  Without `-D` the output lags (SNR vs clean -2.8 dB instead of 22 dB).
  The model is 48 kHz: input is resampled to a 48 kHz 16-bit WAV first.
- Strength 0-1 -> `-a` = 6 + 94 * strength dB (0 = copy, no program run).
  Measured on the fixture's first 6 s + white noise a=0.03: SNR 6.3 dB
  noisy, 17.2 dB at `-a 12`, 22.0 dB at `-a 100`; 0.26 s for 6 s of sound.
- The engine is `DeepFilterNetEngine` (was a `ModuleEngine` for `df`):
  `DEEP_FILTER_BIN`, else `models/deepfilternet/deep-filter`, else PATH;
  installed when `--version` prints `deep_filter <v>`. A failing run raises
  (no silent fallback); `enhance_speech` uses ffmpeg only when the program
  is absent. The download is opt-in (`--deepfilternet`), not part of
  `make setup`, as the engine is optional.

## 2026-11-02 — TASK-114 T38d Cleanup + enhancement UI

- Enhancement had no clip field, endpoint or render step (TASK-112/113 left
  it unwired), so the UI needed them: `Clip.enhance` 0-1 (migration 026,
  default 0 = off), `PUT /clips/{id}/enhance {strength}` (a version
  "enhancement", none when unchanged), and at render the clip's span is
  enhanced to a temp WAV that replaces the main input's sound
  (`render_clip(voice=)`), so cuts, sounds, ducking and loudnorm all apply
  to the enhanced voice.
- The DeepFilterNet gate is informational: the slider always works because
  `enhance_speech` falls back to ffmpeg noise filters.
- The preview cache key ignores `enhance`: the preview has no enhanced sound;
  the panel says to render again to hear it.
- Cleanup is a rail panel (like Hooks); the v1 dialog stays. Operations act
  on the saved clip and wait for unsaved changes. No new third-party API.

## 2026-11-02 — TASK-115 T39a Music library + auto-duck

- Bundled music: no third-party track is downloaded. The four loops in
  `assets/music` are original compositions synthesized by
  `scripts/make_music.py` (numpy sines + seeded noise, bit-exact FLAC via
  ffmpeg), dedicated CC0 1.0 by the project, so no license or attribution
  can be wrong (SPEC-v2 1.2/1.3); `LICENSES.md` lists each with its title,
  moods and the rebuild command. 48 kHz mono FLAC, ~-22 LUFS, 3.5 MB total.
- Verified in the installed ffmpeg 9.0.2 (`ffmpeg -h filter=...`, checked
  2026-11-02; docs https://ffmpeg.org/ffmpeg-filters.html#sidechaincompress
  and #afade): `sidechaincompress` inputs main + sidechain, options
  `threshold` (0.000976563-1, default 0.125), `ratio` (1-20), `attack`
  (0.01-2000 ms), `release` (0.01-9000 ms), `detection` (default rms);
  `afade` `t=in|out`, `st`, `d`; `-stream_loop -1` as an input option loops
  the file and `-t` cuts it. A stereo key with a mono main works.
- Duck settings: threshold 0.01 (-40 dBFS), ratio 4, attack 20 ms, release
  400 ms. Measured on the fixture's speech (-28 dBFS RMS), each bundled loop
  at volume 0.5: during speech -38.0..-39.5 dB vs -26..-27.3 dB undocked;
  gaps -27.4..-31.7 dB (recovered). The first try (-30 dBFS, 10:1) dipped
  only ~5 dB since quiet speech barely crossed it.
- Ducking is the music item's own `duck` prop (default true: "auto-duck"),
  keyed by the clip's sound after its cuts, censor and loudnorm (not the
  layers), so sfx/voiceover do not duck it. Fades are in the item's time
  (before `adelay`), each at most the item's length.
- Music always loops (no prop): a loop shorter than the clip keeps going;
  an upload longer than the item is just cut by `-t`.
- Uploads: `POST /api/library` accepts kind `music` for audio files (MIME
  type now from what the file is, so a music upload is `audio/...`), and
  `GET /api/music` lists bundled loops then music uploads; generic audio
  uploads stay in the media library only.

## 2026-11-02 — TASK-117 T39c TTS voiceover (Kokoro/Piper)

- Sources checked 2026-11-02: kokoro-onnx README and 0.6.1 source
  (https://github.com/thewh1teagle/kokoro-onnx; `Kokoro(model, voices)`,
  `.create(text, voice=, speed=, lang=)` -> float32 samples at 24 kHz, speed
  0.5-2 else ValueError, voices file is an npz); model files from
  https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1
  (sha256 as GitHub lists them); Kokoro-82M license Apache-2.0
  (https://huggingface.co/api/models/hexgrad/Kokoro-82M cardData) and its
  language letters (VOICES.md: a en-us, b en-gb, e es, f fr-fr, h hi, i it,
  p pt-br through espeak-ng; j/z need misaki, so they are not listed).
  Piper: `piper --help` of piper-tts 1.8.0 (`-m`, `-c`, `-f`,
  `--length-scale`, `-s`, text on stdin; blank text crashes it); voice
  files from https://huggingface.co/rhasspy/piper-voices at commit
  b4e358ffcb232591bf73a540e70f7de528e4174a (repo license MIT); the voice
  config gives `language.code`, `dataset`, `audio.quality`, `num_speakers`,
  `speaker_id_map`.
- Both engines are optional and local: Kokoro in-process (kokoro-onnx is
  MIT but pulls in GPL phonemizer/espeak-ng, so it is not a project
  dependency: the owner installs it), Piper as a separate GPL program. The
  default Piper voice is ljspeech (public domain data); the others checked
  have unclear or restrictive licenses.
- A voiceover is an "audio" asset tagged `voiceover` (not a media library
  upload) whose license is the voice's and attribution names the voice;
  the WAV is cached in `data/voiceover/<sha256 of voice, speed, text>.wav`,
  so speaking the same line again costs nothing. The item keeps text,
  voice and speed in `VoiceoverProps`, so it can be spoken again.
- Ducking the clip's own sound under a voiceover is a per-frame `volume`
  expression over the voiceover windows (-12 dB, 0.15 s ramps), not
  sidechaincompress: the windows are known exactly and a compressor keyed
  by the voice would also react to its pauses. Measured with astats on the
  fixture's speech: -28.09 dBFS -> -40.13 dBFS inside, unchanged outside.
  Music still keys on the clip's sound before this duck.
- Existing voiceover items (media library recordings) now duck by default
  (`duck=True`), as music does since TASK-115.
- A voiceover longer than the time left in the clip is 422 (not cut): the
  owner moves it or shortens the text. Re-speaking a recording (no text)
  with only a new voice or speed is 422.
- TTS time is metered as compute seconds for the clip's project.

## 2026-11-02 — Dubbing dropped from v2 (owner decision)
- Decision: AI dubbing (T43a-e: dub translation script, TTS time-fit, Demucs separation + dub mix, voice profiles/voice clone, dubbing UI) and E2E flow 4 are out of scope. Specs moved to .agent/tasks/deferred/.
- Reason: owner does not need dubbing; translated captions (TASK-92) cover multi-language reach. AI voice-over (TTS narration) stays in plan.
- parity.md: "AI dubbing" -> not planned.

## 2026-11-02 — Team mode and mobile PWA dropped from v2 (owner decision)
- Decision: T56a LAN auth, T56b roles/workspaces/invites, T56c share links/activity log/team UI, and T57c responsive PWA are out of scope. Specs moved to .agent/tasks/deferred/.
- Reason: ClipForge stays a local single-user desktop-browser app for now; accounts/teams belong to a later cloud version. Notifications (T57a) and Settings v2 (T57b) stay.
- parity.md: team workspace, mobile app -> not planned.

## 2026-11-02 — v2 scope cut to finish tonight (owner decision)
- Dropped (specs in .agent/tasks/deferred/, parity "not planned"): AI image/video B-roll (T41a/b), AI upscaling/outpainting/eye contact + UI (T42a-d), FCPXML export (T45b), X and LinkedIn publishers (T48a/b), semantic search + auto-catalog (T51c/d), live-stream recorder + live clipping (T52a/b), AI thumbnail generator + UI (T53a/b), analytics + trends (T54a-c), earnings (T58c.1/2), feedback learning (T58e.2), brand kit v2 (T44a-c), voiceover UI (part of T39d), E2E flows 2 and 3.
- Kept: music + SFX UI, stock B-roll (Pexels/Pixabay), export v2, calendar + offline policy, collections + full-text search + library UI, notifications, settings v2, campaign submissions, autopilot drafts + approval inbox, E2E flows 1/autopilot/campaign, README, parity.
- Reason: owner wants v2 finished tonight; dropped items are optional, need unavailable platform approvals, or belong to the later cloud version.

## 2026-11-02 — Always-included hashtags (steering)
- Decision: `Settings.always_hashtags` (stored in `.env.local` as JSON, edited as chips in Settings -> Posting) and `social_account.always_hashtags` (migration 028, `PUT /accounts/{id}/hashtags`, chips in Social accounts) are added to every post text, next to the campaign's `required_hashtags`. `post_tags.required_hashtags(engine, project_id, account)` resolves the three lists (cleaned, no "#", deduplicated ignoring case); anything that writes post text calls it (AI post copy, Quick post, schedule modal, bulk scheduler; the autopilot drafts must call it too).
- They live in `PostText.hashtags`, which `post_payload` appends to the description (YouTube/Facebook), the caption (TikTok/Instagram) and the YouTube `tags`, so both fields get them. `required_tags.merge_tags` puts them first and keeps them even past a platform limit (Instagram 30, YouTube 500 chars): the AI's own tags give way, and the AI text is the part that is shortened. A "none" rewrite returns just the required tags (no LLM call).
- `build_payload` falls back to the required tags only when `PostText.hashtags is None`; an explicit list the owner sent (even `[]`) is respected, so they can delete them by hand in the post sheet.
- Limitation: the schedule modal / quick sheet fetch copy per platform before an account is picked, so they pass the platform's default account (else its first); account-specific tags of another account appear after "Rewrite with AI" or when the server builds the post from a missing hashtag list.

## 2026-11-02: TASK-121 B-roll review UI

- No third-party API is called by the UI: it uses the TASK-120 endpoints
  (`/broll/providers`, `/clips/{id}/broll/spots`, `/clips/{id}/broll[/{item}]`).
  Stock thumbnails are the providers' own `preview_url` images (`<img>`).
- Simplest option: a spot's result "Replace"s the B-roll item that overlaps the
  spot's time, else it inserts a new item over the spot; there is no separate
  "replace" picker. Spots are not saved (regenerate with "Find new spots").
- The e2e test mocks the broll providers/spots routes in the browser: test
  mode has no stock key and its recorded LLM cannot pick spots; unit tests
  cover accept/replace/remove against mocked API answers.

## 2026-11-02 — Project progress and ETA (steering)

- Decision: one overall progress 0-1 per job, stored on `job.overall_progress`/`job.eta_seconds` and mirrored to `project.overall_progress`/`eta_seconds` (migration 029, so `GET /projects`, `/projects/{id}/jobs` and the SSE events all carry them). `job_rows.record_progress` is the single write path (`set_step`, `save_progress`, render jobs).
- Weights: `config.step_weights` (ingest 10, transcribe 25, signals 5, visuals 3, enrich 1, curate 10, score 1, snap 1, reframe 10, render 34), measured shares. Overall = (weights of earlier steps + current weight x step progress) / total weight of the job kind's steps (process: all, reprompt: visuals..render, render: render only). Sub-progress comes from the steps (download bytes, convert, audio seconds, signal chunks, clips rendered / total).
- ETA (`job_progress.EtaEstimator`): none until 10 s of data; raw = remaining / rate (the step's own rate once it has 10 s of data, else the whole run's rate since the first report, so a resumed job does not count earlier work); smoothed `0.3 x raw + 0.7 x (previous - elapsed)`. State is in the worker's memory, persisted on the rows; cleared when a job is claimed, finishes or goes stale.
- `project.opened_at` + `POST /projects/{id}/open` (sent once by the project page when a done project is first shown) drive the "New" badge; the migration marks existing projects as opened.
- The frontend polls projects every 2 s (`POLL_MS`) instead of adding another SSE stream, so cards survive navigation; the processing view uses the SSE values.

## 2026-11-02 — Long-clip render argv, faster reframe, Captions-only clarity (steering)

- Bug: a 20 min "Captions only" clip failed with `[Errno 7] Argument list too long` (E2BIG): its crop x expression has one term per reframe keyframe (10 a second), and a clip framed scene by scene repeated the whole clip's keyframes in every scene part.
- Fix 1 (`clipforge/ffmpeg_args.py`, used by `run_ffmpeg` and `run_ffmpeg_progress`): every filter option (`-filter_complex`, `-lavfi`, `-vf`, `-af`, `-filter[:spec]`) whose value is over 4 KiB is written to a temp file and passed as `-/<option> <file>`. Verified 2026-11-02 with `ffmpeg -h full` / a run on ffmpeg 9.0.2 (ffmpeg docs, "Main options": a leading `/` loads the option value from a file, since ffmpeg 7.0): `-/filter_complex g.txt` works, `-filter_complex_script` is gone ("Unrecognized option"). Generic in the runners, so every caller is covered.
- Fix 2 (`layout_parts.plan_span`): each scene part's plan keeps only the keyframes around the part (the last at or before its start to the first at or after its end, plus `SQUARE_SMOOTHING` on each side so `square_centers` is unchanged); the crop expressions hold outside their keyframes, so frames render the same.
- Rejected: an `if(lt(t,...))` tree for O(log n) per-frame evaluation. The flat ramp sum costs ~15 s per 20 min at 30 fps with 6,000 keyframes (measured), small next to encoding, and changing the expression form would churn many tests.
- Reframe speed (`pipeline/frame_stream.py`, `pipeline/face_cache.py`, `pipeline/reframe_run.py`): frames are decoded by one ffmpeg run per clip, a reader thread keeping 30 frames ahead (decode overlaps detection instead of one ffmpeg + seek per 5 s slice); detections are kept per source frame index (`round(t * fps)`) in `faces_cache.json` in the job's work dir (ignored if fps or analysis size differ), so overlapping clips and re-reframes (other aspect/preset, forced) reuse them; progress is reported every 50 samples, weighted by clip seconds; each clip logs "in X s (Y s per minute of video)". Sampling stays at 10 fps inside each clip only (as before).
- Measured on the M4 Max, 20 min 1080p source (the fixture looped), one 20 min clip: before 125.4 s (6.3 s/min), after 82.4 s (4.1 s/min), cached re-reframe 1.4 s. Target (< 2 min) met. Detection (BlazeFace + mouth landmarks) is now ~95 % of the time.
- Captions only: the Home chip reads "Captions only (no clipping — whole video as one clip)"; in the settings panel, a clip (timeframe) longer than 3 min (`LONG_CAPTIONS_ONLY_S`) shows "This makes one mm:ss clip, not shorts. Are you sure?" with "Switch to AI clipping". A note, not a blocking dialog, so a deliberate captions-only long video stays one click.

## 2026-11-02 — AI agents & API settings page (steering)

- Page `/settings/agents` (Settings tab "AI agents & API"): API keys (create, key shown once with copy, revoke, last used; keys used within 7 days show as "Connected recently"), MCP setup per client, REST docs link (`/api/docs`), webhooks (add with the secret shown once, delete). A key just made is filled into the snippets until it is hidden; otherwise `cfk_YOUR_KEY`.
- `GET /api/agent-setup` (human only, on the api-keys router) gives the API address, this checkout's path and the MCP command (`uv run --project <dir> clipforge-mcp`), so snippets are copy-paste ready. `CLIPFORGE_URL` is added only when the app is not on the MCP server's default `http://127.0.0.1:8000`.
- Config formats verified 2026-11-02 (SPEC 0.1): Hermes from `hermes mcp add -h` and its source (`hermes_cli/mcp_config.py`: `--command`, `--env K=V`, `--args` last; `~/.hermes/config.yaml` `mcp_servers: {name: {command, args, env, enabled}}`; `hermes mcp test`), and a real `hermes mcp add` in a temp `HERMES_HOME` against the test app listed all 59 tools; Claude Code from `claude mcp add --help` (`--scope user -e K=V -- cmd args`); Claude Desktop `mcpServers` JSON; GitHub Copilot CLI `copilot mcp add NAME --env K=V -- cmd args` (docs.github.com, "Adding MCP servers for GitHub Copilot CLI"); VS Code `.vscode/mcp.json` `{"servers": {name: {"type": "stdio", command, args, env}}}` (code.visualstudio.com, "Use MCP servers in VS Code").
- Rejected: a "connected agents" registry. The MCP server is stdio and talks to the app over `/api/v1` with a key, so the key's `last_used_at` is the only honest signal (polled every 30 s).

## 2026-11-02 — TASK-136 (T45a): Export v2, up to source resolution incl. 4K + platform presets

- `clip_export.export_clip(engine, clip_id, work, resolution=, preset=)` renders a clip again, with the same inputs as a normal render (`clip_render.prepare_render`, shared with `clips.render_clip_row`), at `export_presets.export_size`: the design frame's (1080 short side) crop scaled up to the largest size the source's crop has pixels for, then capped by the resolution (`source`, `2160p`, `1440p`, `1080p`, `720p` = short side) and the preset's limits. Never above the source: no upscale (a 3840x2160 source exports 16:9 as 3840x2160, 9:16 as 1214x2158; a 1080p source asked for 2160p stays 1080p-sized). Captions, text and graphics are drawn in the design frame and scaled by libass/the filters; the 1080p and 4K caption extents were checked to be 1:2 (`test_captions_keep_their_share_of_the_frame_at_4k`).
- Exports go to `output/<project>/exports/<clip>-<preset|resolution>.mp4`, not touching the clip's status/output_path or `clips.zip`. No endpoint/UI yet (later tasks).
- Downloads from URLs are still limited to 1080p (`download.YTDLP_FORMAT`); local uploads keep their resolution, so 4K needs a 4K source.
- Presets validate and cap the frame but do not re-plan the crop for another aspect; a wrong ratio is a "problem" returned in `ExportedClip.problems` (the file is kept). Only default-account limits are modelled.
- Platform limits, read from the official docs on 2026-11-02 (GB/MB decimal):
  - `shorts`: 180 s, 256 GB; square or vertical (width <= height). https://support.google.com/youtube/answer/15424877 (Shorts up to 3 min); file size from https://support.google.com/youtube/answer/71673 (256 GB or 12 h).
  - `tiktok`: 600 s, 4 GB; 360-4096 px a side. https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide (every creator can post 3 min; 5 or 10 min for some, per the account's `max_video_post_duration_sec`; 600 s is the ceiling).
  - `reels`: 900 s, 300 MB; min 3 s, width <= 1920, ratio 0.01:1 to 10:1, 23-60 fps, 25 Mbps. https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media ("Reel Specifications").
  - `linkedin`: 1800 s, 500 MB; min 3 s, MP4. https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api. No aspect or resolution limit is documented there; the 4096x2304 figure of secondary sources is not used.
  - `x`: 1200 s, 8 GB for the default account (Premium: 125 min, 16 GB; DM video 140 s / 512 MB, the old well-known figure); long side <= 1280, short <= 720; ratio 1:3 to 3:1; min 0.5 s. https://docs.x.com/x-api/media/quickstart/best-practices

## 2026-11-02 — TASK-149 (T49d): Calendar UI + bulk scheduler dialog

- Built on the posts API of TASK-147 (`GET /posts`, `PATCH /posts/{id}`, `/queue`, `/cancel`, `/bulk-schedule`); no backend change. The calendar loads every post once and lays them out by local day (`lib/calendar.ts`): Sunday-first weeks (as the owner's reference), month = 5-6 weeks, a post's time is `scheduled_at`, else `attempted_at` (posted/failed). Posts without any time (unscheduled drafts) are not on the calendar; canceled posts are hidden unless the status filter asks for them.
- Drag and drop is the browser's HTML Drag and Drop API (`draggable`, `dragstart`/`dragover`/`drop`, `dataTransfer.effectAllowed = "move"`; MDN "HTML Drag and Drop API" and the HTML Living Standard "Drag and drop", read 2026-11-02), no library. Only `queued` ("Scheduled") cards are draggable; the dragged post is kept in React state because `dataTransfer.getData` is empty during `dragover`. A drop keeps the local time of day and changes only the date (`PATCH scheduled_at`); a moment not later than now is refused with a toast. The time itself is changed in the details sheet ("Publish at").
- Details sheet (`PostEditor`): edit text/reschedule/cancel only for draft and queued posts (the API answers 409 `post_locked` otherwise). Text edits send the full `PostText` but only the fields the user changed are replaced; untouched ones stay null so they keep following the clip (on TikTok/Instagram the caption shows title + caption joined, as the publisher builds it; editing it sets the post's own caption and an empty title).
- Bulk dialog: one project's clips (done projects only), every clip to every chosen account, text per platform shared by all its clips with blank fields meaning "each clip's own" (null in the API), queued as the human (`queue: true`). `bulkBody` now takes a list of clip ids.
- Platform badge icons are Phosphor `YoutubeLogoIcon`, `TiktokLogoIcon`, `InstagramLogoIcon`, `FacebookLogoIcon`, `XLogoIcon`, `LinkedinLogoIcon`, nav icon `CalendarDotsIcon` (checked in the installed `@phosphor-icons/react` 2.1.10, `dist/csr/*.d.ts`).
- Sidebar group "Publish" is renamed "Post" (Calendar, Social accounts), as SPEC-v2 3.10 / the reference.
- `settings/Field`'s `aside` no longer renders a bare `0` (an empty caption counter showed "0" unstyled).


## 2026-11-03 — TASK-151 (T50b): Missed-while-offline policy + posting history

- No third-party API is used (SPEC 0.1): only our own DB, the posting
  worker and FastAPI/SQLAlchemy calls already in use (`func.coalesce`,
  `Query(ge=, le=)`); TanStack Query `keepPreviousData` checked in the
  installed `@tanstack/query-core` (`placeholderData: keepPreviousData`).
- "Missed while offline" (ASSUMPTION, simplest without a heartbeat): at
  start, a queued post whose `scheduled_at` is more than
  `post_missed_grace_s` (600 s) before now, with `attempts == 0` and no
  `next_attempt_at`. A post a running worker already held back (rate
  limit, quota, retry backoff, not publishable yet) has `next_attempt_at`
  or attempts set, so it is not "missed"; the grace keeps a quick restart
  or a post that came due just before a crash from being skipped.
  "Publish now" posts have no `scheduled_at` and are never missed.
- `post_missed_policy` (`post_late` default, keeps TASK-150's behaviour |
  `skip`) is read at start from `config.settings`; editable in Settings →
  Posting (`.env.local`).
- Skipping is a new post status `skipped` (queued -> skipped -> queued |
  canceled), with `error` = `post_queue.SKIPPED`. No webhook event for it
  (`post.published`/`post.failed` only; no event name was asked for).
  "Post now" (`POST /posts/{id}/publish`) sends a skipped or failed post
  again; reschedule stays for draft/queued posts only.
- History = published, failed and skipped posts (not drafts, queued or
  canceled: they never went out), newest first by `coalesce(attempted_at,
  scheduled_at)`, `GET /posts/history?status=&account_id=&limit=&offset=`
  (limit 1-500, default 100). Route at `/post-history`, sidebar "Post
  history" in the Post group.


## 2026-11-03 — TASK-152 (T51a): Collections + collection zip export

- No third-party API is used (SPEC 0.1): only our own DB, FastAPI,
  SQLModel and `zipfile` through `pipeline.export.write_zip` (already used by
  the project zip). SQLite `ON DELETE CASCADE` works because every
  connection sets `PRAGMA foreign_keys=ON` (`db.py`).
- A collection is a named, ordered set of clips from any projects
  (`collection`, `collection_item`, migration 030); a clip is in it once
  (`UNIQUE (collection_id, clip_id)`), items keep the order they were added
  in (`position`, no gaps: removing one renumbers the rest). No manual
  reorder yet (ASSUMPTION: not asked for; re-add to move a clip to the end).
- "Add from gallery/results/search" is one endpoint taking clip ids
  (`POST /collections/{id}/items`): every source in the UI only has clips.
  An unknown id rejects the whole request with 404 (nothing is added).
- Zip (`collection_export`): the rendered clips in the collection's order,
  each with the SRT and metadata JSON that exist next to its video (they are
  not regenerated: a clip of another project may have no work directory any
  more), and `manifest.json` (`models.CollectionManifest`: clips and the
  clips left out with the reason). Written to
  `{data_dir}/output/collections/{id}/collection.zip`; 409 when no clip has a
  rendered video. File names are the clip ids, unique across projects.
- Public API/MCP: the router is in `PUBLIC_ROUTERS`; agents may use every
  collection operation (it only organises clips; publishing stays human).
  The MCP tool names come from the function names, so they are
  `*_collection*` (`download_zip` is taken by the project zip).


## 2026-11-03 — TASK-153 (T51b): Library full-text search (FTS5)

- Verified (SPEC 0.1): SQLite FTS5 docs, https://www.sqlite.org/fts5.html
  (read 2026-11-03: `CREATE VIRTUAL TABLE ... USING fts5(...)`, `MATCH`,
  `highlight()`, `rank`/bm25, `unicode61` tokenizer with `remove_diacritics`,
  `UNINDEXED` columns, string and prefix `"x"*` syntax). Checked against the
  bundled SQLite (3.53.1 in `.venv`, `ENABLE_FTS5` on): the migration creates
  the table, `fts5_available()` makes a temp FTS5 table (test
  `test_the_bundled_sqlite_has_fts5`), `highlight(search_fts, 0, a, b)`
  works in a join with `project`, `ORDER BY search_fts.rank` too.
- One FTS5 row per transcript segment (`search_fts`: text, then UNINDEXED
  project_id, segment_id, start, end), tokenizer `unicode61
  remove_diacritics 2` (case and accents ignored). `search_state` holds the
  transcript file's mtime and size per project. A virtual table has no
  foreign keys, so a trigger deletes a project's rows with the project.
  Embeddings (SPEC 4 "SearchIndex") come with the semantic search task.
- The user's text is never FTS5 syntax: every word is quoted (AND, OR, NOT,
  `-`, `:` are text), "quoted words" are a phrase, the last plain word is
  also a prefix (search as you type). A query with no word is 422.
- Index freshness: `index_project` runs when the transcribe step finishes
  (`process.run_step`) and after `vocabulary.replace_everywhere`; both only
  log a failure. Search first runs `sync_index`, which indexes any project
  whose transcript file is new or changed (mtime + size) and drops the rows
  of one whose file is gone, so edits by any other path are found too
  (ASSUMPTION: a stat per project per search is cheap enough for a local
  library). A transcript that cannot be read is skipped with a warning.
- A hit is a segment, so the exact moment is the start of its first
  matching word (`start`; the segment's start if no word matches, e.g. a
  subtitles upload with spread words still has them); `segment_start`
  and `end` give the sentence. Highlights are character spans of `text`,
  taken from `highlight()` with control characters as marks.
- Create clip from a moment (`POST /search/clips {project_id, at, length}`,
  default 30 s, 5-180): the clip starts where the sentence holding `at`
  starts (the next sentence if `at` is in a pause), takes the following
  sentences that end within `length`, and is cut at `length` if the first
  sentence alone is longer (ASSUMPTION: simplest rule that never ends
  mid-sentence except for one long sentence). It is a candidate of the
  project's current result set with the project's caption settings, title
  and description from what is said, zero scores and no hashtags; it is
  rendered by `POST /clips/{id}/render` like a duplicate. 404/409/422 for
  an unknown project, no transcript, nothing said at or after `at`.
- Public API/MCP: `search.router` is in `PUBLIC_ROUTERS`; tools
  `search_library` and `create_clip_from_moment` (unique function names).

## 2026-11-03 — TASK-156 (T51e): Library, collections and storage UI + project filters and reprocess

- The storage manager (SPEC-v2 3.11) did not exist yet, so it is built here
  (backend `storage.py`, `api/storage.py`): `GET /storage` lists each
  project's uploaded source, work files and output, largest first, with the
  total and the free disk space. Clean up deletes only what can be made
  again: `audio.wav`, `faces_cache.json`, cached previews and, once the
  project is done, the uploaded copy (the work dir keeps `source.mp4`).
  Archive keeps the output, `transcript.json` (search, transcript
  downloads), `meta.json` and `thumb.jpg`, deletes the rest and sets
  `Project.archived_at` (migration 032); rendering, reprompt and clips
  from a search of an archived project are 409. Both are 409 while the
  project is queued or running, and both ask first in the UI.
- Reprocess (`POST /projects/{id}/reprocess`, "Process again" in the
  project menu) is only for a failed, non-archived project: it queues the
  same process job again, so the steps already done are skipped
  (ASSUMPTION: a done project is reprompted instead).
- Bulk export from the Library = make a clip of each selected hit (its
  render is queued), put them in a new collection named after the search
  and open it; the collection shows them "Queued" (navigation state, as
  the clip stays a candidate until its render job runs) and polls until
  they are rendered, then "Download zip".
- The top bar search now opens the Media library (`/library?q=`).
- A render job of a clip with no crop plan (a clip from a search moment)
  reframes it first (`clip_crop.ensure_crop_plan`, with the project's
  aspect and reframe preset), instead of failing.
- Project list filters (All, Processing, Ready, Failed, Archived) are chips
  kept in `?status=`.

## 2026-11-02 — TASK-170 (T57a): Notifications (in-app, desktop, SMTP email)

- Verified (installed `smtplib` on Python 3.11, `help()`/signatures, and
  https://docs.python.org/3.11/library/smtplib.html, 2026-11-02):
  `SMTP(host, port, timeout=)`, `SMTP_SSL(host, port, timeout=, context=)`,
  `starttls(context=)`, `has_extn("starttls")`, `login(user, password)`,
  `send_message(msg)`; `SMTPException` subclasses `OSError`. Desktop: `osascript`
  runs an AppleScript that reads its arguments (`on run argv ... display
  notification (item 1 of argv) with title (item 2 of argv)`), so text never
  becomes script (run once here: rc 0); `notify-send --app-name` on Linux.
- Notifications are rows of `notification` (migration 033, `dedupe_key`
  unique for the once-a-month quota messages). Events: project done
  (`process`, `reprompt`), render failed (`clips.render_clip_row`), post
  published/failed (`posts.move`, `post_queue.fail_interrupted`), quota
  warning (`jobs.run_claimed`, after the job's compute is metered).
- Email is on only if `SMTP_HOST` is set and there is a recipient
  (`NOTIFY_EMAIL_TO`, else `SMTP_FROM`, else `SMTP_USER`). Port 465 =
  implicit TLS, else STARTTLS when offered (ASSUMPTION: the owner's SMTP
  server needs no other mode). An empty `SMTP_PORT` (as `.env.example` has
  it) is 587.
- Desktop (`DESKTOP_NOTIFICATIONS`, default off) is the operating system's
  notification from the backend; the browser's own alerts (watch) stay.
- Delivery is synchronous with a 10 s timeout and never raises (ASSUMPTION:
  simplest; a hung mail server delays the job or post by up to 10 s).
- A quota warning comes at `QUOTA_WARN_PERCENT` (80) % of a monthly cap and
  once more when it is used up, each once per month and kind.
- Not done here: Settings page fields for SMTP/desktop (TASK-171), the bell
  UI, the daily digest (autopilot task).

## 2026-11-02 — TASK-171 (T57b): Settings v2

- Verified (installed `radix-ui` 1.8 `Popover`: `Popover.Root open/onOpenChange`,
  `Trigger`, `Portal`, `Content align/sideOffset`; and
  https://www.radix-ui.com/primitives/docs/components/popover, 2026-11-02): the
  bell is a Popover. Its trigger is styled with `buttonVariants`, not the
  `Button` component (not forwardRef; `asChild` would log a ref warning).
- Settings v2 = the existing page plus the missing SPEC-v2 3.17 parts: the
  SMTP/desktop/quota fields (`SettingsView`/`SettingsUpdate`, `smtp_password`
  is write-only like the other keys and redacted from test-llm messages),
  "Defaults for new projects", "Platform connections", "Storage paths" (the
  models folder moved here from Transcription) and the top-bar bell. Engines,
  API keys, usage caps and the LLM were already there.
- ASSUMPTION: the "language" setting is the default speech language of new
  projects (saved through `PUT /api/processing-defaults`, as the panel's "Save
  as default" does); the app UI stays English.
- ASSUMPTION: platform sign-in stays on the Social accounts page; Settings only
  shows account counts and developer-app status (no second sign-in UI).
- The notification fields have their own Save button (like the usage caps), so
  a mistyped port never blocks saving the language model. "Send a test" needs
  saved settings (it uses the server's saved ones).
- The data folder is shown, not edited (the open database lives in it).

## TASK-177 Submission tracker (SPEC-v2 3.18)

- Submissions are created lazily (`submissions.sync` on read) for published posts with a URL in a campaign's projects, not by a publish hook: no change to the posting path, and posts published before the feature are covered.
- `submission.campaign_id` is ON DELETE SET NULL so recorded payouts survive deleting a campaign (`campaign_name` is then null).
- Status machine: not_submitted -> submitted -> approved | rejected -> paid, with the back moves in `submissions.TRANSITIONS`; a self-move is allowed so notes and numbers can be edited. The owner ticks "submitted" by hand: ClipForge never scrapes or automates a campaign board (SPEC 1.5).
- Campaign -> accounts is a `campaign_account` table; accounts outside `allowed_platforms` are refused when that list is set. The bulk schedule of a campaign only takes clips of that campaign's projects and reuses `api.posts.bulk_schedule` (queue stays human-only).
- No third-party API is used (internal only), so no SPEC-v2 0.1 API check applies.

## TASK-180 Autopilot settings + Draft/FeedbackEvent model (SPEC-v2 3.19)

- Settings are one row per campaign (`autopilot_settings`, migration 035); a campaign never set up has the defaults (off, 3 clips per source, 3 posts a day, hard cap 5, drafts expire after 3 days) without a row. `PUT /campaigns/{id}/autopilot` replaces all of them.
- ASSUMPTION: "watched channels" are the campaign's own `source_channel_urls` (3.18), not a second list; "clip length range" and "caption/brand template" are `min_clip_s`/`max_clip_s`, `caption_template`, `brand_template_id`, where None means the campaign's own value.
- ASSUMPTION: `slots` reuse `ScheduleRules` (SPEC 3.10); a day of slots may not have more times than `max_posts_per_day`, so the cap cannot be bypassed by slots. The hard cap 5 is a model constraint (6 is a 422).
- `account_ids` is a JSON list checked on save (exists, platform allowed by the campaign, as `campaign_accounts.check_platform`); accounts disconnected later are dropped when read.
- `draft` has one row per clip (UNIQUE `clip_id`), with `created_at` for the expiry; `feedback_event.clip_id` is ON DELETE SET NULL so what was learned survives deleting a clip. Reject reasons are the 6 chips of the spec (`RejectReason`).
- No third-party API is used (internal only), so no SPEC-v2 0.1 API check applies.

## TASK-181 Autopilot draft pipeline (SPEC-v2 3.19)

- Trigger: drafts are made when a project's process job is done (`process._finish` -> `autopilot.pipeline.drafts_after_job`), only for a project that Auto Import made (a `watched_video` row points at it) for a campaign whose autopilot is on. A project the owner put in a campaign by hand gets no drafts: the spec's flow starts at "new upload detected". A failure to make drafts is logged; the job stays done.
- ASSUMPTION: the autopilot's settings shape the project at import (`import_settings`): `num_clips` = `max_clips_per_source` (speed first for fresh uploads), its caption/brand template, and a "custom" length range from `min_clip_s`/`max_clip_s` with a missing bound taken from the campaign (bounds that leave no range keep the campaign's presets). `preset_new_clips` now gives a campaign project's new clips the project's caption template (the campaign's via the preset, or the autopilot's) so the autopilot's template is not overwritten.
- The best rendered clips of the current result set (overall score, then id) become drafts until the project has `max_clips_per_source` (existing drafts count, so re-running adds none past the cap). Rule check on the owner's local date with platform None (any allowed platform); publishing checks the real platform again. `rule_results` keeps every result; pending if all pass, else needs_fix.
- Invariant: the pipeline never creates a Post or Submission (it imports none of posts/post_schedule/scheduler/submissions/publishers; tested).
- No third-party API is used (internal only), so no SPEC-v2 0.1 API check applies.

## TASK-182 Autopilot safety stops + draft expiry + global pause (SPEC-v2 3.19)

- Global "Pause all autopilot" is a one-row table (`autopilot_pause`, migration 036; the row is there while paused, with `paused_at`) rather than a `.env.local` setting: it is app state the inbox toggles, not configuration, and an env var would win over it. `PUT /api/autopilot/pause` pauses for anyone, but resuming is the owner's (`require_human`: 403 `human_only` for an API key or agent), so an agent can stop the autopilot but never restart it.
- Computed stops (`safety.stop_reason`), each lifting by itself once the cause is gone: paused (global), `permission_missing`, `campaign_inactive` (status paused/ended), `campaign_ended` (end date before the owner's local date; the end date itself still drafts, like the rule checker), `daily_quota`. While stopped, a new upload is imported as a plain campaign project (`import_settings` returns the preset settings; the daily quota is not looked at there) and `make_drafts` makes none.
- ASSUMPTION: the daily quota is `max_posts_per_day` drafts that may be posted (pending or approved) made on the owner's local date per campaign, since each approved draft is posted once on every target account (so a per-account cap is a per-draft cap). needs_fix/rejected/expired drafts do not count. Over the quota, `make_drafts` stops at the first passing clip with no room; the rest get no draft (drafts are made once, when the job is done; the clips stay in the project for the owner).
- ASSUMPTION: "3 consecutive uploads fail" = the campaign's last 3 finished (done/failed) Auto Import projects (a `watched_video` row) are all failed, checked when a process job fails (`process._finish` -> `safety.after_failed_job`). This stop is sticky: the campaign's autopilot is turned off (`enabled = False`) and the owner gets an `autopilot_stopped` notification (dedupe per failing project); it stays off until the owner turns it on again (one more failure then turns it off again, conservatively).
- Alerts: every automatic computed stop notifies `autopilot_stopped` once a day per campaign and reason (dedupe `autopilot:<campaign>:<reason>:<local date>`); the owner's own pause makes none. New `NotificationKind` "autopilot_stopped"; frontend types regenerated.
- Draft expiry: pending and needs_fix drafts made `draft_ttl_days` (campaign's, default 3) or more ago become `expired` (`decided_at` stays None: no owner decision). Runs on every Auto Import tick (and can be called by the inbox), also while paused: fresh clips matter.
- No third-party API is used (internal only), so no SPEC-v2 0.1 API check applies.

## TASK-183 Human-only approval enforcement (SPEC-v2 3.19)

- New Approval Inbox API (`api/drafts.py`, domain `autopilot/inbox.py`): `GET /drafts` (`status`, `campaign_id`), `GET /drafts/{id}`, `POST /drafts` (`{clip_id}`), `POST /drafts/{id}/notes` (`{text}`) are open to agents; `POST /drafts/{id}/approve`, `POST /drafts/{id}/reject` and `POST /campaigns/{id}/drafts/approve` (approve all) are human-only (`dependencies=[Depends(require_human)]`). They are also under `/api/v1` (tag "drafts"); the MCP server offers no tool for the three human-only ones (`mcp_tools.HUMAN_ONLY`) and the app answers 403 `human_only` if a call gets through anyway.
- ASSUMPTION: rejecting is human-only too. The spec lists what agents may do (create drafts, list the inbox, add review notes) and a reject is an owner decision that the feedback learning trusts; agents can say what they think in a review note.
- ASSUMPTION: approving = "schedule into next free slot": the clip's posts go, queued, to each of the autopilot's `account_ids` (none: the campaign's mapped accounts) in the next free slot of the body's `rules` or else the autopilot's `slots` (neither: 422), at most `max_posts_per_day` a day per account (`posts_per_day` capped). It reuses `api.posts.bulk_schedule` with `queue=True`, so every post passes the publish checks; a needs_fix draft can be approved once its clip passes the campaign's rules (the owner fixes it in the editor), else the posting error comes back and the draft stays. "Approve all" takes only pending drafts, oldest first, in one bulk schedule.
- Review notes are a JSON list on the draft (`notes`, migration 037: `{text, by: owner|agent, at}`, at most 50); `by` is "agent" for a call with an API key or under `/api/v1` (`deps.is_agent_call`).
- Hardening: `POST /campaigns/{id}/bulk-schedule` with `queue` now checks human-only before anything else (before, an agent could get a 422 about accounts before the 403).
- Verified (installed source, 2026-11-02): FastAPI 0.162.0 `fastapi/dependencies/utils.py` `solve_dependencies` calls the sub-dependencies (line 676) before it validates path/query/body (lines 738-768), so a route-level `Depends(require_human)` answers 403 even to an empty or invalid body. No other third-party API is used.

## TASK-184 Approval Inbox UI (SPEC-v2 3.19)

- The page is `/inbox`, "Approval inbox" first in the sidebar's Post group (`navigation.INBOX_PATH`). Tabs "To approve (n)" (`GET /api/drafts?status=pending`) and "Needs fix (n)" (`status=needs_fix`); a Campaign select filters both (`campaign_id`).
- ASSUMPTION: Approve sends `{}`: the posts go into the next free slots of the campaign's autopilot (its `slots`/`account_ids`). There is no per-approval rules form; when the autopilot has no slots or accounts the API's 422 message shows as the error toast and the draft stays. The success toast names the first post's slot.
- ASSUMPTION: "Edit (open editor, then approve)" = E/Edit opens `/clips/{id}` with navigation state `EditorBackState` (`lib/editorBack.ts`), so the editor's back arrow reads "Back to the approval inbox" and returns there; the owner then approves. A needs_fix draft shows Approve too: the server's publish checks decide (TASK-183).
- ASSUMPTION: Reject opens the reason chips (one reason at most, optional, as `DraftReject.reason` takes one); "Reject clip" or R again sends it; Esc cancels. A is ignored while the chips are open (no accidental approve). J/K move the selection (the card scrolls into view) and close the chips. Shortcuts are off while typing in a field, with cmd/ctrl/alt, and while the approve-all dialog is open.
- ASSUMPTION: "Approve all for this campaign" needs a campaign chosen in the filter (disabled otherwise) and asks first (`ConfirmDialog`); it approves only pending drafts (the API's rule), the dialog says needs_fix ones are left out.
- Card: the 540p preview (`previewUrl`) plays muted, looping, on load for every card; campaign name and rate (`rate_per_1k_usd`), the score (`ScoreBadge` popover), title, description, hashtags, rule results stored on the draft (failed rules listed, "Show all rules" for all; `RuleResultList` extracted from `RuleCheckPanel`), the source link (`project.source_url`) and freshness (`project.source_published_at`, "Uploaded 5 h ago"), and the review notes (owner/agent).
- Verified (2026-11-02): Chrome autoplay policy "Muted autoplay is always allowed" (https://developer.chrome.com/blog/autoplay), so the `autoPlay muted` previews play without a user gesture (also seen in the e2e: `readyState > 1`). Radix UI 1.8.1 `Tabs`/`AlertDialog` are used as elsewhere in the app (installed source). No third-party service API is used.

## TASK-186 Ready-to-submit list + daily digest (SPEC-v2 3.19)

- The list is the page `/submit` ("Ready to submit", in the sidebar's Post group after the Approval inbox, `navigation.SUBMIT_PATH`): `GET /api/submissions?status=not_submitted` (all campaigns, newest first), each post a `SubmissionItem` (campaign pill, URL, "Copy for submission" = URL + the campaign's required information, the "Submitted on the campaign board" tick). A ticked post leaves the list (the tracker in the campaign keeps showing it and takes the board's answer, views and payout). ClipForge never opens or automates a campaign board (SPEC-v2 1.5).
- ASSUMPTION: "estimated earnings yesterday" = the sum of `approved_views / 1000 * rate_per_1k_usd` of the approved/paid submissions whose board answer or numbers the owner entered yesterday (new `submission.answered_at`, migration 038; set when the status becomes approved/rejected/paid or the approved views/payout change; cleared when the submission goes back to not_submitted/submitted). There are no per-day views yet (the analytics snapshots of SPEC-v2 3.13 are not built), so this is a rough figure and is labeled "(estimate)"; campaigns without a rate add nothing.
- Digest: `autopilot/digest.py`, called by `AutoImporter.tick` (like draft expiry, so it runs every minute without a new thread). From `digest_time` (new setting, "HH:MM" in the computer's local time, default "08:00", empty = off; edited in Settings -> Notifications and `PUT /api/settings`) one `digest` notification a day (`dedupe_key` `digest:<local date>`, also sent by email/desktop when those are on) with: pending drafts waiting, posts scheduled today (queued, uploading or published with `scheduled_at` on the local day), submissions not submitted yet, estimated earnings yesterday. A digest with all four at zero is not sent. ASSUMPTION: needs_fix drafts are not counted as "waiting" (the owner cannot approve them yet).
- ASSUMPTION: if the app was not running at `digest_time`, the day's digest is sent on the first tick after it; if there was nothing to tell then and something comes up later in the day, the digest is sent then (the skipped digest is not recorded).
- No third-party API is used (internal only), so no SPEC-v2 0.1 API check applies.


## TASK-187 E2E flow 1: v1 full flow on v2 (SPEC-v2 5)

- The task lists `frontend/e2e/v1-full-flow.spec.ts`, but the Playwright suite lives in `e2e/` (root), and the v1 full flow already exists there as `e2e/flow.spec.ts` (TASK-49: upload fixture -> clips -> edit -> render -> download mp4, no console errors). The acceptance criterion is "green unmodified", so no duplicate spec was created and `flow.spec.ts` was not touched (no selector updates were needed).
- The screenshot `.agent/screenshots/TASK-187-1.png` came from a throw-away copy of `flow.spec.ts` with one extra `page.screenshot` line (deleted after the run).
- No third-party API used (internal only).

## TASK-191 E2E autopilot (SPEC-v2 6, T58.5)

- The task lists `frontend/e2e/v2-autopilot.spec.ts`; the Playwright suite lives in the root `e2e/` (as decided in TASK-187), so the spec is `e2e/v2-autopilot.spec.ts`.
- Test mode cannot reach YouTube (feed, yt-dlp download) or a platform's OAuth sign-in, so the previous inbox e2e stubbed the approve answer. To run the real autopilot path end to end, the test server (`create_test_app` only; a normal server never mounts it) gets `api/testmode_routes.py` under `/api/testmode`, stand-ins for the outside world only:
  - `POST /api/testmode/accounts/{platform}?name=` saves a connected account like a finished sign-in (`social_accounts.save_account`, placeholder token in the real token store; test mode's posting worker never publishes, so it is never sent).
  - `POST /api/testmode/channels/{channel_id}/uploads?video_id=&title=` hands the real `AutoImporter` (its `_import_entries`, via "push") a new upload of a watched channel whose source is the fixture `sample.mp4` instead of the watch page (a `FeedEntry` subclass overriding `url`). Everything after that is the app's own code: campaign preset, `import_settings` (autopilot's clip count), project, alert, process job, `drafts_after_job` -> drafts, the inbox UI, approve -> `bulk_schedule` into the autopilot's slots, the human-only gate.
  - ASSUMPTION: calling the importer's private `_import_entries`/`_watched` from the test-only router is preferred over adding a public import method used only by tests.
- The spec: account + campaign (watched channel link, permission evidence) + autopilot on (3 clips/source, 3 posts/day, Europe/Zurich 09:00/18:00, the account) -> new upload -> 3 pending drafts -> UI rejects one ("Too long") and approves two (A) -> 2 queued posts on the account at distinct future slots, shown in the Calendar -> an API key may list `/api/v1/drafts` (200) but approving (`/api/v1/drafts/{id}/approve`, `/api/v1/campaigns/{id}/drafts/approve`, `/api/drafts/{id}/approve` with the key), publishing and queueing (`/api/v1/posts/{id}/publish|queue`) answer 403 `human_only`, and nothing changes.
- Verified (installed source, 2026-11-02): Playwright 1.64.1 `APIRequestContext.post/get` take `params` (`{[key]: string|number|boolean}`) and `headers` (`node_modules/playwright-core/types/types.d.ts`). No third-party service API is used.

## TASK-192 E2E campaign flow (SPEC-v2 6, T58.6)

- The task lists `frontend/e2e/v2-campaign.spec.ts`; the Playwright suite lives in the root `e2e/` (TASK-187), so the spec is `e2e/v2-campaign.spec.ts`.
- "Fresh upload project" = a watched campaign creator's new upload (TASK-176): the campaign is created in the UI with the creator's `/channel/UC...` link, and `POST /api/testmode/channels/{id}/uploads` hands it to the real Auto Import, which makes the project with the campaign preset, rights "permission" and `fresh_upload: true` (there is no fresh-upload badge in the UI, so the e2e reads it from the API).
- Test mode cannot reach a platform, so the published post comes from a new stand-in, `POST /api/testmode/posts/{post_id}/publish` (test server only): the real `publishers.publish.publish_post` (rights, rendered video, account, status moves, attempts) with `TestModePublisher`, a `Publisher` that sends nothing and answers id `test-<post id>` and the link `https://example.com/testmode/<platform>/<post id>`. 404 unknown post, 409 `invalid_status` when not queued; publish checks answer their own 409 (`PublishBlocked` handler).
- ASSUMPTION: the earnings dashboard (T58c.1/2) was dropped by the owner (scope cut 2026-11-02), but the kept campaign e2e ends with "dashboard shows earnings" and the acceptance criterion asks for the exact number. Simplest option: an "Earnings" summary in each campaign's Submissions section (`components/submissions/EarningsSummary.tsx`, `lib/earnings.ts`): approved views (approved + paid submissions, as the digest counts them), estimated earnings = approved views x rate / 1,000 (labeled "Estimate", "No rate set" without a rate), and the sum of the payouts entered. No per-platform/month view, CHF conversion or CSV export (still T58c, not planned). Computed in the browser from the submissions the tracker already loads (no new endpoint, no `types.ts` change).
- The AI post copy is answered by `page.route` (test mode's `RecordedLLM` answers every prompt with the clip list), as in `e2e/posts.spec.ts`.
- Verified (installed source, 2026-11-02): `Intl.NumberFormat("en-US", {style: "currency", currency: "USD"})` gives "$30.86" for 30.8625 and "$1,234.50" (ECMA-402; checked with Node v24.18.0 and by `lib/earnings.test.ts` in vitest). Playwright 1.64.1 `locator(selector, { has })` (`node_modules/playwright-core/types/types.d.ts`). No third-party service API is used.


## TASK-193 README v2 (SPEC-v2 2.3/3.10, T58.7)

- Every `### Engine: <name>` section has **Install** and **Install check** (what `Engine.install_check` looks at); every `### <Platform> publishing` section has **Developer app setup.**, **Review notes.** and official doc links. `tests/unit/test_readme_setup.py` enforces both (and the existing `test_engines.py` still checks each engine's anchor).
- ASSUMPTION: the engines of dropped features (demucs, image-gen, realesrgan, voice-clone, embeddings) stay in the registry, so `test_every_engine_has_a_readme_section_for_its_anchor` needs their README sections. Simplest option: keep each section short, with install + check, and say that the feature is not planned and no screen uses the engine. Removing them from the registry (and the pytest markers, Makefile and probes) would be a code change outside a documentation task.
- New README section "Campaigns and autopilot" (campaign rules, submissions + earnings estimate, autopilot settings via `PUT /api/campaigns/{id}/autopilot` because there is no autopilot settings screen, Approval inbox, human-only approve/reject, safety stops, daily digest). Dubbing, X/LinkedIn, AI B-roll, upscaling, earnings dashboard and the other dropped features are not described as features.
- Verified (official docs, fetched 2026-11-03, all answered HTTP 200): https://developers.google.com/identity/protocols/oauth2/native-app, https://developers.google.com/youtube/v3/docs/videos/insert, https://developers.google.com/youtube/v3/determine_quota_cost, https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits, https://developers.tiktok.com/doc/content-posting-api-get-started, https://developers.tiktok.com/doc/content-posting-api-reference-direct-post, https://developers.tiktok.com/doc/login-kit-desktop, https://developers.tiktok.com/doc/content-sharing-guidelines, https://developers.facebook.com/docs/development/create-an-app, https://developers.facebook.com/docs/facebook-login/facebook-login-for-business, https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing, https://developers.facebook.com/docs/video-api/guides/reels-publishing, https://developers.facebook.com/docs/resp-plat-initiatives/app-review. The platform limits in the README were verified in the publisher tasks (T46/T47/T48 notes above) and are unchanged.
- Screenshots in the README are the existing `docs/assets/screenshot-home.png` (no third-party creator thumbnails); none added.

## TASK-194 parity.md complete (SPEC-v2 5, T58.8)

- No third-party API, library call, endpoint or model is used by this task (a docs table and a stdlib script), so there is nothing to verify online.
- `docs/parity.md` gets a "SPEC-v2 section 3 coverage" table: one row for each of the 104 bullets (and sub-bullets) of section 3, numbered by position (`3.4.2`), with a status and evidence paths. `scripts/check_parity.py` (in `make lint`) reads the bullets from `.agent/prd/SPEC-v2.md` and fails on a missing, unknown or repeated id, a status outside the list, or an evidence path that does not exist.
- ASSUMPTION: the spec names three statuses (done / needs platform approval / blocked). Features the owner dropped on 2026-11-02 were never attempted, so "blocked" (cannot be built here, with evidence) would be untrue. Simplest option: two more statuses, "partial" (built, the gap in the notes) and "not planned" (dropped by the owner; evidence is the deferred task spec and the decision entry), the same words the feature table above already uses.
- Statuses are judged from the code and tests in the repo: e.g. the brand template's logo and intro/outro files are stored but the render has no brand pass (3.5.20, 3.5.21 not planned; 3.8.1 partial), and YouTube is "needs platform approval" because an unaudited Google Cloud project may keep uploads private.

## Steering: model picker with validation

- Verified 2026-11-03 against a real account: Copilot `GET https://api.githubcopilot.com/models` answers `{object, data[]}` with `id`, `model_picker_enabled`, `capabilities.type` ("chat" or "embeddings") and, for some models, `supported_endpoints`. The picker lists chat models, the ones Copilot's own picker shows first. OpenAI-compatible: `GET {base}/models` (`data[].id`); Ollama: `GET {host}/api/tags` (`models[].name`); Anthropic: `GET /v1/models` (as before). Claude Code has no list: its model stays a text field.
- `POST /api/settings/models` (replaces `/settings/anthropic-models`) lists the models of the provider in the body or the saved settings; a failure is a 200 with `error`, keys redacted. `clipforge/llm_models.py` holds the reply shapes; each client has `list_models()` (`ModelLister` protocol).
- ASSUMPTION: validation on save is opt-in, `PUT /api/settings?verify_llm=true` (the Settings form sets it), because many API tests and the other sections save without a provider to call. Simplest option over verifying every PUT. It runs one `complete_json` call, only when the provider, the active provider's model, endpoint or credential changed; on failure nothing is saved and the answer is a 422 `llm_rejected` with the provider's error (keys redacted). The form keeps the draft and shows the error as a toast.
- UI: `ModelPicker` loads the list when the provider opens (and with "Load models" after a key or address is typed); a dropdown with "Custom…" (a saved model the list lacks shows as custom); a text field while no list is available. Test mode (`create_test_app`) uses `offline_llm_transport()` so the Settings page never reaches a provider there.

## TASK-201 V3-01 Pro Edit migrations (039_proedit)

- No third-party API, library call or model is used (SQL migration, Pydantic models and SQLModel rows only), so nothing to verify online. SQLite facts checked by the migration test: `ALTER TABLE ... ADD COLUMN` accepts `REFERENCES ... ON DELETE CASCADE` with a NULL default (self-reference on `clip`), and `key` is usable as a column name.
- ASSUMPTION: SPEC-v3 6 says plans are "a plan row with versioned JSON items", while the task lists an `edl_item` table. Simplest option that satisfies both: `pro_edit_plan` is one row per plan version (`UNIQUE (clip_id, version)`, so a change that keeps the version before is a new row) and its edit decisions are `edl_item` rows (`PRIMARY KEY (plan_id, item_id)`, `params` JSON). The column is `item_id` (the item's number within its plan, from 1; `EdlItem.id`), not `id`, so the table has no AUTOINCREMENT id.
- ASSUMPTION: deleting an original clip deletes its Pro Edit variants (`parent_clip_id ... ON DELETE CASCADE`). SET NULL would leave a `pro_edit` clip with no parent, which `Clip` rejects (a `pro_edit` variant, and only it, has a parent), so a clip row could no longer be read.
- ASSUMPTION: `StyleReference.url` is stored as given; the 1-5 link limit and the rights confirmation are checked by the style API (TASK-215+). `critic_scores` of a run is a JSON list of rounds, each `{round, scores: [{check, score 0-10, reason}]}`, so the reason of every checklist score (SPEC-v3 3.7) is kept.
- ASSUMPTION: `EdlItem.params` is a free `dict` for now; the per-kind parameter models, overlap and budget validation are TASK-203. `Asset.license`, `attribution` and `source_url` already exist (v2), so only `bpm`, `key`, `loudness_lufs`, `energy_curve` (JSON list), `category`, `mood` and `downloaded_at` are new.
- `Campaign.allow_heavy_edits` is in `CampaignCreate` (owner input, default `unknown`); the autopilot's `proedit_enabled` (false), `proedit_preset` (`clean_pro`) and `proedit_max_intensity` (`standard`) are in `AutopilotSettingsUpdate`, so `PUT /campaigns/{id}/autopilot` accepts them and an old client that omits them resets them to these defaults. The campaign form keeps the saved switch (`allowHeavyEdits` in `campaignForm.ts`); its control comes with the Pro Edit campaign settings task.
- The config keys of SPEC-v3 6 (`proedit.enabled`, ...) are not part of this task (TASK-202 adds the flag).

## Steering: calmer eased auto-track camera (Camera motion setting)

- No golden record existed (TASK-202, the v3 golden isolation test, is not done yet), so none was regenerated. No third-party API is used (pure Python path planning).
- `pipeline/camera_motion.py` holds the motions: calm (dead-zone 0.12, max pan 0.12 frame widths/s, hold 1.0 s, eased), normal (0.10, 0.18, 0.6 s, eased), fast (0.08, 0.25, no hold, linear: the old `zero_lag -> dead_zone -> limit_speed` path, reproduced exactly; `test_fast_is_the_path_from_before_the_setting` compares it with an inline copy of the old code).
- ASSUMPTION: the spec's duration `max(0.6 s, distance / max_pan)` is the average speed; a smoothstep's peak speed is 1.5x its average, so a move lasts `max(0.6 s, 1.5 * distance / pan)` (`PEAK`), which keeps every per-sample step under the cap (calm 400 px of 1000: 5 s, top step 11.794 px of 12).
- Eased moves are reactive: the window rests until the smoothed aim is more than half the dead-zone away and the hold since the end of the last move has passed, then glides to where the subject will be when the move ends (offline, the whole shot's aims are known): the shortest move whose duration covers the distance to the aim at its own end, else toward the shot's last aim. The hold counts from the end of one move to the start of the next.
- ASSUMPTION: "the subject leaves the crop window" = its smoothed center is more than 0.4 of the window's width from the window center (`EXIT_SHARE`). Then the window re-aims at once (no hold) and a move may use the catch-up pan 0.25 (`CATCH_UP_PAN`), still eased. Without a window width (tests, `follow` without `crop_width`) there is no catch-up. Scene cuts still reset the window at once.
- Velocity continuity: the step changes by at most `STEP_CHANGE_EPSILON` = 0.012 frame widths (12 px of 1000) from one sample to the next in calm and normal; measured 0.906 px (calm) and 2.036 px (normal) for a 400 px jump, 3.755 px for a calm catch-up, against 12.5 px for fast.
- `ProcessingSettings.camera_motion` (default calm) is saved with the processing presets like every setting. Genre presets map to a motion (`ReframeParams.camera_motion`): standup fast (its old dead-zone 0.05 / pan 0.4 are dropped), podcast-2, gaming, vlog and Automatic calm; picking a Reframe style in the settings sets its motion, which the owner can then change. `CropPlan.camera_motion` records the motion a plan was made with (None in older plans: the preset's). `GET /reframe-presets` lists `camera_motion` instead of `dead_zone`/`max_pan`.
- `PUT /projects/{id}/camera-motion` saves the motion and plans the windows of every clip's crop plan again from the faces the plan holds (`reframe.retrack`, `camera_motion_apply.py`; no new face detection); the rendered videos change once the clips are rendered again. The editor's reframe panel has the same Calm / Normal / Fast chips (disabled while the clip has unsaved edits).
- Click-to-track (`pipeline/click_track.py`) keeps the fast path: the owner pointed at a subject to follow it closely. The object-tracking precision tests use `camera_motion="fast"`; a calm test checks the moving object stays inside the window.

## TASK-203 V3-03a EDL schema + validation

- No third-party API, library call or model is used beyond Pydantic 2 (discriminated unions, `TypeAdapter`), already used across the code, so nothing to verify online.
- ASSUMPTION: the task text says "all 25 kinds" and a track "video-motion"; SPEC-v3 3.1 (which wins) lists 23 kinds (the `EdlKind` of TASK-201) and names the first track `zoom`. The code follows the spec: tracks `zoom, fx, grade, overlay, captions, sfx, music, audio_fx`.
- ASSUMPTION: stackable kinds are `text_pop` and `emoji_pop` (together at most 3 at a time) and `sfx` (at most 2). They never conflict with the non-stackable kinds of their track (an `overlay` may sit under pops); every other kind is exclusive in its track, including `music_bed` against `silence_before_drop` (the Director splits the bed around the silence). Items that only touch (`a.t_end == b.t_start`) do not overlap.
- ASSUMPTION: `silence_before_drop` must last 100-300 ms (SPEC-v3 3.3), checked with 20 ms slack because times are snapped to the frame grid. A zoom punch eases over 0 (instant) or 2-4 frames (SPEC-v3 3.3); scale 110-130 %.
- The per-kind param names (e.g. `scale`, `strength`, `asset`, `gain_db`, `anchor`) are the planner's choice where the spec only names the idea; `overlay`/`sfx`/`music_bed` `asset` is a string (an asset id or the name of a procedural overlay) because the skull overlay is procedural. `models.EdlItem.params` stays a free dict (rows and API are unchanged); `proedit.edl.parse_item` gives the typed item.

## TASK-204 V3-03b EDL snapping + intensity budgets

- No third-party API, library call or model is used (stdlib `bisect`/`math`/`itertools.pairwise` and Pydantic 2), so nothing to verify online.
- ASSUMPTION: `EdlItem` has no `snap` field (adding one would change the rows and API); the snap mode is per kind in code (`snap.DEFAULT_SNAP`: word for `zoom_punch`, `text_pop`, `emoji_pop`, `caption_style`; beat for `flash`, `shake`, `glitch`, `rgb_split`, `transition`, `silence_before_drop`; frame for the rest) and a preset/caller may pass other modes per kind (e.g. Phonk: `zoom_punch` on beats).
- ASSUMPTION: "else the word/frame rule applies" = a beat item with no beat within 0.12 s snaps to a word start within 0.25 s, else to the frame grid. The item's start is what snaps (its length in frames is kept); `silence_before_drop` snaps its end (the drop). A snapped place that would overlap another item (exclusive track or stack limit), or fall outside the clip, is not used: the item keeps its plain frame-grid place. Every item's frame place is reserved until it is placed, so snapping one item never forces another off. An item shorter than a frame lasts one frame.
- ASSUMPTION: "word start minus one frame" = the SFX ends at frame `floor(word_start * fps) - 1`, its length kept. It is dropped when it would start before 0, cover another punchline or exceed the SFX stack of 2.
- ASSUMPTION: a density "1 per N s" = at most `count` item starts within any half-open window of N s (starts exactly N s apart are fine). Effect items (counted together, per 5 s) are the kinds of the zoom, fx and overlay tracks plus `grade_change`; vignette, grain, caption style, music and silence are whole-clip or audio and have no budget. The per-kind spacings of the other kinds (`budgets._SPACING_S`) are the planner's analogues of the SFX column; every kind is at least as sparse at a lower intensity (tested).
- ASSUMPTION: over budget, items are kept in priority order (manual before auto, then `budgets.KIND_PRIORITY`, then the earlier item) and the rest dropped with a `PlanNote` naming the broken limit. Manual items can be dropped too when manual items alone break the budget.
- ASSUMPTION: a preset's budget (`PresetBudget`) may only be stricter (`count` ≤ and `window_s` ≥ the global one); a looser one raises `ValueError` naming every raised limit (at preset load). The pattern-interrupt target (pro/extreme 2-4 s) is a target, not a limit: `interrupt_gaps` reports spans longer than 4 s without an interrupt (zoom, fx, overlay or sfx start) for the Director/critic.
- Order (`postprocess.postprocess_plan`): snap, then punchline protection, then budgets.

## TASK-205 V3-04a Signals adapter

- No third-party API, library call or model is used beyond what the existing pipeline modules already call (PySceneDetect, YAMNet, MediaPipe, ffmpeg run through them), so nothing new to verify online. The music beat grid (`librosa`) is TASK-206.
- ASSUMPTION: every time of `ProEditSignals` is in seconds of the rendered clip (EDL time, SPEC-v3 3.1), not of the source: `proedit/clock.ClipClock` maps source seconds through `sections.played_spans` at `settings.render.fps`, so cut ranges, section order and frame rounding are those of the render. Spans a cut splits become one per played part; moments the render drops are left out. Boxes are fractions of the source frame.
- ASSUMPTION: "reuse existing analysis" = read `transcript.json`, `signals.json`, `motion.json` and the face cache (`faces_cache.json`) of the job; the clip's emphasis words, caption overrides and marks give each word's emphasis/emoji (`caption_lines`). Computed only when missing for the clip's span: faces (frames not in the face cache are searched and added to it, models loaded on the first miss) and motion (`motion.json` absent or not covering the clip: the clip's span is measured and nothing is stored). No crop plan is written (it depends on aspect and preset) and no pipeline module changed.
- ASSUMPTION: a punchline is the last word that ends no more than 1.5 s before (or 0.3 s after, laughs are detected a little early) a laugh, applause or cheer; "LLM-marked moments if stored" is skipped, because no step stores any. Speaker turns are runs of words of one transcript speaker; silences are `signals.json` silences, pauses are speech cleanup's pauses (default threshold, no fillers); sentences end at a word ending in `. ! ? …`.
- ASSUMPTION: faces are kept at 2 samples a second per track (every 5th of the 10 fps samples) to keep the Director's JSON compact; a track's `subject_share` tells how often the speaker-following framing (`speaker.mark_subjects`) picks it.

## TASK-206 V3-04b Music beat grid + shared feature extractors

- Verified 2026-11-04 against the installed packages (signatures from `inspect.signature` / docstrings, the same pages as https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html and https://docs.opencv.org/5.x/d4/dee/tutorial_optical_flow.html): librosa 0.11.0 `beat.beat_track(*, y, sr, onset_envelope, hop_length, start_bpm, tightness, trim, bpm, prior, units, sparse)` returns `(tempo, beat_frames)`; `onset.onset_strength(y=, sr=, hop_length=)`; `feature.rms(y=, frame_length=, hop_length=, center=)`; `frames_to_time(frames, sr=, hop_length=)`. OpenCV 5.0.0 (opencv-contrib-python) `goodFeaturesToTrack`, `calcOpticalFlowPyrLK(prev, next, prevPts, nextPts)` (nextPts is only read with `OPTFLOW_USE_INITIAL_FLOW`), `estimateAffinePartial2D(from, to, method=RANSAC, ransacReprojThreshold=)` returns `(2x3 matrix | None, inliers)`. ffmpeg 9.0.2 (`ffmpeg -h filter=zoompan|aevalsrc|hue|drawbox|crop`) for the fixtures (`zoompan` z/x/y/d/s/fps; `aevalsrc` exprs/s/d).
- ASSUMPTION: librosa's beat times lag clicks by ~20 ms (hop 11.6 ms + onset envelope lag) and `trim=True` drops quiet beats, so `beats.py` tracks with `trim=False` and moves each beat to the steepest +6 dB rise of a 256-sample energy within ±70 ms (median shift for beats without one; beats before the first or after the last attack dropped). Measured on the click tracks: < 1 ms error, 120.01 BPM.
- ASSUMPTION: downbeats assume 4/4 (the loudest of the four beat phases starts the bars); no meter detection. A drop is a beat whose own level and the next bar's median level are near the track's loud level (75th percentile − 3 dB) and ≥ 6 dB above the median of the two bars before it; drops ≥ 8 beats apart. The music grid is its own model (`beats.MusicGrid`, music seconds); `beats_in_clip` moves times into clip seconds for `signals.plan_timing`.
- ASSUMPTION (deviation from the task text "cuts (scene_cuts.py)"): the extractor's cut detector is its own histogram detector (`features/cuts.py`: 2x2 grid of 16-bin luma histograms; a cut when the frame and the next 2 differ ≥ 0.3 from each of the 3 before, flashes skipped), because `scene_cuts.py` (PySceneDetect ContentDetector, 15-frame minimum scene) misses rapid cuts (< 0.5 s apart, common in viral edits) and its pixel metric fires on punch zooms and flashes. `scene_cuts.py` is unchanged. Dissolves and shots shorter than 3 frames are not counted.
- ASSUMPTION: zoom/shake come from the frame-to-frame similarity transform (300 corners, LK, `estimateAffinePartial2D` RANSAC 1 px) with a second pass on the frame warped back by the rough estimate, which recovers 20-30 % punches (1.3 -> 1.0 measured 0.7693, true 0.7692). Zoom = runs of |log scale step| ≥ 0.002 per frame summing to ≥ 0.04 (≤ 5 frames = punch, else ramp); shake = shifts ≥ 0.4 % of the width that reverse direction, at least 3 jolts. Coherent object motion in the frame (e.g. an animated pattern) reads as camera motion: the extractors measure what the viewer sees, not the camera.
- ASSUMPTION: saturation is mean chroma ((max − min) RGB / 255), not HSV saturation (noise in dark pixels); B&W = chroma < 0.03. A flash is a near-white frame (luma ≥ 0.9, chroma < 0.1) or a luma spike ≥ 0.2 above the median of 6 frames each side, in runs of at most 6 frames.
- Tolerances of the fixture tests (`test_features_basic.py`): beats/drops ±20 ms, BPM ±1, cut/flash/B&W edges ±1 frame, zoom edges ±2 frames, zoom scale ±0.02, shake edges ±0.2 s, shake amplitude ±0.005, luma ±0.02.

## TASK-207 V3-05a Renderer core (grade, vignette, grain, proxy + final)

- Verified 2026-11-04 with `ffmpeg -h filter=<name>` (ffmpeg 9.0.2, the ffmpeg-full build the Makefile uses; same options as https://ffmpeg.org/ffmpeg-filters.html): `hue` (`s` saturation, timeline support), `eq` (`brightness`, `contrast`, `gamma`, `saturation`; timeline), `vignette` (`angle` 0..π/2, default π/5; timeline), `noise` (`c0s` 0..100, `c0f` flags `a|p|t|u`, `c0_seed` -1..INT_MAX with -1 = random; timeline, slice threads). The noise filter draws its per-line shifts for temporal noise once per frame from its seeded generator, so slice threading keeps it deterministic (tested: the same plan twice gives identical libx264 frame hashes). Encoders `libx264` and `h264_videotoolbox` (`clipforge.encoders`, unchanged).
- ASSUMPTION: each grade-track item is one filter enabled only on its window's frames: `enable='gte(t,a-½f)*lt(t,b-½f)'` (`render/timing.py`) holds exactly the frames that start in `[t_start, t_end)` (frame k starts at k/fps). Looks: bw `hue=s=1-amount`; desat `hue=s=1-0.6·amount`; dark `eq` with gamma 1-0.35·amount, brightness -0.06·amount, contrast 1+0.1·amount, saturation 1-0.2·amount (measured: luma -20 % at amount 1); vignette `angle=strength·π/2` (default strength 0.4 = vignette's own π/5); grain luma-only temporal `noise` of strength·50 seeded with the item's seed (mod 2^31). Order: grade changes, then vignettes, then grain, so grain is never graded away. The graph converts to yuv420p first (component 0 = luma).
- ASSUMPTION: the `lut` look (with `skin_protect`) is TASK-208 (`fx_basic.py`, bundled LUTs). Until then the renderer refuses a plan holding a lut look or any kind it does not draw (`graph.undrawn` -> `UndrawnItemsError`, naming each item) instead of rendering without it. `skin_protect` has no effect on bw/dark/desat yet (TASK-208 adds skin masks). Items of a later stage plug in as a new `graph.Stage` (kinds, filters, problems).
- ASSUMPTION: "final at source resolution" = the final's short side is the source's short side, at least 1080 (never smaller than the normal render) and at most 2160 (4K): 720p/1080p sources -> 1080x1920 (9:16), 4K -> 2160x3840; other aspects scale `aspect.aspect_size` the same way. The proxy is the aspect's frame at 540 on the short side (540x960). The proxy keeps the configured crf (20) and only uses libx264 preset `veryfast`: at crf 28 x264 erased the temporal grain (frame-to-frame difference 0.01 vs 2.9 at crf 20). VideoToolbox is used whenever `settings.render_settings()` picks it (default on Apple silicon); the tests pin libx264 for determinism and run the cut/final test with every encoder ffmpeg has.
- ASSUMPTION: the base of a Pro Edit is the clip's source framed and cut as its normal render (`framing.framed_plan`, `scene_framing.scene_parts`, layout, segments + cut ranges via `sections.played_spans`) with its censor filter kept (beeped words stay beeped). It does not include the normal render's captions, timeline layers, zoom keyframes, hook punch-in, auto color, transitions, enhanced voice or loudness normalization: the EDL draws its own (captions TASK-213, zoom TASK-209, overlays TASK-212, sound and loudnorm TASK-214-216). EDL times are rendered-clip seconds (after the cuts), as in TASK-205. No pipeline module changed (`clip_graph` reused with its defaults).

## TASK-208 V3-05b Renderer core (freeze, flash, LUTs, normalize, skin protection)

- Verified 2026-11-04 with `ffmpeg -h filter=<name>` and the filter sources (ffmpeg 9.0.2, ffmpeg-full): `freezeframes` (`first`, `last`, `replace`: frame numbers from 0; two inputs; no timeline option), `normalize` (`blackpt`, `whitept`, `smoothing` in frames, `independence` 0..1, `strength` 0..1; RGB only; timeline), `lut3d` (`file`, `interp` incl. `tetrahedral`; RGB only; timeline; `.cube` parser skips lines before `LUT_3D_SIZE`, then accepts `TITLE`, `DOMAIN_MIN/MAX` and `#` comments, red changes fastest), `eq` (`eval=frame` re-evaluates `brightness`/`saturation` expressions of `t` each frame), `huesaturation` (coarse color ranges only), `colorbalance` and `colortemperature`.
- ASSUMPTION: freeze_frame holds the frame at `t_start` on every frame of its window (`split` + `freezeframes=first=F:last=E-1:replace=F`, `timing.frame_range`); the clip's length does not change (frames keep their times; the audio runs on). `split` + `freezeframes` keeps memory flat (343 MB vs 352 MB for a plain 60 s 1080p render). Freezes run before the grade track, so a grade window over a freeze (the Skull Moment) grades the held frame; tests render losslessly (libx264 crf 0) because x264 refines P-frames of a still, so lossy decodes of held frames differ slightly.
- ASSUMPTION: a flash is `eq` per frame: brightness ±peak (white +, black -) and saturation 1-peak on the window's first frame, fading linearly to nothing at `t_end`. Flashes run after the grade (a white flash is white whatever the look).
- ASSUMPTION: auto exposure/white balance is `normalize=smoothing=fps/2:independence=1:strength=0.5` inside each grade_change window before its look (new param `normalize`, default true). Independence 1 stretches each channel from its own black/white points (a cast channel is lifted most); independence 0.5 barely changed a warm cast in the test (B/R 0.67 -> 0.62) because the linked half stretches the cast too. Strength 0.5 keeps colorful scenes mostly as shot; smoothing half a second stops flicker. `colorbalance`/`colortemperature` need a known cast/temperature, which a clip does not give, so they are not used. The normal render's auto color (`independence=0`) is unchanged.
- ASSUMPTION: skin-tone protection works in LUT space: the HSV hue range 5-45° (reds through oranges: light to dark skin under daylight and tungsten) with a 15° feather is skin, and a graded skin color's chroma (max-min) stays within 12 % of the source's (`render/skin.py`; out-of-gamut results shift back in, keeping chroma). Protected dark/desat looks and LUT looks become a derived 33-point LUT (`fx_basic.cached_lut`) cached by content in `data/proedit/luts/`; `huesaturation` was not used because its color flags cannot select a skin hue range. bw is never protected (it takes all color by design). Measured: desat leaves skin at ~0.90 of its saturation (blue/green at 0.4); protected teal_orange keeps skin at ~1.15 in the video (1.12 in the LUT; yuv420p rounding) vs 1.31 unprotected.
- ASSUMPTION: the bundled looks `teal_orange`, `clean_pop`, `cold_night` (`assets/luts/*.cube`, 33-point, 4 decimals) are original, written by `render/luts.py` (`uv run python -m clipforge.proedit.render.luts`) under the project license (`assets/luts/LICENSES.md`); a test checks the files equal the code's output. A lut look at amount < 1 blends from no change to the look. normalize and lut3d run in RGB, so the grade stage converts back to `yuv420p` after them (grain's `noise c0` must see luma); the RGB round trip changes frames by < 0.5 levels.

## TASK-209 V3-06a Renderer motion (zoom punch/push/out-reveal, pan, eased keyframes, face-safe crop)

- Verified 2026-11-04 with `ffmpeg -h filter=scale|crop` and test renders (ffmpeg 9.0.2, ffmpeg-full): `scale` has `w`/`h` expressions and `eval=init|frame` (frame re-evaluates them per frame); `crop` has `w`, `h`, `x`, `y`, `exact`; its `iw`/`ih` are the size at init, so the zoom stage writes the output size as numbers; crop rounds x/y down to even for yuv420p unless `exact`. In `scale` with `eval=frame`, `n` is one frame ahead (`gte(n,5)` was already true on frame 4) while `t` is exact, so the stage steps on `t` (half a frame before each frame, like `timing.frame_window`). ffmpeg's `clip(x,min,max)` gives NaN when min > max, so all clamping is done in Python.
- ASSUMPTION: zooms and pans are one stage after freeze frames and before the grade (`graph.STAGES` freeze -> motion -> grade -> flash): a frozen frame is zoomed (the Skull Moment), and the vignette and grain sit on the zoomed picture instead of being magnified. The stage is `pipeline/zoom_graph`'s technique (`scale` eval=frame to an even size >= the frame, `crop` back to the frame size, `setsar=1`), with every frame's numbers computed in Python (`render/motion.py`) and written as balanced sums of `change*gte(t,..)` steps. Scaled sizes step by 2 px (yuv420p), so a slow push has 2 px quantization steps (same as zoom_graph).
- ASSUMPTION: easing curves are the standard ones from easings.net: `ease_in_out` easeInOutCubic, `back` easeOutBack (c1 = 1.70158), `elastic` easeOutElastic (period 2π/3); p is clamped to 0..1. A punch with `ease_frames` 2-4 reaches its scale on frame `ease_frames - 1` (frame k at `ease((k+1)/ease_frames)`); with 0 it is instant. A punch right after another zoom item (adjacent frames) eases from that item's last scale, not from 1. Push/reveal run scale_from -> scale_to over the window (p = k / (count - 1)). A pan keeps its scale and moves the window center. Every item snaps back to scale 1 after t_end. No scale goes below 1 (an out-reveal eased with back would undershoot).
- ASSUMPTION: face safety protects the subject's face only (the crop plan's subject-marked `kind="face"` box, else the first face box; person/object boxes are not faces), from the base's crop plan (`render/face_path.py`: the fill window interpolated like `layout_parts.crop_window`, faces moved linearly between keyframes of the same track, the nearest keyframe's otherwise; frames map through cuts via `ProEditBase.played`; freeze windows keep their held frame's face; split/grid/other layouts know no face and zoom on the frame center, like `zoom_graph.subject_center`). The face keeps `FACE_MARGIN` = 3 % of the zoomed window on each side: the window moves the least that keeps it in, then stays inside the frame. When the planned peak scale (overshoot included) would not fit the face with its margins, the item's whole zoom (scale - 1) is toned down by the share that fits (its curve is kept) rather than its peak clipped. Zoom centers on a face are its center averaged over ±0.25 s (`SMOOTH_S`) so detection jitter does not shake the picture.
- The acceptance test (`tests/pipeline/test_proedit_render_motion.py`) measures each frame's scale with `features.motion.pair_motion` against a render with no items. A grey testsrc2 still was too sparse for the tracker on the pan's ~70 px shift (no estimate) and SIFT matching was worse; adding blurred uniform noise to the still (`noise=alls=100:allf=u,gblur=sigma=2`) gives dense corners: all 120 frames measured within 0.22 % of plan. Disabling the face clamp makes the face test fail (frame 15), so it is not passing trivially.

## TASK-210 V3-06b Renderer motion (shake, speed ramp, slow-mo)

- Verified 2026-11-04 with `ffmpeg -h filter=setpts|settb|trim|minterpolate|tpad|overlay|atempo` and test renders (ffmpeg 9.0.2, ffmpeg-full; https://ffmpeg.org/ffmpeg-filters.html): `trim` has `start_frame`/`end_frame`; `settb` sets the time base (1/1000000 here so step sums are exact µs); `setpts` has `N` (frame index) and `TB`; `minterpolate` has `fps`, `mi_mode=dup|blend|mci`, `mc_mode=obmc|aobmc`, `me_mode=bidir|bilat`, `vsbmc` and places output frames by input pts (first output pts = first input pts; it needs ≥ 2 input frames past the last wanted output, so `LOOKAHEAD = 4`); `tpad` has `start` (generated frames, `start_mode=add`); `overlay` has `eof_action=pass`, `repeatlast` and timeline `enable`. `atempo` (0.5..100 per instance) exists but is not used.
- ASSUMPTION (SPEC-v3 3.3 does not say how a time remap fits a clip whose EDL times are rendered-clip seconds): the clip length and the audio stay unchanged. Inside a slowmo/speed_ramp window frame k shows clip time `t_start + c_k` (`c_0 = 0`, `c_{k+1} = c_k + speed_k / fps`, speed at the frame's middle, clamped 0.1..4); at `t_end` the picture snaps back to real time (a slow window skips the content it did not reach, a fast one repeats). So every item, caption and sound after a window stays where planned and the beats stay in sync; the planner's slow-mo is a visual beat, like a freeze. The audio is not stretched (it would desync everything after the window).
- slowmo eases 1 -> `speed` over `ramp_s` (ease_in_out) and back before `t_end`, each ramp at most half the window; speed_ramp goes `speed_from` -> `speed_to` on its `ease`.
- Filter per window: `split` the stream; the copy is `trim`med to the window's input frames, re-timed with `setpts` (balanced sum of µs steps by `N`), interpolated by `minterpolate=fps=FPS:mi_mode=mci`, trimmed to the window's frame count and `tpad`ded to its start, then `overlay`ed on the window. A plain `setpts=PTS+START/TB` delay makes `overlay` buffer every frame before the window (2.6 GB RSS for a window at 25 s of 1080x1920 vs 0.24 GB with `tpad`). The stage runs first (time -> freeze -> motion+shake -> grade -> flash) so the other stages draw on the remapped frames; `face_path.subject_faces` maps the faces through the windows too.
- `mi_mode=mci` (default obmc/bilat): bar position max error 0.22 frame on the synthetic test, ~2 s per window second at 1080p, ~8 s at 4K; `mc_mode=aobmc:me_mode=bidir:vsbmc=1` was ~2x slower and not better (0.27); `blend` was closer (0.12) but ghosts. The pipeline test checks content positions within `POSITION_FRAMES`, not per-frame speeds (mci jitters ±0.4 frame per step).
- Shake is drawn as cameras on top of the zoom cameras (one `scale`+`crop` stage): the picture is zoomed in just enough to move (`scale = max(zoom, 1 + 2 A max(1, W/H))`, `A = strength * 0.04` frame widths), and its center follows a seeded (`random.Random(seed)`) path of knots every `1 / (2 frequency_hz)` s, alternating sign with sizes 0.5..1 A, y at 0.6 A half a knot later, cosine-eased; centers are clamped with `motion.safe_axis` so the face stays inside. Same seed -> same render. The features extractor (`features/motion.py`) finds the shake spans of the test render exactly in each window and none elsewhere.


## TASK-211 V3-07a Renderer FX (glitch, RGB split, transitions)

- Verified 2026-11-04 with `ffmpeg -h filter=<name>`, `ffmpeg -filters` and test renders (ffmpeg 9.0.2, ffmpeg-full): `rgbashift` (`rh`/`rv`/`gh`/`gv`/`bh`/`bv` integer px ±255, `edge` smear|wrap, timeline), `geq` (`r`/`g`/`b` expressions reading `r(X,Y)`..., timeline, so `enable='eq(n,K)'` draws one frame), `shuffleframes` (`mapping` repeats frames inside a block, pts stay in order), `xfade` (`fade`, `hblur`, `zoomin`, `fadewhite`, `pixelize`; accepts only 444/planar RGB formats), `trim` start_frame/end_frame, `tpad` start, `overlay` enable + `eof_action=pass`.
- ASSUMPTION: every glitch, RGB split and transition is drawn on its window only: a branch of the stream makes the window's frames, is turned back to yuv420p, delayed by `tpad=start=` and overlaid on the window (`render/window.py`). Running `xfade` on the whole stream (as the normal render's `join_graph` does) round-trips every frame through yuv444p and changed every frame (mean diff ~0.6), and two joins added a frame; windowed, frames outside the windows are bit-identical to a render without items and the frame count is unchanged (pipeline test).
- ASSUMPTION: a transition item marks a window, not a cut between two sources: the Pro Edit clip is one continuous shot (or the normal render's cuts), so the window's frames are split at its middle frame and the part before/after are joined by `xfade` over the window (`pipeline/transitions.join_graph`, padded with clones of the last/first frame, half the window each). An odd window ends unblended on its last frame; a single-frame window is not drawn. The xfade per type: crossfade `fade`, whip `hblur`, zoom `zoomin` (the normal render's crossfade/whip/zoom_punch), flash `fadewhite`, glitch `pixelize` plus glitch frames from the glitch stage (`TRANSITION_GLITCH`, strength 0.6, seeded by the item id). The whoosh of a transition is a sound left to the SFX engine (TASK-214).
- ASSUMPTION: stage order time -> freeze -> motion -> transition -> grade -> glitch -> flash: transitions blend the zoomed picture and are graded with it; glitches and RGB splits sit on the graded picture (a glitch is a digital artifact on top of the look), flashes stay last.
- ASSUMPTION: `offset_px` of rgb_split is pixels of a 1080-wide frame (REFERENCE_WIDTH), scaled to the canvas (proxy 540 -> half) and at least 1 px; red moves at `angle_deg` (0 = right, 90 = up) and blue the opposite way.
- ASSUMPTION: a glitch is seeded by `params.seed` and its first frame (`random.Random`), so the same plan glitches the same way: a stutter (a run of 2 frames repeated 1 + round(2 * strength) more times, the rest of the window plays behind and snaps back at `t_end`) and glitch frames (the first frame plus each other with chance 0.3 + 0.5 * strength: 2 + round(4 * strength) horizontal bands slid sideways and red/blue pulled apart, via `geq`).
- Datamosh is not supported: no ffmpeg filter drops a key frame and keeps motion vectors inside a filter graph (it needs bitstream editing between encodes).
- The RGB-split heuristic (`proedit/features/glitches.channel_offset`, also for the critic) matches red's and blue's edge maps (Gaussian σ1 + Sobel) against green's by normalized cross-correlation (`cv2.matchTemplate` TM_CCOEFF_NORMED, ±16 px): phase correlation of the raw channels failed after a yuv420p round trip, the edge match recovers the split exactly (8 px and 6 px on the proxy).

## TASK-212 V3-07b Overlays (procedural skull/skeleton, emoji/arrow/circle; screen/face/object anchors)

- Verified 2026-11-04 with `ffmpeg -h filter=movie|settb|setpts|overlay|format` and test renders (ffmpeg 9.0.2, ffmpeg-full): `movie` (`filename`, `f`/`format_name` = `image2` reads a `%05d.png` sequence), `settb=expr=1/30` + `setpts=N+first` put frame n of the sequence on frame first + n of the clip, `overlay` (`x`, `y`, `eof_action=pass`, `repeatlast=0`, timeline `enable`) draws RGBA PNGs with their alpha on the window and passes every other frame through bit for bit (lossless test). `format` has `color_ranges`: without `format=pix_fmts=yuv420p:color_ranges=tv` on the main input, range negotiation took the PNGs' full range and the render came out `yuvj420p`.
- Verified 2026-11-04 with Pillow 13.0.0 (`python -c` experiments, contact sheet): `ImageDraw` shapes are not anti-aliased (sprites are drawn 4x and scaled down with LANCZOS); polygon `outline` grows inward (rims are closed lines); `ImageFont.truetype` + `text(..., stroke_width, stroke_fill)` draws Noto Emoji glyphs in one color; no raqm, so ZWJ sequences draw as their separate glyphs; `resize`/`rotate` premultiply RGBA; `paste` without mask copies RGBA and clips negative offsets.
- ASSUMPTION: `asset` is a procedural name (`skull`, `skeleton`, `arrow` pointing right, `circle` ring) or `emoji:<emoji>` (Noto Emoji, white with a dark 5 % stroke, monochrome: the bundled emoji font). Library asset ids are not drawn yet: an unknown asset, or an emoji with a code point the font lacks (U+FE0F/U+200D ignored), is an undrawn problem (`UndrawnItemsError`), never a silent skip.
- ASSUMPTION: screen anchor: (x, y) is the sprite's center in fractions of the frame and `scale` its width in frame widths. Face/object anchor: (x, y) are fractions of the box (0.5, 0.5 = its center) and `scale` is in box widths, so the overlay follows and grows with the face/object; the box is the one after the zoom stage (each frame's camera from `motion.cameras_of` + `motion_time.shaken`, mapped with `motion.crop_of`'s even-pixel crop). Frames of the window without a box take the nearest box of the window; with none at all the overlay falls back to a screen placement. The object is the first `kind="object"` box of the crop plan keyframes (object tracking).
- ASSUMPTION: animations over INTRO_S = 0.2 s: fade (opacity in and out), pop (size × ease "back": grows, overshoots, settles), bounce (size × ease "elastic" over 0.4 s), slide (rises from 15 % of the frame height below, ease_in_out); none. `rotation_deg` turns counterclockwise (Pillow `rotate`, BICUBIC, expand).
- ASSUMPTION: stage order ... grade -> overlay -> glitch -> flash: graphics keep their own colors (not graded), glitches and flashes hit them like the rest of the picture.
- ASSUMPTION: each item's frames are drawn in Python (one PNG per window frame, cropped to the even-pixel box holding every frame, inside the frame) and cached under `data/proedit/overlays/<sha256 of the drawing>`, written atomically; the same plan reuses them. Tolerance of the face anchor in tests: 3 px on the 540-wide proxy (measured max 1.9 px: the face moves in whole source pixels, 1.34 proxy px).

## TASK-213 V3-08 Kinetic captions (Pro Edit caption styles)

- Verified 2026-11-05 with libass through ffmpeg 9.0.2 (ffmpeg-full `subtitles` filter) test renders, and the Aegisub ASS tag reference (https://aegisub.org/docs/latest/ass_tags/): `\t(t1,t2,\fscx..\fscy..)` animates size from the event's start, `\frz` + `\t` swings, `\3c` + `\bord` + `\blur` draw a blurred coloured stroke (the neon halo: measured around the white fill in `tests/pipeline/test_proedit_kinetic_render.py`), `\alpha&HFF&` hides an upcoming word's emoji, `\fn` switches to Noto Emoji. All tags were already used by `pipeline/caption_effects`, except `\blur` and `\bord` on a non-pill word.
- ASSUMPTION: kinetic styles are four YAML files in `proedit/captions/styles/` (`pop`, `bounce`, `single_word`, `neon`: the `CaptionStyleParams.style` values), each a caption template + `motion` (pop|bounce) + `glow`; a test keeps the file names equal to the param values. The existing `captions_templates/` are not touched.
- ASSUMPTION: the existing engine gains one default-preserving parameter, `word_writer` (default `caption_effects.word_text`) in `page_text`, `captions.caption_events` and `captions.build_ass`; kinetic captions pass their own writer. The digest of every existing template's ASS (words, emphasis, speaker color, mark emoji, hook) is identical before and after (test).
- ASSUMPTION: the owner's 105 % cap on the active word applies to the v2 templates; Pro Edit styles may overshoot: pop 70 -> size+8 -> size (90 ms each), bounce 80 -> size+15 -> size-4 -> size (80 ms each), emoji 30 -> 130 -> 100.
- ASSUMPTION: a word is loud when its RMS (`pipeline/loudness`, dBFS of 25 ms frames) is at least `LOUD_OVER_DB` = 6 dB above the median word level of the clip (relative: follows the recording's volume). The caller passes the envelope of the rendered clip's sound (`loud.envelope_of`); only the active loud word shakes (`shake_tags`), and only if `shake_on_loud`.
- ASSUMPTION: only the active word gets motion/glow/shake tags; emphasis words of the clip are drawn at `emphasis_scale` percent (static unless active). In a glow style the active word keeps `primary_color` and the halo is `highlight_color`. Emoji (mark, or keyword if `emoji`) pops for the active word, shows still after it, and is invisible before its word.
- NOT DONE here: no render stage draws `caption_style` items yet (`graph.undrawn` still refuses them); the stage needs the rendered clip's sound for the loud words and is left to the render/audio integration (TASK-214+).

## TASK-214 V3-09a SFX placement engine + whoosh matching

- Verified 2026-11-05 with ffmpeg 9.0.2 (ffmpeg-full) `-h filter=` and test renders: `atempo` tempo 0.5-100 (chained below 0.5); `asetrate` r; `apad` whole_dur ends the stream at the length; `adelay` delays in ms with a fraction (`1000.500`) and `all=1`; `amovie` filename; `amix` inputs/duration/normalize; `rubberband` tempo/pitch (present in ffmpeg-full only). Measured on a 0.5 s noise burst: `atempo=0.625` gives 0.764 s of sound (0.781 s with a silent pad), `rubberband=tempo=0.625` 0.800 s.
- ASSUMPTION: pitch variants are varispeed (`asetrate` = 48000 * 2^(semitones/12), then `aresample=48000`): the same sound on every ffmpeg build. The time stretch to the motion (`fit="stretch"`) uses `rubberband=tempo=` when `ffmpeg -filters` lists it (sample-exact) and falls back to the `atempo` chain (+-35 ms at the end); either way `atrim`+`apad` make the item exactly its length. SPEC-v3 3.3 allows both ("asetrate/atempo or rubberband if present").
- ASSUMPTION: two new `SfxParams`: `pitch_semitones` (-12..12, default 0) and `fit` (`natural` default: the sound at its pitched length, cut with a 10 ms fade at `t_end`; `stretch`: lasts the item). Existing plans are unchanged (defaults).
- ASSUMPTION: ducking under speech is a fixed 6 dB (`SPEECH_DUCK_DB`) on the SFX bus over the transcript's spoken word spans (merged, 50 ms ramps) that an SFX sounds in: deterministic and testable, unlike `sidechaincompress` on the clip's own sound. The bus is mixed with `normalize=0` so the clip's sound keeps its level.
- ASSUMPTION: "B-roll cuts" are the hard cuts the caller passes (`place_whooshes(cuts=)`: scene cuts, joins of cut ranges): Pro Edit has no B-roll item kind. Instant events (punch with 0 ease frames, pop with animation none, cuts) get a 0.3 s whoosh centred on the event; motions shorter than 0.1 s count as instant.
- ASSUMPTION: whooshes are the bundled `whoosh_swift` (0.5 s) and `whoosh_soft` (0.9 s), the one nearest the motion in log ratio (least stretch); gain -8 dB; pitch cycles 0, -2, +2, -1, +1 semitones. Events are placed by priority transition > zoom > cut > pop, then time; a whoosh is dropped with a `PlanNote` when it breaks the sfx stack limit or the intensity/preset SFX density (budgets), moved/dropped off punchlines by `snap.protect_punchlines`. An event an SFX already sounds over gets none.
- ASSUMPTION: an SFX asset is a library asset id (digits; `library_sounds` resolves ids of kind sfx/audio/music) or a bundled sound name with or without extension; `graph.undrawn` refuses unknown or missing sounds. Sounds are read with `amovie` inside the graph (no extra ffmpeg inputs).
- NOT DONE here: no caller runs `place_whooshes` yet (director/API integration, later V3 tasks).

## TASK-215 V3-09b Music bed, silence before drop, riser/impact/bass drop, audio fx

- Verified 2026-11-05 with ffmpeg 9.0.2 (ffmpeg-full) `ffmpeg -h filter=<name>` and test renders (filter reference: https://ffmpeg.org/ffmpeg-filters.html): `amovie` `loop` (0 = forever), `aloop` `loop=-1`/`size` in samples, `atrim` start/duration, `afade` t/st/d, `aecho` in_gain/out_gain (<= 1)/delays/decays (`|`-separated), `bass` g/f (low shelf, default 100 Hz), `lowpass` `frequency` (runtime command, T flag), `asendcmd` `c='TIME TARGET COMMAND ARG;...'` (takes effect on the next audio frame), `aeval` exprs/`c` (per sample), `volume` `eval=frame` (per 1024-sample frame), `aformat` channel_layouts, `amix` normalize=0.
- ffmpeg quirks found by test renders (each fixed in the graph, comments in the modules): `amovie loop=0` restarts timestamps on every loop, so a later `atrim` never ends (the output grew without bound) -> `asetpts=N/SR/TB` before `atrim`. `adelay`'s padding frames carry no timestamp, so `t` is NaN in a following `aeval`/`volume` expression -> `asetpts=N/SR/TB` after `adelay`. `aeval c=same` with a mono sound mixed into a stereo one crashes ffmpeg (SIGSEGV, exit -11, no message); `aeval c=stereo` outputs an unordered "2 channels" layout the AAC encoder refuses -> gates are `aformat=channel_layouts=stereo,aeval=...:c=stereo,aformat=channel_layouts=stereo`.
- ASSUMPTION (instead of reusing v2 `pipeline/music.duck_filter`, `sidechaincompress`): music beds duck by a span envelope over the transcript's speech spans (`envelope.dip_filter`, the same ducking as the TASK-214 SFX), because a compressor's dip depends on how loud the speech is and the plan's `duck_db` (and the acceptance's +-1 dB) must be the dip exactly. Measured: 12.0 and 6.0 dB dips (pipeline test).
- ASSUMPTION: `music_bed` and `silence_before_drop` share the exclusive music track (TASK-202 schema), so a silence is a gap between two beds; a new `MusicBedParams.offset` (default None: continue the bed of the same asset before it as if the music had played on, 0 for the first) keeps the beds one piece of music. Beds loop forever and fade over 10 ms at both ends (no click into the silence or on the drop). The silence also mutes the SFX bus (a riser is cut by it), never the speech.
- ASSUMPTION: `audio/drop.drop_moves` adds the moves around a drop: the bed cut around the silence (`split_beds`, explicit offset), the silence (default 0.2 s, 0.1-0.3 s, ending on the drop's frame), the bundled `riser_swell` stretched to end where the silence starts (up to 1.6 s, -8 dB; left out with a note under 0.3 s of room), `impact_boom` from the drop (up to 1.2 s, -3 dB) and a `bass_boost` audio_fx (amount 0.8, 0.6 s): the bundled pack has no bass-drop sound, so the bass drop raises the lows of the boom and the music. A move that would break a plan rule is left out with a `PlanNote` ("dropped"). No caller runs it yet (director integration, later V3 tasks).
- ASSUMPTION: audio_fx act on the whole program sound (speech + SFX + music) in their window only: dry part gated off and wet part gated on per sample (5 ms ramps inside the window), summed. bass_boost: `bass` +amount*12 dB at 100 Hz. reverb_tail: `aecho` (in/out gain 1, 7 delays 43-409 ms, decays amount*0.6*0.75^n), the echoes ring past the window. lowpass_sweep: the cutoff opens exponentially from 20000*(200/20000)^amount Hz to 20 kHz (muffled into what follows), set every 20 ms by `asendcmd`. stutter: the window's first slice repeated 2+round(6*amount) times (`aloop`, 3 ms fades per slice).
- Test signals: pipeline tests compare waveforms of tonal loops (chord, chirp, bright tones): AAC coding decorrelates white noise between two renders (correlation ~0.94) though the WAV graphs are sample-exact.

## TASK-216 V3-09c Dialogue chain + final loudness

- Verified 2026-11-05 with ffmpeg 9.0.2 (ffmpeg-full) `ffmpeg -h filter=<name>` and test renders (https://ffmpeg.org/ffmpeg-filters.html): `highpass` f, `equalizer` f/width_type/w/g, `acompressor` threshold (linear)/ratio/attack/release/makeup (linear, 1-64), `deesser` i/m/f/s, `loudnorm` i/lra/tp/measured_*/linear/print_format (already used by `pipeline/loudnorm`, SPEC 6.11).
- ASSUMPTION: the dialogue chain is `highpass=f=80, equalizer=f=3000:width_type=q:w=1:g=2.5, acompressor=threshold=0.1:ratio=3:attack=10:release=120:makeup=1.5, deesser=i=0.4:m=0.5:f=0.5` on the clip's own sound (after cuts and the censor filter, before the SFX/music/fx). Measured on sines (`tests/pipeline/test_proedit_mix.py`): 40 Hz is 12 dB under 1 kHz, 3 kHz +2.2 dB over 1 kHz, a 0.5-amplitude 1 kHz tone gains 9 dB less than a 0.02 one, a loud 7 kHz tone is 9.6 dB under a loud 1 kHz one while a quiet one is untouched (the de-esser acts on loud sibilance only).
- ASSUMPTION: the final loudness reuses `pipeline/loudnorm` unchanged (two passes, linear second pass, `target_lufs` of the settings, default -14, loudnorm's `tp=-2`): the first pass measures the same audio graph as the render (`graph.proedit_audio_graph`: cuts + censor + dialogue chain + SFX + music + fx), the second ends the mix (`sound_graph(master=)`). `tp=-2` leaves 1 dB for the AAC encode: measured true peaks -6.7 to -4 dBTP on tonal sources, -2.0 dBTP on a source with 0.95-amplitude clicks (its linear gain would put the peak over the target, so loudnorm limits), integrated -14.0 +-0.05 LUFS in all cases. A silent sound is not normalized (loudnorm reports -inf; `mastered_filter` returns "").
- ASSUMPTION: `render_plan(master=True)` is the default (a Pro Edit is always mastered); the sound tests of earlier tasks render with `master=False` (their absolute levels are the plan's). `proedit_graph`/`sound_graph` default to no chain and no master filter.

## TASK-217 V3-10 Freesound audio library (search, license filter, previews, attribution)

- Verified 2026-11-04 in the official docs (https://freesound.org/docs/api/overview.html, `/authentication.html`, `/resources_apiv2.html`): the text search is `GET https://freesound.org/apiv2/search/` (the old `/apiv2/search/text/` was deprecated in November 2025 and now redirects); auth is a token (`Authorization: Token <key>` header or `token=` parameter) from https://freesound.org/apiv2/apply, OAuth2 is a separate flow; `filter` is Solr syntax (`filtername:value`, multi-word values in double quotes, `type:(wav OR aiff)` for alternatives, `duration:[a TO b]` / `[a TO *]` ranges); `fields` picks the metadata of each result (default `id,name,tags,username,license`); `page_size` max 150; the sound `license` is "Attribution", "Attribution NonCommercial" or "Creative Commons 0" (documented values; older answers carry the deed URL, so both are read); `previews` holds `preview-hq-mp3`/`lq-mp3`/`hq-ogg`/`lq-ogg`; the original (`/sounds/<id>/download/`) is "OAuth2 required"; throttling 60 requests/minute and 2000/day (30/500 for download-class resources), a 429 answers with a `detail`.
- Decision: a token is enough, so the HQ preview (128 kbps MP3 from `cdn.freesound.org`, no key sent) is what is stored (SPEC-v3 5.1: "If only previews are available with a token, document it"), with the sound's license, credit, page URL and download time. OAuth2 (needed for the original quality) is not added: the preview is the simplest option that serves SFX and short beds; a later task may add it.
- ASSUMPTION (not verifiable without a key; no key exists in `.env.local`): the license filter is `license:("Creative Commons 0" OR "Attribution")` (the documented OR syntax with the documented license names). The docs show no `license:` example; if the server ignored it, the check on the returned `license` (`licenses.license_label`: only CC0 and CC BY, by name or deed URL; BY-NC, BY-SA, BY-ND, Sampling+ and unknown values are rejected) still drops every other sound, and a download re-reads the sound by id and checks it again. The recorded answers in `tests/fixtures/freesound` are shaped after the documented field list (not captured live).
- Decision: `FREESOUND_API_KEY` is a `Settings` field read from `.env`/`.env.local` (listed in `.env.example` and `scripts/check_prereqs.py`); without it `GET /api/proedit/audio/freesound` answers `{enabled: false, message: "Add a Freesound key: ..."}` and search/download answer 409 `provider_disabled`.
- Decision: rate limits: `RateLimiter` keeps below 60 requests/minute per process (waits up to 10 s for a slot, else "rate limit reached; try again in N s"); every request is one metered API call (stock `get_json`); 429/401/403 become `StockError` (API 502 `stock_error`). Previews come from the CDN, which is not API-throttled. Tags are validated (`[a-z0-9_-]`, words joined by dashes) so a tag can not alter the filter.
- Decision: attribution is `"<name>" by <user> on Freesound (<page url>), <license label>`; stored for CC0 too (every audio asset stores it, SPEC-v3 1.2) but only CC BY assets are credited. Credits are appended to the clip description under "Sound credits:" (`POST /api/proedit/clips/{id}/credits`, once per line); the export JSON (`clip_metadata`) holds the description, so it carries them without changing `pipeline/export.py`. The director/render integration that calls it for a plan's assets comes with the later Pro Edit API tasks.
- `stock.base._fetch` was renamed `fetch_file` (public, same behavior) to reuse the streaming download; `sounds.library_assets` was extracted from `library_sounds` (same result) to find the assets a plan plays.

## TASK-218 V3-11 Pixabay audio import, own uploads with rights, auto-tagging, starter pack

- Verified 2026-11-04: Pixabay's official API (https://pixabay.com/api/docs/) documents "Search Images" (`/api/`) and "Search Videos" (`/api/videos/`) only ("royalty-free images and videos"); `GET /api/audio/?key=x` answers the same "Invalid or missing API key" as the image search (no audio resource), `/api/music/` is a normal 404 page. Decision (SPEC-v3 5.2): no `PIXABAY_API_KEY` audio integration; the "Import Pixabay file" form is the path: `POST /api/proedit/audio/pixabay/import` (multipart: `file`, `source_url`, `license_confirmed`, optional `title`, `category`). `GET /api/proedit/audio/pixabay` says why (`api: false`). The existing `pixabay_api_key` stays for video stock only.
- Pixabay license (https://pixabay.com/service/license-summary/, read 2026-11-04): free to use, no attribution needed, modification allowed, no sale/distribution on its own, no misleading use. Stored as license `Pixabay Content License`, credit `"<title>" on Pixabay (<url>), Pixabay Content License`. ASSUMPTION: Pixabay audio pages live under `https://pixabay.com/music/...` and `https://pixabay.com/sound-effects/...` (the site's own navigation links; the pages answer 403 to curl, so a page could not be fetched); the URL must be https, host `pixabay.com`/`www.pixabay.com` and start with one of these two sections, which also decides music vs sfx. Anything else (another site, YouTube, a Pixabay photo page) is 422.
- Decision: own uploads (`POST /api/proedit/audio/uploads`) need `rights` (a required form field: `own`, `permission`, `cc_by`, `public_domain`; missing or other values, including the v2 `other`, are 422); it is stored as the license ("Own work", "Used with permission", "CC BY", "Public domain"); `cc_by` also needs `attribution`. Files go through `media_library.store_upload` (sniffed audio, ffprobe, size limit, stored once by content hash: a duplicate is 409) but are not tagged as media-library entries, so they are listed by the audio library, not the Media tab.
- Decision: auto-tagging (`proedit/audio/tagging.py`) is heuristic, no LLM (SPEC-v3 5.4 makes the LLM tag optional): loudness = `loudnorm` integrated LUFS (None under 0.4 s, which EBU R128 cannot gate, and for silence), energy curve = RMS per second as a share of the loudest second, tempo = the beat grid of `proedit/beats` (music only: kind `music`, or `audio` of at least 8 s), key = Krumhansl-Kessler profiles on the mean chroma (None under correlation 0.6), onset sharpness = steepest rise over 4 frames (23 ms) near the peak / 20 dB. The `Asset` model has no sharpness field (and a migration was not worth one number): it is stored as the tag `sharp-attack` / `soft-attack` (threshold 0.6); category and mood are stored as fields and as tags. Categories: whoosh, impact, riser, click, chime, music, other (a given category wins). The bundled pack is classified sensibly (whooshes, boom, riser, click) but `crowd_laugh`/`rimshot_badum` come out as "chime": the heuristics only know the SFX shapes the director places.
- Decision: `freesound.download_sound` now also tags the asset (`tag_asset`; a decode failure is logged and the untagged asset kept, the preview was already checked to hold audio). `test_a_download_stores_the_preview_with_its_license_data` was updated for the added mood/attack tags and measurements (the Freesound-owned tags are still the first four).
- Decision: `scripts/fetch_starter_sfx.py` (`proedit/audio/starter.py`) searches six groups (whoosh 6, impact 5, riser 4, click 3, pop 3, ding 3; one search call each, 40 candidates), keeps CC0 sounds only (CC BY skipped so the set needs no credits), downloads the previews into `data/audio/freesound/` (git-ignored), tags them `starter` with the group's category and writes the generated table `assets/sfx/starter/LICENSES.md` (rows only, never audio). It exits 1 with "Add a Freesound key" without `FREESOUND_API_KEY`; nothing runs at install time. It could not be run against the live API (no key).

## TASK-219 V3-12a Presets x6 (YAML) + rule-based director

- Decision: the six presets are YAML files in `backend/clipforge/proedit/presets/` (one per `ProEditPreset` id), loaded and checked by `proedit/preset_defs.py` (`PresetDef`): allowed kinds, per-intensity budget lowerings (`effective_budget`, never raised), music moods + BPM range + level, caption style, base grade / vignette / grain, overlay set, params / lengths / snap modes per kind, the events that get whooshes, ordered rules, interrupt kinds and the Skull Moment spec. Every param layer is validated against `edl_params` at load time, overlay assets against `overlays/procedural.asset_problem`. Preset looks are original combinations; no third-party preset is copied.
- Decision: a rule's trigger key is `signal`, not `on`: YAML 1.1 (PyYAML) reads a bare `on` key as boolean `True`.
- Decision: the task names the module `director_rules.py` (SPEC-v3 3.5 says `rule_director.py`); the task's file list wins. It is split into `director_rules.py` (steps), `director_build.py` (PlanBuilder), `director_moves.py` (moves + bass drop), `director_skull.py`, `director_moments.py`, `director_music.py` to stay under 300 lines each.
- Decision: the Director places every move where post-processing would snap it and only keeps it if the plan stays valid (track overlaps/stacks via the new public `edl.track_problems`, the intensity budget, no SFX over a punchline word); a move that does not fit is a `LeftOut` with the reason. Rules earlier in a preset therefore win (YAML order = priority); `postprocess_plan` runs afterwards anyway and finds little. The returned plan always passes `validate_plan` + `budget_problems` (checked; a failure is a Director bug and raises).
- Decision: layer kinds. `vignette`, `grain` and `shake` are drawn by their own stage (grade.py, motion_time.shaken) on top of their track, so they now only conflict with their own kind (`edl.LAYER_KINDS`, `edl.excludes`; snap uses the same rule). Needed for "dark grade + vignette + grain" looks and the Skull Moment's shake over its freeze. Tests that used shake/flash or grade/grain as conflicting pairs now use glitch/flash, rgb_split and grade/grade.
- Decision: whole-clip looks (an item from 0 to the clip end: caption style, base grade, vignette, grain, bed) are not counted by any budget (`budgets.is_look`, `clip_duration` param of `enforce_budgets` / `budget_problems`; `postprocess_plan` passes it). Otherwise a base grade would use up the effects budget at Clean.
- Decision: `audio/drop.drop_moves(..., riser=False)` skips the riser: the Skull Moment hits on a freeze with no build-up. Bass drops without a music bed are only the impact SFX + `bass_boost` audio_fx.
- Decision: Skull Moment = at the first frame after the strongest punchline word: freeze, instant `bw` (or `dark`) grade_change, skull overlay on the face, instant zoom_punch 1.25, shake (<= 0.5 s), impact + bass drop (silence before it over a bed, no riser), hold, then a `whoosh_swift` at the snap back. Hold = preset `hold_s` raised up to 2.0 s to keep the whoosh one SFX spacing after the impact, cut to fit before the clip end (min 1.0 s, else no Skull Moment). Steps are placed in that priority: below Extreme the budgets drop the lowest ones (Pro: 4 effects per 5 s leaves out the shake; 1 SFX per 2 s leaves out the snap-back whoosh when the hold is under 2 s). On the fixture the 'cheese.' hold is 1.333 s (clip end). The full sequence is asserted at Extreme.
- Decision: the Skull Moment preset has no base grade (the clip stays in color so the B&W hold reads as a change). Cinematic's optional letterbox is skipped: there is no EDL kind for it. Dark Edit's "neon single-word" captions map to the `neon` caption style. The bundled pack has no glitch SFX: Glitch uses `tick_click`.
- Decision: pattern interrupts (Pro/Extreme) fill every span longer than the intensity gap with the preset's interrupt kinds in turn, tried at beats, then word starts, then a 0.5 s grid within [gap start + 2 s, + 4 s]. Cinematic and Skull Moment also allow a soft whoosh SFX (`whoosh_soft`, -10 dB) as the last interrupt kind: their visual effect budget is used by the setup push / skull hit, and SFX count as interrupts (`INTERRUPT_KINDS`). On the fixture no gap is left for any preset.
- Decision: the Director does no I/O. The caller passes a `MusicChoice` (asset, `MusicGrid`, offset); `pick_music(spec, candidates)` scores mood overlap + BPM in range (+2) / unknown (0) / outside (-1). Bundled loops have no BPM tag, so they rank by mood only. Without music there is no bed and beat/downbeat rules find no moments.
- Decision: key words come from the clip's emphasis words; when it has none (the fixture), the longest word of >= 4 letters per sentence. Punchline words are left to the punchline rules.

## TASK-220 V3-12b Phonk Edit / Pro style-trait acceptance test

- Decision: the acceptance test (`backend/tests/pipeline/test_phonk_traits.py`) renders the fixture clip (sample.mp4 16.5-34.5 s, `proedit_signals_expected.json`) with the rule-based Director at Phonk Edit / Pro over a proxy libx264 render, then measures the output with the shared `proedit/features` extractors (`measure_video`). The thresholds come from SPEC-v3 2.1: mean cut/zoom interval <= 1.5 s, >= 1 zoom punch per 3 s, >= 60% of cuts/zooms on a beat (within 1/fps, SPEC-v3 assumption 6), >= 1 flash or shake per 5 s, output mean luma below the source's.
- Decision: trait definitions. Mean interval = `features.cuts.mean_interval` over the detected cuts plus every zoom event start (punch-ins and snap-backs); punch = a zoom event of kind "punch" with scale > 1; on-beat share = `on_beat_share` of those events against the bed's beats in clip seconds; flashes + `ShakeSpan`s per 5 s; source luma = `measure_video` of the source span, full frame.
- Decision: the bed is a generated 140 BPM 808-like kick loop (a 115 -> 55 Hz sine sweep per beat, louder downbeat), written in the test (SPEC-v3 assumption 8). `pick_music` picks the bundled `night_drive` for Phonk, but its grid reads ~100 BPM (outside Phonk's 120-160 range) and gave only 0.67 punches per 3 s. The grid is read back with `beats.music_grid`, as a caller would.
- Decision: the Phonk trait test drops `caption_style` items before `render_plan` (no captions bear on the five traits). Superseded for rendering by TASK-224: the renderer now draws kinetic captions (see TASK-224).
- Decision: new preset field `beat_lengths: {kind: beats}` (1-16). Over a bed, a move whose start snaps exactly to a beat ends that many beats later (`director_moves.beat_end`), unless the kind is end-anchored; without a bed, or past the last beat, the length in seconds applies. Phonk sets `zoom_punch: 1, shake: 1`, so punch snap-backs land on the next beat too. With fixed 0.5 s punches the snap-backs fell off-beat and the on-beat share was ~53%.
- Decision: a `beat` rule now counts its `phase` from the first downbeat in the clip (`director_rules._bar_start`), so Phonk's "every 4, phase 2" is the third beat of every bar whatever the clip's beat phase. Counting from the first beat in the clip put the shake/flash on the same frame as a downbeat punch for some beds, and the extractors do not measure motion into or out of a flash frame, so those punches were not seen.

## TASK-221 V3-13 LLM Director: prompt, schema, retries, post-processing, cost estimate + usage meter

- Verified 2026-11-04: no new third-party API. The Director uses the existing `clipforge.llm` clients (`LLMClient.complete_json`, the same Copilot / OpenAI-compatible / Ollama HTTP calls and their token reporting into `usage.record_tokens`) and Pydantic v2's `BaseModel.model_json_schema()` (the reply schema and each kind's params schema in the system prompt) and `ValidationError.errors()` (via `curate_prompt.describe_errors`) from the installed versions.
- Decision: the module is split to stay under 300 lines: `director_llm.py` (the run: ask, validate, retry, post-process, fall back), `director_prompt.py` (`DirectorRequest`, `DirectorReply`, system/user messages), `director_catalog.py` (the asset catalog: bundled SFX and loops, library sfx/audio/music assets with tags + category/mood, procedural overlays; `catalog_problems`), `director_cost.py` (estimate, month spend, cap). The system prompt is `prompts/proedit_director.md` (string.Template: `$schema`, `$params`, `$tracks`).
- Decision: the reply is `{rationale, items: [{kind, t_start, t_end, params, reason}]}` (extra fields forbidden); the code numbers the items 1..n, sets `source: auto` and `created_by: "director"`. A reply is invalid when Pydantic rejects it (JSON, kinds, params ranges), when it uses a kind the preset does not allow, when `edl.plan_problems` finds overlaps/stacks/past-the-end items, or when an sfx/music_bed/overlay asset is not in the catalog (an overlay may also be any `emoji:<glyph>`). Retries (`curate.MAX_RETRIES` = 2, 3 calls in all) resend the user message with the numbered problems.
- Decision: a valid reply is post-processed like the rule-based plan (`postprocess_plan`: snap, budgets, punchline SFX; then `place_whooshes`). If problems remain afterwards (`plan_problems` + `budget_problems`), or no LLM is configured, the request fails (`LLMError`), 3 replies are invalid, or the cap is reached, the result is the rule-based plan (`rule_plan`, always computed first) with the reason in `DirectorResult.fallback`.
- Decision (SPEC-v3 assumption 10): no LLM provider reports a price, so the USD spend is reported tokens x `proedit.usd_per_million_tokens` (owner-set, default unset). `proedit.monthly_cap_usd` requires that price (config validation error otherwise). Without a price, the estimate shows tokens only ("no price set: proedit.usd_per_million_tokens") and there is no cap.
- Decision: Pro Edit tokens are recorded under the usage kind `proedit` with `cost_usd` (the `usage.recording` context gained `kind`, `usd_per_token` and a `tally`; its defaults are unchanged, so v2 records are still `llm_tokens` without cost). They therefore do not count toward the generic `llm_tokens` cap (no double counting); the Pro Edit API (TASK-224) should still call `usage.check_caps` before queueing.
- Decision: the estimate shown before a run is (system + user message characters) / 4 input tokens plus the rule-based plan serialized as a reply / 4 output tokens, per call; `max_calls` = 3 gives the worst case with every retry (`CostEstimate.text()`).
- Decision: "cap blocks a run with a clear error" and SPEC 3.5 "rule fallback when the LLM is unavailable" are both kept: `check_monthly_cap` raises `ProEditCapExceeded` (a `UsageCapExceeded`; message names the cap, the month's spend and the estimate and how to change `proedit.monthly_cap_usd`) for the API to answer before queueing; inside `director_plan` the same check runs before every call and, when it trips, no call is made and the rule-based plan comes back with that message as the reason.

## TASK-222 V3-14a Critic: capability check, frame/audio sampling, scoring

- Verified 2026-11-05 (SPEC 0.1), image request shapes per provider: OpenAI chat completions content parts `{"type":"text"}` + `{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}`, Responses API `{"type":"input_text"}` + `{"type":"input_image","image_url":"data:..."}` (https://developers.openai.com/api/docs/guides/images-vision); Anthropic Messages `{"type":"image","source":{"type":"base64","media_type":...,"data":...}}` blocks before the text, image cost about ceil(w/28) x ceil(h/28) tokens (https://platform.claude.com/docs/en/build-with-claude/vision); Ollama `/api/chat` user message `"images": [base64...]` (https://docs.ollama.com/api/chat).
- Assumption: GitHub Copilot has no public doc for images; third-party clients send the header `Copilot-Vision-Request: true` with OpenAI-style image parts (karthink/gptel `gptel-gh.el`, openclaw/openclaw `src/media-understanding/image.ts`, cactus-compute/cactus `github-copilot-headers.ts`). `critic/vision.py` does the same on /chat/completions and, for responses-only models, on /responses.
- Decision: the clients stay text-only (`complete_json`); `critic/vision.complete_with_images` builds the image request per provider with the client's own URL, credential, headers and transport, and records reported tokens via `usage.record_tokens` (so `metered` books them as `proedit`). The Claude Code CLI has no image path here: it is "cannot send images" -> Director only.
- Decision: capability check = one probe per (provider, endpoint, model), cached in-process: a 64x64 red PNG and "what color is it?" in JSON. Vision iff the reply contains the word "red". HTTP 400/413/415/422 = the model refuses images (cached). Another failure (network, 5xx, 401) is not cached and counts as no vision for this run (message "Could not check whether ... accepts images"). No LLM / no image path -> director-only without a request. Every director-only result carries the UI message "... Pro Edit runs the Director only (no critic)."
- Decision: frame sampling (`critic/sample.py`): frame numbers, not times. Item first frame = round(t_start x fps), last = round(t_end x fps) - 1 (clamped to the clip), plus a 1 fps baseline (0, fps, 2fps...). Same frame = one sample with merged reasons. Over `proedit.critic_max_frames` (default 24, 1..60), item boundaries win and are spread evenly (index floor(i(n-1)/(k-1))), then the baseline fills the rest the same way. One ffmpeg pass `select='eq(n,a)+...'`, `scale=360:-2`, JPEG q 4 (`FRAME_WIDTH` 360 keeps image tokens low: 13 x 23 patches for 9:16).
- Decision: audio summary (`critic/audio_summary.py`): the mix has no stems, so speech level = frames during words without SFX, music level = frames inside music_bed items with no word and no SFX (a frame that overlaps an excluded span at all is left out, else boundary frames leak 20 dB of speech into the bed), SFX level = frames inside sfx items; levels are power means of `pipeline/loudness` 25 ms RMS frames at 16 kHz; curve every 0.5 s; clipping = samples (any channel, 48 kHz f32) >= 0.999 FS; integrated LUFS / true peak from the loudnorm measurement used by mastering.
- Decision: checklist ids (SPEC-v3 3.7 order): hook, dead_air, captions, crop_faces, effect_balance, audio_balance, punchline, loop_ending, preset_faithfulness. Reply `{"scores":[{check, score 0..10, reason}]}`, every check exactly once (Pydantic); invalid -> resent with problems, 3 calls max (like the Director). No valid reply, an LLM error or the cap -> `CriticResult.failure`, no scores (the Director's edit stands). `passes(scores, threshold)` needs every score >= `proedit.critic_threshold` (default 7); empty scores never pass.
- Decision: cost estimate per call = text tokens (chars / 4) + per-image ceil(w/28) x ceil(h/28) + a 9-check reply; the monthly cap is checked before each critic call (`check_monthly_cap(who="the critic")`), and the vision probe and critic calls are metered as usage kind `proedit`. `director_llm._metered` moved to `director_cost.metered` to be shared.

## TASK-223 V3-14b Critic revisions loop: EDL changes, rounds, early stop, cost cap

- Verified (SPEC 0.1): no third-party API, filter or model is new in this task; it reuses the critic calls of TASK-222 and the plan validation/post-processing of TASK-203/204/221.
- Decision: the critic's reply gains `changes` (default `[]`): `{"op":"add", kind, t_start, t_end, params, reason}`, `{"op":"remove", item_id, reason}`, `{"op":"modify", item_id, t_start?, t_end?, params?, reason}` (a modify must change something; named params are merged into the item's). A malformed change makes the reply invalid (resent with its problems like a missing check); a well-formed change that breaks a rule is ignored with the reason.
- Decision: changes apply one at a time in reply order; ignored (with `IgnoredChange.problem`) when: the id is not in the plan; the item is the user's (`source: manual`, the critic never touches it); an add's kind is not in the preset; or it adds a problem `edl.plan_problems` did not report before (params, clip end, track overlaps, stack limits) or names an asset missing from the catalog. Added items get the next free id and the change's reason (the UI shows it).
- Decision: an applied revision becomes version + 1, `created_by: critic_revision`, then runs the Director's post-processing (`director_llm.finish_plan`: snapping, punchline protection, budgets, whooshes). Still invalid -> the whole revision is dropped (its changes reported as ignored). A critic-added/modified item that the budget then drops is reported as ignored with the post-processing reason.
- Decision: "what changed" = the diff by item id between the judged plan and its revision (`PlanChange{op, item_id, before, after, reason}`; reason = the critic's, or "dropped/moved by post-processing: ..."), stored on the round: `CriticRound` gained `plan_version`, `changes`, `ignored`, `notes` (defaults keep old rows valid; stored in `pro_edit_run.critic_scores` JSON).
- Decision: a round = render the current plan's proxy, score it, and (unless every score >= `proedit.critic_threshold`) revise it. `proedit.critic_max_rounds` (default 2, 0..3; 0 = no critic). The last round's revision is kept without another critic call (its changes were validated by code); the next render is the final. Early stop: all scores pass (`passed`), no change applied (`no_changes`). Vision is checked before the first proxy render (no wasted render when the model cannot see images).
- Decision: cost guard: `critique` checks the monthly cap before every call (`CriticResult.cap_reached`); from round 2 the loop also checks the cap against the last round's estimate before rendering the next proxy (`who="the critic's next round"`), so the cap blocks further rounds without spending a render. The plan stays at the last revision.
- Decision: the critic's system prompt now lists every kind's track and params JSON Schema (static, ~6.6k tokens with the checklist); the user message adds the preset's allowed `kinds`, the `threshold` and the asset `catalog` (ids + tags).

## TASK-224 V3-15 Pro Edit API + jobs + progress/ETA integration

- Verified 2026-11-07 with `ffmpeg -hide_banner -h filter=subtitles` ("Render text subtitles onto input video using the libass library") and `ffmpeg -formats | grep f32le` ("DE f32le PCM 32-bit floating-point little-endian"), ffmpeg 9.0.2. Verified 2026-11-07 in tests: FastAPI 0.162 accepts a Pydantic model as query params (`Annotated[ProEditOptions, Query()]`); `extra="forbid"` answers 422 for an unknown param. No new third-party API.
- Decision: kinetic captions are a render stage after overlays and before glitch/flash/grade (so effects hit the text like the picture). One ASS file per `caption_style` item (`captions/kinetic.kinetic_ass`, sized to the output frame) drawn with libass; "loud" words come from the clip's base sound (mono f32le at a low rate), not the final mix, so music does not mark words loud.
- Decision: a start copies the original as a new clip (`duplicate_clip` with title + " — Pro Edit", `parent_clip_id`, `variant: pro_edit`, status rendering) and copies the parent's crop plan; the original is never written. Only originals can start (422 `not_an_original`); jobs on a variant use regenerate/critic/render (422 `not_a_proedit_variant` otherwise).
- Decision: one active run per variant: a queued or running run makes regenerate/critic/render/patch/reset answer 409 `proedit_busy`. critic/render/reset need a plan (409 `no_plan`).
- Decision: the editor's PATCH and reset store a new plan version (created_by user) and never render; the editor calls `POST .../render`. A patched item equal to the stored one (ignoring `source`) keeps its source; every other item becomes `manual` (the critic never touches it). Invalid items answer 422 `invalid_plan` with `problems` (model errors, `plan_problems` with the clip length, `catalog_problems`).
- Decision: options are `{preset, intensity, style_recipe_id, music, use_critic}`; music is `auto` (the preset's pick of the bundled loops), `none`, or a catalog music asset id/name; regenerate without options reuses the variant's last run's options (else the plan's preset/intensity/recipe). Options are stored on the run.
- Decision: job steps plan -> proxy -> critic -> final with weights 10/15/30/45 (rendering dominates the time); "proxy" is round 1's proxy render, "critic" the later rounds (progress (n-1)/N). A render-mode run jumps to "final". Proxies are cached per plan id in the job dir. `job_concurrency.proedit: 1` (renders are heavy). Only process/reprompt jobs move the project's progress now (render and proedit do not).
- Decision: the estimate endpoint calls no LLM: the Director part is `estimate_cost` on the rule plan; the critic part is `estimate_critic_cost` on placeholder frames of the real sample count and output size plus a silent audio curve, times `critic_max_rounds` (0 with `use_critic: false`). It builds the real signals (face detector included), so it needs a processed project (409 otherwise).
- Decision: why the rule Director planned (LLM failure, cap) and why the critic stopped early (no vision, cap, failure, off) are stored as run `notes` for the UI; the run's `cost_actual` stays None when no priced LLM call happened.
- Decision: the Pro Edit job is a new `Job.kind` "proedit" (SPEC-v3 does not name it; the v1 literal test now lists it) so it shares the worker, resume, poison-job handling and the progress/ETA of every job.
- Decision: a failed run marks its variant failed (if still rendering) and sends `render_failed`; a poison job (stopped the app too often) fails its runs too. Agents may use every Pro Edit endpoint (13 MCP tools): a variant is a draft clip, posting it stays human-only.

## TASK-225 V3-16 Pro Edit dialog + progress view + gallery/inbox variant cards

- Verified 2026-11-08 in `node_modules/@phosphor-icons/react` 2.1.x (SPEC 0.1): `MagicWandIcon`, `SkullIcon`, `WarningIcon`, `WarningCircleIcon`, `ArrowSquareOutIcon`, `ChecksIcon`, `CheckIcon` exist. Playwright `screenshot({animations: "disabled"})` finishes CSS transitions (docs: playwright.dev/docs/api/class-page#page-screenshot).
- Decision: one `GET /proedit/clips/{id}/choices` endpoint feeds the dialog (presets in `ProEditPreset` order, music auto/none/bundled loops/uploads, caption recipes, campaign `max_intensity`/`allow_heavy_edits`) instead of the UI hard-coding presets or reading several endpoints.
- Decision: preset previews are CSS looping approximations (grade filters, vignette, grain, punch/shake keyframes, glitch ghost, skull icon) over the project thumbnail, not rendered sample videos: no new assets and they play instantly. `prefers-reduced-motion` stops the loops.
- Decision: the campaign's max intensity is a UI cap only (the intensity slider stops there); with no campaign or no autopilot row the cap is "extreme". `allow_heavy_edits` "false" shows a non-blocking warning; unknown shows "does not say whether heavy edits are allowed".
- Decision: the dialog turns into the progress view after Run (Plan / Proxy / Critic round n/N / Final render from the job's steps; N from `/proedit/status` `critic_max_rounds`); closing it keeps the job running, and the variant card shows its own progress pill.
- Decision: in the gallery a variant sits right after its original with a "Pro Edit" badge and a "Pro Edit of “title”" link; its Render goes to `/proedit/clips/{id}/render` and its Edit to the original's Pro Edit page, because the v1 editor/render would overwrite the variant's video (the Pro Edit editor is TASK-226/227).
- Decision: "Approve Pro Edit" in the inbox finds the variant's draft for the same campaign or creates one (`POST /drafts`), then approves it; "Approve both" approves the variant first, then the original (so a failing variant leaves the original waiting). Both are hidden once the original's draft is decided.
- Decision: the inbox keyboard shortcuts (A/R/E/J/K) are ignored while focus is inside a dialog, so typing in the Pro Edit dialog never approves a draft.

## TASK-226 V3-17a Pro Edit editor: side-by-side preview + EDL lanes

- Verified (SPEC 0.1): no new third-party API, library or icon; the editor reuses `useDragFrom` (gained an optional `onEnd`, default unchanged), `lib/layers.dragSpan`, `lib/timeline` and `@phosphor-icons/react` icons already in use (`ArrowsClockwiseIcon`, `PlayIcon`, `PauseIcon`).
- Decision: the editor lives on `/clips/{original}/proedit` (the page that listed the variants): it shows the variant named by `?variant=` (default the newest; a picker when there are several). `/clips/{variant}/proedit` redirects there; the gallery/inbox/progress links now open the variant (`proEditPath(original, variant)`).
- Decision: 8 lanes, one per EDL track (Zoom, FX, Grade, Overlays, Captions, SFX, Music, Audio FX), so every item is visible and editable; overlapping items on one lane stack on rows (touching ones share a row).
- Decision: snap targets = word starts and the plan's music beats from a new editor-only `GET /proedit/clips/{id}/timing` (fps, rendered-clip length, words in clip seconds, beats of the plan's beds from the cached music grid) — signals are not persisted, so recomputing them for the editor would be slow; plus other items' edges and the playhead. Tolerance 8 px; then times land on the frame grid (a move keeps its frame length, a trim keeps >= 1 frame).
- Decision: the Pro Edit side plays the variant's rendered file from `GET /proedit/clips/{id}/video` (inline; `?v=` busts the cache after a re-render) because `/clips/{id}/preview` would make a v1 preview. The original plays muted so only the Pro Edit's sound is heard; both play/pause/seek together.
- Decision: a finished drag or an arrow-key nudge (1 frame, Shift 10) PATCHes the whole item list at once (new plan version, shown optimistically; a 422/409 snaps back and shows the server's message). Nothing renders on edit; "Render plan vN" appears when the newest done run rendered another plan. Edits are locked while a job of the variant is queued/running; when it ends the plan, timing, runs and video reload.
- Decision: the timing and video endpoints are editor-only (behind the Pro Edit flag, not in `/api/v1` or MCP), like the Pro Edit audio files.

## TASK-228 V3-18a Style learning: links, limits, rights confirm, download + guaranteed delete

- Verified 2026-11-08 (SPEC 0.1): the yt-dlp selector `bv*[height<=720]+ba/b[height<=720]` is the ingest selector with 720 (yt-dlp "Format Selection" filters, https://github.com/yt-dlp/yt-dlp#format-selection); tests run the installed yt-dlp on canned format lists (a 1080p format whose file is missing is never chosen). `download.probe()` reads `duration` without downloading; a direct media link (generic extractor) has none, so its length and height are checked with ffprobe after the download (and the media is deleted either way).
- Decision: the media directory is `data/work/style_<reference id>` (not the recipe id) so two references never share one; a leftover directory of a crash is cleared before each fetch and one reference is fetched at a time (409/`ReferenceBusy`).
- Decision: `finally` removes the directory and raises `StyleFetchError` if it is still there (the "assert the directory is gone" of SPEC 4.2); `deleted_at` is set whether the analysis worked or not, `analyzed_at` only on success, so "analyze" can be run again for failed references only.
- Decision: the rights checkbox is `rights_confirmed: Literal[True]` in the create body: a missing or false value is a 422 and nothing is stored; every reference gets `rights_confirmed_at` = the creation time. The ToS notice text comes from `GET /proedit/style-recipes/terms` so the UI (a later task) shows the server's text and limits.
- Decision: analyzing is one synchronous request (<= 5 links x <= 3 min, 720p) instead of a new job kind: job kinds are tied to clips (`Job.clip_id`, progress/ETA) and the task only asks for fetch + delete; a job and progress can follow with the UI. Per-reference numbers (`VideoFeatures` as JSON: cuts, motion, color, flashes) are stored under `features["references"]`; TASK-229 aggregates them.


## TASK-229 V3-18b Style learning: cut/motion/color/flash features on references

- Verified 2026-11-08 (SPEC 0.1) against the installed tools: ffmpeg 9.0.2 `ffmpeg -h filter=vignette` (angle default PI/5, x0/y0 = w/2,h/2, aspect 1/1; the factor is cos(angle * d / dmax) ** 4 on the raw Y plane, measured on flat grey: PI/8, PI/5, PI/4 read 0.25, 0.40, 0.50), `-h filter=rgbashift` (rh/bh px, `enable`), `-h filter=noise` (c0s/c0f=t; measured sigma = c0s / sqrt(3) on limited-range Y: c0s=20 reads 0.0485 vs 0.0527 expected after h264). OpenCV 5.0.0 `cv2.filter2D(src, ddepth=-1, kernel)` (https://docs.opencv.org/5.x/d4/d86/group__imgproc__filter.html). Immerkaer, "Fast Noise Variance Estimation", CVIU 64(2) 1996 for the noise kernel.
- ASSUMPTION: vignette strength is estimated per frame from the corner (d >= 0.85 half-diagonals) to middle (d <= 0.35) ratio of L + 16*255/219 (ffmpeg's vignette darkens the limited-range Y toward 0, so full-range luma follows f*(L + 18.6) - 18.6) matched to the cos^4 model; angle / (pi/2) = render/grade.py's VignetteParams.strength. Median over frames. Dark corners in the content also read as a vignette (testsrc2 ~0.07, the cut fixture ~0.3); a frame with a middle darker than 8/255 is skipped; corners clipped to black saturate near 0.65.
- ASSUMPTION: grain is the robust Immerkaer noise sigma (1.4826 * median |Laplacian-difference response| / 6, luma 0..1) at the video's own size, 1 frame a second (a second decode pass): scaling to the 320 px analysis width smoothed noise away (c0s=30 read 0.028 instead of 0.079). Pro Edit output and references are both measured at their own size.
- ASSUMPTION: glitches = runs of RGB-split frames (`features/glitches.channel_offset` at 320 px, shifts up to 12 px = 40 px of a 1080 frame, the rgb_split item maximum) + frame-difference spikes: runs of <= 2 frames that each differ >= 0.08 (mean |grey diff|) from the frame before and after which the picture returns (<= 35 % of the jump); flash, cut and split frames make no spike.
- Decision: the beat grid of a reference comes from its own audio (`beats.music_grid`); cuts and zoom starts within one frame (SPEC-v3 9.6) of a beat count as on beat; no audio stream or < 4 beats -> bpm and shares None. Speech-only audio still gets a (meaningless) grid; TASK-230 adds music presence.
- Decision: the stored reference features become `{video: VideoFeatures, rhythm, motion (punches/ramps/shakes: count, per_minute, median amplitude, median duration), look (vignette, grain), glitches}`; zoom amplitude = max(scale, 1/scale) - 1. `measure_video` gained `on_frame` (default None: same output) so the extra extractors share its one decode pass.

## TASK-230 V3-19a Style learning: caption OCR + audio/structure features

- Verified 2026-11-08 (SPEC 0.1) on this Mac (arm64): OCR engine = Tesseract 5.5.4 from Homebrew (`tesseract --version`: leptonica-1.87.0, `tesseract --list-langs`: eng, osd; Apache-2.0, https://github.com/tesseract-ocr/tesseract). Apple Vision via pyobjc was not used: pyobjc is not installed and Tesseract needs no new Python dependency. `tesseract --help-extra`: `tesseract imagename|imagelist|stdin outputbase|stdout [options...] [configfile...]`, `--psm NUM` (3 = fully automatic page segmentation), `-l LANG`; the `tsv` config writes `level page_num block_num par_num line_num word_num left top width height conf text` (level 5 = word, conf 0..100, -1 for non-words); with an image list file `page_num` counts the listed images from 1 (one process for a batch of frames). OpenCV 5.0.0 `cv2.connectedComponentsWithStats(image, connectivity=4)` -> (count, labels int32, stats [left, top, width, height, area], centroids). librosa 0.11.0 `librosa.onset.onset_detect(*, y, sr, onset_envelope, hop_length, backtrack, energy, units, normalize, sparse)` (units="time"). macOS `say -o file.aiff` for the speech fixture (tests skip without it).
- ASSUMPTION: captions are the outlined/bold kind (white or colored fill, dark outline). Raw OCR of a frame over a busy background read nothing; the glyph mask (`features/glyphs.py`: 4-connected components of luma > 60 that do not touch the border, glyph-sized 0.8-15 % of the height, <= 25 % of the width, fill >= 10 % of the box, counters inside another glyph's box dropped, thickened by 6 % of the median glyph height, black on white) read the fixture's lines at 94-97 % confidence. Words under 60 confidence are dropped. A caption line needs >= 2 letters and a glyph height >= 2 % of the frame (testsrc2's timestamp and corner counters are no captions).
- ASSUMPTION: caption size = the 80th percentile of the line's glyph heights / frame height (about the cap height; measured 0.0406 vs 41/960 = 0.0427 for Montserrat ExtraBold 56 px); position = center of the line's glyph box; color = median RGB of the glyph fill pixels; features = medians over every line read at 2 frames a second (longer captions weigh more), uppercase ratio over all letters read. Without tesseract `captions` is None (warning logged), the rest of the analysis still runs.
- ASSUMPTION: music presence / speech = YAMNet "Music" / "Speech" score >= 0.3 (the signals step's ACTIVE_SCORE) per frame; the reference has music when >= 25 % of its frames do, and only then gets a BPM, beat grid and drops (`beats.grid_of_samples`). A bare click track is not "Music" to YAMNet (so the TASK-229 beat-cut fixture has `audio.bpm` None while `rhythm.bpm` keeps the grid).
- ASSUMPTION: SFX = librosa onsets not covered by a speech frame and not within 0.07 s of a beat or half-beat of the regular grid at the BPM, phased by the circular mean of the tracked beats: the tracked beats themselves snap onto loud SFX (an SFX at 3.125 s moved the beat to 3.13), so they cannot be used directly. A kick cut off before it decayed made onsets of its own at half-beats (fixture kick now 0.45 s).
- ASSUMPTION: silence before a drop = a run of >= 0.1 s in the 1 s before it that is >= 30 dB under the drop's first-beat level (20 dB also matched the fixture's quiet intro at 10 % = -20 dB). Loudness curve = `critic/audio_summary.loudness_curve` (0.5 s steps, dBFS).
- ASSUMPTION: structure effects = cuts, zoom/shake/flash/glitch starts and SFX onsets; hook = time to the first cut or first drop (whole video without either); ending "loop" when the first and last frames' cut descriptors are closer than the cut threshold (0.3), else "hard_cut"; effect density per 5 s window (the last one may be shorter).
- Decision: `store.measure_features(path, cfg=None)` returns `analyze.analyze_reference_media`: the TASK-229 keys plus `captions`, `audio` (None without an audio stream), `structure`. YAMNet is loaded from `cfg.models_dir` only for a video with audio; a missing model is a StepError (the reference's error), like the signals step.

## TASK-231 V3-19b Recipe aggregation, style-match score, recipe editor/import/export

- Decision: a recipe's targets are 28 named metrics (`proedit/style/metrics.py`: rhythm, motion, look, effects, captions, audio, structure), each read from the stored per-reference features by a path reader (`drops_per_minute` derived from drops and duration, `effects_per_window` the mean of the 5 s density, `loop_ending` 1/0). Each metric carries the slider bounds/step of the editor and a tolerance (the least range width it is scored against). A reference missing a metric (no audio, no captions) is left out of that metric (`count`).
- Decision: aggregation = median, min and max over the references that have the metric, rounded to 4 decimals; caption color = per-channel median RGB. Stored as `StyleRecipe.features["targets"]` next to `features["references"]`, so no migration. Re-analysis aggregates again and overwrites hand edits (the references are the source of truth); import and hand edits store `count` 0 for new targets.
- Decision (documented formula, `proedit/style/recipe.py`): per metric `width = max(high - low, tolerance)`, `outside = max(low - v, v - high, 0)`, `score = max(0, 1 - outside / width)`; match = mean over the recipe's metrics the video has; 0-100 = round(100 * match); identical features score exactly 100. The unit tests pin this on the 3-reference fixture.
- Decision: the description is written by the LLM (one metered call, `DESCRIBE_SYSTEM`, JSON `{description}` <= 400 chars) from the target summary only, falling back to a rule-based text (`describe_rules`) on any LLM error or invalid reply, so an offline install still gets a description.
- Decision: the Director reads only `{name, description, targets: {metric: label, unit, target (median), low, high}, caption_color}` of the recipe (`director_recipe`), never the per-reference features (big, and they would leak links' measurements).
- Decision: export = `StyleRecipeExport` `{format: "clipforge.style_recipe", version: 1, name, description, reference_count, targets}` (`extra="forbid"`): no links, paths, per-reference features or media. Import refuses any other field (422) and unknown metric keys, and makes a new recipe without references (`reference_count` copied for information).
- Decision: the style-match of a rendered variant is measured on demand (`POST /proedit/clips/{id}/style-match[?recipe_id=]`, default the current plan's `style_recipe_id`) with the same analyzer as a reference (`store.measure_features`), and cached in the project's work dir as `style_match_<clip>.json` keyed by the video's mtime and the recipe; `GET` answers null when it is stale. Synchronous like the reference analysis (TASK-228 decision); 409 without a recipe, a rendered video or on an analysis error.
- Decision: the recipe page is `/proedit/style-recipes` (no sidebar entry, per the Pro Edit isolation rule SPEC-v3 0.13); it is linked from the Pro Edit dialog's recipe field ("Manage style recipes") and the style-match panel. A slider moves the target and its range together (keeping each side's width, inside the slider's bounds); bounds widen to hold a measured range outside them. Style recipe endpoints stay under `/api` only (not `/api/v1` or MCP), like TASK-228's.

## TASK-232 V3-20 Campaign/autopilot integration (2026-11-08)

- Decision: the autopilot makes a Pro Edit variant (`autopilot/proedit.py`, called by `pipeline.make_drafts` after the drafts are saved) only when `AutopilotSettings.proedit_enabled` and the campaign's `allow_heavy_edits == "true"` (`"false"` and `"unknown"` both mean no, SPEC-v3 1.5), `proedit.enabled` is on and no monthly usage cap is used up. Variants are made for the new *pending* drafts only: a `needs_fix` clip breaks a campaign rule, and its copy would too, so spending LLM credits on it is wasted; the owner can still press Pro Edit by hand.
- Decision: options of an autopilot variant = the autopilot's preset at its `proedit_max_intensity` (the cap is also the chosen intensity; no auto-intensity exists), critic on, auto music, no recipe. A failed `start_run` is logged per clip and never raised, so the drafts stay.
- Decision: no extra draft is made for the variant. The inbox already lists variants under their original's draft (TASK-225: Approve original / Approve Pro Edit / Approve both); approving stays the owner's act (`require_human`), the autopilot never approves anything. The variant is queued directly (no `wake_worker`: the pool polls).
- Decision: the campaign page gets a "Pro Edit" section (`features/proedit/CampaignProEdit.tsx`) that saves `allow_heavy_edits` (PATCH campaign, only if changed) and the switch/preset/max intensity (PUT autopilot with the saved settings merged, since the PUT replaces all). `campaignChanges` no longer sends `allow_heavy_edits`, so a stale campaign form cannot undo it.

## TASK-233 V3-21a Retention/pacing extras: pattern interrupts, J/L cuts, reaction holds, loop ending (2026-11-09)

- Decision: the loop-friendly ending is a `transition` item with `params.type = "loop"` (no whoosh) over the last `round(0.3 * fps)` frames, ending on the clip's last frame (validation: within 0.05 s of the clip end), not a new `EdlKind`: no migration, the editor/timeline already show transitions, budgets and validation already know them. It is pinned (`edl.is_loop_ending`: never beat-snapped, ranked like a manual item in budgets). Render (`render/loop_end.py`, a stage after the other visual stages): the first frame is looped (`loop`) and `blend all_expr` mixes it in with a linear ramp; the audio crossfades the last 0.3 s into the first 0.3 s (`afade` out/in + `adelay` + `amix normalize=0`). ffmpeg's blend variable `N` was off by one inside the window branch, so the ramp uses `round(T*fps)`.
- Decision: the loop ending is opt-in (`ProEditOptions.loop_ending`, default off, "Loop-friendly ending" switch in the dialog) or comes from a style recipe whose median `loop_ending` metric is >= 0.5 (`style/recipe.recipe_loops`). If a manual item sits in the last 0.3 s, the plan is left unchanged; clashing auto items on the transition track are dropped.
- Decision: J/L cuts are automatic in the render, not plan items: `JL_FRAMES` by intensity (clean 2, standard 4, pro 6, extreme 8 frames). At each joint a J cut (next part's audio early) is tried first, then an L cut (previous part's audio late), shrinking a frame at a time; neither the added nor the dropped audio may overlap a source word and the added audio must lie inside the clip. Video and audio are concatenated separately (`render_graph.cut_graph/clip_graph(audio_spans=...)`); total audio length equals video length and no word moves in rendered time, so captions and censor beeps stay valid.
- Decision: reaction holds (`pacing.py`): after every punchline, nothing from `HOLD_KINDS` may start in `(punchline end + 1 frame, punchline end + HOLD_S)` (clean 1.0, standard 0.8, pro 0.6, extreme 0.5 s). `HOLD_KINDS` = visual pattern interrupts minus SFX and layer kinds (vignette, grain, shake): layers run over the beat and Phonk's flash/shake density trait (`test_phonk_traits`) fell below its floor when a beat shake was held out. Manual items, looks, the loop ending and items starting inside a punchline word are exempt. The rule builder rejects such moves; `postprocess_plan` moves an LLM/critic item to the hold's end, or drops it if that would pass the clip end, break another hold or clash on its track. The base cuts are never changed.
- Decision: pattern interrupts (`retention.py`, moved out of `director_rules`) also fill LLM plans: `finish_plan` adds the loop, post-processes, fills dead air with interrupts and places whooshes. Critic revisions call it with `interrupts=False` so a move the critic removed stays removed (the loop ending is still re-added when requested).
- ffmpeg verification (2026-11-05, ffmpeg 9.0.2 via `/opt/homebrew/opt/ffmpeg-full`, prototype in /tmp): https://ffmpeg.org/ffmpeg-filters.html#blend (`all_expr`, `T`, `N`), #loop (`loop`, `size`, `start`), #afade, #amix (`normalize`), #adelay (`all=1`), #concat, #atrim.

## TASK-234 V3-21b Subject cut-out (segmentation): subject in front of text, background blur/swap (2026-11-09)

- Engine (verified 2026-11-05): MediaPipe Image Segmenter task of the installed mediapipe 0.10.33 (Tasks API only, no legacy `mp.solutions`): `vision.ImageSegmenter.create_from_options(ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=...), running_mode=RunningMode.VIDEO, output_confidence_masks=True, output_category_mask=False))`, `segment_for_video(mp.Image(SRGB), timestamp_ms)`; with the selfie model the result holds ONE float32 confidence mask (H, W, 1) of the person at the input's size (the code takes the last mask). Model: SelfieSegmenter square 256x256 float16 (https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter), `https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite`, 249537 bytes, sha256 `191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b`, Apache-2.0 (model card https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Selfie%20Segmentation.pdf). Downloaded by `scripts/download_models.py` into `models/segment/`, never at render time. New engine `segment` (marker `engine_segment`, README section, `make check-engines`).
- Decision: masks come from a pre-pass, not a filter inside the render graph: the frames as the stages before the overlays leave them (`graph.PRE_CUTOUT_STAGES`, same filters, so frame n matches the render's frame n) are scaled to 288 px on the short side, streamed out as rgb24, segmented and written as a lossless gray FFV1 `.mask.mkv` next to the output; the render reads it with `movie=...,settb=expr=1/fps,setpts=N,scale` and deletes it afterwards. The subject layer is `alphamerge` of the frame and the mask; the background is `gblur` (sigma 2 % of the height) or a `drawbox t=fill` color; the subject layer is overlaid back right away and, for "subject in front", once more after the captions stage (overlays and kinetic captions end up behind the person). ffmpeg 9.0.2 filters verified with `ffmpeg -h filter=alphamerge|gblur|drawbox|movie` and test renders.
- Decision: three flat `ProEditOptions` fields (`subject_front`, `background` keep|blur|swap, `background_color`) rather than a nested model: the estimate endpoint reads ProEditOptions as query parameters. "Swap" is a solid color only (no image/video backgrounds: no asset picker yet). Defaults are off, so existing renders are byte-identical (isolation golden test green).
- Decision: the cut-out is optional and never fails a run: no change requested, "subject in front" with no overlay/caption item, a missing package/model or a model that cannot load all skip it with `subject cut-out skipped: <reason>` in the job log, and the render is the same as without it. The proxy cache (`proxy_<plan id>.mp4`) is not keyed by the cut-out options.
- Limits measured on the fixture's drawn face: SelfieSegmenter is weak on full 16:9 frames and on the fixture after ~30 s (mask ~0); on 9:16 crops of the face at 4-14 s the face ellipse is fully covered (100 % > 0.5) while the area above the head stays ~0; it leaks into the background below the head (where a body would be).


## TASK-235 V3-22 v3 e2e flows, README Pro Edit section, parity v3 (2026-11-09)

- Decision: the e2e "mock" for style reference links is a test-mode stand-in route, `GET /api/testmode/style-references/{name}.mp4` (name `^[a-z0-9-]{1,40}$`, else 422), which serves `fixtures/sample.mp4` with Starlette's `FileResponse` (Range requests answer 206, verified in the pytest). It exists only in the test-mode router (`CLIPFORGE_TEST_MODE`), like the other stand-ins. The e2e therefore runs the real path end to end against localhost: yt-dlp's generic extractor (the link ends in `.mp4`), the duration/resolution limits, the feature analysis and the guaranteed media delete (the spec asserts no `style_*` dir remains under `e2e/.run/data/work`). No outside network; about 14 s per reference.
- Decision: the e2e campaign is set up through the API (rules, permission evidence, autopilot settings with `proedit_max_intensity: "pro"` so the dialog allows Pro, a test-mode YouTube account) and the project is assigned to it, so "approve the variant" goes through the real inbox UI and the posting queue (exactly the variant is queued; the original's draft stays pending).
- Decision: the EDL drag moves the zoom item with the most free room after it by min(room/2, 80 px): a fixed drag of the first item can overlap its neighbour and the PATCH correctly answers 422. The test asserts the PATCH status and that plan v2 has exactly one `manual` item.
- Decision: docs/parity.md gets a "v3 (Pro Edit)" column in the OpusClip table ("—" when Pro Edit adds nothing), 3 v3-only rows, and a separate "SPEC-v3 coverage (Pro Edit)" table. `scripts/check_parity.py` still validates only the SPEC-v2 table (unchanged), so the v3 table is checked by hand: every evidence path exists.
- No new third-party API: yt-dlp generic extractor and Starlette `FileResponse` were verified earlier (TASK-228) and in this task's tests.

## TASK-236 V3-23 e2e regressions + Pro Edit UI gaps (2026-11-09)

- v2-autopilot (3 → 2 drafts) was a product bug, not Pro Edit: clip 3's render crashed ffmpeg with SIGBUS (status -10; macOS crash reports: out-of-bounds reads in x264 `plane_copy` and libavfilter). `pipeline/zoom_graph.zoom_filter` scales by a keyframed expression whose `balanced_sum` grouping gives `(1+0.15)+(-0.15+0.12*c)` = 0.9999999999999999 when a zoom ramps back to 1, so `layout_parts.zoomed_side` (`2*trunc(side*scale/2)`) made a 1078x1918 frame for 79 frames while the crop after it takes 1080x1920 (crop's iw/ih are the configured link size), reading past the frame. Decision: `zoomed_side` = `max(side, 2*trunc(side*scale/2))` (a zoom never shrinks the frame); hooks and zoom transitions use the same helper. Pro Edit's `motion.py` already clamps in Python. No encoder fallback was added: libx264 crashed the same way, the bad frame size was the cause. Tests: `test_a_zoom_back_to_1_never_scales_below_the_frame` (expression evaluation) and `tests/pipeline/test_zoom_frame_sizes.py` (real ffmpeg + showinfo: no scaled frame below 1080x1920); both fail without the fix.
- zoom-out.spec (segment text "" instead of "Square"): the product is right, the test depended on layout width. `TimelineSegments` shows a chip's label only when it fits (`labelFits`, steering 7122dbf; the label stays in the chip's title and accessible name). Since the timeline got its lane-label column (Text / Overlays / B-roll / Video / Audio), the 2.5 s first segment is ~47 px wide at 1280 px, too narrow for "Square" (~50 px with padding). The spec now zooms the timeline in twice before the unchanged `toHaveText("Square")`.
- overlays.spec: a product bug plus test hygiene. (1) Product: after a successful save the editor stayed dirty ("Save changes" enabled). `PATCH /clips/{id}/tracks` stores the props with their defaults filled in (`timeline.tidy_props`: a text item `{text, animation_in, box}` comes back with font, size, color, ...), and `useClipEdits` compared its layers with the saved ones by `JSON.stringify`. The old spec only passed because "Save changes" is also disabled while a save is in flight (`TopBar`: `!dirty || invalid || busy`), so `toBeDisabled()` matched before the PATCH answered. Decision: `lib/tidyLayers.sameLayers` compares layers as the backend saves them (each track's props defaults, `SAVED_PROP_DEFAULTS` mirroring BrollProps/OverlayProps/TextProps/AudioProps/MusicProps/VoiceoverProps; voiceover text trimmed; key order ignored). Kept the client sending the props it sets (no default-filling on creation) so older clips and the existing item shapes stay as they are. (2) The spec now waits for both save PATCHes (clip, then tracks) to answer 200 (`e2e/autosave.ts saveChanges`) before the unchanged checks, so it tests the saved state. (3) The uploaded logo.png stayed in the global media library, so a re-run got 409 on upload; afterEach now deletes it (`DELETE /api/library/{id}`, after the project so no clip plays it).
- Inbox Pro Edit variant thumbnail: `InboxVariants.VariantCard` played `previewUrl(variant)` (`GET /clips/{id}/preview`), which renders the clip on demand with the v1 pipeline (not the Pro Edit plan), so the card stayed grey while that render ran or failed, and would have shown the wrong video. Decision: the card plays the variant's rendered Pro Edit video, `GET /proedit/clips/{id}/video?v=<editsVersion>` (`variantVideoUrl`, shared with `ComparePreview`), no new endpoint.
- Pro Edit dialog footer at 1280x720: `DialogFrame` scrolled the whole card, so Cancel / Run Pro Edit sat below the fold. Decision: `DialogFrame` is a flex column (its card still scrolls for other dialogs); `ProEditForm` puts its options in a `min-h-0 overflow-y-auto` group ("Pro Edit options") and keeps the footer outside it, always in view.
- settings.spec (bell showed 28 unread instead of 0): test isolation, the product is right. Notifications persist in the e2e data dir across specs (earlier specs' jobs notify), and the spec assumed a fresh store. It now marks all read first (`POST /api/notifications/read-all`), then keeps its unchanged checks.
- watchlist.spec (empty state expected, "Recent alerts" shown): test isolation, the product is right. Watch alerts persist by design and the v2 autopilot / campaign specs leave some. The spec now checks the state the API reports (`GET /api/watch/events`): none -> the "No alerts yet" empty state, else the "Recent alerts" list; in both cases the region must not show the removed channel (unchanged assertion).
- v3-proedit.spec ("Render plan v2" stayed after the render): product bug. `useRenderVariants` queued the render but did not invalidate `["proedit", "runs", variantId]`, so `ProEditEditor` never saw the new run's job and never followed it to done. Decision: `useRefreshAfterRun` (runApi.ts) invalidates the started variant's runs for every queued run (render and re-run); the duplicate invalidation in `useQueueRun` was removed. Test: ProEditEditor "follows the render it queued" (fails without the fix).
- Seen, not changed: the backend log shows an occasional `FileNotFoundError ... previews/<id>-<hash>.ass.tmp` when two preview requests of the same clip version render at once (they share the tmp name in `step.py`); no spec fails on it (seen before this task too). Left for a follow-up (unrelated to Pro Edit).
