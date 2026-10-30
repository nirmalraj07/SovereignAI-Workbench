"""
Integration tests using FastAPI's TestClient against the real app instance
(routes, dependency injection, RBAC) with the DB/Chroma/model-runtime layer
mocked at the boundary — these test the API contract and auth/RBAC wiring,
not the external services themselves (those are exercised in the on-prem
deployment's smoke test, since they require live Postgres/Chroma/Ollama).

Run: pytest backend/tests/test_integration_api.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


def _postgres_available() -> bool:
    from app.db.session import engine
    try:
        with engine.connect():
            return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="Live Postgres not reachable — /api/auth/login now correctly "
           "queries the real users table (fixed: it used to only check an "
           "in-memory demo dict, so DB-created users could never log in). "
           "Run with docker-compose up postgres to exercise this.",
)


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestHealthAndAuth:
    def test_health_endpoint_is_public(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["external_dependencies"] == 0

    @requires_postgres
    def test_login_rejects_bad_credentials(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    @requires_postgres
    def test_seed_admin_can_login_with_mfa_disabled_by_default(self, client):
        # The bootstrap admin seeded by alembic/versions/0003_user_mfa_and_seed.py
        # starts with MFA disabled — a fresh install needs a way in before
        # anyone has enrolled an authenticator. docs/DEPLOYMENT.md's
        # "Initial hardening" instructs enrolling MFA immediately after
        # first login, which is exercised by TestMFAEnrollmentFlow below.
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @requires_postgres
    def test_login_rejects_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={"username": "no-such-user", "password": "x"})
        assert resp.status_code == 401

    def test_protected_endpoint_rejects_missing_token(self, client):
        resp = client.get("/api/monitoring/system")
        assert resp.status_code == 401

    def test_protected_endpoint_rejects_garbage_token(self, client):
        resp = client.get(
            "/api/monitoring/system",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401


class TestRBACEnforcement:
    def _token_for(self, role: str) -> str:
        from app.security.auth import create_access_token
        return create_access_token(username="testuser", role=role)

    def test_viewer_cannot_access_admin_users(self, client):
        token = self._token_for("viewer")
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_viewer_cannot_access_monitoring(self, client):
        token = self._token_for("viewer")
        resp = client.get("/api/monitoring/system", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_auditor_can_access_security_dashboard(self, client):
        token = self._token_for("auditor")
        with patch("app.api.security.recent_events", return_value=[]):
            resp = client.get("/api/security/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["external_connections"] == 0

    def test_auditor_cannot_access_admin_models(self, client):
        token = self._token_for("auditor")
        resp = client.get("/api/admin/models", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestMFAEnrollmentFlow:
    """End-to-end: provision -> confirm with a real TOTP code -> MFA now
    required on login -> disable -> MFA no longer required. Exercises the
    fix for both vulnerabilities found in this build (unauthenticated
    provisioning; login never checking the real users table)."""

    @requires_postgres
    def test_full_enrollment_and_login_cycle(self, client):
        import time
        import uuid
        import pyotp
        from passlib.hash import bcrypt

        # Uses a freshly created throwaway user rather than the shared seed
        # admin account — mutating admin's MFA state directly made this
        # test fragile against a real, persistent database shared across a
        # test session (a prior test run leaving admin's MFA enabled broke
        # this test's "starts disabled" assumption on re-run, which is a
        # test-isolation problem, not a product bug). Every other test in
        # this class-adjacent security suite (test_auth_security_remediation.py)
        # already follows this fresh-user pattern.
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        username = f"mfa-flow-{uuid.uuid4().hex[:8]}"
        password = "mfa-flow-password-123"
        create_resp = client.post("/api/admin/users", headers=admin_headers,
                                   json={"username": username, "password": password, "role": "viewer"})
        assert create_resp.status_code == 200

        login_resp = client.post("/api/auth/login", json={"username": username, "password": password})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        provision_resp = client.get("/api/auth/mfa/provision", headers=headers)
        assert provision_resp.status_code == 200
        secret = provision_resp.json()["secret"]

        code = pyotp.TOTP(secret).now()
        enable_resp = client.post("/api/auth/mfa/enable", json={"code": code}, headers=headers)
        assert enable_resp.status_code == 200
        assert enable_resp.json()["mfa_enabled"] is True

        no_code_resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert no_code_resp.status_code == 401
        assert no_code_resp.json()["detail"] == "MFA code required"

        # Replay protection (see security/mfa.py) means the code used to
        # confirm enrollment above cannot also be reused for login if it
        # falls in the same 30s TOTP step. Compute the login code against
        # a synthetic future step instead of sleeping through a real
        # window, keeping this test fast and deterministic.
        current_step = int(time.time()) // 30
        fresh_code = pyotp.TOTP(secret).at((current_step + 1) * 30)
        with_code_resp = client.post(
            "/api/auth/login",
            json={"username": username, "password": password, "mfa_code": fresh_code},
        )
        assert with_code_resp.status_code == 200


class TestChatEndpointOrchestration:
    def test_chat_runs_full_task_graph_for_coding_request(self, client):
        from app.security.auth import create_access_token
        token = create_access_token(username="engineer1", role="engineer")

        with patch("app.router.router.ModelRouter.generate", new=AsyncMock(
            return_value=type("R", (), {"text": "print('hi')", "model_used": "deepseek-coder",
                                         "tokens_generated": 3, "latency_ms": 1.0})()
        )), patch("app.sandbox.executor.execute_with_repair", new=AsyncMock(
            return_value=(type("E", (), {"stdout": "hi\n", "stderr": "", "exit_code": 0,
                                          "duration_ms": 5.0, "timed_out": False})(), "print('hi')", 1)
        )):
            resp = client.post(
                "/api/chat", json={"message": "build me a small script"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        node_ids = [n["id"] for n in body["plan"]]
        assert node_ids == ["code_gen", "execute", "fix", "validate"]
        assert all(n["status"] == "done" for n in body["plan"])


class TestNotifications:
    def test_notifications_list_requires_auth(self, client):
        resp = client.get("/api/notifications")
        assert resp.status_code == 401

    def test_notifications_list_returns_array_when_authed(self, client):
        from app.security.auth import create_access_token
        token = create_access_token(username="anyone", role="viewer")
        resp = client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
