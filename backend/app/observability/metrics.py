"""
Production Observability: Prometheus metrics exposition. Wraps key
counters/histograms around agent execution, model routing, sandbox
executions, and HTTP requests, exposed at /metrics for a Prometheus
scrape target — no external SaaS dependency, consistent with the
platform's air-gapped requirement (Prometheus/Grafana run on-prem
alongside everything else, see deploy/k8s/10-observability.yaml).
"""
from prometheus_client import Counter, Histogram, Gauge, CONTENT_TYPE_LATEST, generate_latest
from fastapi import APIRouter, Response

router = APIRouter(tags=["observability"])

http_requests_total = Counter(
    "sovereignai_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
http_request_duration_seconds = Histogram(
    "sovereignai_http_request_duration_seconds", "HTTP request duration", ["method", "path"]
)
agent_runs_total = Counter(
    "sovereignai_agent_runs_total", "Total agent node executions", ["agent_name", "status"]
)
agent_run_duration_seconds = Histogram(
    "sovereignai_agent_run_duration_seconds", "Agent node execution duration", ["agent_name"]
)
model_requests_total = Counter(
    "sovereignai_model_requests_total", "Total model generation requests", ["model_name", "status"]
)
model_pool_replica_healthy = Gauge(
    "sovereignai_model_pool_replica_healthy", "1 if a model pool replica is healthy", ["model_name", "endpoint"]
)
sandbox_executions_total = Counter(
    "sovereignai_sandbox_executions_total", "Total sandbox code executions", ["language", "status"]
)
kb_queries_total = Counter("sovereignai_kb_queries_total", "Total knowledge base queries")
active_websocket_connections = Gauge(
    "sovereignai_active_websocket_connections", "Currently open task-progress WebSocket connections"
)


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
