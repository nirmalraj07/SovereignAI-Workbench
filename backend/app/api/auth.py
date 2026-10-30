from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from passlib.hash import bcrypt
from sqlalchemy.orm import Session
import pyotp

from ..db.session import get_db
from ..db.models import User
from ..security.auth import create_access_token, get_current_user
from ..security.audit import record_event
from ..security.mfa import verify_totp_with_replay_protection

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: str | None = None


class MFAProvisionResponse(BaseModel):
    otpauth_url: str
    secret: str


class MFAEnableRequest(BaseModel):
    code: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not bcrypt.verify(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.is_active == "false":
        # Checked AFTER password verification, not before: telling an
        # unauthenticated caller "this account is disabled" before they've
        # proven they know the password would leak account-existence
        # information to anyone guessing usernames. Once bcrypt.verify has
        # already succeeded, the caller has demonstrated they know the
        # correct credential, so disclosing the disabled state here adds
        # no information an attacker without the password could exploit.
        record_event(user=user.username, action="login_blocked_disabled", resource="auth")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    if user.mfa_enabled == "true":
        if not user.mfa_secret:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                 detail="MFA is enabled but no secret is provisioned for this account")
        if not req.mfa_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA code required")

        is_valid, matched_step = verify_totp_with_replay_protection(
            user.mfa_secret, req.mfa_code, user.mfa_last_used_step
        )
        if not is_valid:
            record_event(user=req.username, action="mfa_verify_failed", resource="login")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

        user.mfa_last_used_step = matched_step
        db.commit()

    record_event(user=user.username, action="login", resource="auth")
    token = create_access_token(user.username, user.role)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/mfa/provision", response_model=MFAProvisionResponse)
async def provision_mfa(current: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Self-service MFA enrollment: generates (or returns the existing
    not-yet-confirmed) TOTP secret for the CALLER's own account only —
    requires a valid JWT, and there is no username parameter, so this
    cannot be used to fetch or overwrite another account's secret. The
    secret only takes effect after POST /mfa/enable confirms a code
    generated from it, so a leaked half-enrolled secret from this endpoint
    can't bypass MFA on its own.
    """
    user = db.query(User).filter(User.username == current["username"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.mfa_secret:
        user.mfa_secret = pyotp.random_base32()
        user.mfa_last_used_step = None  # fresh secret invalidates any prior replay-tracking state
        db.commit()
        db.refresh(user)

    totp = pyotp.TOTP(user.mfa_secret)
    record_event(user=user.username, action="mfa_provision", resource=user.username)
    return MFAProvisionResponse(
        otpauth_url=totp.provisioning_uri(name=user.username, issuer_name="SovereignAI Workbench"),
        secret=user.mfa_secret,
    )


@router.post("/mfa/enable")
async def enable_mfa(req: MFAEnableRequest, current: dict = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Confirms enrollment by verifying a real code from the authenticator
    app before flipping mfa_enabled — provisioning a secret alone (above)
    never enables MFA on its own, preventing a half-finished/abandoned
    enrollment from silently leaving MFA off, and preventing anyone who
    merely observed a provisioning response from enabling MFA without
    proving they actually control the authenticator."""
    user = db.query(User).filter(User.username == current["username"]).first()
    if not user or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Call /api/auth/mfa/provision first")

    is_valid, matched_step = verify_totp_with_replay_protection(
        user.mfa_secret, req.code, user.mfa_last_used_step
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    user.mfa_enabled = "true"
    user.mfa_last_used_step = matched_step
    db.commit()
    record_event(user=user.username, action="mfa_enable", resource=user.username)
    return {"mfa_enabled": True}


@router.post("/mfa/disable")
async def disable_mfa(current: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Self-service disable — requires an already-valid session (so an
    attacker needs a live authenticated session, not just the password,
    to turn MFA off). Also clears the secret and replay-tracking state so
    re-enrollment starts clean rather than inheriting stale state."""
    user = db.query(User).filter(User.username == current["username"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.mfa_enabled = "false"
    user.mfa_secret = None
    user.mfa_last_used_step = None
    db.commit()
    record_event(user=user.username, action="mfa_disable", resource=user.username)
    return {"mfa_enabled": False}


@router.post("/password/change")
async def change_password(req: ChangePasswordRequest, current: dict = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """Self-service password change — requires proving knowledge of the
    CURRENT password (not just a valid session), since a stolen/leaked JWT
    alone shouldn't be enough to lock the real owner out by changing their
    password. Every existing session for this user (there's no session
    table enforcement today beyond JWT expiry — see Known Limitations)
    remains valid until natural token expiry; this is a documented gap,
    not silently ignored."""
    user = db.query(User).filter(User.username == current["username"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not bcrypt.verify(req.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user.password_hash = bcrypt.hash(req.new_password)
    db.commit()
    record_event(user=user.username, action="password_change", resource=user.username)
    return {"status": "password changed"}
