"""
Background task queue using Celery + Redis.

Long-running agent workflows execute here instead of blocking
FastAPI HTTP requests.
"""

import asyncio

from celery import Celery
from celery.signals import worker_ready

from ..core.config import settings


# ============================================================
# CELERY APPLICATION
# ============================================================

celery_app = Celery(
    "sovereignai",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


# ============================================================
# PROMETHEUS METRICS
# ============================================================

@worker_ready.connect
def _start_metrics_server(**kwargs):
    """
    Start the Prometheus metrics HTTP server inside the Celery worker.
    """

    from prometheus_client import start_http_server

    try:
        start_http_server(9100)
    except OSError:
        # Port may already be occupied if the worker was restarted
        # in the same environment.
        pass


# ============================================================
# CELERY CONFIGURATION
# ============================================================

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    task_track_started=True,

    result_expires=3600,

    beat_schedule={

        "nightly-full-backup": {
            "task": "workers.run_nightly_backup",
            "schedule": 86400.0,
        },

        "check-secret-rotation-due": {
            "task": "workers.check_secret_rotation",
            "schedule": 3600.0,
        },

    },
)


# ============================================================
# NIGHTLY BACKUP
# ============================================================

@celery_app.task(
    name="workers.run_nightly_backup"
)
def run_nightly_backup():

    from ..api.notifications import push_notification
    from ..backup import service as backup_service
    from ..config import service as config_service
    from ..db.session import db_session

    with db_session() as db:

        result = backup_service.backup_full(
            db,
            triggered_by="scheduler",
        )

        retention_days = config_service.get_config(
            db,
            "backup.retention_days",
        )

        pruned = backup_service.prune_expired(
            db,
            retention_days,
        )

    failures = [

        key

        for key, value in result.items()

        if value.get("status") == "failed"

    ]

    if failures:

        push_notification(
            "Nightly backup failed",
            f"Failed components: {', '.join(failures)}",
            level="error",
        )

    else:

        push_notification(
            "Nightly backup completed",
            f"Pruned {pruned} expired backup(s)",
            level="success",
        )

    return {
        "result": result,
        "pruned": pruned,
    }


# ============================================================
# SECRET ROTATION
# ============================================================

@celery_app.task(
    name="workers.check_secret_rotation"
)
def check_secret_rotation():

    from ..api.notifications import push_notification
    from ..db.session import db_session
    from ..secrets import rotation

    with db_session() as db:

        due = rotation.due_for_rotation(db)

        results = [

            rotation.rotate_secret(
                db,
                name,
                triggered_by="scheduler",
            )

            for name in due

        ]

    if results:

        secret_names = [

            result["secret_name"]

            for result in results

        ]

        push_notification(
            "Automatic secret rotation performed",
            f"Rotated: {', '.join(secret_names)}",
            level="info",
        )

    return results


# ============================================================
# SINGLE DISTRIBUTED AGENT NODE
# ============================================================

@celery_app.task(
    name="workers.run_single_agent_node"
)
def run_single_agent_node(
    agent_name: str,
    instruction: str,
    context: dict,
):
    """
    Executes exactly one agent.

    Used by DistributedOrchestrator when agent execution is distributed
    across multiple Celery queues/workers.
    """

    from ..agents.base import PlanningAgent
    from ..agents.specialists import build_agent_registry

    async def _run():

        agents = build_agent_registry()

        agents["planning"] = PlanningAgent()

        agent = agents.get(agent_name)

        if agent is None:

            raise ValueError(
                f"No agent registered for '{agent_name}'"
            )

        return await agent.run(
            instruction,
            context,
        )

    return asyncio.run(_run())


# ============================================================
# FULL AGENT WORKFLOW
# ============================================================

@celery_app.task(
    bind=True,
    name="workers.run_agent_task",
)
def run_agent_task(
    self,
    message: str,
    image_b64: str | None = None,
    filename: str | None = None,
):
    """
    Runs the complete:

        PlanningAgent
            ↓
        TaskGraph
            ↓
        DistributedOrchestrator / Orchestrator
            ↓
        Specialist Agents

    OCR uploads are passed through:

        image_b64
        filename

    in the shared workflow context.
    """

    from ..agents.base import (
        Orchestrator,
        PlanningAgent,
    )

    from ..agents.distributed import (
        DistributedOrchestrator,
    )

    from ..agents.specialists import (
        build_agent_registry,
    )

    from ..api.notifications import (
        push_notification,
    )

    from ..config import service as config_service
    from ..db.session import db_session

    # ========================================================
    # CHECK DISTRIBUTED EXECUTION
    # ========================================================

    distributed_enabled = False

    try:

        with db_session() as db:

            distributed_enabled = bool(
                config_service.get_config(
                    db,
                    "agents.distributed_execution_enabled",
                )
            )

    except Exception:

        distributed_enabled = False


    # ========================================================
    # ASYNC WORKFLOW
    # ========================================================

    async def _run():

        # ----------------------------------------------------
        # Build agents
        # ----------------------------------------------------

        agents = build_agent_registry()

        agents["planning"] = PlanningAgent()

        planner = agents["planning"]

        # ----------------------------------------------------
        # Generate graph
        # ----------------------------------------------------

        graph = await planner.run(
            message,
            context={},
        )

        # ----------------------------------------------------
        # Shared workflow context
        # ----------------------------------------------------

        context = {

            "image_b64": image_b64,

            "filename": filename or "uploaded_file",

        }

        # ----------------------------------------------------
        # Distributed execution
        # ----------------------------------------------------

        if distributed_enabled:

            try:

                orchestrator = DistributedOrchestrator()

                graph = await orchestrator.execute(
                    graph,
                    context,
                )

                return graph

            except Exception:

                # Reset graph for safe in-process fallback.

                for node in graph.nodes:

                    node.status = "pending"

                    node.result = None


        # ----------------------------------------------------
        # In-process execution
        # ----------------------------------------------------

        orchestrator = Orchestrator(
            agents
        )

        graph = await orchestrator.execute(
            graph,
            context,
        )

        return graph


    # ========================================================
    # RUN ASYNC WORKFLOW
    # ========================================================

    graph = asyncio.run(
        _run()
    )


    # ========================================================
    # SERIALIZE RESULT
    # ========================================================

    result = {

        "plan": [

            {
                "id": node.id,
                "agent": node.agent,
                "status": node.status,
            }

            for node in graph.nodes

        ],

        "results": {

            node.id: node.result

            for node in graph.nodes

        },

    }


    # ========================================================
    # SEND NOTIFICATION
    # ========================================================

    failed_nodes = [

        node

        for node in result["plan"]

        if node["status"] == "failed"

    ]


    if failed_nodes:

        failed_ids = ", ".join(
            node["id"]
            for node in failed_nodes
        )

        push_notification(

            title="Agent task completed with errors",

            message=(
                f"{len(failed_nodes)} step(s) failed: "
                f"{failed_ids}"
            ),

            level="warning",

        )

    else:

        push_notification(

            title="Agent task completed",

            message=message[:100],

            level="success",

        )


    return result