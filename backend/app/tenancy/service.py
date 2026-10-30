"""
Tenant Isolation Layer: a single-deployment can host multiple business
units/departments as tenants sharing the platform but with row-level data
separation. tenant_id is nullable on shared tables (documents, tasks) —
NULL means globally shared (the default for a single-tenant deployment);
a non-null tenant_id scopes visibility to that tenant only.

This is enforced at the service layer (every query goes through
scope_query()) rather than Postgres RLS, matching the rest of this
codebase's plain-SQLAlchemy style — a production hardening pass can add
RLS policies as defense in depth without changing this interface.
"""
from __future__ import annotations
import uuid
from sqlalchemy.orm import Session, Query
from sqlalchemy import or_

from ..db.models import Tenant


def scope_query(query: Query, model, tenant_id: str | None) -> Query:
    """Restricts `query` to rows matching tenant_id, or globally-shared
    rows (tenant_id IS NULL), for any model with a tenant_id column."""
    if tenant_id is None:
        return query
    return query.filter(or_(model.tenant_id == tenant_id, model.tenant_id.is_(None)))


def create_tenant(db: Session, name: str, slug: str, classification_default: str = "internal") -> dict:
    tenant = Tenant(id=str(uuid.uuid4()), name=name, slug=slug,
                     classification_default=classification_default, active="true")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return _serialize(tenant)


def list_tenants(db: Session) -> list[dict]:
    return [_serialize(t) for t in db.query(Tenant).order_by(Tenant.created_at.asc()).all()]


def deactivate_tenant(db: Session, tenant_id: str) -> dict:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise KeyError("Tenant not found")
    tenant.active = "false"
    db.commit()
    db.refresh(tenant)
    return _serialize(tenant)


def _serialize(t: Tenant) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "classification_default": t.classification_default,
        "active": t.active == "true",
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
