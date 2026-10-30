"""
Advanced Audit Analytics: aggregation queries over audit_log for the
Security Dashboard's analytics view and for Compliance Reporting. Pure
read-side aggregation — no new tables, just indexed queries against the
existing audit_log (see alembic/versions/0001_initial.py indexes).
"""
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import AuditLog


def events_by_action(db: Session, since: datetime) -> list[dict]:
    rows = (
        db.query(AuditLog.action, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .all()
    )
    return [{"action": action, "count": count} for action, count in rows]


def events_by_day(db: Session, since: datetime) -> list[dict]:
    rows = (
        db.query(func.date(AuditLog.created_at), func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(func.date(AuditLog.created_at))
        .order_by(func.date(AuditLog.created_at))
        .all()
    )
    return [{"date": str(day), "count": count} for day, count in rows]


def top_resources(db: Session, since: datetime, limit: int = 10) -> list[dict]:
    rows = (
        db.query(AuditLog.resource, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(AuditLog.resource)
        .order_by(func.count(AuditLog.id).desc())
        .limit(limit)
        .all()
    )
    return [{"resource": resource, "count": count} for resource, count in rows]


def anomaly_scan(db: Session, since: datetime, spike_threshold: float = 3.0) -> list[dict]:
    """Flags actions whose daily count on any given day exceeds
    spike_threshold times the mean daily count for that action over the
    window — a simple, explainable anomaly signal (no ML dependency) for
    an on-prem deployment where you can't call out to an anomaly-detection
    SaaS."""
    action_day_counts = (
        db.query(AuditLog.action, func.date(AuditLog.created_at), func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(AuditLog.action, func.date(AuditLog.created_at))
        .all()
    )
    by_action: dict[str, list[tuple[str, int]]] = {}
    for action, day, count in action_day_counts:
        by_action.setdefault(action, []).append((str(day), count))

    anomalies = []
    for action, day_counts in by_action.items():
        counts = [c for _, c in day_counts]
        mean = sum(counts) / len(counts) if counts else 0
        if mean == 0:
            continue
        for day, count in day_counts:
            if count > spike_threshold * mean and count > 5:
                anomalies.append({
                    "action": action, "date": day, "count": count,
                    "baseline_mean": round(mean, 1),
                    "reason": f"{count} events vs. baseline mean {mean:.1f} ({spike_threshold}x threshold)",
                })
    return sorted(anomalies, key=lambda a: a["count"], reverse=True)


def summary(db: Session, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    total = db.query(func.count(AuditLog.id)).filter(AuditLog.created_at >= since).scalar()
    return {
        "window_days": days,
        "total_events": total,
        "by_action": events_by_action(db, since),
        "by_day": events_by_day(db, since),
        "top_resources": top_resources(db, since),
        "anomalies": anomaly_scan(db, since),
    }
