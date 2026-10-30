"""
Enterprise Policy Engine: evaluates structured rules against a resource
context and returns allow / deny / require_approval. Rules are stored in
the policy_rules table (editable via the API, no redeploy needed) and
evaluated in creation order — first matching rule wins; no match defaults
to allow (fail-open for usability) unless `policy.fail_closed` is set in
system_config (fail-closed for high-security deployments).

Example rule condition (JSON): {"field": "classification", "op": "eq", "value": "restricted"}
combined with resource_type "document" and action "require_approval" means:
any document ingestion where classification == "restricted" requires
approval before indexing.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ..db.models import PolicyRule
from ..config import service as config_service

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "gt": lambda a, b: a is not None and a > b,
    "lt": lambda a, b: a is not None and a < b,
    "contains": lambda a, b: b in a if a is not None else False,
}


@dataclass
class PolicyDecision:
    action: str  # allow | deny | require_approval
    matched_rule: str | None
    reason: str


def _evaluate_condition(condition: dict, context: dict) -> bool:
    field = condition.get("field")
    op = condition.get("op", "eq")
    expected = condition.get("value")
    actual = context.get(field)
    op_fn = _OPS.get(op)
    if not op_fn:
        return False
    try:
        return op_fn(actual, expected)
    except TypeError:
        return False


def evaluate(db: Session, resource_type: str, context: dict) -> PolicyDecision:
    rules = (
        db.query(PolicyRule)
        .filter(PolicyRule.resource_type == resource_type, PolicyRule.enabled == "true")
        .order_by(PolicyRule.created_at.asc())
        .all()
    )
    for rule in rules:
        if _evaluate_condition(rule.condition or {}, context):
            return PolicyDecision(action=rule.action, matched_rule=rule.name,
                                   reason=f"Matched policy '{rule.name}'")

    fail_closed = False
    try:
        fail_closed = bool(config_service.get_config(db, "policy.fail_closed"))
    except KeyError:
        pass

    if fail_closed:
        return PolicyDecision(action="deny", matched_rule=None, reason="No matching rule; fail-closed default")
    return PolicyDecision(action="allow", matched_rule=None, reason="No matching rule; fail-open default")


def create_rule(db: Session, name: str, description: str, resource_type: str,
                 condition: dict, action: str, created_by: str) -> dict:
    rule = PolicyRule(
        id=str(uuid.uuid4()), name=name, description=description, resource_type=resource_type,
        condition=condition, action=action, enabled="true", created_by=created_by,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


def list_rules(db: Session, resource_type: str | None = None) -> list[dict]:
    q = db.query(PolicyRule)
    if resource_type:
        q = q.filter(PolicyRule.resource_type == resource_type)
    return [_serialize(r) for r in q.order_by(PolicyRule.created_at.asc()).all()]


def set_enabled(db: Session, rule_id: str, enabled: bool) -> dict:
    rule = db.query(PolicyRule).filter(PolicyRule.id == rule_id).first()
    if not rule:
        raise KeyError("Rule not found")
    rule.enabled = "true" if enabled else "false"
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


def _serialize(rule: PolicyRule) -> dict:
    return {
        "id": rule.id, "name": rule.name, "description": rule.description,
        "resource_type": rule.resource_type, "condition": rule.condition,
        "action": rule.action, "enabled": rule.enabled == "true",
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }
