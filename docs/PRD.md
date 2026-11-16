# ClipForge PRD

Source of truth: `.agent/prd/SPEC.md` (owner's full spec, sections 0-12). This PRD summarizes and adds decisions; on any conflict SPEC.md wins. Section refs like "SPEC 6.3" point there.

## 1. Overview, objectives, success criteria
- Local single-user OpusClip-style clipper: paste link/upload -> settings -> AI finds ranked vertical clips with virality scores -> transcript editor -> render/export.
- Primary content: stand-up comedy (owner has permission); also podcasts, talks.
- Own name/logo (text "ClipForge")/colors. No OpusClip assets, copy, fonts.
- Success: `make check` green; pipeline integration test (SPEC 9.3) and Playwright e2e (SPEC 9.6) pass on fixture; real run on a 10-min comedy video yields >= 5 clips rendered 1080x1920 with captions.

## 2. Audience
Owner only (Omair), macOS Apple Silicon, 48 GB RAM. No accounts, cloud, payments, telemetry.

## 3. Core features (TASK ids map to .agent/tasks.json; T-ids from SPEC 12)
- Scaffolding + `make check` (T01): TASK-2..4
- Config, models, DB, migrations (T02, SPEC 4-5): TASK-5..7
- Fixtures (T03, SPEC 9.1): TASK-8..9
- ffmpeg wrapper + ingest (T04, SPEC 6.1): TASK-10..11
- Transcribe (T05, SPEC 6.2): TASK-12
- LLM clients + curate (T06, SPEC 2, 6.5): TASK-13..14
- Minimal render + `clipforge run` (T07): TASK-15
- Signals (T08, SPEC 6.3): TASK-16..17
- Enrich + genre prompts (T09, SPEC 6.4-6.5): TASK-18..19
- Score + snap (T10, SPEC 6.6-6.7): TASK-20..21
- Reframe (T11, SPEC 6.8): TASK-22..23
- Captions (T12, SPEC 6.9): TASK-24..26
- Polish + cut_ranges render (T13, SPEC 6.10-6.11): TASK-27..28
- Export (T14, SPEC 6.12): TASK-29..30
- Job worker + API + SSE (T15, SPEC 7): TASK-31..35
- Frontend shell + type gen (T16): TASK-36..37
- Home + settings panel (T17, SPEC 8.1-8.2): TASK-38..39
- Processing view (T18, SPEC 8.3): TASK-40
- Gallery (T19, SPEC 8.4): TASK-41
- Editor core (T20, SPEC 8.5): TASK-42..43
- Editor panels + render (T21, SPEC 8.5): TASK-44..45
- Brand templates + settings pages (T22, SPEC 8.6-8.7): TASK-46..47
- Playwright e2e (T23, SPEC 9.6): TASK-48..49
- README + parity + final check (T24, SPEC 10): TASK-50..51

## 4. Key user flows
1. Home: paste YouTube link or upload/drag file -> settings panel (thumb, title, duration) -> "Get clips".
2. Processing view: steps Download, Transcribe, Analyze audio, Find clips, Score, Reframe, Captions; live SSE progress; leave and return.
3. Gallery: scored 9:16 cards, sort/filter/search, Download all.
4. Editor: transcript cut/extend, timeline trim, captions/layout/brand/text tabs, Save, Render, Download.
5. Export: mp4, srt, json, zip, Premiere FCP7 XML.

## 5. Stack
Fixed by SPEC 2. No substitutions. Versions resolved by uv/npm, recorded in docs/stack.md.

## 6. Prerequisites and access
- Host tools verified 2026-10-30: ffmpeg/ffprobe 9.0.1 (/opt/homebrew/bin), uv 0.11.26, node v26.4.0, npm, ollama (installed, server not running), docker (not used).
- Python 3.11: not on PATH; `uv python install 3.11` in TASK-1/2.
- Database: local SQLite file data/clipforge.db; no external DB.
- MCPs: none required. Playwright chromium installed by `npx playwright install chromium` in TASK-48.
- Env vars (placeholders in `.env.local`, values filled manually by owner; app also reads `.env`):
  - `LLM_PROVIDER`: `copilot` (default), `openai` (OpenAI-compatible) or `ollama`.
  - `GITHUB_COPILOT_TOKEN`: optional; if empty the app runs `gh auth token -u omairtemurian`.
  - `OPENAI_BASE_URL`: default for owner = `https://models.github.ai/inference` (GitHub Models, OpenAI-compatible chat/completions, supports response_format json_object).
  - `OPENAI_API_KEY`: owner's personal GitHub PAT with `models:read`. Never committed.
  - `LLM_MODEL`: e.g. `openai/gpt-4.1` (GitHub Models id format publisher/model).
  - `OLLAMA_HOST`: http://localhost:11434.
  - `HF_TOKEN`: optional, diarization only.
- Login/test users: none (single-user, no auth).
- Network needed for: uv/npm installs, faster-whisper model download, YAMNet download, face model download, yt-dlp. Tests never need network (SPEC 0.5).
- Gaps / decisions:
  - LLM = owner's personal GitHub Copilot (SPEC 13.1): LLM_PROVIDER=copilot default, CopilotClient -> api.githubcopilot.com, token via `gh auth token -u omairtemurian`. Verified 2026-10-30. GitHub Models/OpenAI/Ollama remain options.
  - Loop runs on macOS host, not Ralph's Docker sandbox (spec needs macOS arm64 binaries). Decision: proceed; local runner adaptation done before loop start.
  - Pushing: only to github.com/omairtemurian/clipforge, private (pre-push hook enforces). Ralph agents never push.

## 7. Data model
Exactly SPEC 5 in backend/clipforge/models.py; DB tables project, clip, job, brand_template, schema_version via migrations/NNN_name.sql. Types exported to frontend/src/api/types.ts by scripts/gen_types.py (SPEC 0.9).

## 8. UI principles
SPEC 8. Dark default, left sidebar (Home, Projects, Brand templates, Settings). Own palette: accent `#FF6B35` (ember orange), surfaces zinc-900/950. Text logo "ClipForge". Min width 1280px. Score badge: >=80 green, 60-79 yellow, <60 gray.

## 9. Security
Localhost only (bind 127.0.0.1). subprocess arg lists, never shell=True. Uploads saved under data/input with sanitized names. Path params resolved and checked inside data/. Error JSON {error, message}, no stack traces. Secrets only in .env/.env.local (gitignored).

## 10. Phases
P1 backend pipeline CLI (TASK-2..30) -> P2 API (31..35) -> P3 UI (36..47) -> P4 e2e + docs (48..51).

## 11. Decisions added beyond SPEC (also copied into docs/decisions.md by TASK-2)
- Settings page (SPEC 8.7) needs an API SPEC 7 omits: add `GET/PUT /api/settings` and `POST /api/settings/test-llm` (simplest consistent option, SPEC 0.6).
- Task ids: TASK-1 = prerequisite check; SPEC T-ids kept in order, split into TASK-2..51; each task title carries its T-id.
- Ralph per-iteration rule = SPEC 0.10 (one task, `make check`, commit naming task id) plus HANDOFF.md (SPEC 0.11).

## 12. Out of scope
SPEC 11.

## 13. Assumptions
Owner fills .env.local; enough disk for models (~2 GB); fonts Montserrat ExtraBold + Inter Bold (OFL) downloaded into assets/fonts with their OFL license files.
