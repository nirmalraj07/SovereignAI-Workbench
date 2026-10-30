"""add is_active for soft-disable (distinct from delete)

Revision ID: 0005_user_is_active
Revises: 0004_mfa_replay_protection
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_user_is_active"
down_revision = "0004_mfa_replay_protection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_active", sa.String, server_default="true"))


def downgrade() -> None:
    op.drop_column("users", "is_active")
