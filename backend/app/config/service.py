"""
System Configuration Management: versioned key/value store for runtime-
tunable platform settings (sandbox timeouts, retrieval top_k, MFA
enforcement, rotation intervals, etc.) so operators can adjust behavior
without a redeploy. Every change is recorded in config_history for audit.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from ..db.models import SystemConfig, ConfigHistory

DEFAULTS: dict[str, tuple[object, str, str]] = {
    # key: (default_value, category, description)
    "sandbox.timeout_seconds": (30, "sandbox", "Max seconds a sandboxed execution may run"),
    "sandbox.max_repair_attempts": (3, "sandbox", "Max auto-repair cycles before giving up"),
    "rag.default_top_k": (5, "rag", "Default number of chunks retrieved per KB query"),
    "rag.chunk_size": (800, "rag", "Words per chunk during ingestion"),
    "auth.mfa_required": (True, "security", "Whether MFA is mandatory for all users"),
    "auth.access_token_minutes": (60, "security", "JWT access token lifetime in minutes"),
    "secrets.rotation_interval_days": (90, "security", "Days between automatic secret rotations"),
    "backup.retention_days": (30, "backup", "Days to retain automated backups"),
    "backup.schedule_cron": ("0 2 * * *", "backup", "Cron expression for the nightly backup job"),
    "ocr.confidence_fallback_threshold": (60.0, "ocr", "Mean confidence below which PaddleOCR fallback triggers"),
    "agents.distributed_execution_enabled": (False, "agents", "Route agent nodes to per-type Celery queues (gpu_queue/cpu_queue/io_queue) instead of running them in-process"),
}


def get_config(db: Session, key: str):
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row:
        return row.value
    if key in DEFAULTS:
        return DEFAULTS[key][0]
    raise KeyError(f"Unknown config key: {key}")


def get_all(db: Session) -> list[dict]:
    stored = {row.key: row for row in db.query(SystemConfig).all()}
    result = []
    for key, (default, category, description) in DEFAULTS.items():
        row = stored.get(key)
        result.append({
            "key": key,
            "value": row.value if row else default,
            "category": category,
            "description": description,
            "version": row.version if row else 0,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        })
    # Include any custom keys not in DEFAULTS (operator-added config)
    for key, row in stored.items():
        if key not in DEFAULTS:
            result.append({
                "key": key, "value": row.value, "category": row.category,
                "description": row.description, "version": row.version,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            })
    return result


def set_config(db: Session, key: str, value, changed_by: str | None,
                category: str | None = None, description: str | None = None) -> dict:
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    old_value = row.value if row else DEFAULTS.get(key, (None,))[0]

    if row:
        row.value = value
        row.version += 1
        row.updated_at = datetime.utcnow()
        row.updated_by = changed_by
        if category:
            row.category = category
        if description:
            row.description = description
    else:
        default_category, default_description = (DEFAULTS.get(key, (None, "custom", ""))[1:]
                                                    if key in DEFAULTS else ("custom", ""))
        row = SystemConfig(
            id=str(uuid.uuid4()), key=key, value=value,
            category=category or default_category,
            description=description or default_description,
            updated_by=changed_by, version=1,
        )
        db.add(row)

    db.add(ConfigHistory(
        id=str(uuid.uuid4()), key=key, old_value=old_value, new_value=value,
        changed_by=changed_by,
    ))
    db.commit()
    db.refresh(row)
    return {
        "key": row.key, "value": row.value, "category": row.category,
        "description": row.description, "version": row.version,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_history(db: Session, key: str, limit: int = 50) -> list[dict]:
    rows = (
        db.query(ConfigHistory)
        .filter(ConfigHistory.key == key)
        .order_by(ConfigHistory.changed_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {"old_value": r.old_value, "new_value": r.new_value, "changed_by": r.changed_by,
         "changed_at": r.changed_at.isoformat() if r.changed_at else None}
        for r in rows
    ]
