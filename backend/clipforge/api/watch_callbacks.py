"""The push callbacks of the watch (T28c): what the YouTube WebSub hub and
Twitch EventSub call through the public callback URL. They are not part of
the app's own API: each request proves itself (the WebSub intent check
echoes only a topic we asked for; notifications must carry the HMAC
signature of their secret, else 403). Request headers and bodies are never
logged.
"""

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from clipforge.auto_import import find_channel
from clipforge.watch import websub
from clipforge.watch.twitch_watcher import TwitchWatcher
from clipforge.watch.youtube_watcher import AutoImporter

router = APIRouter(prefix="/watch")

# What a push may weigh: a WebSub Atom entry or an EventSub message is a few KB.
MAX_PUSH_BYTES = 1_000_000


@router.get("/websub/{channel_id}", include_in_schema=False)
def websub_verify(channel_id: str, request: Request) -> Response:
    """Answer the hub's intent check: echo hub.challenge, or 404."""
    importer: AutoImporter = request.app.state.importer
    params = dict(request.query_params)
    channel = find_channel(importer.engine, channel_id)
    challenge = websub.verify_intent(
        importer.engine, channel, channel_id, params, importer.wall_clock()
    )
    if challenge is None:
        return Response(status_code=404)
    return Response(
        content=challenge,
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/websub/{channel_id}", include_in_schema=False)
async def websub_notify(channel_id: str, request: Request) -> Response:
    """Import the new videos of a pushed notification (see receive_push)."""
    importer: AutoImporter = request.app.state.importer
    body = await request.body()
    if len(body) > MAX_PUSH_BYTES:
        return Response(status_code=413)
    signature = request.headers.get("x-hub-signature")
    answer = await run_in_threadpool(importer.receive_push, channel_id, body, signature)
    return Response(status_code=answer.status)


@router.post("/twitch/eventsub", include_in_schema=False)
async def twitch_eventsub(request: Request) -> Response:
    """Answer a Twitch EventSub webhook message."""
    watcher: TwitchWatcher = request.app.state.twitch
    body = await request.body()
    if len(body) > MAX_PUSH_BYTES:
        return Response(status_code=413)
    answer = await run_in_threadpool(
        watcher.handle_eventsub, dict(request.headers), body
    )
    if answer.status == 200:
        return Response(content=answer.body, media_type="text/plain")
    return Response(status_code=answer.status)
