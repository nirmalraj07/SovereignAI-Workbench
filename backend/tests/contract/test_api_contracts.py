"""
API Contract Tests: validates that the app's generated OpenAPI schema is
well-formed and internally consistent, and that key endpoints' actual JSON
responses conform to their declared Pydantic response models — catching
drift between what a route claims to return and what it actually returns
(a common source of silent frontend breakage when a backend field is
renamed but the frontend TypeScript type isn't updated in lockstep).

Run: pytest backend/tests/contract -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate as jsonschema_validate, ValidationError


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def openapi_schema(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    return resp.json()


def _postgres_available() -> bool:
    from app.db.session import engine
    try:
        with engine.connect():
            return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="Live Postgres not reachable in this environment — these contract "
           "tests validate response shape against real DB-backed endpoints "
           "and are meant for a staging/CI run with docker-compose up postgres.",
)


class TestOpenAPISchemaWellFormed:
    def test_schema_has_required_top_level_keys(self, openapi_schema):
        for key in ("openapi", "info", "paths", "components"):
            assert key in openapi_schema

    def test_every_path_has_at_least_one_method(self, openapi_schema):
        for path, methods in openapi_schema["paths"].items():
            http_methods = {"get", "post", "put", "patch", "delete", "options", "head"}
            assert http_methods & set(methods.keys()), f"{path} has no HTTP methods defined"

    def test_every_operation_has_a_response_schema(self, openapi_schema):
        missing = []
        for path, methods in openapi_schema["paths"].items():
            for method, operation in methods.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                responses = operation.get("responses", {})
                success_codes = [c for c in responses if c.startswith("2")]
                if not success_codes:
                    missing.append(f"{method.upper()} {path}")
        assert not missing, f"Operations missing a 2xx response schema: {missing}"

    def test_all_protected_endpoints_declare_security_or_expected_401(self, client, openapi_schema):
        """Every route that isn't explicitly public should reject an
        unauthenticated request with 401, not 200 or 500 — a contract-level
        guardrail against a route accidentally shipping without its
        Depends(get_current_user)/require_role() dependency."""
        public_paths = {"/api/health", "/api/auth/login", "/openapi.json", "/docs",
                         "/docs/oauth2-redirect", "/redoc",
                         "/metrics"}  # Prometheus scrape target — no JWT carried by
                                      # the scraper; access is restricted at the
                                      # network layer (NetworkPolicy ingress rule
                                      # allowing only the observability namespace,
                                      # see deploy/k8s/10-observability.yaml), the
                                      # same pattern as /api/health.
        get_paths = [p for p, m in openapi_schema["paths"].items() if "get" in m]
        for path in get_paths:
            if path in public_paths or "{" in path:  # skip parameterized paths (need real IDs)
                continue
            resp = client.get(path)
            assert resp.status_code == 401, f"{path} did not require auth (got {resp.status_code})"


class TestResponseShapeContracts:
    """Validates real endpoint responses against a JSON Schema derived from
    the same shape the frontend's TypeScript types (frontend/types/index.ts)
    expect — catching drift between backend and frontend contracts."""

    def _token(self, role: str = "admin") -> str:
        from app.security.auth import create_access_token
        return create_access_token(username="contract-test-user", role=role)

    def test_health_response_shape(self, client):
        schema = {
            "type": "object",
            "required": ["status", "app", "external_dependencies"],
            "properties": {
                "status": {"type": "string"},
                "app": {"type": "string"},
                "external_dependencies": {"type": "number"},
            },
        }
        resp = client.get("/api/health")
        jsonschema_validate(resp.json(), schema)

    def test_security_dashboard_response_shape(self, client, monkeypatch):
        from unittest.mock import patch
        schema = {
            "type": "object",
            "required": ["external_connections", "external_api_calls", "network_egress_allowed", "audit_events"],
            "properties": {
                "external_connections": {"type": "number"},
                "external_api_calls": {"type": "number"},
                "network_egress_allowed": {"type": "boolean"},
                "audit_events": {"type": "array"},
            },
        }
        token = self._token("auditor")
        with patch("app.api.security.recent_events", return_value=[]):
            resp = client.get("/api/security/dashboard", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        jsonschema_validate(resp.json(), schema)

    def test_tasks_submit_response_shape(self, client):
        from unittest.mock import patch, MagicMock
        schema = {
            "type": "object",
            "required": ["task_id", "status"],
            "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}},
        }
        token = self._token("viewer")
        fake_result = MagicMock()
        fake_result.id = "fake-task-id-123"
        with patch("app.api.tasks.run_agent_task.delay", return_value=fake_result):
            resp = client.post("/api/tasks/submit", json={"message": "hello"},
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        jsonschema_validate(resp.json(), schema)

    @requires_postgres
    def test_policy_evaluate_response_shape(self, client):
        schema = {
            "type": "object",
            "required": ["action", "reason"],
            "properties": {
                "action": {"type": "string", "enum": ["allow", "deny", "require_approval"]},
                "matched_rule": {"type": ["string", "null"]},
                "reason": {"type": "string"},
            },
        }
        token = self._token("engineer")
        resp = client.post(
            "/api/policy/evaluate",
            json={"resource_type": "document", "context": {"classification": "internal"}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        jsonschema_validate(resp.json(), schema)

    @requires_postgres
    def test_config_list_response_is_array_of_well_shaped_items(self, client):
        item_schema = {
            "type": "object",
            "required": ["key", "value", "category"],
            "properties": {
                "key": {"type": "string"},
                "category": {"type": "string"},
                "version": {"type": "number"},
            },
        }
        token = self._token("viewer")
        resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) > 0
        for item in body:
            jsonschema_validate(item, item_schema)


class TestBackwardCompatibilityGuards:
    """Fields the frontend depends on by exact name — renaming these without
    a coordinated frontend change is a breaking contract change this test
    is designed to catch."""

    def _token(self) -> str:
        from app.security.auth import create_access_token
        return create_access_token(username="contract-test-user", role="admin")

    @requires_postgres
    def test_admin_users_list_uses_snake_case_created_at(self, client):
        token = self._token()
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        for user in resp.json():
            assert "created_at" in user  # NOT "createdAt" — frontend/types/index.ts AdminUser expects this
            assert "username" in user
            assert "role" in user

    def test_notifications_use_expected_field_names(self, client):
        token = self._token()
        resp = client.get("/api/notifications", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        # empty list is valid; if non-empty, verify shape matches NotificationItem
        for note in resp.json():
            assert set(note.keys()) >= {"id", "title", "message", "level", "created_at", "read"}
