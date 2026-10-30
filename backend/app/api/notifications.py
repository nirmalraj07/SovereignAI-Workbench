"""
Notification system: a lightweight in-app notification feed. Notifications
are pushed by other subsystems (e.g. the Celery task worker on task
failure, the security dashboard on an anomalous event) via push_notification(),
and read by the frontend's bell icon via the API below.

Phase 1 storage is an in-memory per-process deque (bounded, newest-first) —
sufficient for a single-backend-replica on-prem deployment; swap for a
`notifications` table + migration if the platform scales to multiple
backend replicas behind a load balancer.
"""
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime

from fastapi import APIRouter, Depends
from ..security.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

_MAX_NOTIFICATIONS = 200
_STORE: deque = deque(maxlen=_MAX_NOTIFICATIONS)


@dataclass
class Notification:
    id: str
    title: str
    message: str
    level: str  # info | warning | error | success
    created_at: str
    read: bool = False


def push_notification(title: str, message: str, level: str = "info") -> Notification:
    note = Notification(
        id=str(uuid.uuid4()), title=title, message=message, level=level,
        created_at=datetime.utcnow().isoformat(),
    )
    _STORE.appendleft(note)
    return note


@router.get("")
async def list_notifications(user: dict = Depends(get_current_user)):
    return [asdict(n) for n in _STORE]


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, user: dict = Depends(get_current_user)):
    for n in _STORE:
        if n.id == notification_id:
            n.read = True
            return asdict(n)
    return {"error": "not found"}
