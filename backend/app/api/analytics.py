from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..observability import audit_analytics, compliance_report
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/audit-summary")
async def audit_summary(days: int = 30, db: Session = Depends(get_db),
                         user: dict = Depends(require_role("auditor"))):
    return audit_analytics.summary(db, days)


@router.post("/compliance-report")
async def compliance_report_route(days: int = 30, db: Session = Depends(get_db),
                                   admin: dict = Depends(require_role("admin"))):
    path = compliance_report.generate_compliance_report(db, days, prepared_by=admin["username"])
    record_event(user=admin["username"], action="generate_compliance_report", resource=str(path))
    return {"file_path": str(path), "download_url": f"/api/files/download?path={path}"}
