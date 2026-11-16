# Gotchas archive

Verified facts and failed approaches collected in docs/HANDOFF.md up to
TASK-176, moved here to keep HANDOFF under 150 lines (SPEC 0.11). New ones
go to HANDOFF first; the code and git log win over this file.

## Gotchas (moved from HANDOFF at TASK-89: layouts, posts, public API)
- Layout UI (T32e): CropTrack fixtures in frontend tests need
  `facecam: null` (generated types make it required). Layout constants
  with JSX live in `components/layoutOptions.tsx` (react-refresh warns on
  mixed exports). Running `e2e/reframe.spec.ts` rewrites TASK-83
  screenshots: `git checkout` them. Saving in e2e then deleting the
  project logs a failed preview (`.ass` missing): teardown race, harmless.
- Crop keyframes (T32d): ffmpeg 9.0.2 `crop` logs `n: t: x: y:` per frame
  at `-loglevel trace` (vf_crop.c): x/y are `lrint`ed, clamped inside the
  frame, then rounded down to even for yuv420p. Use it to check a crop
  expression (`run_ffmpeg(..., loglevel="trace")`, `-f null -`).
  Keyframe API routes are in `api/clip_keyframes.py`, not `clips.py`.
- Default layout (T32c): `set_planned_layouts` now lives in
  `clip_layouts.py` (import it from there). "dynamic" needs meta.json and
  signals.json in the work dir. Split with three equal faces follows the
  left and middle one (two largest, first on tie): make the middle face
  smaller in tests that expect left/right. Scene lengths summed from
  floats tie inexactly: compare rounded. `frontend/node_modules` vanished
  mid-run once (not the Makefile): `npm --prefix frontend ci` restores it.
- Layouts: a new `Layout` value must also go into `test_models`
  SPEC_LITERALS, frontend `ClipCard` LAYOUT_LABEL and `lib/scenes`
  SceneChoice/SCENE_LABELS + SceneChooser HINTS (Records, else tsc fails).
  A new Framing field must go into frontend `DEFAULT_FRAMING` (generated
  types make defaulted fields required). Crop expressions/fit graph now
  live in `pipeline/layout_parts.py`. `crop` accepts `iw*0.25` style
  expressions; start a chain from a split label with `[label]null,...`.
  Facecam box None = video takes the whole output. Under full-suite load
  `EditorSave.test.tsx` "text panel" timed out at 5 s (`user.type` of
  145 chars): it now uses `user.paste`; prefer paste for long input.
  `vstack` needs equal widths, `hstack` equal heights (ffmpeg 9.0.2 help).
  A window's xs must have one entry per plan keyframe (crop_window uses
  the keyframe times). `plan_crop` needs exactly `sample_times` many
  face samples (identity zips strictly): 20 for a 2 s clip.
  Pip inset follows subject switches by panning like the fill window.
- Reframe UI: the preset is a project setting used when clips are found
  (no per-clip override or replan endpoint), so the editor cannot change
  it. Editor tests that open the Layout panel must route
  `GET /api/reframe-presets` (404 is silent, the style then reads
  "Automatic"). `npx prettier --write src` rewrites the generated
  `api/types.ts`: `git checkout` it afterwards. Playwright starts its own
  servers on 8000/5173: stop `make dev` first (kill by pid from `lsof -ti`).
- Reframe presets: `plan.preset` is kept by `replan`; split share 1.0 means
  never split (needs > all samples). Gaming = fit layout (kept in T32b:
  it covers screen recordings; default layout is T32c). API tests live in tests/api (the
  `client` fixture is not visible from tests/pipeline).
- Object tracking: only faceless shots (no face AND no person) are
  tracked; boxes are `kind="object"` (identity matches same kind only;
  `face_pairs`/`wants_split` ignore them). Needs a still camera. A
  `connectedComponentsWithStats` call returns 4 values (count, labels,
  stats, centroids). Measure crop error against the center clamped to keep
  the crop inside the frame (1:1 cannot center a subject 70 px from the
  edge). The 5x5 blur widens motion boxes by ~1 px per side. A faceless
  clip now costs ~5 s per 30 s of 720p video in reframe.
- Aspect: a `str` "W:H", so never `get_args(Aspect)`/Literal checks; use
  `aspect.PRESETS`, `check_aspect`, `aspect_size`. CropPlan has `width`,
  `height`, `y` (no `.fill`). Test `plan_crop(ClipSpan, aspect, frame, faces, [])`.
- Clip anything: a new pipeline step must also go into test_enrich,
  test_job_resume and test_reprompt step lists and frontend
  `processingSteps.ts` (projectStatus.test percentages shift). Motion of a
  talking head is ~0.012, testsrc2 ~0.03-0.05, a still picture 0.
  `engines.is_installed` caches: call `engines.clear_cache()` around respx
  Ollama mocks (`tests/vlm_fakes.mock_ollama`). Without clip anything a
  silent video gets an empty enriched.txt and no candidates (no LLM call).
- VLM: Ollama is installed (`/opt/homebrew/bin/ollama` 0.34.4) but not
  running by default: start `ollama serve` for the engine (else the
  engine_ollama_vlm test is skipped). qwen3.5 thinks unless `think: false`.
  Cold load ~17 s, ~0.5 s per frame warm. Tests mock Ollama with respx at
  `HOST = http://vlm.test:11434` (`use_server(monkeypatch)` sets
  ollama_host/vlm_model on config.settings).
- New Clip/Project field: also `test_models` SPEC_FIELDS, frontend
  `mockApi` `project()`/`clip()`, regenerate types. Migration tests that
  load ClipRow/ProjectRow after an early `migrations_through` must call
  `migrate(engine)` first. Config defaults in `config.py` must match
  `config.yaml` (test_worker_pool reads the repo-root yaml when run from the
  root, as `make check` does; from backend/ it passes either way).
- Curate returns early if candidates.json exists: use a fresh job dir per
  curate call in tests (or force=True). It dedupes IoU > 0.5 (fixture: D
  dropped for A). keyword_search reads transcript.json, not enriched.txt.
- A new ProcessingSettings field: also add it to frontend literals
  (mockApi DEFAULTS, SettingsPanel.test), tests/api/test_presets_api
  DEFAULTS and test_models (fields list + defaults dump).
- Human-only rule: `deps.require_human` 403s `human_only` when the request
  has `X-API-Key` or `Authorization` or its path starts with `/api/v1/`.
  TASK-164 (public API) and TASK-166 (MCP, done) authenticate with these
  headers / prefix, else agents could publish. Agents may draft and
  reschedule drafts only. Tests: `post_api_fakes.AGENT` header.
- Posts API: queue/publish need a rendered clip (`post_api_fakes.
  rendered_clip(engine, title)`), drafts do not. `accounts(engine,
  *platforms)` makes accounts with external_id `"{platform}-{i}"`, token_ref
  `ref-{external_id}`. Publish now runs `publish_post` as a FastAPI
  BackgroundTask (TestClient runs it before returning); store a token with
  `TokenStore.from_settings().save("ref-tiktok-0", Token(...))` and
  `social_fakes.register_example(monkeypatch)` (ExamplePublisher as
  "tiktok"). The campaign-rules 409 body has an extra `failed` key: do not
  use `assert_error` on it.
- Timestamps: always `watch.times.as_utc` before saving; SQLite drops tz,
  `social_rows._utc` adds UTC on read; the API returns "...Z".
- Scheduler: `scheduler/slots.py` is pure (`allocate(clip_ids,
  [AccountTarget(id, max_per_day)], rules, now, busy=[(account_id, at)])`);
  `post_schedule.bulk_schedule` builds/checks every payload first, then
  allocates, then saves (all or nothing). Tests: `schedule_fakes.rules()`.
- Publishing: a platform publisher subclasses `publishers.base.Publisher`,
  sets `platform`, and is registered in `registry.ENTRIES` with the env keys
  it needs; the factory returns None when unconfigured (publish now ->
  412). Retryable failures -> `PublishError(retryable=True)`.
- Posts: uploading cannot be canceled; `move` with fields outside
  `MOVE_FIELDS` raises ValueError; edits go through `update_post` (only
  `EDIT_FIELDS`, conditional on draft|queued -> `PostLocked`).
  Post.account_id is nullable (history after disconnect).
- New migration: bump version lists in test_db/test_migrations, row column
  order == model field order. Migration tests: `v1db.migrate_to_v1`,
  `seed_v1`, `migrations_through(tmp_path, N)`; read old tables by raw SQL.
- respx `respx_mock` patches httpcore; API tests use `client`/`api_engine`
  (tests/api/conftest.py, ENV_SETTINGS lists editable env settings);
  `assert_error` expects exactly {error, message}.
- Public API: a new core router is public only once added to
  `api/v1.PUBLIC_ROUTERS`; the contract tests (`tests/api/v1/test_contract
  .py`) then require every operation to answer 401 without a key and a
  documented status + schema with one, so document extra statuses via
  `responses=`. `"4XX"` in responses suppresses FastAPI's 422 entry.
  Router-level dependencies run before body validation (no key -> 401, not
  422). Keys are SHA-256 hashed (256-bit random; decision in decisions.md).
  `from conftest import` resolves to tests/conftest.py: put shared helpers
  in modules (`api_key_fakes.make_key`). Tests limit via
  `config.settings.model_copy(update={"api_rate_limit_per_min": 3})`
  before `create_app`.

## Gotchas (TASK-1..176)
- Payload: `PostText.copy` is impossible (shadows BaseModel.copy): the
  field is `text`. The stored payload = the options model's
  `model_dump(mode="json", include=keys)` plus `payload["text"]` (the
  PostText). `post_payload.TEXT_FIELDS` are refused in `options`.
- Accounts UI: connect opens `window.open("", "_blank")` on the click, then
  sets its location to `authorize_url` (popup blockers); the page polls
  `GET /accounts` every 2 s while a sign-in is open.
- Post copy: `POST /clips/{id}/post-copy` saves nothing; the generator cuts
  to the platform limits itself (`post_copy_fit`), reserving the hashtag
  line `post_payload` appends. Tests use `FakeLLMClient` +
  `tests/fixtures/post_copy/replies.json`; the e2e test server's LLM only
  returns the curate reply, so e2e mocks `**/api/clips/*/post-copy`.
- `Button` does not forward refs: use `buttonVariants` on Radix triggers.
  `ffmpeg.extract_frame` exits 0 past the end of the video:
  `thumbnails.check_time` probes the duration first.
- Campaign watch: a campaign channel's end date passes without a sync, so
  the importer calls `campaign_watch.is_watched` before reading a feed or
  accepting a push (410 for a closed campaign). Handles in campaign links
  need `YOUTUBE_API_KEY`; without it they are skipped (logged), the save
  still works. A channel the owner already watches is adopted by the first
  campaign that lists it (removing the link then removes the channel). A
  migration test that reads `ProjectRow`/`WatchedChannelRow` through the ORM
  at an older version fails once a later migration adds a column (use raw
  SQL). `Project.fresh_upload` uses the real clock: test it with dates
  relative to `datetime.now`. A new migration also needs the version lists in
  test_db / test_migrations and the field lists of test_models.
  TASK-177+ (publishing): the Auto Import UI does not show `campaign_id` yet.
- Campaign UI: the API resets `permission_checked_at` whenever a PATCH body
  holds `permission_source_url`, so the form sends only changed fields
  (`campaignChanges`) and a screenshot-only save sends no PATCH. The API
  stores hashtags without "#": the form shows "#tag" and strips it on send.
  The rule check is of the stored clip (not unsaved edits); the editor's
  Rules panel and gallery refetch after a save/apply (`campaignCheckKey`).
  The editor's floating player toolbar overlaps the top of the rail's
  drawers (pre-existing for every panel). Tests of a project's gallery must
  mock `GET /api/campaigns` (the campaign select loads it).
- Campaign rules/presets: the publish/schedule endpoints (TASK-138+, 147,
  177) must depend on BOTH `require_campaign_permission` (path
  `project_id`) and `require_campaign_rules` (path `clip_id`, `platform`
  query or path param); the rule guard alone already covers permission and
  source rights per clip. Campaign "length range" = overlapping
  `length_presets` (strict overlap: 2-30 s -> only `lt30`); the exact
  min/max is a rule on the played length (segments minus cuts). An empty
  `allowed_platforms` fails the platform rule. Caption template names are
  the yaml stems (`clean_subtitle`, not `clean`). `ApiError(..., extra=)`
  adds body fields; `assert_error` expects exactly {error, message}, so a
  409 with `failed` is asserted by hand. TASK-176 should call
  `campaign_presets.apply_campaign` for projects it creates.
- Campaigns: `CampaignRow(**model.model_dump())` (python mode: a DATE
  column rejects the ISO string that `mode="json"` gives); table rows do not
  validate. `Campaign` fields come in the order of `CampaignCreate` +
  mixin: the mixin (`id`, screenshot id, date) is first because pydantic
  collects base fields in reverse base order, so `test_db`'s
  row-vs-model order check and migration 015's column order follow it.
  Every `BaseModel` of models.py must appear in types.ts (the mixin is
  `_CampaignSaved`). SQLite returns `permission_checked_at` naive; the row's
  `to_model` makes it UTC. The publish/schedule endpoints (TASK-138+, 177)
  must add `Depends(require_campaign_permission)` (path param
  `project_id`); the guard passes a project without a campaign. A campaign
  is linked to a project only through `project.campaign_id`, set by
  `PUT /projects/{id}/campaign` (TASK-174). BSD sed needs `-i ''` on this Mac.
- Creator watch: the watcher threads start only with `run_watch`
  (default `run_worker`); API tests (`run_worker=False`) and the e2e test
  server (`run_watch=False`) never poll, but `app.state.importer/.twitch`
  exist so the push callbacks answer. A new feed slot is due at once.
  DB datetimes come back tz-aware UTC (`watch.times.as_utc`). The keys
  master file is in `settings.data_dir` (tests: the tmp data dir). A push
  older than the channel's `created_at` gets no project: tests set
  created_at before `watch_fakes.NEWEST_PUBLISHED`. EventSub header names
  are matched lowercased. Playwright `getByLabel` matches substrings (a
  section named "YouTube channels" vs field "YouTube channel"): use
  `exact: true`. Never `prettier --write` src/ wholesale: it reformats
  types.ts and `gen_types --check` fails (regenerate it).
- Watchlist (ex Auto Import) UI: invalidating the `["auto-import","channels"]` prefix
  refetched the videos of a just-removed channel (404 console error), so
  the videos have their own key `["auto-import","videos",id]`. Python is
  3.11: no PEP 695 `def f[T]`. A router module named `auto_import` clashes
  with the `AutoImporter` local in app.py's lifespan (it is `importer`).
  Two `SourceRightsField`s on one page need distinct ids (`useId`).
- Auto Import: the YouTube feed had no ETag and `max-age=900` (validators
  are still sent; a 304 is handled); feed-level
  `<yt:channelId>` drops the `UC` prefix (use the entry's or the stored
  id). The first successful read (`last_checked_at` NULL) only records the
  feed; `last_error` is cleared by the next good read. Tests answer the
  feed with `youtube_fakes.feed_route(respx_mock, "feed_before", ...)`
  (side_effect list: one answer per poll). A new watched table with a
  composite PK has no AUTOINCREMENT (test_db's AUTOINCREMENT check only
  covers rows with an `id`). Migration tests seed on v1
  (`migrate_to_v1` + `seed_v1`) before applying later migrations.
- Dropbox: download-style endpoints (`get_shared_link_file`) are POSTs to
  content.dropboxapi.com with the argument as JSON in the `Dropbox-API-Arg`
  header (no body); metadata is a JSON POST to api.dropboxapi.com. Link
  metadata has no media info (video = file extension) and `size` is a number.
  Dropbox errors are `{"error_summary", "error": {".tag"}}` (429:
  `error.reason`); 400 is plain text. Authorize with `token_access_type=offline`
  for a refresh token; PKCE means no app secret is sent.
- OAuth/Drive: respx's `respx_mock` fixture patches httpcore (not the
  FastAPI TestClient); register the `params={"alt": "media"}` route before
  the plain files.get route. Drive `size`/`durationMillis` are strings.
  Google installed apps always get a refresh token (no access_type);
  refresh answers may omit it (kept). `oauth.py` must not import
  `oauth_flows` (cycle). The callback redirect URI comes from
  `request.url_for` (vite proxy -> 127.0.0.1:8000). GOOGLE_OAUTH_* are in
  the API conftest ENV_SETTINGS. A new VideoSource kind needs
  useSourceDetails + useAddProject branches.
- Inbox watch: a file is imported on the 2nd poll with equal (size, mtime_ns);
  `.env.example` keys are checked by test_config and test_check_prereqs
  (every key must be listed there as v1 or v2 credential), so a new Settings
  field that is not a credential goes into README, not `.env.example`.
  The project's `source_path` is the file in the inbox (ingest copies it).
- Chunked upload: the client must send the offset the server reports; a
  resend of an already stored chunk is 409 offset_mismatch (the client
  then GETs the session and continues). A checksum mismatch writes
  nothing. Abandoned sessions stay in data/upload_sessions until DELETE
  (no automatic cleanup yet). The frontend remembers a session in
  localStorage under `clipforge.upload:<name>:<size>:<lastModified>` and
  forgets it after complete. `crypto.subtle` and `Blob.arrayBuffer` work in
  the Vitest jsdom env.
- Settings panel: `length_presets` is a list (never empty; settingsToSend
  falls back to ["auto"]). clipping "captions_only" (was "none") skips LLM curation and snap (the
  clip is exactly the timeframe); auto_headline is disabled there. Presets
  and the default live in data/processing_presets.json (not the DB); a
  preset keeps the current timeframe and subtitles_id when applied. SRT
  and VTT uploads are referenced by a 32-hex `subtitles_id`; the file is
  always stored as `<token>.srt` and WebVTT is told by its `WEBVTT` line. Frontend
  speech-languages / processing-presets queries are `silent` (mockRoutes
  404s unknown routes). Auto color on a lavfi test pattern barely changes
  stats; test it on a dulled real frame.
- Curate (TASK-73): clipping "keyword_search" reads transcript.json (not
  enriched.txt) and never makes an LLM client; it needs `search_terms`
  (validator). The prompt-to-clip text is prompts/prompt_to_clip.md
  (`$request`), filled into curate_base.md as `$request_section`; tests
  assert "The user is looking for: <request>\n". A new ProcessingSettings
  field must be added to frontend literals (mockApi DEFAULTS,
  SettingsPanel.test) and tests/api/test_presets_api DEFAULTS.
- Reprompt (TASK-74): a "reprompt" job runs in the work directory of the
  project's process job (`run_step(..., work=, processing=)`), forced
  curate/score/snap with keyword_prompt=prompt and clipping "ai"; no step
  marker is touched (the markers of the first run stay). `process_clips`
  saves/clears only result_set 1; `reprompt._make_set` saves set N+1.
  Project.result_set changes only when the new set is done; a failed job
  deletes its clips and restores status done (`restore_project`). Anything
  that lists a project's clips must filter `ClipRow.result_set ==
  project.result_set` (list_clips, `_best_first`, webhook, zips). A new
  Clip/Project field needs test_models SPEC_FIELDS and mockApi.
  `process_work_dir` now lives in `job_rows` (no implicit re-export).
- Reframe samples at 10 fps now: `plan_crop` needs exactly one face list
  per `sample_times(start, end)` (track_ids zips strictly); a 34 s clip has
  339 keyframes. The face landmarker fails on whole 640 px frames' small
  faces; it runs on 1.5x face crops scaled to 256 px.
- Auto cut and auto zoom are ON by default: tests that need a plain clip
  (render frame checks, `save_clips` without a transcript) pass
  `ProcessingSettings(auto_cut=False, auto_zoom=False)`. A new Clip field
  needs test_models SPEC_FIELDS, `mockApi.clip()`, the clipLook /
  useClipEdits expectations and (settings) test_sources_api defaults.
  ffmpeg crop's `iw`/`ih` stay at the first frame's size after a
  `scale eval=frame`: write the scaled size out in crop's x/y. A bool ClipRow column must be
  declared `BOOLEAN` in its migration (test_db compares SQLite affinities).
  Migration tests that read ClipRow after an older migration must apply
  the rest first (`migrate(engine)`).
- Captions: template sizes are pixels of the output frame and the libass
  font size is winAscent + winDescent (Montserrat cap height = 0.448 of the
  size, Inter 0.601). Caption preview PNGs draw 1080-sized text on a
  540x960 frame (twice as large relative to the image).
- Encoders: renders default to h264_videotoolbox on this Mac. A test of a
  new render path must take the `render_settings` (or `encoder`) fixture of
  tests/pipeline/conftest.py so it runs with both encoders; VideoToolbox
  takes no -crf/-preset (only -q:v / -b:v) and writes no x264 options into
  the stream. `encoders.available_encoders` is `functools.cache`d per
  ffmpeg path; monkeypatch the module attribute in tests.
- Resume: a stage is skipped iff `steps/<name>.done` exists in the job's
  work dir; a new stage must call `mark_done` after ALL its outputs. Clips
  are deleted at job start only without the `clips` marker. Attempts count
  claims, not exceptions: a raising job fails at once; only jobs left
  `running` by a dead process hit `job_max_attempts`. Patch
  `process.load_step` (not `step.load_step`) to spy on/replace steps.
- Jobs: claim only via `jobs.claim_next` (never select-then-update). Pool
  slots/GPU lock are in-process, taken under the pool mutex with the claim.
  config cannot import `models` (models imports config): job-kind names in
  settings are checked by `WorkerPool`. A new job kind: add it to `JobKind`,
  `run_claimed`, and (if GPU-heavy) `gpu_job_kinds`. mypy types RETURNING
  row items as optional. Pool tests: force overlap with `threading.Barrier`.
- Project API: `ProjectPatch` is partial (use `model_fields_set`). In the
  Home panel "Source rights" is a required select: a test that clicks "Get
  clips" must choose it first. POST/upload bodies now carry `source_rights`
  and `credit_line`.
- Migrations: a test of migration N must apply only 1..N with
  `v1db.migrations_through(tmp_path, N)` (latest: 016); `migrate(engine)` now also runs
  later migrations. Bump the version lists in test_db.py/test_migrations.py
  for each new migration. New `Project`/`ProjectRow` fields go AFTER
  `created_at` and the mock `mockApi.project()` needs them (types.ts is
  required-output). `db.py` imports `assets` lazily (assets imports db).
- Timeline: `Clip.start`/`end` are computed (not fields): `model_copy(update=
  {"start": ..})` on a Clip silently does nothing; change `segments` (and
  rebuild `tracks.video` with `timeline.with_segments`). `ClipRow` has no
  start/end; use `row.to_model().start`. Build test clips with
  `make_clip(start=, end=)` or `timeline_of`. SQLite `json_array(REAL)`
  rounds to 15 digits in 3.53.1 (venv): write floats in SQL JSON with
  `json(printf('%!.17g', x))`. A table rebuild migration must copy the
  `sqlite_sequence` row (AUTOINCREMENT) and recreate indexes.
- Engines: add one with an `ENGINES` entry (`clipforge/engines/__init__.py`),
  its marker in pyproject.toml and the Makefile `ENGINE_MARKERS` (pytest `-m`
  has no wildcard), a `VERIFY` in tests/engine_probes.py and an "Engine:
  <name>" README heading (slug `engine-<name with hyphens>` is the
  `doc_anchor`; a test checks it). A feature asks `engines.is_installed(name)`
  (cached; `refresh=True` re-checks) and the UI wraps it in `EngineGate`.
  Ollama: `GET /api/version`, `GET /api/tags`, `POST /api/show {"model"}` ->
  `capabilities` ("vision"); start `ollama serve` for the live test.
  `uv pip install --dry-run --python .venv/bin/python <pkg>` probes a
  package without installing; `uv sync` removes such installs. No `timeout`
  command on macOS. `GET /api/engines` is called by the Settings page: a test
  that renders `/settings` must answer it (Settings.test.tsx does).
- Run prettier from `frontend/` (`cd frontend && npx prettier --write
  ../x`); the root `npx prettier` downloads another version. Never
  `prettier --write`/`eslint --fix` `src/api/types.ts`; after any models.py
  change run `uv run python scripts/gen_types.py` and commit types.ts.
  Never run `tsc -b` without deleting `frontend/tsconfig.tsbuildinfo`.
  Run vitest from `frontend/` (the `@/` alias breaks elsewhere).
- E2E: stop `make dev` first (ports 8000/5173). The test backend's cwd is
  `e2e/.run`; it needs `MODELS_DIR` and sees no `.env.local`. Specs share
  one server: delete what a spec creates. Playwright 1.64.1 uses
  chromium-1248. `make dev` leaves vite/uvicorn if killed by name: kill the
  PIDs of `ps aux | grep projects/clipforge`.
- Settings read `.env`, `.env.local` from cwd (tests `chdir` to temp);
  init > env > dotenv > config.yaml; `extra="ignore"`. `PUT /settings`
  writes `.env.local` in the SERVER's cwd: smoke servers run from a temp dir.
  Any test that renders `/settings` must answer `GET /api/settings`.
- ffmpeg: always `ffmpeg.ffmpeg_bin()`/`ffprobe_bin()`; ffmpeg-full 9.0.2
  (keg-only, libass) must be first on PATH (the Makefile does it). Plain
  ffmpeg has no libass. loudnorm output is 192 kHz: `aresample=48000,
  asetpts=N/SR/TB+STARTPTS`. trim/atrim keep pts. Escape filter values with
  `ffmpeg.filter_value`. `crop` w/h are evaluated once, x/y per frame. A
  bad `-preset` exits 234 with an empty file; `-map 0:V:0` skips cover art.
- Project cards: a card of a queued/running project fetches
  `/projects/{id}/jobs`; tests that render cards must answer it (or accept
  the 404 toast). Radix DropdownMenu/AlertDialog work in jsdom with
  user-event (menuitem / alertdialog roles). A running project cannot be
  deleted: e2e cleanup must wait until it is done/failed.
- Frontend tests: Vitest has no globals; jsdom lacks EventSource
  (`testing/fakeEventSource.ts`), DragEvent, `scrollIntoView`,
  `createObjectURL`. Mock API route keys include the query string. A render
  test needs `mockEventSource()`. react-hooks lint: no ref access or
  setState in render/effect bodies; keep media elements in a `useRef`.
- API tests: `create_app(run_worker=False)`, `TestClient(app,
  raise_server_exceptions=False)`; SSE via `client.stream`; shared asserts
  in `tests/apihelpers.py`; unique test basenames (no __init__). UI smoke:
  seed with `backend/tests/seed.py`, `DATA_DIR` temp, vite on 5173.
- SQLModel: FK pragma per connection; `Literal` needs `sa_type=AutoString`;
  `flush()` gives ids. Prompts use `$$` for "$". Never print the gh token.
- Style: ruff 88 cols (`ruff format`, `ruff check --fix`, B905 `zip(
  strict=)`); files < 300 lines; mypy --strict. Never stage `ralph-local.sh`
  or the owner's uncommitted task edits. caplog needs `set_level(INFO)`.
- Older detail (brand, yt-dlp, pipeline, editor, crop, polish gotchas) is in
  docs/progress.md and docs/decisions.md; the code and git log win.

- Usage: `UsageRecordRow.at` must be timezone-aware (SQLModel refuses a naive
  datetime): use `usage.utc_now()`, month bounds are aware UTC. Metering
  failures are logged, never raised (a job must not fail on it). A caller
  of an LLM client outside a job must wrap it in `usage.recording` or its
  tokens are not counted. `tests/api/conftest.py` ENV_SETTINGS lists every
  editable setting's env var: add the new ones. The `usage` name is both
  `clipforge.usage` and `clipforge.api.usage`.

- URL sources: a new site works when the installed yt-dlp has an extractor
  (`extractors.require_supported`); never hardcode sites. yt-dlp refuses
  `file://` without `enable_file_urls`. A direct file link has no `height`:
  a `[height<=N]` selector matches nothing for it. `IE_NAME` is typed as a
  callable in the stubs: wrap it in `str()`.
  yt-dlp renames a format_id equal to a codec name ("opus" -> "fopus"): use
  YouTube-style numeric ids in canned formats. Ingest progress bands
  (DOWNLOADED 0.5, CONVERT_START 0.51, SOURCE_READY 0.9) are mirrored in
  frontend `INGEST_CONVERT_BAND`: change both together.

- YouTube: quotas are metered only inside `usage.recording(engine, pid)`
  (ContextVar); new publish/schedule code must open it. Units are recorded
  before each call. Thumbnail failures never fail a post. Tests build the
  publisher with `youtube_publish_fakes.make_publisher()` (256 KiB chunks,
  fixed clock NOW = 2026-11-01 07:30Z = 00:30 PDT, recorded sleeps).
  YouTube API docs moved to developers.google.com/youtube/data/reference/rest/v3.
- TikTok: OAuth uses `client_key` (not client_id), comma-separated scopes
  and a HEX sha256 PKCE challenge (`OAuthClient(client_id_param=,
  scope_separator=, pkce_hex=)`). creator_info errors come with HTTP 200;
  the status field is spelled `publicaly_available_post_id`; private posts
  never get a post id (publish_id is stored). No cover upload (thumbnail
  ignored). No privacy default: a payload without privacy_level fails.
  Unaudited apps: SELF_ONLY on private accounts only. Tests:
  `tiktok_publish_fakes.make_publisher()` (1 KiB chunks, 2600-byte video),
  `ready_tiktok_post`, `mock_direct_post`, `publish_tiktok`.
- Instagram/Meta: Facebook Login for Business on graph.facebook.com v26.0
  (local file upload needs it). Code exchange is a GET; no refresh tokens:
  `finish_sign_in` swaps for a long-lived token and the session "refresh"
  is another fb_exchange_token (fails with 190 once expired -> reconnect).
  external_id = IG user id; the upload reads `upload.account_external_id`.
  Seeded test clips play 2.5 s (< Instagram's 3 s): use
  `instagram_publish_fakes.ready_instagram_post` (lengthens to 30 s),
  `mock_reel(respx_mock, route=effect)`, `publish_instagram`. No cover file
  (cover_url must be public).
- Facebook: posts as the Page with a Page token read from /me/accounts on
  every upload (nothing extra stored); `MetaPublisher`, `GraphSession` and
  `meta_upload.send_video` are shared with Instagram. Never retry after
  `finish` was accepted (checks status first; processing = accepted). No
  custom thumbnail yet (TASK-148); the 30 reels/24 h cap is not queryable.
  Tests: `facebook_publish_fakes.make_publisher()`, `ready_facebook_post`,
  `mock_reel(respx_mock, route=effect)`, `publish_facebook`.
- Tokens: deleting `data/watch_secret.key` makes every stored token
  unreadable (load -> None, user reconnects). Never log a Token or headers;
  callback logs only the exception type. Tests build stores with
  `TokenStore(tmp/"tokens", tmp)` (data_dir is required).

- Post copy/covers (TASK-148): `Button` (ui/button.tsx) does not forward
  refs: use `buttonVariants` on a Radix trigger, not `<Trigger asChild>
  <Button>`. `ffmpeg.extract_frame` exits 0 without a frame past the end:
  `thumbnails.check_time` probes the duration first. TikTok/Instagram carry
  title+caption+hashtag line in one caption, so the copy generator reserves
  the hashtag line's budget. The test server's LLM answers every prompt with
  the curate reply, so e2e mocks `**/api/clips/*/post-copy`. Backend tests
  for frames need a real mp4 at `clip_output(...)` (copy `sample_mp4`).

### Public API (TASK-164)

- /api/v1 includes the app's routers a second time (`api/v1/__init__.py`
  `PUBLIC_ROUTERS`); a new router that agents should reach must be added
  there, and the contract tests then cover it automatically.
- `deps.require_human` still treats every /api/v1 path and any request with
  `X-API-Key`/`Authorization` as an agent. The old tests' `AGENT` header
  (`cf_agent_key`) on /api/... is not validated; on /api/v1 a real key is
  needed (`api_key_fakes.make_key(client)`, fixtures `api_key`/`agent` in
  `tests/api/v1/conftest.py`).
- `from conftest import ...` resolves to backend/tests/conftest.py (the
  pythonpath), not a sub-directory's conftest: put helpers in a module.
- `ApiKeyRow` has `key_hash`, which `ApiKey` lacks: test_db uses `ROWS`
  (all row classes) besides `ROW_MODELS`.
- The rate limiter lives on `app.state.api_limiter`, built from
  `config.settings` in `create_app`: patch settings before making the app.
- A reprompt / clip-by-topic sets the project to `queued` (not `running`),
  so `ProjectPage` shows `Processing` until it is `done` again; the jobs list
  is newest first, so `useProcessJob` takes the first `process` or `reprompt`
  job. The clips query key holds `project.result_set`: without it the gallery
  would keep the old set after a reprompt (status is `done` before and after).

## Do NOT (TASK-1..176)
- Do not rebuild a clip's SRT from the DB at zip time; do not add
  Premiere-only attributes to xmeml, point pathurl away from work/source.mp4,
  or count frames at meta.fps (VFR drift).
- Do not drop `asetpts=N/SR/TB+STARTPTS` after loudnorm; do not cut with
  select/aselect, cut before the layout, or snap a clip's own start/end to
  frames; compare cut/caption times in int ms (`to_ms`).
- Do not escape filter values by hand, reuse an old .ass, name template fonts
  "Inter", build crop x as a flat sum (eval depth 100) or use sendcmd.
- Do not grow process.py or put non-schema logic in models.py; do not accept
  a local path in `POST /projects`; do not edit `types.ts` by hand.
- Do not upgrade mediapipe unchecked, add opencv-python, tensorflow,
  pyannote or torch without a task that needs it, let tests download models,
  or commit `models/`/`data/`. Do not run Whisper without `vad_filter=True`.
- No `shell=True` or `fakes` in backend/clipforge; do not log request
  headers; live tests `@pytest.mark.live`, model tests `slow`, engine tests
  `engine_<name>`; tests never touch the network (Ollama on localhost only
  in engine tests).
- Do not clear a project's clips in `jobs.run_claimed` (it breaks resume:
  crop plans are keyed by clip id); do not let a skipped step rewrite its
  marker (`test_step_skips_finished_work_unless_forced` checks mtimes).
- Do not add Clip start/end columns back or store them twice; do not
  `json_array()` a REAL in a migration (precision loss, see Gotchas).
- Do not change `YTDLP_FORMAT`, edit `expected.json` or an applied migration,
  use `create_all`, or add Redis/Celery.
- Do not render, return or log an API key; write `.env.local` with mode
  0600; build brand paths from client file names; run tests in the repo cwd.
- Do not add a toast library, disabled placeholder buttons in the editor, or
  suggest cleanup cuts in the frontend (backend `polish` owns them).
- Do not store crop keyframes in clip-relative time or vary the crop window
  size over time; do not preview unsaved edits through the backend.

### Webhooks (TASK-165)

- Raise an event only through `webhook_events` (never raises); tests read
  the queue with `webhook_fakes.delivery_log(engine, hook_id)` and send with
  `make_worker(engine, FakeWallClock(START))` + `endpoint(respx_mock, 500,
  200)` (statuses in order, the last repeats). `emit(..., now=)` takes the
  fake time: a delivery is due when `next_attempt_at <= worker.now()`.
- `WebhookRow.secret_enc` is Fernet of the secret; `webhooks.secret_of(row)`.
  `token_store.fernet_for(data_dir, purpose)` got a `purpose` argument.
- `models.HttpUrl` is the existing http(s) validator; reuse it.
- A new table needs its row classes in `test_db.ROWS` and its indexes
  declared in `__table_args__` (test_migrated_schema_matches_row_classes).

### Posting worker (moved from HANDOFF, TASK-165)

- Posting worker: `PostWorker(engine, store, retry=, publisher_for=,
  now=FakeWallClock)`; call `poll()` / `run(post)` / `recover()` directly in
  tests (`tests/post_worker_fakes.py`: `connect`, `queue`, `make_worker`,
  `answer_published`, `answer_busy`, `RETRY` 60/120/240 s cap, 6 tries).
  Default `post_account_gap_s` = 60 holds a second post of the same
  account: use separate accounts or set it to 0. respx `respx_mock`
  asserts every route was called: do not register an unused route.
- `DailyQuota.zone` must be a `ZoneInfo` (messages use `.key`), not `UTC`.
  `publish_post(..., retry=, now=)`; a `QuotaExceeded` in an upload goes
  back to queued with the old attempts/attempted_at and `retry_at`.
- `posts.queue_post` resets attempts/next_attempt_at; `MOVE_FIELDS` has
  `attempted_at` and `next_attempt_at`. Migration 019 added both columns.

### Frontend posts (moved from HANDOFF, TASK-165)

- Frontend posts: the modal sends `title: ""` for TikTok/Instagram and
  shows the joined title+description as the caption; TikTok privacy has no
  default (Post now disabled until chosen). Bulk rules use
  `Intl.DateTimeFormat().resolvedOptions().timeZone`. e2e mocks
  `/api/accounts`, `/api/clips/*/posts`, `/api/posts/*/queue` via
  `page.route` (no real OAuth).

### MCP server (TASK-166)

- `mcp` is 2.x: `from mcp.server import Server`, handlers
  `(ctx, params)` passed to the constructor, types in `mcp_types` (snake_case
  fields: `input_schema`, `is_error`). No `@server.list_tools()` decorators.
- Tools are built from `/api/openapi.json` (`mcp_tools.build_tools`); the
  tool name is the operation id before `_api_v1_`. A new `/api/v1`
  operation becomes a tool automatically; to keep one from agents add it to
  `HUMAN_ONLY` / `NOT_OVER_MCP` in `mcp_tools.py` (`test_mcp_tools` lists
  the excluded operations and fails until the list is updated).
- The server is sync httpx run in `anyio.to_thread`; tests give it a
  `TestClient(app, headers={"X-API-Key": key})` (an httpx.Client), never
  httpx's ASGI transport (no lifespan). Do not pass `timeout=` per request
  to a TestClient (Starlette warns): it is set on the client in `connect`.
- The owner's `client` fixture has no key: build the agent's client with a
  second `TestClient(client.app, headers=...)` (the app is already started).
- Tests of an in-process MCP session: `Client(create_server(api, tools))`
  inside `asyncio.run` (no pytest-asyncio here). Shared loop helpers:
  `tests/loop_fakes.py` (`processed_clip`, `finish_render`).
- Length presets: `curate.run` returns early when candidates.json exists, so
  a test that curates twice in one job dir needs a fresh dir (or `force`).
  Curate also dedupes (IoU > 0.5): in llm_response.json D is dropped for A.
- Chapters / clip by topic: `StepSettings.ranges` (not a setting) restricts
  `curate.run`; `plan_scopes` gives each range its own `SourceMeta` timeframe
  so `select_candidates` drops clips outside it. A test that curates with
  ranges needs a custom length preset that fits the range (the fixture
  chapters are 16-24 s long). `get_llm` reads `app.state.llm`: a test can set
  it after startup (`client.app.state.llm = BrokenLLM()`).
- Audio events: `signals.analyze_signals` returns events and per-second
  tracks (`detect_audio_signals` = its events); `signals.CLASSES` is
  `audio_events.EVENT_CLASSES`. Tests fake YAMNet with `Yamnet(FakeSession,
  names)` and `monkeypatch.setattr(yamnet, "load_yamnet", ...)`; frame i stands
  for [0.48 i + 0.24, 0.48 i + 0.72] s. Test modules cannot import each other
  (`from test_score import` fails): copy the candidate.
- The real model finds `music` in the fixture's speech: tests of signals.json
  must filter by kind (`silence`) instead of comparing all kinds.
- VLM (engines/vlm_ollama): qwen3.5 is a thinking model: send `"think":
  false` to /api/chat or the reply may be empty within num_predict. The first
  call loads the 23 GB model (~17 s); later frames take ~0.5 s. ffmpeg's
  mjpeg encoder errors out ("Non full-range YUV is non-standard") when it
  gets no frame (time past the end): grab_frame turns both that and an empty
  stdout into StepError. `make check-engines` needs `ollama serve` running,
  else the engine_ollama_vlm test is skipped with the reason.

## Moved from HANDOFF at TASK-112 (media library, text overlays, transitions, drag)
- A library upload is an Asset tagged `media-library`; the owner's tags are
  the others (`media-library`, `uploaded`, `bundled` are reserved). Its
  extra info is `info.json` next to the file, not a DB column.
- `apihelpers.assert_error` needs the body to be exactly `{error, message}`:
  an `ApiError` with `extra` fails it.
- Library routes are `/api/library`, since `/api/media/{project_id}/...`
  serves a project's source.
- Text overlays: at most 5 text items (`MAX_TEXT_LAYERS`); the API 422s a
  6th, `clip_layers` drops extras of old timelines. `text_filter(props,
  font, height, start, end)` now lives in `pipeline/text_overlay.py`.
- ffmpeg 9 drawtext re-evaluates `alpha`, `x`, `y` and `fontsize` on every
  frame (t = time in the rendered clip); `alpha` fades the box too.
  Quote expressions with commas in single quotes inside the graph.
- `filter_value("a:b")` is `a\\:b` in the graph (two escape levels).
- Transitions (`pipeline/transitions.py`): `tpad` clone pads + `xfade`
  centred on each cut keep the clip's length, so captions, layers and audio
  keep their timing. Audio stays a hard cut.
- `xfade` needs both inputs on the same timebase: `concat` outputs
  1/1000000, a `trim` piece 1/fps -> put `settb=AVTB` on every piece.
- `ClipTransitions.sections[i]` is positional: the cut after the i-th section
  in play order (extras ignored); `auto` only applies to jump cuts inside a
  section. A join shorter than 1 frame per side is a hard cut.
- New Clip/ClipRow fields go at the END (after `result_set`): tests compare
  model field order, ClipRow columns and the migrated schema, and
  `tests/unit/test_models.py` has an explicit field-order list.
- Media drag: the kind is in the MIME type
  (`application/x-clipforge-media-<kind>`, `lib/newLayerItems.ts`) since
  drag data can only be read on drop; dragover checks `types` only.
- jsdom has no DragEvent: `fireEvent.drop` loses `clientX`; build it with
  `createEvent.drop(el, {dataTransfer})` and
  `Object.defineProperty(event, "clientX", {value})`, then `fireEvent(el, event)`.


## Stock B-roll (TASK-119)
- Pexels' `Authorization` header is the bare key (no "Bearer"); Pixabay takes
  `key=` in the query string. Pexels `video_files` can hold an HLS entry with
  `width`/`height` null: skip it. Pixabay `videos.large.url` can be "".
- Pexels/Pixabay download links are CDN URLs: never send the API key there.
- `stock.pixabay.cache` is module-level (24 h, Pixabay's rule): tests clear it
  with `pixabay.cache.clear()`.
- Python is 3.11: no `def f[T]()` syntax, use `TypeVar`.

## Moved from HANDOFF at TASK-170 (calendar, export v2, theme, posting history)
- Posting history (TASK-151): a new post status must be added to `tests/publishers/test_framework.py` (`LEGAL` and `at_status` path) or its parametrized transition tests fail. "Missed" = queued, `attempts == 0`, `next_attempt_at` NULL, `scheduled_at` < start − `post_missed_grace_s`; the worker reads `post_missed_policy` from `config.settings` at start. Skipped posts send no webhook. `/posts/history` must stay declared before `/posts/{post_id}`.
- Calendar (TASK-149): HTML drag data cannot be read during `dragover`, so `CalendarGrid` keeps the dragged post in state; jsdom drag tests pass `dataTransfer: { setData: vi.fn(), effectAllowed: "", dropEffect: "" }` to `fireEvent.dragStart/dragOver/drop`, Playwright `locator.dragTo` works in Chromium. Calendar tests fix "now" with `vi.useFakeTimers({ toFake: ["Date"] })` / `page.clock.setFixedTime` and build times with `localIso` (timezone-independent). Take theme screenshots with `animations: "disabled"` or the colour transition is caught half-way. A post's payload keeps its original `PostText` under `"text"`; send the whole `PostText` on edit (null = follow the clip).
- Export v2 (TASK-136): captions/text are laid out in the 1080 design frame (`aspect_size`) and scaled by libass/filters, so render at any `size=` without touching `captions.py`. `download.YTDLP_FORMAT` still caps URL downloads at 1080p: only 4K uploads give a 4K export. X limits: the 140 s / 512 MB figure is DM video only. Never ask `render_clip` for a size above `export_size`'s result (upscale).
- Theme (TASK-200): ember-coloured TEXT is `text-primary-ink` (never `text-primary`, fails AA in light); fills stay `bg-primary` with dark `text-primary-foreground`. Dialog overlays `bg-scrim`, inputs `bg-field`, no hard-coded zinc/black/white outside the player/video areas. Icons are Phosphor `XxxIcon` (`weight="fill"`, not `fill-current`); type `Icon` from `@phosphor-icons/react`. Theme key `clipforge.theme` (light|dark|system); keep `index.html`'s `#theme-init` and `lib/theme.ts` in sync (`lib/theme.test.ts` checks it). UI fonts live in `frontend/public/fonts`, never `assets/fonts` (caption picker + backend tests). In vitest a CSS `?raw` import is empty: read files with `readFileSync` (cwd frontend/). In Playwright init scripts `document.documentElement` can be null: observe `document`.
