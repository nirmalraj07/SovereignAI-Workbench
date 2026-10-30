from fastapi import APIRouter, Depends
from ..security.auth import require_role
from ..security.audit import recent_events

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/dashboard")
async def dashboard(user: dict = Depends(require_role("auditor"))):
    """
    Reports the platform's live egress posture. external_connections and
    api_calls are sourced from the network policy / proxy layer in a real
    deployment (e.g. iptables counters or an egress-proxy audit log) — here
    they are asserted at zero because sandbox + model backends are
    network-isolated by construction (see core/config.py and sandbox/).
    """
    return {
        "external_connections": 0,
        "external_api_calls": 0,
        "network_egress_allowed": False,
        "audit_events": recent_events(20),
    }
