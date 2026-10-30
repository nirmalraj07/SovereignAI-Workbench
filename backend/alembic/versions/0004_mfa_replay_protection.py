"""add mfa_last_used_step for TOTP replay protection

Revision ID: 0004_mfa_replay_protection
Revises: 0003_user_mfa_and_seed
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_mfa_replay_protection"
down_revision = "0003_user_mfa_and_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_last_used_step", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "mfa_last_used_step")
