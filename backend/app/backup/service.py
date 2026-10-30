"""
Backup and Restore: triggers pg_dump for Postgres and a tar snapshot of the
ChromaDB persistence directory, writes both to BACKUP_DIR, records metadata
in backup_records, and supports restore from either. Runs as subprocesses
so it works identically whether invoked from the API (ad hoc) or a Celery
beat schedule (nightly, per system_config `backup.schedule_cron`).
"""
from __future__ import annotations
import hashlib
import subprocess
import tarfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.models import BackupRecord

BACKUP_DIR = Path("/data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_DATA_DIR = Path("/data/chroma")  # mounted read-only into the backend for backup purposes


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_pg_url() -> dict:
    # postgresql://user:pass@host:port/dbname
    rest = settings.database_url.split("://", 1)[1]
    creds, hostpart = rest.split("@", 1)
    user, password = creds.split(":", 1)
    hostport, dbname = hostpart.split("/", 1)
    host, port = (hostport.split(":") + ["5432"])[:2]
    return {"user": user, "password": password, "host": host, "port": port, "dbname": dbname}


def backup_postgres(db: Session, triggered_by: str) -> dict:
    conn = _parse_pg_url()
    filename = f"postgres-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.dump"
    out_path = BACKUP_DIR / filename

    env = {"PGPASSWORD": conn["password"]}
    cmd = [
        "pg_dump", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
        "-F", "c", "-f", str(out_path), conn["dbname"],
    ]
    proc = subprocess.run(cmd, env={**env}, capture_output=True, text=True, timeout=600)
    status = "completed" if proc.returncode == 0 else "failed"

    record = BackupRecord(
        id=str(uuid.uuid4()), backup_type="postgres", file_path=str(out_path),
        size_bytes=out_path.stat().st_size if out_path.exists() else 0,
        checksum=_checksum(out_path) if out_path.exists() else "",
        status=status, triggered_by=triggered_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id, "backup_type": "postgres", "status": status,
        "file_path": str(out_path), "stderr": proc.stderr if status == "failed" else None,
    }


def backup_chromadb(db: Session, triggered_by: str) -> dict:
    filename = f"chromadb-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    out_path = BACKUP_DIR / filename

    status = "completed"
    error = None
    try:
        with tarfile.open(out_path, "w:gz") as tar:
            if CHROMA_DATA_DIR.exists():
                tar.add(CHROMA_DATA_DIR, arcname="chroma")
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)

    record = BackupRecord(
        id=str(uuid.uuid4()), backup_type="chromadb", file_path=str(out_path),
        size_bytes=out_path.stat().st_size if out_path.exists() else 0,
        checksum=_checksum(out_path) if out_path.exists() and status == "completed" else "",
        status=status, triggered_by=triggered_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "backup_type": "chromadb", "status": status,
            "file_path": str(out_path), "error": error}


def backup_full(db: Session, triggered_by: str) -> dict:
    pg = backup_postgres(db, triggered_by)
    chroma = backup_chromadb(db, triggered_by)
    return {"postgres": pg, "chromadb": chroma}


def restore_postgres(db: Session, backup_id: str) -> dict:
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id,
                                            BackupRecord.backup_type == "postgres").first()
    if not record:
        raise FileNotFoundError(f"No postgres backup record with id {backup_id}")

    path = Path(record.file_path)
    if not path.exists():
        raise FileNotFoundError(f"Backup file missing on disk: {path}")
    if _checksum(path) != record.checksum:
        raise ValueError("Backup file checksum mismatch — refusing to restore a corrupted/tampered dump")

    conn = _parse_pg_url()
    cmd = [
        "pg_restore", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
        "-d", conn["dbname"], "--clean", "--if-exists", str(path),
    ]
    proc = subprocess.run(cmd, env={"PGPASSWORD": conn["password"]}, capture_output=True, text=True, timeout=900)
    return {"status": "completed" if proc.returncode == 0 else "failed", "stderr": proc.stderr}


def list_backups(db: Session, backup_type: str | None = None, limit: int = 50) -> list[dict]:
    q = db.query(BackupRecord)
    if backup_type:
        q = q.filter(BackupRecord.backup_type == backup_type)
    rows = q.order_by(BackupRecord.created_at.desc()).limit(limit).all()
    return [
        {"id": r.id, "backup_type": r.backup_type, "file_path": r.file_path,
         "size_bytes": r.size_bytes, "status": r.status, "triggered_by": r.triggered_by,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


def prune_expired(db: Session, retention_days: int) -> int:
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    expired = db.query(BackupRecord).filter(BackupRecord.created_at < cutoff).all()
    count = 0
    for record in expired:
        path = Path(record.file_path)
        if path.exists():
            path.unlink()
        db.delete(record)
        count += 1
    db.commit()
    return count
