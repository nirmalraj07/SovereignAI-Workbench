"""
Tests for the Model Failover / Multi-GPU Scheduling logic in
app/router/router.py's ModelPool. Uses fake backends (no real Ollama
needed) to deterministically exercise round-robin selection, failover on
error, and cooldown-based recovery.
Run: pytest backend/tests/test_router_ha.py -v
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.router.router import ModelPool
from app.router.base import ModelBackend, Modality, GenerationRequest, GenerationResult


class FakeBackend(ModelBackend):
    def __init__(self, name: str, base_url: str, fail: bool = False, modality=Modality.TEXT):
        self.name = name
        self.base_url = base_url
        self.modality = modality
        self.fail = fail
        self.call_count = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.call_count += 1
        if self.fail:
            raise ConnectionError(f"{self.base_url} is down")
        return GenerationResult(text=f"response from {self.base_url}", model_used=self.name,
                                 tokens_generated=1, latency_ms=1.0)

    async def health(self) -> bool:
        return not self.fail


@pytest.fixture
def request_obj():
    return GenerationRequest(prompt="hello")


class TestRoundRobin:
    @pytest.mark.asyncio
    async def test_distributes_across_healthy_replicas(self, request_obj):
        b1 = FakeBackend("m", "http://gpu0")
        b2 = FakeBackend("m", "http://gpu1")
        pool = ModelPool([b1, b2])

        results = [await pool.generate(request_obj) for _ in range(4)]
        urls_hit = [r.text for r in results]
        assert "response from http://gpu0" in urls_hit
        assert "response from http://gpu1" in urls_hit
        # Roughly even distribution over 4 calls across 2 replicas
        assert b1.call_count == 2
        assert b2.call_count == 2


class TestFailover:
    @pytest.mark.asyncio
    async def test_failover_to_healthy_replica_when_one_errors(self, request_obj):
        bad = FakeBackend("m", "http://gpu0", fail=True)
        good = FakeBackend("m", "http://gpu1", fail=False)
        pool = ModelPool([bad, good])

        result = await pool.generate(request_obj)
        assert "gpu1" in result.text

    @pytest.mark.asyncio
    async def test_all_replicas_down_raises_with_context(self, request_obj):
        bad1 = FakeBackend("m", "http://gpu0", fail=True)
        bad2 = FakeBackend("m", "http://gpu1", fail=True)
        pool = ModelPool([bad1, bad2])

        with pytest.raises(RuntimeError, match="All 2 replica"):
            await pool.generate(request_obj)

    @pytest.mark.asyncio
    async def test_failed_replica_is_skipped_on_subsequent_calls_within_cooldown(self, request_obj):
        bad = FakeBackend("m", "http://gpu0", fail=True)
        good = FakeBackend("m", "http://gpu1", fail=False)
        pool = ModelPool([bad, good])

        await pool.generate(request_obj)  # bad fails, good serves, bad marked unhealthy
        await pool.generate(request_obj)  # bad should be skipped due to cooldown

        # good should have served both calls; bad should not have been
        # retried a second time while in cooldown
        assert good.call_count == 2
        assert bad.call_count == 1

    @pytest.mark.asyncio
    async def test_recovered_replica_rejoins_after_cooldown_expires(self, request_obj, monkeypatch):
        bad = FakeBackend("m", "http://gpu0", fail=True)
        good = FakeBackend("m", "http://gpu1", fail=False)
        pool = ModelPool([bad, good])

        await pool.generate(request_obj)  # marks gpu0 unhealthy
        assert not pool._is_healthy(0)

        # Simulate cooldown expiry by monkeypatching time.time() forward
        import app.router.router as router_module
        real_time = time.time
        monkeypatch.setattr(router_module.time, "time", lambda: real_time() + 999)
        assert pool._is_healthy(0)  # cooldown window has passed

    @pytest.mark.asyncio
    async def test_successful_call_clears_unhealthy_marker(self, request_obj):
        flaky = FakeBackend("m", "http://gpu0", fail=True)
        pool = ModelPool([flaky])
        with pytest.raises(RuntimeError):
            await pool.generate(request_obj)
        assert not pool._is_healthy(0)

        flaky.fail = False  # simulate recovery
        # Force past cooldown so the retry attempt actually reaches the backend
        pool._unhealthy_until[0] = 0
        await pool.generate(request_obj)
        assert pool._is_healthy(0)


class TestHealthReport:
    @pytest.mark.asyncio
    async def test_health_report_reflects_backend_and_cooldown_state(self, request_obj):
        bad = FakeBackend("m", "http://gpu0", fail=True)
        good = FakeBackend("m", "http://gpu1", fail=False)
        pool = ModelPool([bad, good])
        await pool.generate(request_obj)  # trips gpu0 into cooldown

        report = await pool.health_report()
        by_url = {r["endpoint"]: r for r in report}
        assert by_url["http://gpu0"]["online"] is False
        assert by_url["http://gpu0"]["in_cooldown"] is True
        assert by_url["http://gpu1"]["online"] is True
        assert by_url["http://gpu1"]["in_cooldown"] is False
