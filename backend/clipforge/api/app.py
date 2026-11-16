"""FastAPI application (SPEC 7): every route is under /api.

create_app builds the app; `app` is what uvicorn serves
(`uvicorn clipforge.api.app:app --host 127.0.0.1`, see `make dev`: the
API is local and is never bound to another address). Its lifespan checks
ffmpeg, opens the database in the configured data_dir (migrations applied),
runs the job worker pool that executes the queued jobs, the posting worker
that publishes the due queued posts, the creator watch (Auto Import of the
watched YouTube channels' new videos, Twitch go-live alerts) and, if
inbox_dir is set, the inbox folder watch that queues the videos put there.

The public REST API for scripts and AI agents is under /api/v1 (api.v1:
API key, rate limit); its OpenAPI document is /api/openapi.json, shown at
/api/docs.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI

from clipforge import config
from clipforge.api import (
    accounts,
    api_keys,
    auto_import,
    autopilot,
    brand,
    broll,
    campaign_accounts,
    campaign_rules,
    campaigns,
    caption_templates,
    caption_translation,
    censor,
    chapters,
    clip_cleanup,
    clip_copies,
    clip_crop,
    clip_cuts,
    clip_files,
    clip_graphics,
    clip_hook,
    clip_keyframes,
    clip_sections,
    clip_versions,
    clips,
    collections,
    drafts,
    dropbox,
    engines,
    gdrive,
    jobs,
    media,
    music,
    notifications,
    post_copy,
    posts,
    presets,
    proedit,
    proedit_audio,
    proedit_audio_files,
    proedit_editor,
    proedit_style,
    proedit_style_match,
    project_camera_motion,
    project_zoom_out,
    projects,
    quick_post,
    search,
    settings,
    sfx,
    sources,
    storage,
    submissions,
    thumbnails,
    timeline,
    uploads,
    usage,
    vocabulary,
    voiceover,
    watch,
    watch_callbacks,
    webhooks,
)
from clipforge.api.errors import install_error_handlers
from clipforge.api.v1 import build_router
from clipforge.api.v1.auth import KeyRateLimiter
from clipforge.caption_previews import ensure_previews
from clipforge.db import init_db
from clipforge.ffmpeg import check_ffmpeg
from clipforge.inbox_watch import InboxWatcher
from clipforge.llm import LLMClient
from clipforge.scheduler.post_worker import PostWorker
from clipforge.watch.twitch_watcher import TwitchWatcher
from clipforge.watch.youtube_watcher import AutoImporter
from clipforge.webhook_delivery import WebhookWorker
from clipforge.worker_pool import WorkerPool

API_PREFIX = "/api"
# Seconds that shutdown waits for each job that a worker is running.
WORKER_STOP_TIMEOUT = 5.0


def create_app(
    *,
    run_worker: bool = True,
    llm: LLMClient | None = None,
    transcript: Path | None = None,
    caption_previews: bool = True,
    llm_transport: httpx.BaseTransport | None = None,
    run_watch: bool | None = None,
    run_posting: bool | None = None,
) -> FastAPI:
    """Return a ClipForge app.

    With run_worker off no job runs (jobs stay queued). The creator watch
    (YouTube feeds, Twitch) polls when run_watch is on, which defaults to
    run_worker; its push callbacks answer either way. The posting worker
    publishes due posts, and the webhook worker sends the queued webhook
    deliveries, when run_posting is on, which also defaults to
    run_worker. llm and transcript
    are passed to the worker's process jobs (test mode), and llm also
    rewrites clip texts (else the configured client does). Startup draws the
    caption template previews unless caption_previews is off (they are then
    drawn when first asked for). llm_transport carries the HTTP requests of
    POST /settings/test-llm and /settings/models (and the verified save of
    PUT /settings) instead of the network (tests).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Refuse to start if ffmpeg lacks libass (check_ffmpeg), draw the
        caption previews, then open the database and start the worker pool; stop
        them on shutdown."""
        check_ffmpeg()
        if caption_previews:
            ensure_previews()
        engine = init_db()
        worker = (
            WorkerPool(engine, llm=llm, transcript=transcript) if run_worker else None
        )
        app.state.engine = engine
        app.state.worker = worker
        app.state.llm = llm
        app.state.llm_transport = llm_transport
        if worker is not None:
            worker.start()
        inbox = InboxWatcher.from_settings(
            engine, worker.wake if worker is not None else None
        )
        if inbox is not None:
            inbox.start()
        importer = AutoImporter.from_settings(
            engine, worker.wake if worker is not None else None
        )
        twitch = TwitchWatcher.from_settings(engine)
        app.state.importer = importer
        app.state.twitch = twitch
        if run_worker if run_watch is None else run_watch:
            importer.start()
            twitch.start()
        poster = PostWorker.from_settings(engine)
        if run_worker if run_posting is None else run_posting:
            poster.start()
        sender = WebhookWorker(engine)
        if run_worker if run_posting is None else run_posting:
            sender.start()
        try:
            yield
        finally:
            sender.stop(WORKER_STOP_TIMEOUT)
            poster.stop(WORKER_STOP_TIMEOUT)
            twitch.stop(WORKER_STOP_TIMEOUT)
            importer.stop(WORKER_STOP_TIMEOUT)
            if inbox is not None:
                inbox.stop(WORKER_STOP_TIMEOUT)
            if worker is not None:
                worker.stop(WORKER_STOP_TIMEOUT)
            engine.dispose()

    app = FastAPI(
        title="ClipForge",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.state.api_limiter = KeyRateLimiter(config.settings.api_rate_limit_per_min)
    install_error_handlers(app)
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(projects.router)
    api.include_router(project_zoom_out.router)
    api.include_router(project_camera_motion.router)
    api.include_router(chapters.router)
    api.include_router(jobs.router)
    api.include_router(clips.router)
    api.include_router(clip_files.router)
    api.include_router(collections.router)
    api.include_router(search.router)
    api.include_router(storage.router)
    api.include_router(clip_crop.router)
    api.include_router(clip_keyframes.router)
    api.include_router(clip_cuts.router)
    api.include_router(clip_cleanup.router)
    api.include_router(clip_sections.router)
    api.include_router(clip_hook.router)
    api.include_router(clip_graphics.router)
    api.include_router(clip_copies.router)
    api.include_router(timeline.router)
    api.include_router(clip_versions.router)
    api.include_router(media.router)
    api.include_router(music.router)
    api.include_router(sfx.router)
    api.include_router(voiceover.router)
    api.include_router(broll.router)
    api.include_router(brand.router)
    api.include_router(caption_templates.router)
    api.include_router(settings.router)
    api.include_router(engines.router)
    api.include_router(notifications.router)
    api.include_router(usage.router)
    api.include_router(sources.router)
    api.include_router(presets.router)
    api.include_router(uploads.router)
    api.include_router(gdrive.router)
    api.include_router(dropbox.router)
    api.include_router(auto_import.router)
    api.include_router(campaigns.router)
    api.include_router(campaign_rules.router)
    api.include_router(campaign_accounts.router)
    api.include_router(submissions.router)
    api.include_router(autopilot.router)
    api.include_router(drafts.router)
    api.include_router(watch.router)
    api.include_router(watch_callbacks.router)
    api.include_router(accounts.router)
    api.include_router(posts.router)
    api.include_router(post_copy.router)
    api.include_router(quick_post.router)
    api.include_router(caption_translation.router)
    api.include_router(vocabulary.router)
    api.include_router(censor.router)
    api.include_router(thumbnails.router)
    api.include_router(api_keys.router)
    api.include_router(webhooks.router)
    api.include_router(proedit.router)
    api.include_router(proedit_audio.router)
    api.include_router(proedit_audio_files.router)
    api.include_router(proedit_editor.router)
    api.include_router(proedit_style.router)
    api.include_router(proedit_style_match.router)
    api.include_router(build_router())
    app.include_router(api)
    return app


app = create_app()
