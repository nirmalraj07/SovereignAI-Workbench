import shutil
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..updates import service as updates_service
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("")
async def list_packages(db: Session = Depends(get_db), admin: dict = Depends(require_role("admin"))):
    return updates_service.list_packages(db)


@router.post("/upload")
async def upload_package(
    version: str = Form(...),
    checksum: str = Form(...),
    notes: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: dict = Depends(require_role("admin")),
):
    dest = updates_service.UPDATE_STAGING_DIR / f"{version}.tar"
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        result = updates_service.register_package(db, dest, version, checksum, notes)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))

    record_event(user=admin["username"], action="update_upload", resource=version)
    return result


@router.post("/{package_id}/apply")
async def apply_package(package_id: str, db: Session = Depends(get_db),
                         admin: dict = Depends(require_role("admin"))):
    try:
        result = updates_service.apply_package(db, package_id, applied_by=admin["username"])
    except KeyError:
        raise HTTPException(status_code=404, detail="Update package not found")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    record_event(user=admin["username"], action="update_apply", resource=package_id)
    return result
