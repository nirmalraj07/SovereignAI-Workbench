from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..backup import service as backup_service
from ..config import service as config_service
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("")
async def list_backups(backup_type: str | None = None, db: Session = Depends(get_db),
                        user: dict = Depends(require_role("auditor"))):
    return backup_service.list_backups(db, backup_type)


@router.post("/run")
async def run_backup(backup_type: str = "full", db: Session = Depends(get_db),
                      admin: dict = Depends(require_role("admin"))):
    if backup_type == "postgres":
        result = backup_service.backup_postgres(db, triggered_by=admin["username"])
    elif backup_type == "chromadb":
        result = backup_service.backup_chromadb(db, triggered_by=admin["username"])
    elif backup_type == "full":
        result = backup_service.backup_full(db, triggered_by=admin["username"])
    else:
        raise HTTPException(status_code=400, detail="backup_type must be postgres, chromadb, or full")
    record_event(user=admin["username"], action="backup_run", resource=backup_type)
    return result


@router.post("/restore/{backup_id}")
async def restore(backup_id: str, db: Session = Depends(get_db),
                   admin: dict = Depends(require_role("admin"))):
    try:
        result = backup_service.restore_postgres(db, backup_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    record_event(user=admin["username"], action="backup_restore", resource=backup_id)
    return result


@router.post("/prune")
async def prune(db: Session = Depends(get_db), admin: dict = Depends(require_role("admin"))):
    retention_days = config_service.get_config(db, "backup.retention_days")
    count = backup_service.prune_expired(db, retention_days)
    record_event(user=admin["username"], action="backup_prune", resource=f"{count} expired")
    return {"pruned": count}
