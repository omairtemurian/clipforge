# MCP server

`clipforge-mcp` lets an AI agent (Claude Desktop, Claude Code, Copilot, any
MCP client) run ClipForge through MCP tools (SPEC-v2 3.14). It is a small
separate program that talks to the running ClipForge app over the
[public API](public-api.md) with an API key, and speaks MCP over stdio.
Every rule of the API applies to it.

## Set up

The easy way: open **Settings → AI agents & API** (`/settings/agents`) in
the app. Make a key there (it is shown once, with a copy button) and copy
the ready-made setup for Hermes (`hermes mcp add` or `~/.hermes/config.yaml`),
Claude Desktop, Claude Code (`claude mcp add`), GitHub Copilot CLI
(`copilot mcp add`) or VS Code (`servers` JSON), or the generic
`mcpServers` JSON, with this checkout's path and your key filled in
(`GET /api/agent-setup`, human only, gives the path and command). The page
also shows when each key was last used, so you can see which agents
connected recently.

By hand:

1. Start ClipForge (`make dev`, or the app on `127.0.0.1:8000`).
2. Make a key (it is shown once):

   ```sh
   curl -s -X POST http://127.0.0.1:8000/api/api-keys \
     -H 'Content-Type: application/json' -d '{"name": "my agent"}'
   ```

3. Add the server to your MCP client. For a client that reads an
   `mcpServers` JSON (Claude Desktop, Claude Code `.mcp.json`):

   ```json
   {
     "mcpServers": {
       "clipforge": {
         "command": "uv",
         "args": [
           "run",
           "--project",
           "/path/to/clipforge",
           "clipforge-mcp"
         ],
         "env": { "CLIPFORGE_API_KEY": "cfk_..." }
       }
     }
   }
   ```

Options (`clipforge-mcp -h`): `--url` (or `CLIPFORGE_URL`; default
`http://127.0.0.1:8000`) and `--download-dir` (default
`~/clipforge-downloads`). The key is read from `CLIPFORGE_API_KEY` only, so
it never shows in a process list. The tools are read from the app's OpenAPI
document at startup: restart the server after updating ClipForge.

## Tools

One tool per operation of `/api/v1` (88 of them), named after it
(`create_project`, `list_clips`, `patch_clip`, `queue_render`, `post_copy`,
`create_posts`, `bulk_schedule`, `list_posts`, ...). The input of a tool is
a JSON Schema: the path and query parameters, then the fields of the JSON
body (for example `create_posts` takes `clip_id`, `targets`, `scheduled_at`).
A tool returns the API's JSON. An error comes back as a tool error with the
API's `status`, `error` and `message` (and `retry_after_seconds` for a 429).

| Step                      | Tools                                                                  |
| ------------------------- | ---------------------------------------------------------------------- |
| Project from URL or file  | `create_project` (`url`), `upload_project` (`file`: a path on this machine) |
| Poll the job              | `list_project_jobs`, `get_job`                                         |
| List and score clips      | `list_clips` (`sort=score`), `get_clip`, `get_clip_transcript`         |
| Edit text or trim         | `patch_clip` (`title`, `start`, `end`, ...), `regenerate_clip_text`    |
| Render                    | `queue_render`, then `get_job`; `download_clip`, `download_zip`        |
| Post copy                 | `post_copy` (`platform`)                                               |
| Accounts and drafts       | `list_accounts`, `create_posts`, `bulk_schedule`                       |
| Posts and their status    | `list_posts`, `get_post`, `patch_post`, `cancel_post`                  |
| Approval Inbox            | `list_drafts`, `get_draft`, `create_draft`, `add_draft_note`           |
| Pro Edit                  | `get_proedit_choices`, `estimate_proedit`, `start_proedit`, `get_proedit_run`, `get_proedit_plan`, `patch_proedit_plan`, `render_proedit` |

Also templates, presets, the campaign check, covers and exports. A file
answer (`download_clip`, the zip, an image) is saved in the download
directory and the tool returns `{"saved_to": path, "content_type", "bytes"}`.

### What agents cannot do

Agents stop at drafts (owner's rule of 2026-10-31). There is **no tool** to
queue a post, publish now, quick-post, or approve or reject a draft
(`approve_draft`, `reject_draft`, `approve_campaign_drafts` do not exist),
and `bulk_schedule` has no `queue` input. If a call got through anyway the app would answer 403 `human_only`.
The owner approves drafts in the ClipForge app. Not offered over MCP:
chunked uploads (use `upload_project` with a file path), the job event
stream (poll `get_job`) and the raw cover upload.

## Example agent prompt

> Use the ClipForge tools. Make a project from
> https://www.youtube.com/watch?v=VIDEO_ID with `create_project`
> (`source_rights` "own") and poll its process job with `get_job` every 30
> seconds until it is done. List the clips with `list_clips` (`sort`
> "score") and take the three with the best overall score. Shorten each
> title to under 60 characters with `patch_clip`, then `queue_render` and
> poll the render job. When a clip is rendered, call `post_copy` for
> "tiktok". Use `bulk_schedule` (no queue) to make a draft for TikTok
> account 2 at the next free 18:00 slot (Europe/Zurich), or `create_posts`
> with a `scheduled_at`. Report the draft post ids and tell me to approve
> them in ClipForge. You cannot publish. If a call fails with
> `rate_limited`, wait `retry_after_seconds`.
