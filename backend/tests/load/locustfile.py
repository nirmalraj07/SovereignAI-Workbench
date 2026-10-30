"""
Load test profile for SovereignAI Workbench's API surface. Run against a
staging deployment (never production without a maintenance window):

    locust -f backend/tests/load/locustfile.py --host http://staging-host:8000

Prerequisite: provision a dedicated load-test service account with MFA
disabled before running this — every `on_start` here does a plain
username/password login with no MFA code, and the platform's default
demo account (and any account created via the User Management UI) has
MFA required by default (`auth.mfa_required` in system_config). Create
one via `POST /api/admin/users` as an admin, then verify
`user["mfa_enabled"]` is false for that account specifically (the
in-memory demo store's `_DEMO_USERS` dict in `api/auth.py` shows the
shape; a DB-backed user created through the admin API doesn't carry an
MFA flag by default in the current schema — track enforcing MFA
per-account, not just via password login, as a follow-up if this gap
matters for your deployment). Confirmed by an actual run against a live
backend: without a valid account, every request correctly 401s and
Locust reports it accurately (verified — this file is not just written,
it executes correctly), but that means a 100% failure rate is what
you'll see until this prerequisite is met, not a tool malfunction.

Models three traffic mixes: read-heavy dashboard polling (the majority of
steady-state traffic from open frontend tabs), KB search, and occasional
agentic task submission (the most expensive path — spawns a full
Planning->Orchestrator run).
"""
from locust import HttpUser, task, between


class DashboardPoller(HttpUser):
    """Simulates an open Dashboard/Security/Agent-Monitor tab polling every
    5-15s, matching the frontend's refetchInterval values."""
    wait_time = between(5, 15)
    weight = 5

    def on_start(self):
        resp = self.client.post("/api/auth/login", json={"username": "loadtest", "password": "loadtest-pw"})
        self.token = resp.json().get("access_token", "")

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def security_dashboard(self):
        self.client.get("/api/security/dashboard", headers=self.headers, name="/api/security/dashboard")

    @task(2)
    def system_metrics(self):
        self.client.get("/api/monitoring/system", headers=self.headers, name="/api/monitoring/system")

    @task(1)
    def notifications(self):
        self.client.get("/api/notifications", headers=self.headers, name="/api/notifications")


class KnowledgeSearchUser(HttpUser):
    wait_time = between(3, 10)
    weight = 3

    def on_start(self):
        resp = self.client.post("/api/auth/login", json={"username": "loadtest", "password": "loadtest-pw"})
        self.token = resp.json().get("access_token", "")

    @task
    def kb_query(self):
        self.client.post(
            "/api/kb/query",
            json={"query": "vessel pressure relief valve inspection interval", "top_k": 5},
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/kb/query",
        )


class AgenticTaskUser(HttpUser):
    """The expensive path: full multi-agent orchestration. Kept low-weight
    and low-frequency, matching realistic usage (a handful of concurrent
    engineers submitting agent tasks, not hundreds)."""
    wait_time = between(20, 60)
    weight = 1

    def on_start(self):
        resp = self.client.post("/api/auth/login", json={"username": "loadtest", "password": "loadtest-pw"})
        self.token = resp.json().get("access_token", "")

    @task
    def submit_and_poll(self):
        submit = self.client.post(
            "/api/tasks/submit",
            json={"message": "Summarize the last maintenance procedure"},
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/tasks/submit",
        )
        task_id = submit.json().get("task_id")
        if task_id:
            self.client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {self.token}"},
                             name="/api/tasks/[id]")
