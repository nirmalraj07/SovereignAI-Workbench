"""
Plug-and-play model backend interface. Any new open-weight model is added by
implementing this interface and registering it in routing_table.yaml — no
changes to router or agent code required.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Modality(str, Enum):
    TEXT = "text"
    VISION = "vision"
    CODE = "code"


@dataclass
class GenerationRequest:
    prompt: str
    modality: Modality = Modality.TEXT
    image_b64: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.2


@dataclass
class GenerationResult:
    text: str
    model_used: str
    tokens_generated: int
    latency_ms: float


class ModelBackend(ABC):
    """Every local model runtime (Ollama, vLLM, TGI, ...) implements this."""

    name: str
    modality: Modality

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        ...

    @abstractmethod
    async def health(self) -> bool:
        ...


class OllamaBackend(ModelBackend):
    """Example adapter — talks to a local Ollama instance, LAN-only."""

    def __init__(self, name: str, base_url: str, modality: Modality = Modality.TEXT):
        self.name = name
        self.base_url = base_url  # must be validated against ALLOWED_HOST_PATTERNS
        self.modality = modality

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        import time
        import httpx

        start = time.time()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.name,
                    "prompt": request.prompt,
                    "options": {"temperature": request.temperature},
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return GenerationResult(
            text=data.get("response", ""),
            model_used=self.name,
            tokens_generated=data.get("eval_count", 0),
            latency_ms=(time.time() - start) * 1000,
        )

    async def health(self) -> bool:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
