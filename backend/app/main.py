import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .api import (
    chat, security, auth, kb, code, files, monitoring, tasks, admin_users, admin_models,
    notifications, config, secrets, backup, policy, analytics, tenants, plugins, updates,
)
from .observability import metrics as metrics_module

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(security.router)
app.include_router(kb.router)
app.include_router(code.router)
app.include_router(files.router)
app.include_router(monitoring.router)
app.include_router(tasks.router)
app.include_router(admin_users.router)
app.include_router(admin_models.router)
app.include_router(notifications.router)
app.include_router(config.router)
app.include_router(secrets.router)
app.include_router(backup.router)
app.include_router(policy.router)
app.include_router(analytics.router)
app.include_router(tenants.router)
app.include_router(plugins.router)
app.include_router(updates.router)
app.include_router(metrics_module.router)


@app.middleware("http")
async def prometheus_request_timing(request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    # Use the route's declared path template (e.g. "/api/files/download",
    # not "/api/files/download?path=/etc/x") as the label so cardinality
    # stays bounded — high-cardinality labels (raw query strings, IDs) are
    # a classic way to quietly blow up a Prometheus instance's memory.
    path_template = request.scope.get("route").path if request.scope.get("route") else request.url.path
    metrics_module.http_requests_total.labels(
        method=request.method, path=path_template, status=response.status_code
    ).inc()
    metrics_module.http_request_duration_seconds.labels(
        method=request.method, path=path_template
    ).observe(duration)
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "external_dependencies": 0}
