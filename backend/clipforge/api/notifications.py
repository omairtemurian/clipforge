"""Notification endpoints (SPEC-v2 3.17): the owner's in-app notifications
(clipforge/notifications.py) and the channels besides the app.

    GET    /notifications               -> NotificationList (newest first;
                                           ?unread=true, ?limit=)
    GET    /notifications/channels      -> NotificationChannels
    POST   /notifications/test          -> Notification (a test message, sent
                                           to the channels that are on)
    POST   /notifications/read-all      -> NotificationList
    POST   /notifications/{id}/read     -> Notification
    DELETE /notifications/{id}          -> 204
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Engine

from clipforge import config, notifications
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.models import Notification, NotificationChannels, NotificationList
from clipforge.notification_delivery import channels

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/notifications")
def list_notifications(
    engine: EngineDep,
    unread: bool = False,
    limit: Annotated[
        int, Query(ge=1, le=notifications.LIST_LIMIT_MAX)
    ] = notifications.LIST_LIMIT,
) -> NotificationList:
    """Return the newest notifications, and how many unread ones there are."""
    return notifications.list_notifications(engine, unread_only=unread, limit=limit)


@router.get("/notifications/channels")
def get_notification_channels() -> NotificationChannels:
    """Return whether notifications are also emailed (and to whom) and shown
    on the desktop; email is on only if SMTP_HOST is set."""
    return channels(config.settings)


@router.post("/notifications/test", status_code=201)
def send_test_notification(engine: EngineDep) -> Notification:
    """Make a test notification, to try the email and desktop channels."""
    sent = notifications.notify(
        engine,
        "test",
        "Test notification",
        "ClipForge can reach you here.",
        "/settings",
    )
    assert sent is not None
    return sent


@router.post("/notifications/read-all")
def read_all_notifications(engine: EngineDep) -> NotificationList:
    """Mark every notification read."""
    notifications.mark_all_read(engine)
    return notifications.list_notifications(engine)


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, engine: EngineDep) -> Notification:
    """Mark a notification read; 404 if there is none."""
    try:
        return notifications.mark_read(engine, notification_id)
    except notifications.NotificationNotFound as exc:
        raise not_found("Notification", notification_id) from exc


@router.delete("/notifications/{notification_id}", status_code=204)
def delete_notification(notification_id: int, engine: EngineDep) -> Response:
    """Delete a notification; 404 if there is none."""
    try:
        notifications.delete(engine, notification_id)
    except notifications.NotificationNotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    return Response(status_code=204)
