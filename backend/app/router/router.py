"""
Intelligent Model Router: classifies incoming requests by task type / modality /
complexity, then selects a registered model backend per routing_table.yaml.
"""
from __future__ import annotations

import time
import yaml

from pathlib import Path
from dataclasses import dataclass

from .base import (
    ModelBackend,
    OllamaBackend,
    Modality,
    GenerationRequest,
    GenerationResult,
)


TABLE_PATH = Path(__file__).parent / "routing_table.yaml"
UNHEALTHY_COOLDOWN_SECONDS = 30


_TASK_KEYWORDS = {
    "coding": [
        "write code",
        "function",
        "class ",
        "debug",
        "stack trace",
        "script",
        "implement",
    ],
    "vision": [
        "diagram",
        "drawing",
        "p&id",
        "image",
        "photo",
        "layout",
    ],
    "summarization": [
        "summarize",
        "summary",
        "tl;dr",
    ],
    "approval_note": [
        "approval note",
        "sign-off",
        "sign off",
    ],
    "reasoning": [
        "why",
        "analyze",
        "explain the trade-off",
        "compare",
    ],
}


@dataclass
class RoutingDecision:
    task_type: str
    model_name: str
    modality: Modality


class ModelPool:
    """Round-robin, failover-aware pool of model backends."""

    def __init__(self, backends: list[ModelBackend]):
        self.backends = backends
        self._index = 0
        self._unhealthy_until: dict[int, float] = {}

    def _is_healthy(self, idx: int) -> bool:
        expiry = self._unhealthy_until.get(idx)
        return expiry is None or time.time() >= expiry

    def _mark_unhealthy(self, idx: int) -> None:
        self._unhealthy_until[idx] = (
            time.time() + UNHEALTHY_COOLDOWN_SECONDS
        )

    def _mark_healthy(self, idx: int) -> None:
        self._unhealthy_until.pop(idx, None)

    def _ordered_candidates(self) -> list[int]:
        n = len(self.backends)

        if n == 0:
            return []

        order = [
            (self._index + i) % n
            for i in range(n)
        ]

        self._index = (self._index + 1) % n

        healthy = [
            i for i in order
            if self._is_healthy(i)
        ]

        unhealthy = [
            i for i in order
            if not self._is_healthy(i)
        ]

        return healthy + unhealthy

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:

        from ..observability.metrics import model_requests_total

        last_error: Exception | None = None

        for idx in self._ordered_candidates():

            backend = self.backends[idx]

            try:
                result = await backend.generate(request)

                self._mark_healthy(idx)

                model_requests_total.labels(
                    model_name=backend.name,
                    status="success",
                ).inc()

                return result

            except Exception as exc:

                last_error = exc

                self._mark_unhealthy(idx)

                model_requests_total.labels(
                    model_name=backend.name,
                    status="error",
                ).inc()

                continue

        raise RuntimeError(
            f"All {len(self.backends)} replica(s) failed for this model pool. "
            f"Last error: {last_error}"
        )

    async def health_report(self) -> list[dict]:
        results = []

        for idx, backend in enumerate(self.backends):

            online = await backend.health()

            results.append({
                "endpoint": getattr(
                    backend,
                    "base_url",
                    "unknown",
                ),
                "online": online,
                "in_cooldown": not self._is_healthy(idx),
            })

        return results


class ModelRouter:

    def __init__(
        self,
        table_path: Path = TABLE_PATH,
    ):

        with open(table_path, encoding="utf-8") as f:
            self.table = yaml.safe_load(f)

        self._pools: dict[str, ModelPool] = {}

        for model_name, cfg in self.table["models"].items():

            if cfg["backend"] != "ollama":
                continue

            endpoints = (
                cfg.get("endpoints")
                or [cfg["base_url"]]
            )

            # Exact model name installed in Ollama.
            # If ollama_model is not specified,
            # use the logical model name.
            ollama_model = cfg.get(
                "ollama_model",
                model_name,
            )

            backends = [
                OllamaBackend(
                    name=ollama_model,
                    base_url=url,
                    modality=Modality(
                        cfg["modality"]
                    ),
                )
                for url in endpoints
            ]

            self._pools[model_name] = ModelPool(
                backends
            )

        # Backward compatibility for existing callers.
        self._backends: dict[str, ModelBackend] = {
            name: pool.backends[0]
            for name, pool in self._pools.items()
            if pool.backends
        }

    def classify_task(
        self,
        prompt: str,
        explicit_modality: str | None = None,
    ) -> str:

        text = prompt.lower()

        # Important for Coding Workspace.
        if explicit_modality == "code":
            return "coding"

        if explicit_modality == "vision":
            return "vision"

        for task, keywords in _TASK_KEYWORDS.items():

            if any(
                keyword in text
                for keyword in keywords
            ):
                return task

        return "reasoning"

    def route(
        self,
        prompt: str,
        explicit_modality: str | None = None,
    ) -> RoutingDecision:

        task_type = self.classify_task(
            prompt,
            explicit_modality,
        )

        model_name = self.table[
            "task_routing"
        ].get(
            task_type,
            "llama3.1",
        )

        modality = Modality(
            self.table["models"][model_name][
                "modality"
            ]
        )

        return RoutingDecision(
            task_type=task_type,
            model_name=model_name,
            modality=modality,
        )

    async def generate(
        self,
        prompt: str,
        explicit_modality: str | None = None,
        image_b64: str | None = None,
    ) -> GenerationResult:

        decision = self.route(
            prompt,
            explicit_modality,
        )

        pool = self._pools[
            decision.model_name
        ]

        request = GenerationRequest(
            prompt=prompt,
            modality=decision.modality,
            image_b64=image_b64,
        )

        try:
            return await pool.generate(request)

        except RuntimeError:

            # Try another model with the same modality.
            for fallback_name, fallback_pool in self._pools.items():

                if fallback_name == decision.model_name:
                    continue

                fallback_modality = Modality(
                    self.table["models"][fallback_name][
                        "modality"
                    ]
                )

                if fallback_modality != decision.modality:
                    continue

                try:
                    return await fallback_pool.generate(
                        request
                    )

                except RuntimeError:
                    continue

            raise

    async def pool_health(self) -> dict[str, list[dict]]:

        return {
            name: await pool.health_report()
            for name, pool in self._pools.items()
        }


router = ModelRouter()