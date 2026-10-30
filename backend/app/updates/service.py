"""
Offline Software Update Framework: for an air-gapped deployment, updates
arrive as a signed/checksummed tarball transferred in via removable media
or an internal file share — never a live "check for updates" call to the
internet. This module verifies the package integrity, records it, and runs
the deployment-provided apply script (docker image reload + migration +
rolling restart), all orchestrated from inside the network boundary.
"""
from __future__ import annotations
import hashlib
import subprocess
import tarfile
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from ..db.models import UpdatePackageRecord

UPDATE_STAGING_DIR = Path("/data/updates")
UPDATE_STAGING_DIR.mkdir(parents=True, exist_ok=True)

APPLY_SCRIPT = Path(__file__).resolve().parents[3] / "deploy" / "scripts" / "apply_update.sh"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register_package(db: Session, file_path: Path, version: str, expected_checksum: str,
                      notes: str = "") -> dict:
    actual_checksum = _sha256(file_path)
    if actual_checksum != expected_checksum:
        raise ValueError(
            f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}. "
            f"Refusing to register a tampered or corrupted update package."
        )
    if not tarfile.is_tarfile(file_path):
        raise ValueError("Update package must be a valid tar archive")

    record = UpdatePackageRecord(
        id=str(uuid.uuid4()), version=version, checksum=actual_checksum,
        applied="false", notes=notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize(record)


def apply_package(db: Session, package_id: str, applied_by: str) -> dict:
    record = db.query(UpdatePackageRecord).filter(UpdatePackageRecord.id == package_id).first()
    if not record:
        raise KeyError("Update package not found")
    if record.applied == "true":
        return {"status": "already_applied", "version": record.version}

    package_path = UPDATE_STAGING_DIR / f"{record.version}.tar"
    if not package_path.exists():
        raise FileNotFoundError(f"Staged package file missing: {package_path}")
    if _sha256(package_path) != record.checksum:
        raise ValueError("Staged file checksum no longer matches registered checksum — aborting apply")

    if APPLY_SCRIPT.exists():
        proc = subprocess.run(
            ["bash", str(APPLY_SCRIPT), str(package_path), record.version],
            capture_output=True, text=True, timeout=1800,
        )
        status = "applied" if proc.returncode == 0 else "failed"
        output = proc.stdout + proc.stderr
    else:
        status, output = "failed", f"Apply script not found at {APPLY_SCRIPT}"

    record.applied = "true" if status == "applied" else "false"
    record.applied_at = datetime.utcnow() if status == "applied" else None
    db.commit()
    db.refresh(record)
    return {"status": status, "version": record.version, "output": output[-4000:]}


def list_packages(db: Session) -> list[dict]:
    rows = db.query(UpdatePackageRecord).order_by(UpdatePackageRecord.uploaded_at.desc()).all()
    return [_serialize(r) for r in rows]


def _serialize(r: UpdatePackageRecord) -> dict:
    return {
        "id": r.id, "version": r.version, "checksum": r.checksum,
        "applied": r.applied == "true", "applied_at": r.applied_at.isoformat() if r.applied_at else None,
        "notes": r.notes, "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
    }
