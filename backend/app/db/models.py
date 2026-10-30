import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")  # admin|engineer|viewer|auditor
    is_active = Column(String, default="true")  # "true"/"false" — soft-disable, distinct from delete (preserves audit trail / FK references)
    mfa_secret = Column(String, nullable=True)
    mfa_enabled = Column(String, default="false")  # "true"/"false" — string for consistency with Tenant.active etc.
    mfa_last_used_step = Column(Integer, nullable=True)  # TOTP replay protection — see security/mfa.py
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    token = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    filename = Column(String, nullable=False)
    source_type = Column(String)  # pdf|docx|txt|image|scan
    classification = Column(String, default="internal")
    ingested_by = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    ingested_at = Column(DateTime, default=datetime.utcnow)
    checksum = Column(String)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"))
    chunk_text = Column(Text)
    embedding_ref = Column(String)  # id into ChromaDB collection
    page = Column(Integer)
    offset = Column(Integer)


class KBQuery(Base):
    __tablename__ = "kb_queries"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    query_text = Column(Text)
    retrieved_chunk_ids = Column(JSON)
    answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    request_text = Column(Text)
    plan_json = Column(JSON)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    task_id = Column(UUID(as_uuid=False), ForeignKey("tasks.id"))
    agent_name = Column(String)
    input = Column(Text)
    output = Column(Text)
    model_used = Column(String)
    status = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)


class SandboxExecution(Base):
    __tablename__ = "sandbox_executions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    task_id = Column(UUID(as_uuid=False), ForeignKey("tasks.id"))
    language = Column(String)
    code = Column(Text)
    stdout = Column(Text)
    stderr = Column(Text)
    exit_code = Column(Integer)
    duration_ms = Column(Integer)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"))
    action = Column(String)
    resource = Column(String)
    ip = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, unique=True)
    backend_type = Column(String)
    endpoint = Column(String)
    modality = Column(String)
    status = Column(String, default="unknown")


class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    key = Column(String, unique=True, nullable=False)
    value = Column(JSON, nullable=False)
    category = Column(String, default="general")
    description = Column(Text)
    updated_by = Column(String, nullable=True)  # username string, not a users.id FK — matches
                                                  # SecretRotationLog.rotated_by/BackupRecord.triggered_by
                                                  # convention; callers pass admin["username"] from the
                                                  # JWT, and system actors like "secret-rotation-service"
                                                  # are not real user rows either. A UUID FK here crashed
                                                  # in production against real Postgres — found live.
    updated_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)


class ConfigHistory(Base):
    __tablename__ = "config_history"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    key = Column(String, nullable=False)
    old_value = Column(JSON)
    new_value = Column(JSON)
    changed_by = Column(String, nullable=True)  # username string — see updated_by comment above
    changed_at = Column(DateTime, default=datetime.utcnow)


class SecretRotationLog(Base):
    __tablename__ = "secret_rotation_log"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    secret_name = Column(String, nullable=False)
    rotated_by = Column(String)  # "scheduler" or username
    status = Column(String)  # success | failed
    detail = Column(Text)
    rotated_at = Column(DateTime, default=datetime.utcnow)
    next_rotation_due = Column(DateTime)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    backup_type = Column(String)  # postgres | chromadb | full
    file_path = Column(String)
    size_bytes = Column(Integer)
    checksum = Column(String)
    status = Column(String, default="completed")
    triggered_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    resource_type = Column(String)  # e.g. "document", "code_execution", "file_generation"
    condition = Column(JSON)  # structured rule, e.g. {"field": "classification", "op": "eq", "value": "restricted"}
    action = Column(String)  # allow | deny | require_approval
    enabled = Column(String, default="true")
    created_by = Column(String, nullable=True)  # username string — see SystemConfig.updated_by comment
    created_at = Column(DateTime, default=datetime.utcnow)


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, unique=True, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    classification_default = Column(String, default="internal")
    active = Column(String, default="true")
    created_at = Column(DateTime, default=datetime.utcnow)


class PluginRecord(Base):
    __tablename__ = "plugins"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, unique=True, nullable=False)
    version = Column(String)
    entry_point = Column(String)
    enabled = Column(String, default="true")
    installed_at = Column(DateTime, default=datetime.utcnow)
    manifest = Column(JSON)


class UpdatePackageRecord(Base):
    __tablename__ = "update_packages"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    version = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    applied = Column(String, default="false")
    applied_at = Column(DateTime)
    notes = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
