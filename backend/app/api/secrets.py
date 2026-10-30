from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..secrets import rotation
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


@router.get("/rotation-status")
async def status(db: Session = Depends(get_db), user: dict = Depends(require_role("admin"))):
    return rotation.rotation_status(db)


@router.post("/rotate/{secret_name}")
async def rotate(secret_name: str, db: Session = Depends(get_db),
                  admin: dict = Depends(require_role("admin"))):
    try:
        result = rotation.rotate_secret(db, secret_name, triggered_by=admin["username"])
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown rotation target: {secret_name}")
    record_event(user=admin["username"], action="secret_rotate", resource=secret_name)
    return result
