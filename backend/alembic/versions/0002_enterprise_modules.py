"""enterprise modules: config, secrets, backup, policy, tenancy, plugins, updates

Revision ID: 0002_enterprise_modules
Revises: 0001_initial
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_enterprise_modules"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String, unique=True, nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("category", sa.String, server_default="general"),
        sa.Column("description", sa.Text),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("version", sa.Integer, server_default="1"),
    )
    op.create_index("ix_system_config_key", "system_config", ["key"])
    op.create_index("ix_system_config_category", "system_config", ["category"])

    op.create_table(
        "config_history",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("old_value", sa.JSON),
        sa.Column("new_value", sa.JSON),
        sa.Column("changed_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("changed_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_config_history_key", "config_history", ["key"])

    op.create_table(
        "secret_rotation_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("secret_name", sa.String, nullable=False),
        sa.Column("rotated_by", sa.String),
        sa.Column("status", sa.String),
        sa.Column("detail", sa.Text),
        sa.Column("rotated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("next_rotation_due", sa.DateTime),
    )
    op.create_index("ix_secret_rotation_log_secret_name", "secret_rotation_log", ["secret_name"])

    op.create_table(
        "backup_records",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("backup_type", sa.String),
        sa.Column("file_path", sa.String),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("checksum", sa.String),
        sa.Column("status", sa.String, server_default="completed"),
        sa.Column("triggered_by", sa.String),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_backup_records_created_at", "backup_records", ["created_at"])

    op.create_table(
        "policy_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("resource_type", sa.String),
        sa.Column("condition", sa.JSON),
        sa.Column("action", sa.String),
        sa.Column("enabled", sa.String, server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_policy_rules_resource_type", "policy_rules", ["resource_type"])

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
        sa.Column("slug", sa.String, unique=True, nullable=False),
        sa.Column("classification_default", sa.String, server_default="internal"),
        sa.Column("active", sa.String, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "plugins",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
        sa.Column("version", sa.String),
        sa.Column("entry_point", sa.String),
        sa.Column("enabled", sa.String, server_default="true"),
        sa.Column("installed_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("manifest", sa.JSON),
    )

    op.create_table(
        "update_packages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("checksum", sa.String, nullable=False),
        sa.Column("applied", sa.String, server_default="false"),
        sa.Column("applied_at", sa.DateTime),
        sa.Column("notes", sa.Text),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now()),
    )

    # tenant_id added to core content tables for isolation (nullable — NULL
    # means "shared/global", matching a single-tenant deployment by default)
    op.add_column("documents", sa.Column("tenant_id", postgresql.UUID(as_uuid=False),
                                          sa.ForeignKey("tenants.id"), nullable=True))
    op.add_column("tasks", sa.Column("tenant_id", postgresql.UUID(as_uuid=False),
                                      sa.ForeignKey("tenants.id"), nullable=True))
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_tasks_tenant_id", "tasks", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_tenant_id", table_name="tasks")
    op.drop_index("ix_documents_tenant_id", table_name="documents")
    op.drop_column("tasks", "tenant_id")
    op.drop_column("documents", "tenant_id")
    op.drop_table("update_packages")
    op.drop_table("plugins")
    op.drop_table("tenants")
    op.drop_table("policy_rules")
    op.drop_table("backup_records")
    op.drop_table("secret_rotation_log")
    op.drop_table("config_history")
    op.drop_table("system_config")
