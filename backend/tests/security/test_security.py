"""
Security-focused tests: JWT tampering, sandbox/file path traversal, RBAC
boundary enforcement beyond the happy-path integration tests, and the
air-gap host-allowlist guardrail. Run: pytest backend/tests/security -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient
from jose import jwt


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestJWTTampering:
    def test_token_signed_with_wrong_secret_is_rejected(self, client):
        forged = jwt.encode({"sub": "admin", "role": "admin"}, "wrong-secret", algorithm="HS256")
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {forged}"})
        assert resp.status_code == 401

    def test_token_with_tampered_role_claim_rejected_if_resigned_wrong(self, client):
        # Simulates an attacker editing the payload without the real secret —
        # the signature check must fail, not the role check.
        from app.core.config import settings
        forged = jwt.encode({"sub": "attacker", "role": "admin"}, settings.jwt_secret + "x", algorithm="HS256")
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {forged}"})
        assert resp.status_code == 401

    def test_expired_token_is_rejected(self, client):
        from datetime import datetime, timedelta
        from app.core.config import settings
        expired = jwt.encode(
            {"sub": "admin", "role": "admin", "exp": datetime.utcnow() - timedelta(minutes=5)},
            settings.jwt_secret, algorithm=settings.jwt_algorithm,
        )
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401

    def test_privilege_escalation_via_role_claim_requires_valid_signature(self, client):
        """A viewer cannot simply mint their own admin token — only a
        server-issued, correctly-signed token grants elevated access."""
        from app.security.auth import create_access_token
        real_viewer_token = create_access_token(username="viewer1", role="viewer")
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {real_viewer_token}"})
        assert resp.status_code == 403


class TestFileDownloadPathTraversal:
    def test_download_rejects_path_outside_generated_dir(self, client):
        from app.security.auth import create_access_token
        token = create_access_token(username="user1", role="viewer")
        resp = client.get(
            "/api/files/download",
            params={"path": "/etc/passwd"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_download_rejects_relative_traversal(self, client):
        from app.security.auth import create_access_token
        token = create_access_token(username="user1", role="viewer")
        resp = client.get(
            "/api/files/download",
            params={"path": "/data/generated/../../etc/passwd"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (403, 404)  # normalized path must not resolve inside OUTPUT_DIR


class TestAirGapGuardrail:
    def test_boots_with_internal_only_hosts(self):
        from app.core.config import Settings, _assert_no_external_egress
        s = Settings()
        _assert_no_external_egress(s)  # should not raise

    def test_refuses_external_database_host(self):
        from app.core.config import Settings, _assert_no_external_egress
        s = Settings(database_url="postgresql://user:pass@evil-external-host.com:5432/db")
        with pytest.raises(RuntimeError, match="on-prem allowlist"):
            _assert_no_external_egress(s)

    def test_refuses_external_model_runtime_host(self):
        from app.core.config import Settings, _assert_no_external_egress
        s = Settings(model_runtime_url="https://api.some-cloud-llm-provider.com/v1")
        with pytest.raises(RuntimeError):
            _assert_no_external_egress(s)


class TestMFAProvisioningAuthenticationRequired:
    """Regression guard for a real vulnerability found and fixed in this
    build: GET /api/auth/mfa/provision/{username} originally had NO auth
    dependency and returned any user's TOTP secret by username alone — a
    full MFA-bypass/account-takeover primitive. Fixed by removing the
    username path parameter entirely (the endpoint now only provisions
    the CALLER's own account, identified from their JWT) and requiring
    authentication. These tests don't need a live database: the auth
    dependency rejects an invalid/missing token before any DB query runs."""

    def test_provisioning_rejects_unauthenticated_request(self, client):
        resp = client.get("/api/auth/mfa/provision")
        assert resp.status_code == 401

    def test_old_vulnerable_url_shape_no_longer_exists(self, client):
        # The old route accepted a username in the path; that path no
        # longer resolves to anything at all now.
        resp = client.get("/api/auth/mfa/provision/admin")
        assert resp.status_code in (401, 404, 405)

    def test_enable_mfa_rejects_unauthenticated_request(self, client):
        resp = client.post("/api/auth/mfa/enable", json={"code": "123456"})
        assert resp.status_code == 401

    def test_disable_mfa_rejects_unauthenticated_request(self, client):
        resp = client.post("/api/auth/mfa/disable")
        assert resp.status_code == 401


class TestSandboxLanguageAllowlist:
    @pytest.mark.asyncio
    async def test_unsupported_language_rejected_without_executing(self):
        from app.sandbox.executor import execute
        result = await execute("import os; os.system('echo pwned')", "ruby")
        assert result.exit_code == -1
        assert "Unsupported language" in result.stderr
