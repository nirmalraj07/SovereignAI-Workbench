"""
Tests for the distributed-execution-safety changes: Orchestrator's
context["upstream"] propagation, ResearchAgent/CodingAgent reading from
upstream results instead of relying on shared-memory mutation, and
DistributedOrchestrator's queue routing table.
Run: pytest backend/tests/test_distributed_agents.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch, AsyncMock

from app.agents.base import Orchestrator, TaskGraph, TaskNode, BaseAgent
from app.agents.distributed import queue_for_agent, AGENT_QUEUE_MAP, DEFAULT_QUEUE


class EchoAgent(BaseAgent):
    name = "echo"

    async def run(self, instruction: str, context: dict):
        return {"echoed": instruction, "saw_upstream": dict(context.get("upstream", {}))}


class TestUpstreamContextPropagation:
    @pytest.mark.asyncio
    async def test_completed_node_result_appears_in_upstream_for_dependents(self):
        graph = TaskGraph(request_text="test", nodes=[
            TaskNode("a", "echo", "first"),
            TaskNode("b", "echo", "second", depends_on=["a"]),
        ])
        orchestrator = Orchestrator({"echo": EchoAgent()})
        context = {}
        result_graph = await orchestrator.execute(graph, context)

        node_b = result_graph.get("b")
        assert node_b.status == "done"
        assert node_b.result["saw_upstream"]["a"] == {"echoed": "first", "saw_upstream": {}}

    @pytest.mark.asyncio
    async def test_upstream_accumulates_across_multiple_dependencies(self):
        graph = TaskGraph(request_text="test", nodes=[
            TaskNode("a", "echo", "first"),
            TaskNode("b", "echo", "second"),
            TaskNode("c", "echo", "third", depends_on=["a", "b"]),
        ])
        orchestrator = Orchestrator({"echo": EchoAgent()})
        context = {}
        result_graph = await orchestrator.execute(graph, context)

        node_c = result_graph.get("c")
        assert set(node_c.result["saw_upstream"].keys()) == {"a", "b"}


class TestKnowledgeBaseToResearchHandoff:
    @pytest.mark.asyncio
    async def test_research_agent_grounds_from_upstream_retrieved_chunks(self):
        from app.agents.specialists import ResearchAgent

        fake_router_result = type("R", (), {"text": "grounded answer", "model_used": "llama3.1",
                                              "tokens_generated": 5, "latency_ms": 1.0})()
        agent = ResearchAgent()
        context = {
            "upstream": {
                "kb_query": {
                    "retrieved_chunks": [
                        {"filename": "sop-101.pdf", "page": 3, "score": 0.9,
                         "document_id": "doc-1", "text": "Inspect valve every 6 months."}
                    ],
                    "count": 1,
                }
            }
        }
        with patch("app.agents.specialists.router.generate", new=AsyncMock(return_value=fake_router_result)):
            result = await agent.run("How often should the valve be inspected?", context)

        assert result["answer"] == "grounded answer"
        assert result["citations"][0]["source"] == "sop-101.pdf"
        assert result["citations"][0]["page"] == 3

    @pytest.mark.asyncio
    async def test_research_agent_falls_back_to_legacy_kb_chunks_when_no_upstream(self):
        from app.agents.specialists import ResearchAgent
        from app.rag.pipeline import RetrievedChunk

        fake_router_result = type("R", (), {"text": "answer", "model_used": "llama3.1",
                                              "tokens_generated": 5, "latency_ms": 1.0})()
        agent = ResearchAgent()
        legacy_chunk = RetrievedChunk(text="legacy grounding", document_id="d1",
                                       filename="legacy.pdf", page=1, score=0.8)
        context = {"kb_chunks": [legacy_chunk]}

        with patch("app.agents.specialists.router.generate", new=AsyncMock(return_value=fake_router_result)):
            result = await agent.run("question", context)

        assert result["citations"][0]["source"] == "legacy.pdf"


class TestCodingAgentStageDetection:
    @pytest.mark.asyncio
    async def test_no_upstream_and_no_code_means_generate_stage(self):
        from app.agents.specialists import CodingAgent

        fake_result = type("R", (), {"text": "print(1)", "model_used": "deepseek-coder",
                                      "tokens_generated": 3, "latency_ms": 1.0})()
        agent = CodingAgent()
        with patch("app.agents.specialists.router.generate", new=AsyncMock(return_value=fake_result)):
            result = await agent.run("write a script", {})
        assert result["stage"] == "generated"
        assert result["code"] == "print(1)"

    @pytest.mark.asyncio
    async def test_upstream_code_gen_result_triggers_execute_stage(self):
        from app.agents.specialists import CodingAgent

        fake_exec = type("E", (), {"stdout": "1\n", "stderr": "", "exit_code": 0,
                                    "duration_ms": 5.0, "timed_out": False})()
        agent = CodingAgent()
        context = {"upstream": {"code_gen": {"code": "print(1)", "model_used": "deepseek-coder"}}}

        with patch("app.agents.specialists.sandbox.execute_with_repair",
                   new=AsyncMock(return_value=(fake_exec, "print(1)", 1))):
            result = await agent.run("run it", context)

        assert result["success"] is True
        assert result["stdout"] == "1\n"

    @pytest.mark.asyncio
    async def test_upstream_final_code_from_execute_node_used_by_fix_node(self):
        """The 'fix' node depends on 'execute', whose result key is
        final_code (not code) — CodingAgent must recognize both."""
        from app.agents.specialists import CodingAgent

        fake_exec = type("E", (), {"stdout": "", "stderr": "", "exit_code": 0,
                                    "duration_ms": 5.0, "timed_out": False})()
        agent = CodingAgent()
        context = {"upstream": {"execute": {"final_code": "print(2)", "success": True}}}

        with patch("app.agents.specialists.sandbox.execute_with_repair",
                   new=AsyncMock(return_value=(fake_exec, "print(2)", 1))) as mock_exec:
            await agent.run("re-run", context)

        called_code = mock_exec.call_args[0][0]
        assert called_code == "print(2)"


class TestQueueRouting:
    def test_gpu_bound_agents_route_to_gpu_queue(self):
        for agent_name in ("coding", "vision", "ocr"):
            assert queue_for_agent(agent_name) == "gpu_queue"

    def test_io_bound_agents_route_to_io_queue(self):
        for agent_name in ("knowledge_base", "document", "spreadsheet", "presentation",
                            "reporting", "approval_note"):
            assert queue_for_agent(agent_name) == "io_queue"

    def test_cpu_light_agents_route_to_cpu_queue(self):
        for agent_name in ("research", "validation", "calculation", "monitoring"):
            assert queue_for_agent(agent_name) == "cpu_queue"

    def test_unknown_agent_falls_back_to_default_queue(self):
        assert queue_for_agent("some_future_plugin_agent") == DEFAULT_QUEUE

    def test_every_built_in_agent_has_an_explicit_mapping(self):
        # Guards against silently defaulting a new built-in agent to
        # cpu_queue when it should really be gpu_queue or io_queue.
        built_in_agents = {
            "research", "knowledge_base", "coding", "ocr", "vision", "document",
            "spreadsheet", "presentation", "calculation", "validation",
            "reporting", "approval_note", "monitoring",
        }
        assert built_in_agents <= set(AGENT_QUEUE_MAP.keys())
