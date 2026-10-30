from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..plugins import loader
from ..security.auth import require_role
from ..security.audit import record_event

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("/discover")
async def discover(admin: dict = Depends(require_role("admin"))):
    return loader.discover_plugins()


@router.get("")
async def list_installed(db: Session = Depends(get_db), admin: dict = Depends(require_role("admin"))):
    return loader.list_installed(db)


@router.post("/load/{plugin_name}")
async def load(plugin_name: str, db: Session = Depends(get_db), admin: dict = Depends(require_role("admin"))):
    try:
        result = loader.load_plugin(db, plugin_name, installed_by=admin["username"])
    except loader.PluginLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record_event(user=admin["username"], action="plugin_load", resource=plugin_name)
    return result


@router.post("/{plugin_name}/disable")
async def disable(plugin_name: str, db: Session = Depends(get_db), admin: dict = Depends(require_role("admin"))):
    try:
        result = loader.disable_plugin(db, plugin_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Plugin not found")
    record_event(user=admin["username"], action="plugin_disable", resource=plugin_name)
    return result
