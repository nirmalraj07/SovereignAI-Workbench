"""
Agent framework. Each specialist agent implements BaseAgent.run(). The
Orchestrator builds a task graph from the Planning Agent's output and
executes nodes (currently sequential; parallelizable by dependency later).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from ..router.router import router


@dataclass
class TaskNode:
    id: str
    agent: str
    instruction: str
    depends_on: list[str] = field(default_factory=list)
    result: Any = None
    status: str = "pending"   # pending | running | done | failed


@dataclass
class TaskGraph:
    request_text: str
    nodes: list[TaskNode] = field(default_factory=list)

    def get(self, node_id: str) -> TaskNode:
        return next(n for n in self.nodes if n.id == node_id)

    def ready_nodes(self) -> list[TaskNode]:
        return [
            n for n in self.nodes
            if n.status == "pending"
            and all(self.get(dep).status == "done" for dep in n.depends_on)
        ]


class BaseAgent(ABC):
    name: str

    @abstractmethod
    async def run(self, instruction: str, context: dict) -> Any:
        ...


class PlanningAgent(BaseAgent):
    name = "planning"

    async def run(self, instruction: str, context: dict) -> TaskGraph:
        # Minimal deterministic planner for common patterns; falls back to a
        # single reasoning-agent node for anything unrecognized. A learned/
        # LLM-driven planner can replace this without changing the interface.
        text = instruction.lower()
        nodes: list[TaskNode] = []

        if "inspection report" in text or ("scan" in text and "report" in text):
            nodes = [
                TaskNode("ocr", "ocr", "Extract text from the uploaded scan"),
                TaskNode("research", "research", "Search SOP database for related procedures",
                         depends_on=["ocr"]),
                TaskNode("approval_note", "approval_note", "Draft an approval note",
                         depends_on=["research"]),
                TaskNode("validate", "validation", "Validate the drafted note",
                         depends_on=["approval_note"]),
                TaskNode("export", "document", "Export approval note as DOCX",
                         depends_on=["validate"]),
            ]
        elif "engineering drawing" in text or "p&id" in text or "diagram" in text:
            nodes = [
                TaskNode("vision", "vision", "Analyze the uploaded engineering drawing"),
                TaskNode("summary", "document", "Generate a technical summary",
                         depends_on=["vision"]),
            ]
        elif "sop" in text and ("question" in text or "?" in text):
            nodes = [
                TaskNode("kb_query", "knowledge_base", "Retrieve relevant SOP documents"),
                TaskNode("answer", "research", "Generate grounded answer with citations",
                         depends_on=["kb_query"]),
            ]
        elif any(k in text for k in ["build", "code", "software", "application", "script"]):
            nodes = [
                TaskNode("code_gen", "coding", "Generate the requested application code"),
                TaskNode("execute", "coding", "Execute in sandbox and capture errors",
                         depends_on=["code_gen"]),
                TaskNode("fix", "coding", "Fix errors and re-run until working",
                         depends_on=["execute"]),
                TaskNode("validate", "validation", "Validate final deliverable",
                         depends_on=["fix"]),
            ]
        else:
            nodes = [TaskNode("general", "research", instruction)]

        return TaskGraph(request_text=instruction, nodes=nodes)


class Orchestrator:
    def __init__(self, agents: dict[str, BaseAgent]):
        self.agents = agents

    async def execute(self, graph: TaskGraph, context: dict) -> TaskGraph:
        from ..observability.metrics import agent_runs_total, agent_run_duration_seconds
        import time

        while True:
            ready = graph.ready_nodes()
            if not ready:
                break
            for node in ready:
                node.status = "running"
                agent = self.agents.get(node.agent)
                if agent is None:
                    node.status = "failed"
                    node.result = f"No agent registered for '{node.agent}'"
                    agent_runs_total.labels(agent_name=node.agent, status="failed").inc()
                    continue
                start = time.time()
                try:
                    node.result = await agent.run(node.instruction, context)
                    node.status = "done"
                except Exception as exc:  # noqa: BLE001
                    node.status = "failed"
                    node.result = str(exc)
                agent_runs_total.labels(agent_name=node.agent, status=node.status).inc()
                agent_run_duration_seconds.labels(agent_name=node.agent).observe(time.time() - start)
                # Every node's serialized result is mirrored into
                # context["upstream"][node.id] regardless of execution mode.
                # In-process agents may additionally read/write the shared
                # `context` dict directly (existing behavior, e.g.
                # KnowledgeBaseAgent setting context["kb_chunks"]), but
                # context["upstream"] is the contract that also works when
                # nodes run in separate processes (DistributedOrchestrator,
                # agents/distributed.py) — agents should prefer reading
                # dependency data from context["upstream"][dep_id] so the
                # same agent code works correctly in both orchestrators.
                context.setdefault("upstream", {})[node.id] = node.result
        return graph
