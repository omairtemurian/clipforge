# Automation: webhooks, n8n and Zapier (SPEC-v2 3.14)

ClipForge can tell other tools when something happens. You register a
webhook (an `http://` or `https://` address) and ClipForge POSTs each event
you chose to it, signed so that the receiver knows it came from your
ClipForge. Use it with n8n, Zapier, Make or your own script. To act on an
event (render a clip, make a draft), call the [public API](public-api.md).

Webhooks are managed by the owner only: a call with an API key gets 403
`human_only`, so an agent cannot send your events to a server of its own.

## Events

| Event               | When                                                     | `data`                                                              |
| ------------------- | -------------------------------------------------------- | ------------------------------------------------------------------- |
| `project.completed` | the process job of a project is done                     | `project` (id, title, source_url, duration, created_at, path), `clips` (id, title) |
| `clip.rendered`     | a clip's video was made (also when you render it again)  | `clip` (id, project_id, title, overall_score, download_path, srt_path) |
| `post.published`    | a post was uploaded to its platform                      | `post` (id, clip_id, platform, status, url, external_post_id, error, attempts)  |
| `post.failed`       | a post failed for good (a retry is not an event)         | the same `post`, with `error` saying why                            |

`path`, `download_path` and `srt_path` are paths of the ClipForge API
(`http://127.0.0.1:8000` + path; with an API key under `/api/v1`). Files on
your disk are never sent.

## Register a webhook

In the app: **Settings → AI agents & API → Webhooks** (URL, events, the
secret shown once, delete). Or with the API:

```sh
API=http://127.0.0.1:8000/api
curl -s -X POST $API/webhooks -H 'Content-Type: application/json' \
  -d '{"url": "http://localhost:5678/webhook/clipforge",
       "events": ["post.published", "post.failed"]}'
# {"id": 1, "url": "...", "events": [...], "enabled": true,
#  "created_at": "...", "secret": "whsec_..."}
curl -s $API/webhooks                                     # list (no secrets)
curl -s -X PATCH $API/webhooks/1 -H 'Content-Type: application/json' \
  -d '{"enabled": false}'                                 # pause / edit
curl -s "$API/webhooks/1/deliveries?limit=20"             # the delivery log
curl -s -X DELETE $API/webhooks/1                         # and its log
```

The `secret` is shown **once**, in the answer to POST: copy it into your
receiver. (It is kept encrypted on disk with a key from the data directory,
not hashed, because signing needs the secret itself.) To change the secret,
delete the webhook and make a new one.

## What is sent

A POST with `Content-Type: application/json` and the body (compact JSON,
keys sorted):

```json
{
  "id": 41,
  "event": "post.published",
  "created_at": "2030-01-15T09:00:03Z",
  "data": { "post": { "id": 9, "clip_id": 7, "platform": "tiktok", "status": "published",
                      "url": "https://...", "external_post_id": "...", "error": null, "attempts": 1 } }
}
```

| Header                   | Value                                                          |
| ------------------------ | -------------------------------------------------------------- |
| `X-ClipForge-Event`      | the event name                                                 |
| `X-ClipForge-Delivery`   | the delivery id (`id` of the body); the same on every retry    |
| `X-ClipForge-Timestamp`  | Unix seconds of this attempt                                   |
| `X-ClipForge-Signature`  | `sha256=` + hex HMAC-SHA256 of `"<timestamp>.<raw body>"`, key = the secret |

### Check the signature

Compute the HMAC over the **raw bytes** of the body (not over re-encoded
JSON), compare in constant time, and refuse a timestamp more than 5 minutes
old (replay).

```python
import hashlib, hmac, time

def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return hmac.compare_digest("sha256=" + digest.hexdigest(), signature)
```

```js
const crypto = require("crypto");

function verify(secret, timestamp, rawBody, signature) {
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return false;
  const mac = crypto.createHmac("sha256", secret).update(`${timestamp}.`).update(rawBody);
  const expected = Buffer.from("sha256=" + mac.digest("hex"));
  const given = Buffer.from(signature);
  return expected.length === given.length && crypto.timingSafeEqual(expected, given);
}
```

## Delivery, retries and the log

ClipForge never makes a job or a post wait for your endpoint: an event is
written to the delivery log first, and a background worker sends it (every
2 seconds when something is due).

- Any `2xx` answer delivers the event. Anything else (another status, a
  redirect, a timeout of 10 s, no connection) is a failed attempt; redirects
  are not followed.
- A failed attempt is retried after 30 s, 1 min, 2 min, 4 min, then 8 min:
  exponential backoff, at most 6 attempts, then the delivery is `failed`.
- Delivery is at least once. If ClipForge stops while a request is in
  flight, the event is sent again after the restart, so deduplicate on
  `X-ClipForge-Delivery`. Order is not guaranteed across retries.
- `GET /api/webhooks/{id}/deliveries` shows, newest first, each delivery's
  `status` (`pending`, `delivered`, `failed`), `attempts`, `attempted_at`,
  `next_attempt_at`, the last `response_status` and `error`.
- Pausing a webhook (`enabled: false`) stops new events; deliveries that
  are still pending then fail with "The webhook is deleted or disabled."

## n8n

1. In n8n, import [`examples/n8n-clipforge.json`](../examples/n8n-clipforge.json)
   (**Workflows > Import from file**). It has a Webhook trigger (POST,
   path `clipforge`), an IF node on `post.published` and a node that writes
   a message with the clip and the post URL. Add your own nodes after it:
   Slack, Telegram, Google Sheets, an HTTP Request that calls the ClipForge
   API with your key (`X-API-Key` header) to fetch `download_path`, ...
2. Publish the workflow, copy the **Production URL** of the Webhook node
   and register it (`POST /api/webhooks`). If n8n runs in Docker and
   ClipForge on the host, use `http://host.docker.internal:5678/...`.
3. Optional signature check: in the Webhook node's **Options** turn on
   **Raw Body**, then add a Code node that reads the buffer with
   `await this.helpers.getBinaryDataBuffer(0, "data")` and runs the
   JavaScript `verify` above. `require("crypto")` needs the n8n
   environment variable `NODE_FUNCTION_ALLOW_BUILTIN=crypto`. (The example
   workflow does not check the signature: its URL is the secret. The
   workflow JSON and the Code-node steps follow n8n's current docs; they
   were not run against an n8n server in ClipForge's tests.)

## Zapier

Zapier's **Webhooks by Zapier** trigger **Catch Hook** gives a URL: register
it as a webhook, then continue with any Zap actions. Catch Hook does not let
you verify the HMAC; use it only with a secret URL, and call the ClipForge
API from a later step (**Webhooks by Zapier > Custom Request**) if you need
more data. ClipForge only sends to addresses it can reach, so a tool on the
internet needs a public URL for your machine (a tunnel), while ClipForge
itself stays on `127.0.0.1`.

## Checks

`backend/tests/test_webhooks.py`, `test_webhook_delivery.py` (signature,
backoff on a fake clock, delivery log), `test_webhook_pipeline.py` (a real
process job and its signed deliveries) and
`backend/tests/api/v1/test_webhooks_api.py` cover this page.
