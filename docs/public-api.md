# Public REST API (/api/v1)

ClipForge serves a REST API for scripts, n8n/Zapier-style tools and AI
agents at `http://127.0.0.1:8000/api/v1` (SPEC-v2 3.14). It has the same
endpoints and JSON models as the app's own API, plus an API key and a rate
limit. The OpenAPI document is `/api/openapi.json`, and `/api/docs` shows
it in Swagger UI. Click **Authorize** there to send a key.

## API keys

The owner makes, copies and revokes keys in **Settings → AI agents & API**
(`/settings/agents`), which also shows each key's last use, or in the app's
own API. These endpoints are human only: a request with an API key, or from
an agent, gets 403.

```sh
curl -s -X POST http://127.0.0.1:8000/api/api-keys \
  -H 'Content-Type: application/json' -d '{"name": "n8n"}'
# {"id": 1, "name": "n8n", "prefix": "cfk_AbCdEf", "key": "cfk_...", ...}
curl -s http://127.0.0.1:8000/api/api-keys            # list (no keys)
curl -s -X DELETE http://127.0.0.1:8000/api/api-keys/1 # revoke
```

The key is shown **once**, in the answer to POST. Only its SHA-256 digest
is stored, so a lost key cannot be recovered: revoke it and make a new one.
Send it with every request as `X-API-Key: <key>` or
`Authorization: Bearer <key>`.

| Answer | When                                                                                                              |
| ------ | ----------------------------------------------------------------------------------------------------------------- |
| 401    | `api_key_missing` (no key) or `api_key_invalid` (wrong or revoked key)                                            |
| 429    | `rate_limited`: over `api_rate_limit_per_min` requests (default 120) of one key in a minute; wait `Retry-After` s |
| 403    | `human_only`: queue, publish, quick-post, or approve/reject a draft (see below)                                   |

Every error body is `{"error": "<code>", "message": "<sentence>"}`.

## What agents may do

Agents (API keys, the MCP server) may do everything **up to drafts and
draft schedules**. Queueing a post for publishing (`POST
/posts/{id}/queue`, `bulk-schedule` with `"queue": true`), publishing now
(`POST /posts/{id}/publish`), the one-click quick post (`POST
/clips/{id}/quick-post`, which renders, writes the text and queues the
posts in one call) and changing a queued post answer 403 `human_only`. Only the owner does these, in the ClipForge app. There is no
auto-publish setting.

The autopilot's Approval Inbox (SPEC-v2 3.19) follows the same rule.
Agents may list it (`GET /drafts?status=pending&campaign_id=`, `GET
/drafts/{id}`), make a draft of a campaign clip (`POST /drafts`
`{"clip_id": 7}`: pending if it passes the campaign's rules, else
needs_fix) and add review notes (`POST /drafts/{id}/notes` `{"text":
"..."}`, saved with `"by": "agent"`). Approving a draft (`POST
/drafts/{id}/approve`, which queues its posts into the next free slots),
rejecting it (`POST /drafts/{id}/reject`) and approving all drafts of a
campaign (`POST /campaigns/{id}/drafts/approve`) answer 403 `human_only`.

## Pro Edit

Agents may run Pro Edit (SPEC-v3 3.8) under `/proedit`: a variant is a
draft clip, so approving or posting it stays human-only like every clip's.
`GET /proedit/clips/{id}/choices` lists what a run can use on a clip: the
presets (name, description, BPM range), music (`auto`, `none`, the bundled
loops and uploaded music), caption style recipes, and the campaign's
`max_intensity` and `allow_heavy_edits` (`true`, `false` or `unknown`;
null when the clip's project has no campaign).
`GET /proedit/clips/{id}/estimate?preset=&intensity=&style_recipe_id=&music=&use_critic=`
prices a run without calling the LLM; `POST /proedit/clips/{id}/runs`
(optional body: those options; `music` is `auto`, `none` or a catalog
music asset) makes a new variant of an original clip and queues its
`proedit` job (202 `{clip, run, job_id}`; poll `GET /jobs/{job_id}` for the
plan, proxy, critic and final steps, then `GET /proedit/runs/{id}` for the
notes and scores). On a variant: `GET .../runs`, `GET .../plan`, `GET
.../plans`, `PATCH .../plan` `{"items": [...]}` (422 `invalid_plan` with
`problems`), `POST .../reset`, and the jobs `POST .../regenerate`,
`.../critic`, `.../render` (409 `proedit_busy` while a run of it is queued
or running, 409 `no_plan` before it has a plan). The original clip is
never changed.

## The automation loop

```sh
H='X-API-Key: cfk_...'; API=http://127.0.0.1:8000/api/v1
# 1. a project from a URL (or POST /projects/upload, or /uploads in chunks)
curl -s -X POST $API/projects -H "$H" -H 'Content-Type: application/json' \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID", "source_rights": "own"}'
# 2. poll its job until status is done (or stream GET /jobs/{id}/events)
curl -s $API/projects/1/jobs -H "$H"; curl -s $API/jobs/1 -H "$H"
# 3. the clips with their scores, best first
curl -s "$API/projects/1/clips?sort=score" -H "$H"
# 4. edit the text or trim (start/end in source seconds)
curl -s -X PATCH $API/clips/7 -H "$H" -H 'Content-Type: application/json' \
  -d '{"title": "The best pizza", "start": 12.0, "end": 48.5}'
# 5. render, then poll the render job; download when the clip is rendered
curl -s -X POST $API/clips/7/render -H "$H"
curl -s -o clip.mp4 $API/clips/7/download -H "$H"
# 6. post copy for a platform, the accounts, a scheduled draft
curl -s -X POST $API/clips/7/post-copy -H "$H" -H 'Content-Type: application/json' \
  -d '{"platform": "tiktok"}'
curl -s $API/accounts -H "$H"
curl -s -X POST $API/clips/7/posts -H "$H" -H 'Content-Type: application/json' \
  -d '{"targets": [{"account_id": 2, "text": {"caption": "..."}}],
       "scheduled_at": "2030-01-15T09:00:00Z"}'
# 7. the posts and their status (draft until the owner queues them)
curl -s "$API/posts?clip_id=7" -H "$H"
```

Also there: clip transcripts (`GET /clips/{id}/transcript`), SRT, zip and
Premiere XML exports, brand and caption templates, processing presets, the
campaign rule check, covers (`/clips/{id}/thumbnail`) and the bulk
scheduler (`POST /posts/bulk-schedule`, drafts). The OpenAPI document lists
every endpoint and model. Collections (`/collections`: create, rename,
list, delete, add clips from any project, remove them, and
`/collections/{id}/download.zip` with the rendered clips and a
`manifest.json`) are there too, and so is the library search
(`GET /search?q=yoga`: the segments of all transcripts that say it, with the
project and the second, and `POST /search/clips` to make a clip of a hit).
Webhooks (events
sent to n8n, Zapier or your script) are in [automation.md](automation.md).
AI agents can use the same operations as MCP tools: see [mcp.md](mcp.md).

## Example agent prompt

> You can use the ClipForge API at http://127.0.0.1:8000/api/v1 (OpenAPI:
> /api/openapi.json). Send `X-API-Key: <key>` with every request. Make a
> project from https://www.youtube.com/watch?v=VIDEO_ID with source_rights
> "own" and poll its process job every 30 s until it is done. Then take the
> three clips with the highest overall score. Shorten each title to under
> 60 characters and render it. When a clip is rendered, ask for TikTok post
> copy. Make a draft post for TikTok account 2 at the next free 18:00 slot
> (Europe/Zurich): use POST /posts/bulk-schedule without "queue". Report the
> draft ids. Do not try to queue or publish: the owner approves drafts in
> the app. If you get 429, wait for Retry-After.

## Security note

The API is bound to 127.0.0.1. The app's own endpoints under `/api` (not
`/v1`) need no key: they are the owner's local UI session. LAN mode with
users and sessions comes with TASK-167.
