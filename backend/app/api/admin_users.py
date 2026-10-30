import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import User
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UpdateRoleRequest(BaseModel):
    role: str


class ResetPasswordRequest(BaseModel):
    new_password: str


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


def _serialize(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "is_active": u.is_active == "true",
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }


@router.get("", response_model=list[UserOut])
async def list_users(db: Session = Depends(get_db), user: dict = Depends(require_role("admin"))):
    return [_serialize(u) for u in db.query(User).order_by(User.created_at.desc()).all()]


@router.post("", response_model=UserOut)
async def create_user(req: CreateUserRequest, db: Session = Depends(get_db),
                       admin: dict = Depends(require_role("admin"))):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = User(
        id=str(uuid.uuid4()),
        username=req.username,
        password_hash=bcrypt.hash(req.password),
        role=req.role,
        mfa_enabled="false",  # new users enroll their own MFA via self-service
                               # /api/auth/mfa/provision + /mfa/enable on first
                               # login — an admin can never set someone else's
                               # MFA secret (see auth.py provision_mfa docstring)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    record_event(user=admin["username"], action="admin_create_user", resource=req.username)
    return _serialize(new_user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_role(user_id: str, req: UpdateRoleRequest, db: Session = Depends(get_db),
                       admin: dict = Depends(require_role("admin"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = req.role
    db.commit()
    db.refresh(target)
    record_event(user=admin["username"], action="admin_update_role", resource=f"{target.username}->{req.role}")
    return _serialize(target)


@router.delete("/{user_id}")
async def delete_user(user_id: str, db: Session = Depends(get_db),
                       admin: dict = Depends(require_role("admin"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(target)
    db.commit()
    record_event(user=admin["username"], action="admin_delete_user", resource=target.username)
    return {"deleted": user_id}


@router.post("/{user_id}/disable", response_model=UserOut)
async def disable_user(user_id: str, db: Session = Depends(get_db),
                        admin: dict = Depends(require_role("admin"))):
    """Soft-disable, distinct from delete: preserves the row (and every
    FK reference to it — tasks, audit_log, documents.ingested_by, etc.)
    while blocking login. Use this for the common "offboard someone but
    keep their history" case; use DELETE only when the row itself should
    stop existing."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_active = "false"
    db.commit()
    db.refresh(target)
    record_event(user=admin["username"], action="admin_disable_user", resource=target.username)
    return _serialize(target)


@router.post("/{user_id}/enable", response_model=UserOut)
async def enable_user(user_id: str, db: Session = Depends(get_db),
                       admin: dict = Depends(require_role("admin"))):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_active = "true"
    db.commit()
    db.refresh(target)
    record_event(user=admin["username"], action="admin_enable_user", resource=target.username)
    return _serialize(target)


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, req: ResetPasswordRequest, db: Session = Depends(get_db),
                          admin: dict = Depends(require_role("admin"))):
    """Admin-initiated reset — sets a new password directly with no
    knowledge of the old one required, appropriate for an air-gapped
    deployment with no outbound email to power a token-link reset flow.
    The new password should be communicated to the user out-of-band by
    the admin; nothing here transmits it anywhere else."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    target.password_hash = bcrypt.hash(req.new_password)
    db.commit()
    record_event(user=admin["username"], action="admin_reset_password", resource=target.username)
    return {"status": "password reset"}
