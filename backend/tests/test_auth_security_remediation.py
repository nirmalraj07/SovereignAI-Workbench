"""
Full authentication/authorization regression suite, written after a live
security-remediation pass against a real PostgreSQL database (not mocks).
Every test here requires a live DB — that's deliberate: several of the
bugs this suite guards against (the actor-column UUID/string mismatch,
users-created-via-admin-API being unable to log in) only manifest against
a real database and were invisible to every prior mock-based test.

Run: pytest backend/tests/test_auth_security_remediation.py -v
Requires: docker-compose up postgres (or an equivalent local Postgres
with DATABASE_URL pointing at it) and `alembic upgrade head` already run.
"""
import sys
import uuid
from pathlib import Path
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
    reason="Live Postgres required — this suite specifically guards against bugs "
           "(actor-column type mismatches, DB-backed login) that are invisible to "
           "mocked tests. Run: docker-compose up postgres && alembic upgrade head",
)

pytestmark = requires_postgres


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "change-me"})
    assert resp.status_code == 200, "Seed admin login failed — is alembic upgrade head applied?"
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _create_user(client, admin_headers, role="viewer"):
    username = f"testuser-{uuid.uuid4().hex[:8]}"
    password = "test-password-123"
    resp = client.post("/api/admin/users", headers=admin_headers,
                        json={"username": username, "password": password, "role": role})
    assert resp.status_code == 200
    return resp.json()["id"], username, password


class TestObjective1_MFASecretDisclosureFixed:
    def test_provisioning_endpoint_has_no_username_path_parameter(self, client):
        # The vulnerable shape (/mfa/provision/{username}) must not resolve
        resp = client.get("/api/auth/mfa/provision/admin")
        assert resp.status_code in (401, 404, 405)

    def test_provisioning_requires_authentication(self, client):
        resp = client.get("/api/auth/mfa/provision")
        assert resp.status_code == 401

    def test_authenticated_user_can_only_provision_their_own_account(self, client, admin_headers):
        resp = client.get("/api/auth/mfa/provision", headers=admin_headers)
        assert resp.status_code == 200
        # No mechanism exists to target another user — the endpoint takes
        # no user-identifying parameter at all beyond the JWT.
        assert "secret" in resp.json()


class TestObjective2and3_DBBackedLoginAndNewUsers:
    def test_seed_admin_authenticates_against_real_db(self, admin_token):
        assert admin_token  # fixture already asserts 200; this documents intent

    def test_admin_created_user_can_log_in(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers)
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_wrong_password_and_nonexistent_user_give_identical_error(self, client, admin_headers):
        """User-enumeration guard: an attacker probing usernames should
        not be able to distinguish 'wrong password' from 'no such user'."""
        _, username, _ = _create_user(client, admin_headers)
        wrong_pw = client.post("/api/auth/login", json={"username": username, "password": "wrong"})
        no_user = client.post("/api/auth/login", json={"username": "definitely-not-a-real-user", "password": "x"})
        assert wrong_pw.status_code == no_user.status_code == 401
        assert wrong_pw.json()["detail"] == no_user.json()["detail"] == "Invalid credentials"


class TestObjective4and10_RBACAndPrivilegeEscalation:
    def test_viewer_cannot_access_admin_endpoints(self, client, admin_headers):
        user_id, username, password = _create_user(client, admin_headers, role="viewer")
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        for path in ("/api/admin/users", "/api/admin/models", "/api/secrets/rotation-status", "/api/updates"):
            resp = client.get(path, headers=headers)
            assert resp.status_code == 403, f"{path} should reject viewer role"

    def test_user_cannot_escalate_their_own_role_via_admin_api(self, client, admin_headers):
        user_id, username, password = _create_user(client, admin_headers, role="viewer")
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.patch(f"/api/admin/users/{user_id}", headers=headers, json={"role": "admin"})
        assert resp.status_code == 403

        # Confirm the role genuinely did not change
        listing = client.get("/api/admin/users", headers=admin_headers).json()
        target = next(u for u in listing if u["id"] == user_id)
        assert target["role"] == "viewer"

    def test_engineer_cannot_disable_other_users(self, client, admin_headers):
        victim_id, _, _ = _create_user(client, admin_headers, role="viewer")
        _, eng_username, eng_password = _create_user(client, admin_headers, role="engineer")
        eng_token = client.post("/api/auth/login",
                                 json={"username": eng_username, "password": eng_password}).json()["access_token"]
        resp = client.post(f"/api/admin/users/{victim_id}/disable",
                            headers={"Authorization": f"Bearer {eng_token}"})
        assert resp.status_code == 403


class TestObjective5_FullMFALifecycle:
    def test_enroll_activate_login_disable_cycle(self, client, admin_headers):
        import pyotp

        _, username, password = _create_user(client, admin_headers)
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Enroll
        provision = client.get("/api/auth/mfa/provision", headers=headers)
        assert provision.status_code == 200
        secret = provision.json()["secret"]

        # Activate with a real code
        code = pyotp.TOTP(secret).now()
        enable = client.post("/api/auth/mfa/enable", json={"code": code}, headers=headers)
        assert enable.status_code == 200
        assert enable.json()["mfa_enabled"] is True

        # Login without a code now fails
        no_code = client.post("/api/auth/login", json={"username": username, "password": password})
        assert no_code.status_code == 401
        assert no_code.json()["detail"] == "MFA code required"

        # Login with a wrong code fails
        wrong_code = client.post("/api/auth/login",
                                  json={"username": username, "password": password, "mfa_code": "000000"})
        assert wrong_code.status_code == 401

        # Disable requires an authenticated session (use the token from before MFA was required)
        disable = client.post("/api/auth/mfa/disable", headers=headers)
        assert disable.status_code == 200

        # Login without a code works again
        after_disable = client.post("/api/auth/login", json={"username": username, "password": password})
        assert after_disable.status_code == 200

    def test_mfa_enable_rejects_invalid_code(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers)
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.get("/api/auth/mfa/provision", headers=headers)
        resp = client.post("/api/auth/mfa/enable", json={"code": "000000"}, headers=headers)
        assert resp.status_code == 401


class TestObjective6_DisabledAndDeletedUsers:
    def test_disabled_user_cannot_log_in(self, client, admin_headers):
        user_id, username, password = _create_user(client, admin_headers)
        client.post(f"/api/admin/users/{user_id}/disable", headers=admin_headers)
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Account disabled"

    def test_re_enabled_user_can_log_in_again(self, client, admin_headers):
        user_id, username, password = _create_user(client, admin_headers)
        client.post(f"/api/admin/users/{user_id}/disable", headers=admin_headers)
        client.post(f"/api/admin/users/{user_id}/enable", headers=admin_headers)
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200

    def test_deleted_user_cannot_log_in(self, client, admin_headers):
        user_id, username, password = _create_user(client, admin_headers)
        client.delete(f"/api/admin/users/{user_id}", headers=admin_headers)
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 401


class TestPasswordChangeAndReset:
    def test_self_service_change_requires_correct_current_password(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers)
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        wrong = client.post("/api/auth/password/change", headers=headers,
                             json={"current_password": "wrong", "new_password": "newpassword123"})
        assert wrong.status_code == 401

        correct = client.post("/api/auth/password/change", headers=headers,
                               json={"current_password": password, "new_password": "newpassword123"})
        assert correct.status_code == 200

        old_login = client.post("/api/auth/login", json={"username": username, "password": password})
        assert old_login.status_code == 401
        new_login = client.post("/api/auth/login", json={"username": username, "password": "newpassword123"})
        assert new_login.status_code == 200

    def test_admin_reset_password_does_not_require_old_password(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers)
        user_id = next(u["id"] for u in client.get("/api/admin/users", headers=admin_headers).json()
                        if u["username"] == username)

        resp = client.post(f"/api/admin/users/{user_id}/reset-password", headers=admin_headers,
                            json={"new_password": "admin-reset-password-456"})
        assert resp.status_code == 200

        old_login = client.post("/api/auth/login", json={"username": username, "password": password})
        assert old_login.status_code == 401
        new_login = client.post("/api/auth/login",
                                 json={"username": username, "password": "admin-reset-password-456"})
        assert new_login.status_code == 200

    def test_engineer_cannot_reset_another_users_password(self, client, admin_headers):
        victim_id, _, _ = _create_user(client, admin_headers)
        _, eng_username, eng_password = _create_user(client, admin_headers, role="engineer")
        eng_token = client.post("/api/auth/login",
                                 json={"username": eng_username, "password": eng_password}).json()["access_token"]
        resp = client.post(f"/api/admin/users/{victim_id}/reset-password",
                            headers={"Authorization": f"Bearer {eng_token}"},
                            json={"new_password": "hacked"})
        assert resp.status_code == 403

    def test_admin_reset_password_rejects_short_password(self, client, admin_headers):
        user_id, _, _ = _create_user(client, admin_headers)
        resp = client.post(f"/api/admin/users/{user_id}/reset-password", headers=admin_headers,
                            json={"new_password": "short"})
        assert resp.status_code == 400

    def test_self_change_rejects_short_new_password(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers)
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/auth/password/change", headers=headers,
                            json={"current_password": password, "new_password": "short"})
        assert resp.status_code == 400


class TestObjective7_NoSecretExposure:
    def test_user_list_never_exposes_password_hash_or_mfa_secret(self, client, admin_headers):
        resp = client.get("/api/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        for user in resp.json():
            assert "password_hash" not in user
            assert "mfa_secret" not in user
            assert "mfa_last_used_step" not in user

    def test_secret_rotation_fingerprint_is_truncated_not_full_secret(self, client, admin_headers):
        resp = client.post("/api/secrets/rotate/jwt_signing_secret", headers=admin_headers)
        assert resp.status_code == 200  # regression guard for the UUID/string actor-column bug

        config = client.get("/api/config", headers=admin_headers).json()
        fingerprint_entries = [c for c in config if "fingerprint" in c["key"]]
        assert fingerprint_entries
        for entry in fingerprint_entries:
            assert len(str(entry["value"])) < 15  # truncated, never the full secret


class TestIDORAndNotFoundHandling:
    """Every admin_users mutation route (update role, delete, disable,
    enable, reset-password) must return 404 for a nonexistent user_id
    rather than a 500 or silently succeeding — covers the error branches
    that a coverage report flagged as unexercised, and doubles as an IDOR
    guard: probing random UUIDs should never leak whether a row exists via
    a different status code or behavior."""

    def test_update_role_on_nonexistent_user_returns_404(self, client, admin_headers):
        fake_id = str(uuid.uuid4())
        resp = client.patch(f"/api/admin/users/{fake_id}", headers=admin_headers, json={"role": "admin"})
        assert resp.status_code == 404

    def test_delete_nonexistent_user_returns_404(self, client, admin_headers):
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/admin/users/{fake_id}", headers=admin_headers)
        assert resp.status_code == 404

    def test_disable_nonexistent_user_returns_404(self, client, admin_headers):
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/admin/users/{fake_id}/disable", headers=admin_headers)
        assert resp.status_code == 404

    def test_enable_nonexistent_user_returns_404(self, client, admin_headers):
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/admin/users/{fake_id}/enable", headers=admin_headers)
        assert resp.status_code == 404

    def test_reset_password_on_nonexistent_user_returns_404(self, client, admin_headers):
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/admin/users/{fake_id}/reset-password", headers=admin_headers,
                            json={"new_password": "irrelevant123"})
        assert resp.status_code == 404

    def test_create_duplicate_username_returns_409_not_500(self, client, admin_headers):
        _, username, _ = _create_user(client, admin_headers)
        resp = client.post("/api/admin/users", headers=admin_headers,
                            json={"username": username, "password": "whatever123", "role": "viewer"})
        assert resp.status_code == 409


class TestMFAErrorBranches:
    """Covers auth.py's remaining error branches: MFA-required-but-no-secret
    (a defensive fail-closed case that should be unreachable via the normal
    API but is tested directly against the DB state to prove the guard
    actually fires), enable-without-provisioning-first, and disable/change
    password on a since-deleted account."""

    def test_enable_mfa_without_provisioning_first_returns_400(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers)
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/auth/mfa/enable", json={"code": "123456"}, headers=headers)
        assert resp.status_code == 400
        assert "provision" in resp.json()["detail"].lower()

    def test_mfa_enabled_but_secret_missing_fails_closed(self, client, admin_headers):
        """Defensive guard for a state that should be unreachable through
        the normal API (mfa_enabled only ever flips true alongside a
        secret in the same code path) — directly manipulates the DB to
        simulate data corruption/a bad manual migration, and confirms
        login fails closed (500, MFA blocks the login) rather than
        silently treating a corrupted account as MFA-exempt (which would
        be a de-facto MFA bypass)."""
        from app.db.session import SessionLocal
        from app.db.models import User

        _, username, password = _create_user(client, admin_headers)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            user.mfa_enabled = "true"
            user.mfa_secret = None
            db.commit()
        finally:
            db.close()

        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 500  # fails closed, not a silent bypass

    def test_password_change_and_mfa_disable_on_deleted_account(self, client, admin_headers):
        """A JWT issued before account deletion is still cryptographically
        valid until it expires (documented limitation — no session-revocation
        table). This test locks in what actually happens in that window:
        the route's own DB lookup returns 404, not a crash or silent success."""
        user_id, username, password = _create_user(client, admin_headers)
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        client.delete(f"/api/admin/users/{user_id}", headers=admin_headers)

        resp = client.post("/api/auth/password/change", headers=headers,
                            json={"current_password": password, "new_password": "newpassword123"})
        assert resp.status_code == 404

        resp2 = client.post("/api/auth/mfa/disable", headers=headers)
        assert resp2.status_code == 404


class TestTaskOwnershipAndWebSocketAuth:
    """Regression guard for a real vulnerability found live in this
    session: GET /api/tasks/ws/{task_id} had no authentication at all —
    confirmed exploitable by connecting with zero credentials and
    streaming a task's full results. Separately, GET /api/tasks/{task_id}
    (REST polling) had no ownership check either — any authenticated user
    could read any other user's task results by guessing/observing a
    task_id. Both are fixed via workers/task_ownership.py; these tests use
    the REST endpoint (deterministic, no real WebSocket handshake needed
    in a unit-test context) to lock in the ownership semantics that also
    protect the WebSocket path, which shares the same can_access() check."""

    def test_task_owner_can_read_their_own_task_status(self, client, admin_headers):
        submit = client.post("/api/tasks/submit", headers=admin_headers, json={"message": "owner test"})
        task_id = submit.json()["task_id"]
        resp = client.get(f"/api/tasks/{task_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_other_user_cannot_read_someone_elses_task_status(self, client, admin_headers):
        submit = client.post("/api/tasks/submit", headers=admin_headers, json={"message": "victim task"})
        task_id = submit.json()["task_id"]

        _, username, password = _create_user(client, admin_headers, role="viewer")
        other_token = client.post("/api/auth/login",
                                   json={"username": username, "password": password}).json()["access_token"]
        resp = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {other_token}"})
        assert resp.status_code == 404  # not 403 — see api/tasks.py comment on enumeration

    def test_admin_can_read_any_users_task_status(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers, role="viewer")
        user_token = client.post("/api/auth/login",
                                  json={"username": username, "password": password}).json()["access_token"]
        submit = client.post("/api/tasks/submit", headers={"Authorization": f"Bearer {user_token}"},
                              json={"message": "regular user task"})
        task_id = submit.json()["task_id"]
        resp = client.get(f"/api/tasks/{task_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_nonexistent_task_id_for_non_owner_returns_404(self, client, admin_headers):
        _, username, password = _create_user(client, admin_headers, role="viewer")
        token = client.post("/api/auth/login", json={"username": username, "password": password}).json()["access_token"]
        resp = client.get(f"/api/tasks/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_nonexistent_task_id_for_admin_reports_pending_not_an_error(self, client, admin_headers):
        """Admins bypass the ownership check by design (operational need to
        inspect any task). Celery's AsyncResult can't distinguish "this ID
        was never submitted" from "not started yet" without a persistent
        result-backend lookup, so an unknown ID reports PENDING rather than
        404 for an admin caller. This carries no result data and reveals
        nothing about whether any real task exists — not an info leak,
        just a Celery API characteristic worth locking in explicitly
        rather than leaving as an untested assumption."""
        resp = client.get(f"/api/tasks/{uuid.uuid4()}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["state"] == "PENDING"
        assert "result" not in resp.json()

    def test_unauthenticated_request_to_task_status_rejected(self, client):
        resp = client.get(f"/api/tasks/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestWebSocketAuthentication:
    """Automated version of the manual live-exploit verification done in
    this session: FastAPI's TestClient.websocket_connect() runs the ASGI
    WebSocket handler in-process, so these don't need a separately-running
    server on a port the way the original manual proof-of-concept did."""

    def test_connection_without_token_is_rejected(self, client, admin_headers):
        submit = client.post("/api/tasks/submit", headers=admin_headers, json={"message": "ws test"})
        task_id = submit.json()["task_id"]
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/tasks/ws/{task_id}"):
                pass  # should never get here — connection must be rejected

    def test_connection_with_invalid_token_is_rejected(self, client, admin_headers):
        submit = client.post("/api/tasks/submit", headers=admin_headers, json={"message": "ws test"})
        task_id = submit.json()["task_id"]
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/tasks/ws/{task_id}?token=not-a-real-jwt"):
                pass

    def test_connection_with_valid_token_but_wrong_owner_is_rejected(self, client, admin_headers):
        submit = client.post("/api/tasks/submit", headers=admin_headers, json={"message": "ws test"})
        task_id = submit.json()["task_id"]

        _, username, password = _create_user(client, admin_headers, role="viewer")
        other_token = client.post("/api/auth/login",
                                   json={"username": username, "password": password}).json()["access_token"]
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/tasks/ws/{task_id}?token={other_token}"):
                pass

    def test_connection_with_correct_owner_token_succeeds(self, client, admin_headers):
        submit = client.post("/api/tasks/submit", headers=admin_headers, json={"message": "ws test"})
        task_id = submit.json()["task_id"]
        admin_token = admin_headers["Authorization"].split(" ")[1]

        with client.websocket_connect(f"/api/tasks/ws/{task_id}?token={admin_token}") as ws:
            data = ws.receive_json()
            assert data["task_id"] == task_id
            assert data["state"] in ("PENDING", "STARTED", "SUCCESS", "FAILURE")


class TestActorColumnRegressionGuard:
    """Direct regression guard for the UUID-FK-vs-username-string bug found
    live in this session: config_history.changed_by, system_config.updated_by,
    and policy_rules.created_by all crashed on first real write because they
    were typed as UUID foreign keys but every caller passes a username
    string. Fixed via migration 0006_fix_actor_columns_to_string.py."""

    def test_config_update_persists_with_real_username_actor(self, client, admin_headers):
        resp = client.put("/api/config/sandbox.timeout_seconds", headers=admin_headers, json={"value": 60})
        assert resp.status_code == 200

        history = client.get("/api/config/sandbox.timeout_seconds/history", headers=admin_headers).json()
        assert history[0]["changed_by"] == "admin"

    def test_policy_rule_creation_persists_with_real_username_actor(self, client, admin_headers):
        resp = client.post("/api/policy", headers=admin_headers, json={
            "name": f"test-rule-{uuid.uuid4().hex[:8]}",
            "description": "regression guard rule",
            "resource_type": "test_resource",
            "condition": {"field": "x", "op": "eq", "value": "y"},
            "action": "allow",
        })
        assert resp.status_code == 200  # would 500 on the old UUID-typed column
