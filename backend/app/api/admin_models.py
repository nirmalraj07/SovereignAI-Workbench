from fastapi import APIRouter, Depends
from ..router.router import router as model_router
from ..security.auth import require_role

router = APIRouter(prefix="/api/admin/models", tags=["admin"])


@router.get("")
async def list_models(user: dict = Depends(require_role("admin"))):
    results = []
    for name, cfg in model_router.table["models"].items():
        pool = model_router._pools.get(name)
        replicas = await pool.health_report() if pool else []
        any_online = any(r["online"] for r in replicas)
        results.append({
            "name": name,
            "backend_type": cfg["backend"],
            "modality": cfg["modality"],
            "status": "online" if any_online else "offline",
            "good_for": cfg.get("good_for", []),
            "replicas": replicas,
        })
    return results


@router.get("/pool-health")
async def pool_health(user: dict = Depends(require_role("admin"))):
    """Per-replica health for every model pool — the basis for the Multi-GPU
    Scheduling / Model Failover status view (each entry's `in_cooldown` flag
    shows whether the router has temporarily failed that replica out after
    an error, per ModelPool's cooldown window)."""
    return await model_router.pool_health()
