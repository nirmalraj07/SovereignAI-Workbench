"""
Task ownership tracking: records which user submitted each Celery task so
the status-polling REST endpoint and the WebSocket endpoint can enforce
that only the submitting user (or an admin) can read a task's results.

Uses Redis directly (already required infrastructure — it's the Celery
result backend) rather than a new DB table, with a TTL matching Celery's
`result_expires` (see workers/celery_app.py) so ownership records and
task results expire together instead of the ownership record outliving
or expiring before the result it's meant to protect.
"""
from __future__ import annotations
import redis
from ..core.config import settings

_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
_OWNER_KEY_PREFIX = "sovereignai:task_owner:"
_TTL_SECONDS = 3600  # matches celery_app.py's result_expires


def record_owner(task_id: str, username: str) -> None:
    _client.set(f"{_OWNER_KEY_PREFIX}{task_id}", username, ex=_TTL_SECONDS)


def get_owner(task_id: str) -> str | None:
    return _client.get(f"{_OWNER_KEY_PREFIX}{task_id}")


def can_access(task_id: str, username: str, role: str) -> bool:
    """Admins can access any task (operational necessity — e.g. debugging
    a stuck task reported by another user). Everyone else must be the
    original submitter. A task_id with no recorded owner (mapping expired,
    or predates this fix) is NOT accessible to non-admins — fails closed
    rather than treating "unknown owner" as "anyone may view it"."""
    if role == "admin":
        return True
    owner = get_owner(task_id)
    return owner is not None and owner == username
