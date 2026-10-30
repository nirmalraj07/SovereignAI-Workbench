import shutil
import psutil
from fastapi import APIRouter, Depends
from ..security.auth import require_role

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


def _gpu_stats() -> list[dict]:
    """Best-effort NVIDIA GPU stats via nvidia-smi; empty list on CPU-only hosts."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=3,
        ).decode()
        gpus = []
        for line in out.strip().splitlines():
            idx, name, util, mem_used, mem_total = [p.strip() for p in line.split(",")]
            gpus.append({"index": int(idx), "name": name, "utilization_pct": float(util),
                         "memory_used_mb": float(mem_used), "memory_total_mb": float(mem_total)})
        return gpus
    except Exception:
        return []


@router.get("/system")
async def system_metrics(user: dict = Depends(require_role("engineer"))):
    disk = shutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_used_gb": round(psutil.virtual_memory().used / 1e9, 2),
        "memory_total_gb": round(psutil.virtual_memory().total / 1e9, 2),
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "disk_percent": round(disk.used / disk.total * 100, 1),
        "gpus": _gpu_stats(),
    }
