"""
Central configuration. Fails fast (refuses to boot) if any setting implies
an external network dependency — this is the enforcement point for the
"zero external API calls" requirement.
"""
from pydantic_settings import BaseSettings
from typing import List


ALLOWED_HOST_PATTERNS = ("localhost", "127.0.0.1", "0.0.0.0", "postgres", "chromadb",
                          "model-runtime", "backend", "frontend", "redis")


class Settings(BaseSettings):
    app_name: str = "SovereignAI Workbench"
    environment: str = "on-prem"

    # Internal-only service URLs. Any hostname outside ALLOWED_HOST_PATTERNS
    # (i.e. anything that looks like a public domain) triggers a boot-time refusal.
    database_url: str = "postgresql://sovereign:sovereign@postgres:5432/sovereignai"
    chroma_url: str = "http://chromadb:8000"
    model_runtime_url: str = "http://model-runtime:11434"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "CHANGE_ME_AT_DEPLOY_TIME"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    sandbox_network_mode: str = "none"     # containers get NO network by default
    sandbox_cpu_limit: str = "1.0"
    sandbox_mem_limit: str = "512m"
    sandbox_timeout_seconds: int = 30

    cors_allow_origins: List[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"


def _assert_no_external_egress(settings: "Settings") -> None:
    for url in (settings.database_url, settings.chroma_url, settings.model_runtime_url, settings.redis_url):
        # Strip scheme, then credentials (user:pass@), then path, then port —
        # order matters: splitting on ":" before "@" truncates at the
        # password's colon and silently extracts the wrong segment.
        authority = url.split("://")[-1].split("/")[0]
        host = authority.split("@")[-1].split(":")[0]
        if not any(host == pattern or host.endswith(f".{pattern}") for pattern in ALLOWED_HOST_PATTERNS):
            raise RuntimeError(
                f"Refusing to start: configured host '{host}' is not in the on-prem "
                f"allowlist {ALLOWED_HOST_PATTERNS}. SovereignAI Workbench must not be "
                f"pointed at any external/cloud endpoint."
            )


settings = Settings()
_assert_no_external_egress(settings)
