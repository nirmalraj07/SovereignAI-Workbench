from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..policy import engine as policy_engine
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/policy", tags=["policy"])


class CreateRuleRequest(BaseModel):
    name: str
    description: str = ""
    resource_type: str
    condition: dict[str, Any]
    action: str  # allow | deny | require_approval


class EvaluateRequest(BaseModel):
    resource_type: str
    context: dict[str, Any]


@router.get("")
async def list_rules(resource_type: str | None = None, db: Session = Depends(get_db),
                      user: dict = Depends(require_role("auditor"))):
    return policy_engine.list_rules(db, resource_type)


@router.post("")
async def create_rule(req: CreateRuleRequest, db: Session = Depends(get_db),
                       admin: dict = Depends(require_role("admin"))):
    if req.action not in ("allow", "deny", "require_approval"):
        raise HTTPException(status_code=400, detail="action must be allow, deny, or require_approval")
    result = policy_engine.create_rule(db, req.name, req.description, req.resource_type,
                                        req.condition, req.action, created_by=admin["username"])
    record_event(user=admin["username"], action="policy_create_rule", resource=req.name)
    return result


@router.patch("/{rule_id}/enabled")
async def set_enabled(rule_id: str, enabled: bool, db: Session = Depends(get_db),
                       admin: dict = Depends(require_role("admin"))):
    try:
        result = policy_engine.set_enabled(db, rule_id, enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found")
    record_event(user=admin["username"], action="policy_toggle_rule", resource=rule_id)
    return result


@router.post("/evaluate")
async def evaluate(req: EvaluateRequest, db: Session = Depends(get_db),
                    user: dict = Depends(require_role("engineer"))):
    decision = policy_engine.evaluate(db, req.resource_type, req.context)
    return {"action": decision.action, "matched_rule": decision.matched_rule, "reason": decision.reason}
