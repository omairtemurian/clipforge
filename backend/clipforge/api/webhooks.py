"""Webhook endpoints (SPEC-v2 3.14): the owner registers the endpoints that
ClipForge sends its events to, and reads their delivery log.

    GET    /webhooks                   -> [Webhook]
    POST   /webhooks                   WebhookCreate -> WebhookCreated (201;
                                       the signing secret, once)
    PATCH  /webhooks/{id}              WebhookUpdate -> Webhook
    DELETE /webhooks/{id}              -> 204 (and its delivery log)
    GET    /webhooks/{id}/deliveries   -> [WebhookDelivery] (newest first)

Human only: an agent with an API key could otherwise send the owner's
events (clip titles, post URLs) to a server of its own.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Engine

from clipforge import webhooks
from clipforge.api.deps import get_engine, require_human
from clipforge.api.errors import not_found
from clipforge.models import (
    Webhook,
    WebhookCreate,
    WebhookCreated,
    WebhookDelivery,
    WebhookUpdate,
)

router = APIRouter(dependencies=[Depends(require_human)])

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/webhooks")
def list_webhooks(engine: EngineDep) -> list[Webhook]:
    """Return every webhook, oldest first (never the secret)."""
    return webhooks.list_webhooks(engine)


@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookCreate, engine: EngineDep) -> WebhookCreated:
    """Register a webhook; the answer is the only time its secret is shown."""
    return webhooks.create_webhook(engine, body.url, body.events)


@router.patch("/webhooks/{webhook_id}")
def update_webhook(webhook_id: int, body: WebhookUpdate, engine: EngineDep) -> Webhook:
    """Change a webhook's url, events or enabled flag."""
    try:
        return webhooks.update_webhook(engine, webhook_id, body)
    except webhooks.WebhookNotFound as exc:
        raise not_found("Webhook", webhook_id) from exc


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: int, engine: EngineDep) -> Response:
    """Delete a webhook and its delivery log."""
    try:
        webhooks.delete_webhook(engine, webhook_id)
    except webhooks.WebhookNotFound as exc:
        raise not_found("Webhook", webhook_id) from exc
    return Response(status_code=204)


@router.get("/webhooks/{webhook_id}/deliveries")
def list_deliveries(
    webhook_id: int,
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[WebhookDelivery]:
    """Return the latest deliveries of a webhook with their attempts and
    answers, newest first."""
    try:
        return webhooks.list_deliveries(engine, webhook_id, limit)
    except webhooks.WebhookNotFound as exc:
        raise not_found("Webhook", webhook_id) from exc
