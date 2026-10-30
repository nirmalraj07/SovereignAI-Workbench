from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..config import service as config_service
from ..security.auth import require_role, get_current_user
from ..security.audit import record_event

router = APIRouter(prefix="/api/config", tags=["configuration"])


class SetConfigRequest(BaseModel):
    value: Any
    category: str | None = None
    description: str | None = None


@router.get("")
async def list_config(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    return config_service.get_all(db)


@router.get("/{key}")
async def get_config(key: str, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    try:
        return {"key": key, "value": config_service.get_config(db, key)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")


@router.put("/{key}")
async def set_config(key: str, req: SetConfigRequest, db: Session = Depends(get_db),
                      admin: dict = Depends(require_role("admin"))):
    result = config_service.set_config(db, key, req.value, changed_by=admin["username"],
                                        category=req.category, description=req.description)
    record_event(user=admin["username"], action="config_update", resource=key)
    return result


@router.get("/{key}/history")
async def config_history(key: str, db: Session = Depends(get_db),
                          user: dict = Depends(require_role("auditor"))):
    return config_service.get_history(db, key)
