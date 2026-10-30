"""fix updated_by/changed_by/created_by columns: UUID FK -> username string

These three columns were declared as UUID foreign keys to users.id, but
every real call site (api/config.py, api/policy.py, secrets/rotation.py)
passes a plain username string (from JWT claims, or a system actor name
like "secret-rotation-service" that isn't a real user row at all). This
was never caught before because no prior session ran these code paths
against a live Postgres — the very first live execution of
PUT /api/config/{key} and the JWT-secret rotation task both crashed with
psycopg2.errors.InvalidTextRepresentation. This migration converts the
columns to match the codebase's actual established convention (plain
String username, same as SecretRotationLog.rotated_by / BackupRecord.triggered_by).

Revision ID: 0006_fix_actor_columns_to_string
Revises: 0005_user_is_active
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_fix_actor_columns_to_string"
down_revision = "0005_user_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("system_config_updated_by_fkey", "system_config", type_="foreignkey")
    op.alter_column("system_config", "updated_by", type_=sa.String, postgresql_using="updated_by::text")

    op.drop_constraint("config_history_changed_by_fkey", "config_history", type_="foreignkey")
    op.alter_column("config_history", "changed_by", type_=sa.String, postgresql_using="changed_by::text")

    op.drop_constraint("policy_rules_created_by_fkey", "policy_rules", type_="foreignkey")
    op.alter_column("policy_rules", "created_by", type_=sa.String, postgresql_using="created_by::text")


def downgrade() -> None:
    # Downgrade path is lossy if any non-UUID username strings were
    # written while on the String schema (expected — that's the whole
    # point of this migration) — those rows' actor columns are set NULL
    # rather than failing the downgrade outright.
    op.execute("UPDATE system_config SET updated_by = NULL WHERE updated_by !~ "
               "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'")
    op.alter_column("system_config", "updated_by", type_=sa.dialects.postgresql.UUID(as_uuid=False),
                     postgresql_using="updated_by::uuid")
    op.create_foreign_key("system_config_updated_by_fkey", "system_config", "users", ["updated_by"], ["id"])

    op.execute("UPDATE config_history SET changed_by = NULL WHERE changed_by !~ "
               "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'")
    op.alter_column("config_history", "changed_by", type_=sa.dialects.postgresql.UUID(as_uuid=False),
                     postgresql_using="changed_by::uuid")
    op.create_foreign_key("config_history_changed_by_fkey", "config_history", "users", ["changed_by"], ["id"])

    op.execute("UPDATE policy_rules SET created_by = NULL WHERE created_by !~ "
               "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'")
    op.alter_column("policy_rules", "created_by", type_=sa.dialects.postgresql.UUID(as_uuid=False),
                     postgresql_using="created_by::uuid")
    op.create_foreign_key("policy_rules_created_by_fkey", "policy_rules", "users", ["created_by"], ["id"])
