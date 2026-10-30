"""
Append-only audit logging, persisted to the audit_log table. This is the
source for the Security Dashboard's audit stream and for compliance review.
Falls back to an in-memory ring buffer if the DB is unreachable so a
Postgres outage never silently drops a request path (it still logs to
stderr for ops to catch).
"""
import logging
import uuid
from datetime import datetime

from ..db.session import db_session
from ..db.models import AuditLog

logger = logging.getLogger("audit")
_FALLBACK_BUFFER: list[dict] = []


def record_event(user: str, action: str, resource: str, ip: str = "internal") -> None:
    entry = {"user": user, "action": action, "resource": resource, "ip": ip,
              "created_at": datetime.utcnow().isoformat()}
    try:
        with db_session() as db:
            db.add(AuditLog(id=str(uuid.uuid4()), user_id=None, action=action,
                             resource=f"{user}:{resource}"[:512], ip=ip))
    except Exception as exc:  # DB unavailable — never let audit failure break the request
        logger.error("audit_log write failed, buffering in memory: %s", exc)
        _FALLBACK_BUFFER.append(entry)


def recent_events(limit: int = 100) -> list[dict]:
    try:
        with db_session() as db:
            rows = (
                db.query(AuditLog)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {"action": r.action, "resource": r.resource, "ip": r.ip,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows
            ]
    except Exception as exc:
        logger.error("audit_log read failed, returning in-memory fallback: %s", exc)
        return _FALLBACK_BUFFER[-limit:]
