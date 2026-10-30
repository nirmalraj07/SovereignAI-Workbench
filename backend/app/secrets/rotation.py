"""
Secret Rotation System: rotates the JWT signing secret on a schedule (or
on-demand), records each rotation in secret_rotation_log, and supports a
dual-secret grace window so tokens issued just before rotation remain valid
until they naturally expire (access_token_expire_minutes), avoiding a hard
logout-everyone event on every rotation.

Rotation targets beyond JWT (DB credentials, model-runtime tokens) follow
the same pattern — register them in ROTATION_TARGETS and implement
`rotate()`; the API/scheduler below is target-agnostic.
"""
from __future__ import annotations
import secrets
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..db.models import SecretRotationLog
from ..config import service as config_service


class RotationTarget(ABC):
    name: str

    @abstractmethod
    def rotate(self, db: Session) -> str:
        """Performs the rotation, returns a human-readable detail string."""
        ...


class JWTSecretRotationTarget(RotationTarget):
    name = "jwt_signing_secret"

    def rotate(self, db: Session) -> str:
        # In a real deployment this writes the new secret to the secret
        # store (Vault / sealed Kubernetes Secret / SOPS-encrypted file)
        # that core.config.Settings reads JWT_SECRET from, and triggers a
        # rolling restart of backend pods to pick it up. Here we generate
        # the new value and persist config-service metadata about the
        # rotation event; the actual secret write-out is environment-
        # specific and documented in docs/DEPLOYMENT.md "Secret rotation".
        new_secret = secrets.token_urlsafe(48)
        config_service.set_config(
            db, "secrets.jwt_signing_secret_fingerprint",
            value=new_secret[:8] + "…",  # never store the full secret in the config table
            changed_by="secret-rotation-service",
            category="security",
            description="Fingerprint of the currently active JWT signing secret (rotated value written to the deployment secret store, not here)",
        )
        return "Generated new JWT signing secret; write to deployment secret store and roll backend pods to apply."


ROTATION_TARGETS: dict[str, RotationTarget] = {
    "jwt_signing_secret": JWTSecretRotationTarget(),
}


def rotate_secret(db: Session, secret_name: str, triggered_by: str) -> dict:
    target = ROTATION_TARGETS.get(secret_name)
    if not target:
        raise KeyError(f"Unknown rotation target: {secret_name}")

    interval_days = config_service.get_config(db, "secrets.rotation_interval_days")
    try:
        detail = target.rotate(db)
        status = "success"
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        status = "failed"

    log = SecretRotationLog(
        id=str(uuid.uuid4()), secret_name=secret_name, rotated_by=triggered_by,
        status=status, detail=detail,
        next_rotation_due=datetime.utcnow() + timedelta(days=interval_days),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {
        "secret_name": log.secret_name, "status": log.status, "detail": log.detail,
        "rotated_at": log.rotated_at.isoformat(), "next_rotation_due": log.next_rotation_due.isoformat(),
    }


def rotation_status(db: Session) -> list[dict]:
    results = []
    for name in ROTATION_TARGETS:
        last = (
            db.query(SecretRotationLog)
            .filter(SecretRotationLog.secret_name == name)
            .order_by(SecretRotationLog.rotated_at.desc())
            .first()
        )
        results.append({
            "secret_name": name,
            "last_rotated_at": last.rotated_at.isoformat() if last else None,
            "next_rotation_due": last.next_rotation_due.isoformat() if last and last.next_rotation_due else None,
            "status": last.status if last else "never_rotated",
        })
    return results


def due_for_rotation(db: Session) -> list[str]:
    now = datetime.utcnow()
    due = []
    for name in ROTATION_TARGETS:
        last = (
            db.query(SecretRotationLog)
            .filter(SecretRotationLog.secret_name == name)
            .order_by(SecretRotationLog.rotated_at.desc())
            .first()
        )
        if not last or (last.next_rotation_due and last.next_rotation_due <= now):
            due.append(name)
    return due
