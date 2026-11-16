Use the prd-creator skill to help me create a PRD and task list for ClipForge VERSION 2.
ClipForge v1 already exists in this repository (see docs/PRD.md, docs/parity.md, docs/HANDOFF.md). v2 extends it to FULL feature parity with OpusClip's publicly documented product (opus.pro and help.opus.pro), as listed in section 3.
Read this whole document, then read the existing code, docs/PRD.md, docs/decisions.md and docs/HANDOFF.md BEFORE writing anything. Follow it literally. Where it is silent, follow section 0.

=====================================================================
0. RULES (same as v1 — still mandatory)
=====================================================================
0.1 Never invent library APIs, CLI flags, model names, endpoints, quotas, or config keys. Verify by installing and reading help/source/types, or by reading the provider's CURRENT official docs; record the doc URL + date in docs/decisions.md.
0.2 Never invent package versions; let uv/npm lockfiles pin them; record in docs/stack.md.
0.3 No stubs, placeholders, fake data, TODOs, or hardcoded demo results in delivered code. If something can't be built, leave it out and explain in docs/questions.md.
0.4 A task is DONE only when its verification command ran and passed in this iteration; paste the real output tail into docs/progress.md.
0.5 Do not weaken/skip/delete tests. Mock only external boundaries (LLM HTTP, social platform APIs, stock APIs, model downloads). Tests NEVER call real external APIs.
0.6 Ambiguity: pick the simplest option consistent with this document, log it in docs/decisions.md, continue.
0.7 Blocked by something outside the repo (needs an API key, platform app approval, a model that won't install): log exact error in docs/questions.md, mark task BLOCKED, move to the next independent task.
0.8 Stay inside the project directory. Never commit .env, tokens, model weights, user media, or data/.
0.9 Schemas: single source of truth in backend/clipforge/models.py; regenerate frontend types; DB changes only via new numbered migrations that migrate existing v1 data.
0.10 Each iteration: read docs/HANDOFF.md FIRST, then progress/decisions/task list; do ONE task; run `make check`; commit with the task id.
0.11 SELF-HANDOFF: before any compaction/summarization, before ending an iteration, and after finishing or blocking a task, overwrite docs/HANDOFF.md (<150 lines) with: Updated; Current task + status; Done so far; Next exact step (with command); Last verification (command + real output tail); Open problems (exact errors); Gotchas learned; Do NOT (failed approaches). After any compaction/reset read it first and continue from "Next exact step". Code + git log win over HANDOFF.md on conflict. Commit it with each task.
0.12 Do not break v1: all v1 tests must keep passing. v1 features may be refactored, never removed.

=====================================================================
1. LEGAL / CLEAN-ROOM RULES (mandatory)
=====================================================================
1.1 Clean-room build: implement features from the functional descriptions in THIS document only. Do NOT scrape, crawl, decompile, or reverse-engineer opus.pro, its apps, its API, or its models (their Terms of Service forbid it). Do not fetch opus.pro pages from code or during the loop.
1.2 Do not copy OpusClip names for UI copy, logos, icons, images, fonts, templates, music, SFX, or text. Use ClipForge branding and original wording. Generic feature names (captions, scheduler, B-roll, reframe) are fine.
1.3 All bundled assets (fonts, music, SFX, stock, models) must be open-licensed; store each asset's LICENSE/attribution in assets/<type>/LICENSES.md. Models: record license in docs/stack.md; no models with non-commercial licenses unless marked "personal use only" in the UI.
1.4 Voice cloning / dubbing / eye-contact / face edits: only on the user's own voice/face. Require an explicit consent checkbox per voice profile ("This is my voice or I have written permission"), store the consent record, and watermark-free output only for consented profiles.
1.5 Social platforms: only official APIs with the user's own OAuth login. No browser automation of social sites, no password storage, no unofficial/private endpoints. Respect each platform's rate limits and content policies.
1.6 Copyright guard: every project has a "source rights" field (own content / permission / CC BY / public domain / other) and a credit line; publishing is blocked until it is set.

=====================================================================
2. ARCHITECTURE CHANGES FOR V2
=====================================================================
2.1 Still runs locally by default, single machine. Add optional "LAN multi-user mode" for team features (section 3.12): local accounts (argon2 password hashes), sessions, roles. Default stays single-user with no login.
2.2 Job system: upgrade the SQLite worker to N workers with job priorities and per-job-type concurrency limits (GPU-heavy jobs = 1 at a time). Jobs are resumable after app restart.
2.3 Heavy AI features run as optional "engines": each engine is a module with install_check(), install instructions in README, and a capability flag the UI reads. If an engine isn't installed, its UI shows "Not installed — see setup" instead of failing.
2.4 Credits-like usage meter: track local compute time and any paid API spend per project (LLM tokens, stock API calls, TTS) in a usage table; Settings shows totals and optional monthly caps that block new jobs when exceeded.
2.5 Public REST API + webhooks for automation (section 3.14). API keys hashed in DB.

=====================================================================
3. FEATURES — FULL PARITY (each must be built, tested, and listed in docs/parity.md)
=====================================================================
3.1 Submit / import
- Sources: YouTube URL, generic video URL (yt-dlp supported sites), local upload (resumable, up to 30 GB, chunked), local inbox folder watch, Google Drive (OAuth, Drive API files.get media download), Dropbox (optional), Zoom/Vimeo via yt-dlp where supported (verify).
- Upload own SRT/VTT with the video to skip transcription (word timings distributed inside cues, flagged approximate).
- Auto Import: watch one or more YouTube channels (public RSS feed; verify URL format) and auto-create projects with saved per-channel default settings; optional auto-schedule as drafts.
- Live-stream clipping: record a live HLS/YouTube live stream via yt-dlp/ffmpeg into rolling segments; run the pipeline on segments as they finish; clips appear while the stream is live; handle gaps ("recording gap" marker), stream not live yet (waiting state), stop recording.
- "Captions/reframe only" mode: process the whole video (or a timeframe) as one clip without AI clipping.
- Supported languages: transcription in all Whisper languages with auto-detect; RTL languages (Persian, Arabic, Hebrew) render correctly in captions.

3.2 AI clipping controls
- Clip length presets and custom ranges (0-1m, 1-3m, 3-5m, 5-10m, 10-15m) as well as v1 presets.
- Processing timeframe, genre, number of clips, keyword/topic search, and "prompt to clip" (natural-language request, e.g. "every time he talks about his mom").
- Reprompt: refine an existing project's results with a new prompt without re-transcribing.
- Non-speech clipping ("clip anything"): find moments from visual + audio events, not only speech — use scene changes, motion energy, audio events (laugh, applause, music, cheering via YAMNet classes), and a vision-language model on sampled frames (local VLM engine, e.g. a Qwen2-VL/LLaVA-class model via Ollama if available — verify) to caption frames; feed frame captions into the curate prompt.
- Topic chapters: segment long videos into topics and let the user clip by topic.
- Virality score with Hook/Flow/Value/Trend breakdown and explanation (v1) plus an optional "trend" input from 3.13.

3.3 AI reframe & layouts
- Aspect ratios 9:16, 1:1, 4:5, 16:9; custom crop ratio.
- Speaker/face tracking (v1) + moving subject tracking (non-human objects: generic object tracker, e.g. OpenCV CSRT/ByteTrack-class — verify availability) + manual subject tracking (click a point/box to follow).
- Genre-specific reframing presets (podcast 2-person, stand-up single performer, gaming/screenshare, vlog).
- Layouts: fill, fit (blur bg), split (2 speakers), three-speaker grid, screenshare + facecam, gameplay + facecam, picture-in-picture; dynamic layout switching per segment (auto by speaker/scene + manual per segment); set default layout.
- Manual reframe: drag/resize crop box per segment with keyframes.

3.4 Captions
- Animated caption templates (10+ original templates), live preview, per-clip and per-word editing.
- AI emojis and AI keyword highlights (editable per word).
- Speaker-based caption colors.
- Caption position, size, font, colors, stroke, shadow, box, uppercase, line count, words per line.
- Custom font upload (TTF/OTF), used in captions and brand templates.
- Translate captions to other languages (LLM), with RTL support (bundle an OFL Persian-capable font, e.g. Vazirmatn).
- Brand vocabulary: term list -> Whisper hotwords/initial prompt (verify faster-whisper params) + post-correction map + "replace everywhere in project".
- Auto censor curse words: default list + custom list + per-word manual censor; beep or mute; masked caption text.
- Download transcripts (txt) and subtitles (srt, vtt) for source and per clip.

3.5 Editor (timeline + transcript)
- Transcript-based editing (v1) + multi-track timeline: main video, B-roll, overlays, text, music, SFX, voiceover tracks.
- Trim/extend, add a section from anywhere in the source, split at playhead, delete, drag-rearrange sections, duplicate clip, split one clip into two clips.
- Snap editing (word boundaries, segment edges, playhead, other layers) with toggle.
- Keyboard precise editing: frame step, 1 s step, split, delete, zoom, copy/paste, playback speed.
- Undo/redo history, autosave, version restore.
- Text overlays: up to 5 layers, each with font/size/colors/box/position/animation in/out/start/end.
- Transitions: auto on jump cuts + manual; at least crossfade, zoom punch, whip, slide (verify ffmpeg xfade options).
- Media uploads: user images/videos/logos/audio in a media library; drag onto timeline.
- Viral hook: 5+ original hook templates (animated text + punch-in zoom + whoosh) applied to the first 2-3 s, filled from captions or video theme; editable/removable.
- Auto headline: one-line opening text overlay generated by the LLM, styled by brand template.
- Motion graphics: LLM finds names, numbers, dates, key phrases -> animated lower-thirds/number callouts (original templates) at the right timestamps; editable.
- Speech cleanup: filler words (multi-language list), pauses (user-set threshold), bad takes (LLM detects repeated/abandoned sentences); show what will be removed and let user uncheck before applying.
- Speech enhancement: noise reduction + voice isolation (local engine, e.g. DeepFilterNet — verify; fallback ffmpeg arnndn/afftdn), strength slider.
- Music: bundled royalty-free library (CC0/CC BY with attribution) + user upload; volume, fades, auto-duck under speech.
- Auto SFX: bundled CC0 SFX pack; AI places SFX at key moments (punchlines, cuts, emphasis words); generate-by-prompt only if a local open-license SFX model is available (verify), else search the bundled pack by tag.
- AI voiceover: local TTS (Kokoro/Piper — verify), multiple voices, edit/move/delete, duck original audio.
- Eye contact correction: optional engine using an open-source gaze-redirection model if one exists with a usable license and runs on macOS arm64 (research, verify, record in decisions.md); apply only to frontal talking-head shots; if none is usable, mark BLOCKED with evidence.
- AI upscaling: optional engine (Real-ESRGAN ncnn/Vulkan or Core ML build for macOS arm64 — verify); clips up to 5 min; preview before/after.
- AI expand (outpainting) to change aspect ratio without cropping: optional engine via a local open-license image/video outpainting model if feasible (verify); otherwise mark BLOCKED with evidence.
- Intro/outro cards (from brand template or uploaded).
- Watermark/logo overlay from brand template.

3.6 B-roll
- Stock B-roll: Pexels and Pixabay APIs (keys in .env; verify endpoints + license terms; store attribution); "find spots" = LLM picks sentences that benefit from B-roll and search keywords; user reviews; insert as full-screen cutaway or picture-in-picture.
- AI image B-roll: local image model engine (e.g. Stable Diffusion/SDXL/FLUX-schnell class via diffusers or mflux on Apple Silicon — verify license + install) with style presets; generate per sentence; Ken-Burns motion.
- AI video B-roll: optional engine (local open-license text-to-video model if feasible on the hardware — verify); else BLOCKED with evidence.
- Regenerate / replace / remove B-roll; B-roll per segment.

3.7 Dubbing & translation
- Video dubbing into 25+ languages: transcript -> LLM translation -> TTS in target language -> time-fit (speed adjust within limits, re-segment) -> mix with original background (source separation via Demucs engine — verify) -> captions in target language.
- Voice clone dubbing: optional engine using an open-license voice-cloning TTS (e.g. XTTS-class — check license; if non-commercial, mark "personal use only") with the consent rule 1.4.
- Edit the dubbed transcript and re-render.

3.8 Brand
- Brand templates (unlimited locally): caption style, fonts, colors, logo + position + opacity, intro/outro, default layout, hook/headline style, music default.
- Brand kit: shared assets (logos, colors, fonts) reused across templates.
- Apply a template at project creation or per clip; set default template.

3.9 Export
- MP4 up to the source resolution incl. 4K (no upscaling unless 3.5 upscale is used); bulk download as zip; export XML for Premiere Pro (FCP7 xmeml) and DaVinci Resolve (FCPXML — verify version Resolve imports) including captions as SRT and B-roll/overlays as separate tracks where the format allows.
- Export presets per platform (Shorts, TikTok, Reels, LinkedIn, X) with correct max durations and sizes (verify each platform's current limits; record sources).

3.10 Publishing & scheduler
- Social accounts via official APIs + OAuth (user's own app credentials in .env/settings; document each platform's developer-app setup and review requirements in README):
  - YouTube (Data API v3: resumable upload, publishAt scheduling, thumbnails, tags, category, made-for-kids, synthetic-media flag).
  - TikTok (Content Posting API), Instagram (Graph API, professional accounts — Reels), Facebook Pages (Graph API video/Reels), X (API v2 media upload), LinkedIn (Posts API with video).
  - For each: verify CURRENT official docs for endpoints, scopes, quotas, review requirements, and "unaudited app" restrictions (e.g. private-only uploads); record in docs/decisions.md; surface restrictions in the UI. If a platform can't be used without approval, implement and test against recorded responses and mark it "needs platform approval" in parity.md.
- Multiple accounts per platform.
- Publish now, schedule, calendar (month/week, drag to reschedule, cancel), bulk scheduler (posts/day, time slots, skip days, multiple platforms at once), per-platform post customization (title, caption, hashtags, collaborator tags where the API supports it, link to the full video, privacy), custom thumbnails/covers (frame picker or upload, apply to all).
- AI post copy generator: title, description, hashtags per platform style.
- Posting rate limits per platform/account; quota guard; retry/backoff; posting history with links to the live posts.
- Scheduled posts publish even when the UI is closed (background worker); posts due while the machine was off publish on next start (configurable: post late or skip).

3.11 Library, search & organization
- Projects list with filters, auto-save, rename projects/clips, delete with confirm, reprocess.
- Collections (add from gallery/results/search; export a collection as zip).
- Library search across all videos: full-text (SQLite FTS5) over transcripts + semantic search (local embeddings, e.g. sentence-transformers or Ollama embeddings — verify) + visual search over frame captions from 3.2; results jump to the exact moment; "create clip from this moment"; bulk export results.
- Auto-cataloging: LLM tags each video/clip (topics, people, mood, genre) for filtering.
- Storage manager: disk usage per project, cleanup of work files, archive projects.

3.12 Team workspace (LAN multi-user mode, optional)
- Local accounts, roles (owner, editor, viewer), invite via one-time link on LAN, sub-teams/folders, member permissions per workspace, shared brand templates, share a project link (read-only or comment) on LAN.
- Activity log. Off by default.

3.13 Growth & analytics
- Clip analytics: pull views, watch time, likes, comments, shares per published post from each connected platform's official analytics API where available (verify); show on cards, per-clip charts, and an Analytics dashboard (top clips, views over time, by template/length/genre/layout).
- Trend input: optional — fetch trending topics/hashtags only from official APIs the user has access to (verify; e.g. YouTube videos.list chart=mostPopular per region) and use them as context for clip selection and post copy. No scraping.
- Insights: simple aggregates and recommendations ("clips 30-45 s with karaoke_bold get 2x views") — no ML training.

3.14 Automation & integrations
- Public REST API (/api/v1) mirroring core actions: create project (URL/upload), get clips, render, export, schedule post, get transcript, brand templates, collections, censor job, thumbnail job. API keys, rate limits, OpenAPI docs at /api/docs.
- Webhooks: project.completed, clip.rendered, post.published, post.failed (HMAC-signed, retries).
- Zapier-style: document how to use webhooks + API with n8n/Zapier; ship an example n8n workflow JSON.
- MCP server: expose ClipForge actions as MCP tools for AI agents (verify current MCP SDK API).

3.15 Thumbnails & covers
- AI thumbnail generator: best frame selection (face, eyes open, expression via face landmarks) + bold title text templates; optional local image model background; export 1280x720 and 1080x1920.

3.16 Mobile access
- Responsive PWA: projects, clip gallery, preview, approve/schedule, calendar on phone over LAN; heavy editing stays desktop. (No native app.)

3.17 Notifications & settings
- In-app notifications + optional email (SMTP settings) and desktop notifications: project done, render failed, post published/failed, quota warnings.
- Settings: engines status, API keys, platform connections, defaults, usage caps, storage paths, language.

3.18 Clipping campaigns & earnings (my main income use case)
- Campaign model: Campaign {id, name, creator_name, source_channel_urls, platform_board ("whop"|"direct"|"other"), campaign_url, permission_source_url, permission_screenshot_asset_id, permission_checked_at, badge ("open"|"register_first"|"apply_first"|"paid"), rate_per_1k_usd|None, budget_note, allowed_platforms, required_hashtags, required_credit_line, required_tags_mentions, min_duration_s, max_duration_s, banned_content_notes, monetization_allowed_elsewhere (bool|unknown), submission_instructions, status ("active"|"paused"|"ended"), notes}.
- All campaign data is entered by the user (form + paste); NO scraping of Whop, Clip-OK, Discord, or creator sites. Store the permission source URL + a user-uploaded screenshot + date; block publishing for a campaign until permission fields are filled (extends rule 1.6).
- Watch campaign creators: per campaign, add the creator's YouTube channel(s) to Auto Import (3.1) so new uploads become projects within minutes; "fresh upload" badge + speed-first queue priority.
- Campaign presets: applying a campaign to a project auto-sets clip length range, caption template, required credit line in description, required hashtags, allowed platforms, and checks every rule before publish (rule checker shows pass/fail per rule; publish blocked on fail).
- Multi-account: map each campaign to the clipper's own social accounts (3.10); bulk schedule per campaign.
- Submission tracker: after publishing, show the post URL with a one-click "copy for submission" (URL + required info) and a checklist the user ticks when submitted on the campaign board; Submission {post_id, campaign_id, submitted_at, status ("not_submitted"|"submitted"|"approved"|"rejected"|"paid"), approved_views|None, payout_usd|None, notes}.
- Earnings dashboard: per campaign / platform / month — views (from 3.13 analytics), estimated campaign earnings = approved_views/1000 * rate (clearly labeled estimate), actual payouts entered by user, YouTube revenue entered manually or via YouTube Analytics estimatedRevenue if the account is in YPP (verify metric availability), total income, CHF conversion with a user-set rate, CSV export for Swiss tax records.
- Performance insights: which creators/campaigns/templates/lengths/hooks earn most per hour of work; "stop/continue" suggestions as simple aggregates.

3.19 Autopilot with approval (human-in-the-loop automation)
- Purpose: ClipForge finds, clips, checks, and schedules automatically; NOTHING is published until the user approves it.
- Per-campaign autopilot settings: on/off, watched channels (from 3.18), max clips per new source video (default 3), clip length range, caption/brand template, target social accounts, posting slots, max posts/day per account (default 3, hard cap 5), auto-expire drafts after N days (default 3, since fresh clips matter).
- Flow: new upload detected (3.1 Auto Import) -> project created with campaign preset -> clips generated -> rule checker (3.18) -> passing clips become Drafts in the Approval Inbox; failing clips are kept in a "Needs fix" tab with the failed rules listed. Autopilot never publishes, schedules, or submits on its own.
- Approval Inbox page: card per draft with autoplay preview, title, description, hashtags, campaign, rate, virality score, rule-check results, source video link, time since source upload (freshness). Actions: Approve (schedule into next free slot), Edit (open editor, then approve), Reject (optional reason chips: boring, out of context, bad crop, bad captions, too long, other), Approve all for this campaign (with confirm dialog). Keyboard: A approve, R reject, E edit, J/K next/prev.
- After publish: "Ready to submit" list with one-click copy of post URL + required campaign info; user submits on the campaign platform manually and ticks "submitted" (3.18 Submission).
- Learning from feedback: store reject reasons and approve/reject per clip; use them as (a) few-shot examples in the curate prompt per campaign/creator and (b) score adjustments (e.g. penalize lengths/templates often rejected). Simple, deterministic, tested; no model training.
- Safety switches: global "Pause all autopilot" button; per-campaign toggle; automatic stop when permission evidence is missing, the campaign status is ended/paused, the end date passed, the daily quota/rate limit is reached, or 3 consecutive uploads fail (alert the user).
- Approval is human-only: the approve/schedule/publish actions require a local UI session (not an API key); API/MCP clients (3.14) may create drafts, list the inbox, and add review notes, but cannot approve or publish. Enforce server-side and test it (403 for API key on approve/publish).
- Daily digest notification (3.17): new drafts waiting, posts scheduled today, submissions pending, estimated earnings yesterday.
- Integrations: campaign platforms are NEVER automated via browser bots or scraping (rule 1.5 extended to campaign marketplaces); use only official APIs/MCP connectors a platform documents (verify per rule 0.1) — otherwise manual submission.

=====================================================================
4. DATA MODEL ADDITIONS (exact names; add fields via migrations)
=====================================================================
Clip.segments: list[[start,end]] (replaces start/end; migrate v1 data), Clip.tracks: Timeline {video, broll, overlays, text, music, sfx, voiceover}, each item {id, kind, asset_id|None, start, end, props: dict}.
Asset {id, kind: video|image|audio|font|logo|music|sfx, path, license, attribution, source_url|None, tags}
BrandKit, BrandTemplate (extends v1), CaptionTemplate (user-created allowed)
VoiceProfile {id, name, sample_paths, consent_text, consent_at, engine}
SocialAccount {id, platform, external_id, display_name, token_ref, scopes, connected_at, restrictions: list[str]}
Post {id, clip_id, account_id, platform, payload: dict, thumbnail_asset_id|None, scheduled_at|None, status: draft|queued|uploading|published|failed|canceled, external_post_id|None, url|None, error|None, attempts}
Collection, CollectionItem; Tag; SearchIndex (FTS5 + embeddings table)
User, Workspace, Membership {role}, Invite, ActivityLog (LAN mode only)
ApiKey {id, name, hash, created_at, last_used_at}, Webhook {id, url, events, secret_hash}, WebhookDelivery
UsageRecord {id, project_id|None, kind, units, cost_usd|None, at}
AnalyticsSnapshot {post_id, date, views, watch_time_s, likes, comments, shares}
Project.source_rights: own|permission|cc_by|public_domain|other, Project.credit_line, Project.campaign_id|None
Campaign, Submission (fields in 3.18)
AutopilotSettings {campaign_id, enabled, max_clips_per_source, slots, max_posts_per_day, draft_ttl_days, account_ids}, Draft {clip_id, campaign_id, status: pending|needs_fix|approved|rejected|expired, rule_results, reject_reason|None, decided_at|None}, FeedbackEvent {clip_id, campaign_id, action, reason|None, at}

=====================================================================
5. TESTING & ACCEPTANCE (v2)
=====================================================================
- All external APIs (social, Drive, Pexels/Pixabay, analytics, LLM) tested with recorded responses (respx); zero real network calls in `make check`.
- Optional engines: tests use tiny fixtures and are skipped with a clear reason ONLY when the engine is not installed (pytest marker `engine_<name>`); `make check-engines` runs them when installed. The skip must never hide a failure of an installed engine.
- Renders: ffprobe-verified (size, codecs, duration ±0.2 s) for every new layout, overlay, transition, dub, music duck, censor beep (audio RMS spike at the censored word time), 4K export, XML exports (validate against basic structure, and import-tested manually: document steps).
- Scheduler: deterministic tests with a fake clock: slot generation, timezones/DST, skip days, multi-platform bulk, due pickup, missed-while-offline policy, retries/backoff, quota guard, rate limits.
- Live clipping: test with a local looping HLS stream produced by ffmpeg.
- Team mode: auth, roles, permission checks on every endpoint (tests for 401/403).
- Public API + webhooks: contract tests generated from OpenAPI; HMAC signature test.
- Autopilot: fake-clock tests for upload->drafts flow, never-publish-without-approval invariant, API key gets 403 on approve/publish, safety stops (missing permission, ended campaign, quota, 3 failures), draft expiry, feedback affects next curate prompt/score.
- Campaigns: rule-checker unit tests (each rule pass/fail), publish blocked without permission fields, earnings math (exact numbers), CSV export format.
- Playwright e2e: (1) live-free full flow from v1 still passes; (2) prompt-to-clip -> edit with B-roll + text overlay + music -> render -> bulk schedule to 2 mocked platforms -> calendar shows posts -> reschedule -> cancel; (3) library search -> create clip from result -> add to collection -> export collection; (4) dubbing flow with a mocked TTS engine.
- docs/parity.md: every feature in section 3 with status done / needs platform approval / blocked (with evidence) — no feature may be silently missing.
- `make check` green after every task; HANDOFF.md updated per 0.11.

=====================================================================
6. TASK ORDER (vertical slices; split any task too big for one iteration)
=====================================================================
  T25 Migrations: segments/tracks timeline model, assets, source_rights; v1 data migration + tests
  T26 Worker upgrade (N workers, priorities, GPU lock, resume) + engines framework + usage meter
  T27 Import sources: generic URL, chunked 30 GB upload, inbox watch, Google Drive, SRT/VTT upload, captions-only mode
  T28 Auto Import (YouTube RSS, per-channel defaults)
  T29 Clipping controls: custom lengths, prompt-to-clip, reprompt, topic chapters
  T30 Clip-anything: VLM frame captions + audio event classes into curation
  T31 Reframe v2: 4:5/custom, object tracking, manual tracking, genre presets
  T32 Layouts v2: 3-grid, screenshare/gameplay+facecam, PiP, dynamic per-segment switching, keyframed manual reframe
  T33 Captions v2: 10 templates, speaker colors, custom fonts, translation + RTL, brand vocabulary, censor
  T34 Multi-track timeline editor core (tracks, snap, keyboard, undo/redo, autosave, versions)
  T35 Trim/extend/add section/split/rearrange/duplicate/split-into-two
  T36 Text overlays + transitions + media library uploads
  T37 Viral hooks + auto headline + motion graphics
  T38 Speech cleanup (fillers multi-language, pauses, bad takes) + speech enhancement engine
  T39 Music library + auto-duck + Auto SFX + TTS voiceover engine
  T40 Stock B-roll (Pexels/Pixabay) + find spots
  T41 AI image B-roll engine + Ken Burns; AI video B-roll engine (or BLOCKED with evidence)
  T42 Upscale engine + AI expand engine (or BLOCKED with evidence) + eye contact engine (or BLOCKED with evidence)
  T43 Dubbing pipeline (translate, TTS, time-fit, Demucs background) + voice clone engine with consent
  T44 Brand kit + brand templates v2 + intro/outro
  T45 Export v2: 4K, platform presets, FCPXML for Resolve, collection export
  T46 Publisher framework + YouTube (upload, schedule, thumbnails, quota)
  T47 TikTok + Instagram + Facebook publishers (recorded-response tests; approval status in parity.md)
  T48 X + LinkedIn publishers
  T49 Calendar + bulk scheduler (multi-platform) + post customization + thumbnails/covers + AI post copy
  T50 Posting worker hardening: rate limits, retries, missed-while-offline policy, history
  T51 Collections + FTS5 + semantic + visual search + auto-cataloging + storage manager
  T52 Live-stream clipping
  T53 AI thumbnail generator
  T54 Analytics ingestion per platform + dashboard + insights + trend input (official APIs only)
  T55 Public REST API v1 + API keys + OpenAPI + webhooks + n8n example + MCP server
  T56 LAN team mode: users, roles, invites, sub-teams, permissions, share links, activity log
  T57 Notifications (in-app, desktop, SMTP) + settings v2 + responsive PWA
  T58a Campaign model + forms + permission evidence + presets + rule checker
  T58b Campaign watch (Auto Import priority) + submission tracker
  T58c Earnings dashboard + CHF + CSV tax export + insights
  T58d Autopilot settings + draft pipeline + safety stops
  T58e Approval Inbox UI + keyboard + ready-to-submit + daily digest + feedback learning
  T58 Playwright e2e v2 suite (incl. autopilot: new upload -> drafts in inbox -> approve 2, reject 1 -> 2 scheduled -> API key approve attempt returns 403; campaign flow: create campaign -> fresh upload project -> clips with campaign preset -> rule check -> schedule -> mark submitted -> enter payout -> dashboard shows earnings) + README v2 (engines setup, platform developer-app setup) + parity.md complete + final `make check`
- Each task: id, title, goal, files, testable acceptance criteria, verification command(s), dependencies, and "docs/HANDOFF.md updated and committed".
- Never start a task whose dependencies are not DONE.
