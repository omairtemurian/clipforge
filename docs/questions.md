# Open questions

## DECIDE: is Standard strong enough? (TASK-237, 2026-11-06)

The owner saw "no difference" on a Skull Moment / Standard run. The main
cause is fixed: the Skull Moment and the bass drop are now one budget unit
and kept whole (the B&W freeze with the skull now renders; see
`tests/pipeline/test_proedit_skull_render.py`). The Standard numbers in code
equal the SPEC-v3 3.1 table exactly (`budgets.py`: SFX 1 per 4 s, 2 effect
items per 5 s, no pattern-interrupt target), so they were not changed. The
SPEC itself keeps Standard subtle outside the signature move. Options:

- A: keep the SPEC table (Standard = signature move + light accents);
  re-check on the owner's clip first. (Recommended)
- B: raise Standard to 3 effect items per 5 s and SFX 1 per 3 s (a SPEC
  change; presets still may lower it).
- C: keep the densities but give Standard a pattern-interrupt target
  (e.g. every 4-6 s) so `retention.fill_plan` fills long gaps.

## DeepFilterNet pip package unusable (TASK-113, 2026-11-02)

Not blocking: the engine uses the official `deep-filter` 0.5.6 program
instead (README "Engine: deepfilternet"). The pip package `deepfilternet`
0.5.6 (last release, 2023-08) installs on macOS arm64 but fails to import
with current torchaudio:

```
File ".../site-packages/df/io.py", line 9, in <module>
    from torchaudio.backend.common import AudioMetaData
ModuleNotFoundError: No module named 'torchaudio.backend'
```

and pins numpy<2 (the project has numpy 2.4.6). Revisit if a new release
fixes both.

## BLOCKED gaps: v2 credentials (TASK-55, 2026-10-31)

`uv run python scripts/check_prereqs.py` finds all 24 v2 credentials missing
(`.env`, `.env.local` and the environment). Nothing is stubbed: the code, the
settings UI and the recorded-response (respx) tests are built; only the live
call stays untested until the owner sets the value in `.env.local` (SPEC-v2
0.7). Platform developer apps also need each platform's own review (README
v2, T58).

- GOOGLE_OAUTH_CLIENT_ID: blocks the live YouTube login and upload
  (Shorts), Google Drive import and YouTube analytics.
- GOOGLE_OAUTH_CLIENT_SECRET: same features as GOOGLE_OAUTH_CLIENT_ID.
  TASK-66 (Drive import) is built and tested with recorded Google responses
  (respx); untested live: the consent + callback on a real Desktop client,
  files.get on a real Drive file and the `drive.readonly` consent screen.
  Without the ID the Drive dialog shows "Google Drive needs credentials"
  and `/api/sources/gdrive/{connect,file,import}` answer 412.
  TASK-139 (YouTube publisher) uses the same client and is tested with
  recorded YouTube Data API answers only; untested live: the channel
  consent (`youtube.upload` + `youtube.readonly`), a real resumable upload,
  publishAt, thumbnails.set (needs a verified channel) and whether an
  unaudited project's public uploads stay private. Without the ID
  `/api/accounts/youtube/connect` answers 412 needs_credentials.
- TIKTOK_CLIENT_KEY: blocks the live TikTok login and Content Posting API
  publish. TASK-140 (TikTok publisher) is built and tested with recorded
  answers only; untested live: the desktop Login Kit consent (hex PKCE,
  loopback redirect), creator_info, a real chunked upload and the post
  status. Even with keys, an unaudited app posts only as SELF_ONLY to
  private accounts, and TikTok's audit is unlikely to accept a personal
  tool. Without the key `/api/accounts/tiktok/connect` answers 412
  needs_credentials.
- TIKTOK_CLIENT_SECRET: same features as TIKTOK_CLIENT_KEY.
- META_APP_ID: blocks the live Instagram Reels and Facebook Page publish and
  their insights. The Instagram publisher (TASK-141) is implemented and
  tested with recorded Graph API answers only; with the keys, only accounts
  of people with a role on the Meta app can post until Meta grants
  Advanced Access (App Review + Business Verification). Without the keys
  `/api/accounts/instagram/connect` answers 412 needs_credentials. The
  Facebook Pages reel publisher (TASK-142) is the same: recorded answers
  only, 412 on `/api/accounts/facebook/connect`.
- META_APP_SECRET: same features as META_APP_ID.
- META_LOGIN_CONFIG_ID (optional): a Facebook Login for Business
  configuration id sent as `config_id`; not needed with the classic
  permission dialog.
- X_CLIENT_ID: blocks the live X login and post with video.
- X_CLIENT_SECRET: same features as X_CLIENT_ID.
- LINKEDIN_CLIENT_ID: blocks the live LinkedIn login and video post.
- LINKEDIN_CLIENT_SECRET: same features as LINKEDIN_CLIENT_ID.
- PEXELS_API_KEY: blocks live Pexels stock B-roll search and download.
- PIXABAY_API_KEY: blocks live Pixabay stock B-roll search and download.
- DROPBOX_APP_KEY: blocks the optional Dropbox import. TASK-67 is built and
  tested with recorded-shape Dropbox responses (respx); untested live: the
  consent + redirect on a real app (the redirect URL
  `http://127.0.0.1:8000/api/sources/dropbox/callback` must be registered),
  and the real answers of `get_shared_link_metadata` / `get_shared_link_file`.
  Without the key `/api/sources/dropbox/*` answers 412 needs_credentials.
- DROPBOX_APP_SECRET: not used (PKCE); listed for completeness.
- SMTP_HOST: blocks sending notification emails (in-app and desktop
  notifications still work).
- SMTP_PORT: same feature as SMTP_HOST.
- SMTP_USER: same feature as SMTP_HOST.
- SMTP_PASSWORD: same feature as SMTP_HOST.
- SMTP_FROM: same feature as SMTP_HOST.
- YOUTUBE_API_KEY: blocks adding a YouTube channel by `@handle` on the
  Watchlist (TASK-195; channel ids and /channel/ links work without it).
- TWITCH_CLIENT_ID: blocks Twitch go-live alerts (Helix polling and
  EventSub `stream.online`); tested with Twitch's documented payloads only.
- TWITCH_CLIENT_SECRET: same feature as TWITCH_CLIENT_ID.
- PUBLIC_CALLBACK_URL (setting, not a credential): without it YouTube and
  Twitch are polled every 60 s instead of pushing; the WebSub and EventSub
  handshakes are tested with recorded requests only. Kick is deferred until
  a Kick app exists (decisions.md TASK-195).
- HF_TOKEN: blocks speaker diarization (speaker caption colors and split
  layouts, pyannote needs a token) and the download of gated Hugging Face
  models for engines.

Optional engines that are not installed are not blockers: their UI shows "Not
installed" (SPEC-v2 2.3). The availability of each is in docs/stack.md.

## Resolved (owner/Hermes review, 2026-10-31)

- (TASK-13, STEERING 8) Default LLM model / gpt-6-luna refused: the 400
  `model_not_supported` came from the account, not the client. Hermes'
  probes: on omairtemurian only gpt-4.1 (/chat/completions) and
  gpt-5.4-nano (/responses) work; on <your-github-account> claude-sonnet-5.5 and
  claude-opus-5.5 work on /chat/completions and gpt-6-luna and gpt-6.1-sol
  on /responses. Owner decision: new setting `copilot_account` (default
  <your-github-account>) for the `gh auth token -u` fallback, default `llm_model`
  claude-sonnet-5.5 (gpt-6-luna the documented alternative). Both pass the
  live test here (docs/progress.md, decisions.md "TASK-13 copilot_account").
- (TASK-16) Fixture laughs were pink noise, which YAMNet hears as Waterfall
  (Laughter <= 0.001), so the SPEC 9.3 laugh check was a strict xfail.
  Owner chose B: `scripts/make_fixture.sh` now cuts the three laughs from a
  CC0 crowd laughing (`assets/sfx/crowd_laugh.flac`, Freesound 76693 by
  moxobna; source and license in assets/sfx/LICENSES.md). They are detected
  within 0.5 s (14.16-16.08, 33.36-34.8, 52.08-54.48) and the test passes;
  details in decisions.md ("TASK-16 fixture laughs").
- (TASK-12) Diarization: stays out of v1 scope. SPEC 2 makes it optional and
  off by default; every word gets speaker "S0". pyannote + torch are not added.
  Revisit in v2 (speaker-based caption colors, split layouts).
- (TASK-13) GitHub Models retired 2026-07-30: `OPENAI_BASE_URL` default changed
  to https://api.openai.com/v1 (SPEC 4 value) in config.py, config.yaml,
  .env.example. Default provider remains copilot.
- (TASK-24) ffmpeg without libass: option A. Installed Homebrew `ffmpeg-full`
  9.0.2 (keg-only; `-filters` lists subtitles, ass, drawtext). Makefile and
  ralph-local.sh put /opt/homebrew/opt/ffmpeg-full/bin first on PATH.
