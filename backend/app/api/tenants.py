from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..tenancy import service as tenancy_service
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/tenants", tags=["tenancy"])


class CreateTenantRequest(BaseModel):
    name: str
    slug: str
    classification_default: str = "internal"


@router.get("")
async def list_tenants(db: Session = Depends(get_db), admin: dict = Depends(require_role("admin"))):
    return tenancy_service.list_tenants(db)


@router.post("")
async def create_tenant(req: CreateTenantRequest, db: Session = Depends(get_db),
                         admin: dict = Depends(require_role("admin"))):
    result = tenancy_service.create_tenant(db, req.name, req.slug, req.classification_default)
    record_event(user=admin["username"], action="tenant_create", resource=req.slug)
    return result


@router.post("/{tenant_id}/deactivate")
async def deactivate(tenant_id: str, db: Session = Depends(get_db),
                      admin: dict = Depends(require_role("admin"))):
    try:
        result = tenancy_service.deactivate_tenant(db, tenant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Tenant not found")
    record_event(user=admin["username"], action="tenant_deactivate", resource=tenant_id)
    return result
