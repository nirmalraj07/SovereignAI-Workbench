"""
Distributed Agent Execution: dispatches each TaskGraph node to a Celery
task on a queue selected by agent category, instead of running every
agent type in-process on whichever worker picked up the parent task. This
lets operators scale GPU-bound agent categories (coding, vision, ocr)
independently from lightweight ones (research, validation, monitoring) by
running separate `celery worker -Q gpu_queue` / `-Q cpu_queue` / `-Q
io_queue` pools with different replica counts and node affinities (see
deploy/k8s/07-celery-worker.yaml for the per-queue Deployment split).

Same TaskGraph-execution contract as agents.base.Orchestrator — nodes
within one "ready" batch have no dependencies on each other, so they are
dispatched in parallel across queues/workers and awaited together.
"""
from __future__ import annotations
import asyncio
from .base import TaskGraph

AGENT_QUEUE_MAP: dict[str, str] = {
    # GPU-bound: model inference (coding gen, vision inference) or heavy
    # CV (OCR fallback to PaddleOCR) — scale these with GPU-backed workers.
    "coding": "gpu_queue",
    "vision": "gpu_queue",
    "ocr": "gpu_queue",
    # I/O-bound: mostly waiting on disk/DB/network (retrieval, file writes).
    "knowledge_base": "io_queue",
    "document": "io_queue",
    "spreadsheet": "io_queue",
    "presentation": "io_queue",
    "reporting": "io_queue",
    "approval_note": "io_queue",
    # CPU-light: text generation calls through the router but no heavy
    # local compute of their own.
    "research": "cpu_queue",
    "validation": "cpu_queue",
    "calculation": "cpu_queue",
    "monitoring": "cpu_queue",
}
DEFAULT_QUEUE = "cpu_queue"


def queue_for_agent(agent_name: str) -> str:
    return AGENT_QUEUE_MAP.get(agent_name, DEFAULT_QUEUE)


class DistributedOrchestrator:
    """Drop-in alternative to agents.base.Orchestrator. Requires a running
    Celery broker (Redis) and at least one worker consuming each queue in
    AGENT_QUEUE_MAP's values — see docs/DEPLOYMENT.md 'Distributed agent
    execution'. Falls back is the caller's responsibility: catch the
    exception raised when Celery is unreachable and use the in-process
    Orchestrator instead (workers/celery_app.py's run_agent_task does this)."""

    def __init__(self, task_timeout_seconds: int = 120):
        self.task_timeout_seconds = task_timeout_seconds

    async def execute(self, graph: TaskGraph, context: dict) -> TaskGraph:
        from ..workers.celery_app import run_single_agent_node

        while True:
            ready = graph.ready_nodes()
            if not ready:
                break

            async_results = {}
            for node in ready:
                node.status = "running"
                queue = queue_for_agent(node.agent)
                async_results[node.id] = run_single_agent_node.apply_async(
                    args=[node.agent, node.instruction, context], queue=queue,
                )

            async def _collect(node_id: str, async_result):
                try:
                    result = await asyncio.to_thread(
                        async_result.get, timeout=self.task_timeout_seconds
                    )
                    return node_id, "done", result
                except Exception as exc:  # noqa: BLE001 — worker crash, timeout, or agent-level error
                    return node_id, "failed", str(exc)

            outcomes = await asyncio.gather(*(_collect(nid, ar) for nid, ar in async_results.items()))
            for node_id, status, result in outcomes:
                node = graph.get(node_id)
                node.status = status
                node.result = result
                context.setdefault("upstream", {})[node_id] = result
        return graph
