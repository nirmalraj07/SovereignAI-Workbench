"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("username", sa.String, unique=True, nullable=False),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("token", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("source_type", sa.String),
        sa.Column("classification", sa.String, server_default="internal"),
        sa.Column("ingested_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("ingested_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("checksum", sa.String),
    )
    op.create_index("ix_documents_classification", "documents", ["classification"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id")),
        sa.Column("chunk_text", sa.Text),
        sa.Column("embedding_ref", sa.String),
        sa.Column("page", sa.Integer),
        sa.Column("offset", sa.Integer),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    op.create_table(
        "kb_queries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("query_text", sa.Text),
        sa.Column("retrieved_chunk_ids", sa.JSON),
        sa.Column("answer", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("request_text", sa.Text),
        sa.Column("plan_json", sa.JSON),
        sa.Column("status", sa.String, server_default="pending"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id")),
        sa.Column("agent_name", sa.String),
        sa.Column("input", sa.Text),
        sa.Column("output", sa.Text),
        sa.Column("model_used", sa.String),
        sa.Column("status", sa.String),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime),
    )
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])

    op.create_table(
        "sandbox_executions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id")),
        sa.Column("language", sa.String),
        sa.Column("code", sa.Text),
        sa.Column("stdout", sa.Text),
        sa.Column("stderr", sa.Text),
        sa.Column("exit_code", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String),
        sa.Column("resource", sa.String),
        sa.Column("ip", sa.String),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])

    op.create_table(
        "model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String, unique=True),
        sa.Column("backend_type", sa.String),
        sa.Column("endpoint", sa.String),
        sa.Column("modality", sa.String),
        sa.Column("status", sa.String, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_table("model_registry")
    op.drop_table("audit_log")
    op.drop_table("sandbox_executions")
    op.drop_table("agent_runs")
    op.drop_table("tasks")
    op.drop_table("kb_queries")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("sessions")
    op.drop_table("users")
