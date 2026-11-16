"""Public REST API /api/v1 (SPEC-v2 3.14) for scripts and AI agents.

It serves the core endpoints of the app's own API under /api/v1, the same
handlers and models, behind an API key and a rate limit (api.v1.auth):
create a project from a URL or an upload (also chunked) and poll its job,
list and edit clips (scores, text, trim), render, export (video, SRT, zip,
Premiere XML), clip transcripts, brand and caption templates, processing
presets, the campaign rule check, the connected accounts (read only), post
copy, covers, posts, collections, the library search, the autopilot's
Approval Inbox and Pro Edit (start a variant, its plans, runs and jobs).
The OpenAPI document is /api/openapi.json, shown at /api/docs.

Agents stop at drafts (owner's rule of 2026-10-31, SPEC-v2 3.19): they may
draft posts and draft schedules, edit and cancel drafts, make autopilot
drafts, list the inbox and add review notes, but queueing, publishing and
approving or rejecting a draft answer 403 human_only (api.deps.require_human
treats every /api/v1 call as an agent's). There is no auto-publish setting.
"""

from typing import Any

from fastapi import APIRouter, Depends

from clipforge.api import (
    accounts,
    brand,
    campaign_rules,
    caption_templates,
    clip_files,
    clips,
    collections,
    drafts,
    jobs,
    post_copy,
    posts,
    presets,
    proedit,
    projects,
    search,
    sources,
    thumbnails,
    uploads,
)
from clipforge.api.v1.auth import require_api_key
from clipforge.models import ErrorBody

V1_PREFIX = "/v1"
# Documented error answers of every endpoint; "4XX" covers the others (404,
# 409, 422, ...), which all have the same body (api.errors).
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorBody, "description": "No API key, or not a valid one"},
    429: {"model": ErrorBody, "description": "Rate limit: see Retry-After"},
    "4XX": {"model": ErrorBody, "description": "Any other error"},
}

# (router, tag of its endpoints in the OpenAPI document)
PUBLIC_ROUTERS = (
    (projects.router, "projects"),
    (uploads.router, "uploads"),
    (sources.router, "sources"),
    (presets.router, "presets"),
    (jobs.router, "jobs"),
    (clips.router, "clips"),
    (clip_files.router, "clips"),
    (collections.router, "collections"),
    (search.router, "search"),
    (campaign_rules.router, "campaigns"),
    (brand.router, "templates"),
    (caption_templates.router, "templates"),
    (post_copy.router, "posts"),
    (thumbnails.router, "posts"),
    (posts.router, "posts"),
    (drafts.router, "drafts"),
    (proedit.router, "proedit"),
)


def build_router() -> APIRouter:
    """Return the /v1 router (to include under /api): every public endpoint,
    each requiring an API key."""
    router = APIRouter(
        prefix=V1_PREFIX,
        dependencies=[Depends(require_api_key)],
        responses=ERROR_RESPONSES,
    )
    for public, tag in PUBLIC_ROUTERS:
        router.include_router(public, tags=[tag])
    router.add_api_route(
        "/accounts",
        accounts.list_accounts,
        methods=["GET"],
        tags=["accounts"],
        summary="List the connected social accounts",
    )
    return router
