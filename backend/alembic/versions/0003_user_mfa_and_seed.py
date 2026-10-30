"""add mfa fields to users, seed bootstrap admin

Revision ID: 0003_user_mfa_and_seed
Revises: 0002_enterprise_modules
Create Date: 2026-08-29
"""
import uuid
from alembic import op
import sqlalchemy as sa
from passlib.hash import bcrypt

revision = "0003_user_mfa_and_seed"
down_revision = "0002_enterprise_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret", sa.String, nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.String, server_default="false"))

    # Seed a bootstrap admin so a fresh deployment has a way in. MFA starts
    # disabled — docs/DEPLOYMENT.md "Initial hardening" instructs the
    # operator to change this password and enroll MFA immediately via
    # POST /api/auth/mfa/provision (self-service, authenticated) as the
    # very first action after first login. Skipped if a users table
    # already has rows (idempotent re-run / already-bootstrapped deployment).
    conn = op.get_bind()
    existing = conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
    if existing == 0:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, username, password_hash, role, mfa_enabled, created_at) "
                "VALUES (:id, :username, :password_hash, :role, :mfa_enabled, now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "username": "admin",
                "password_hash": bcrypt.hash("nirmalraj"),
                "role": "admin",
                "mfa_enabled": "false",
            },
        )


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
