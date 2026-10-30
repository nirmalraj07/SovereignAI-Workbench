from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..agents.base import PlanningAgent, Orchestrator
from ..agents.specialists import build_agent_registry
from ..security.auth import get_current_user
from ..security.audit import record_event

router = APIRouter(prefix="/api/chat", tags=["chat"])

_agents = build_agent_registry()
_agents["planning"] = PlanningAgent()
_orchestrator = Orchestrator(_agents)


class ChatRequest(BaseModel):
    message: str
    image_b64: str | None = None


@router.post("")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    record_event(user=user["username"], action="chat_request", resource=req.message[:80])

    planner = _agents["planning"]
    graph = await planner.run(req.message, context={})
    graph = await _orchestrator.execute(graph, context={"image_b64": req.image_b64})

    return {
        "plan": [{"id": n.id, "agent": n.agent, "status": n.status} for n in graph.nodes],
        "results": {n.id: n.result for n in graph.nodes},
    }
