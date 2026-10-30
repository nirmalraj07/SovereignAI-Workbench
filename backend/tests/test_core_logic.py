"""
Unit tests requiring no external services (Postgres/Chroma/Ollama) — pure
logic tests for chunking, routing classification, and RBAC hierarchy.
Run: pytest backend/tests -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.pipeline import chunk_text  # noqa: E402
from app.router.router import ModelRouter  # noqa: E402
from app.security.auth import ROLE_HIERARCHY  # noqa: E402
from app.agents.base import PlanningAgent, TaskGraph, TaskNode  # noqa: E402


class TestChunking:
    def test_empty_text_returns_no_chunks(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        text = "one two three four five"
        chunks = chunk_text(text, chunk_size=800, overlap=150)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_overlaps_correctly(self):
        words = [f"word{i}" for i in range(2000)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=800, overlap=150)
        assert len(chunks) > 1
        # verify overlap: last 150 words of chunk 0 should appear at the
        # start of chunk 1
        chunk0_words = chunks[0].split()
        chunk1_words = chunks[1].split()
        assert chunk0_words[-150:] == chunk1_words[:150]


class TestModelRouterClassification:
    def setup_method(self):
        self.router = ModelRouter()

    def test_classifies_coding_task(self):
        decision = self.router.route("Write code to reverse a linked list")
        assert decision.task_type == "coding"
        assert decision.model_name == "deepseek-coder"

    def test_classifies_vision_task_by_modality_override(self):
        decision = self.router.route("What is this?", explicit_modality="vision")
        assert decision.task_type == "vision"
        assert decision.model_name == "qwen2.5-vl"

    def test_classifies_summarization(self):
        decision = self.router.route("Please summarize this SOP document")
        assert decision.task_type == "summarization"
        assert decision.model_name == "llama3.1"

    def test_falls_back_to_reasoning(self):
        decision = self.router.route("What is the meaning of process safety culture?")
        assert decision.task_type == "reasoning"


class TestRBACHierarchy:
    def test_admin_outranks_all(self):
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["engineer"]
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["auditor"]
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["viewer"]

    def test_viewer_is_lowest(self):
        assert ROLE_HIERARCHY["viewer"] == min(ROLE_HIERARCHY.values())


class TestPlanningAgentGraphs:
    async def _plan(self, instruction: str) -> TaskGraph:
        return await PlanningAgent().run(instruction, context={})

    def test_inspection_report_produces_ocr_to_export_chain(self):
        import asyncio
        graph = asyncio.run(self._plan("Process this scanned inspection report"))
        node_ids = [n.id for n in graph.nodes]
        assert "ocr" in node_ids
        assert "export" in node_ids
        assert graph.get("export").depends_on == ["validate"]

    def test_coding_request_produces_generate_execute_fix_chain(self):
        import asyncio
        graph = asyncio.run(self._plan("Build me an inventory management application"))
        node_ids = [n.id for n in graph.nodes]
        assert node_ids == ["code_gen", "execute", "fix", "validate"]

    def test_ready_nodes_respects_dependencies(self):
        graph = TaskGraph(request_text="test", nodes=[
            TaskNode("a", "research", "step a"),
            TaskNode("b", "research", "step b", depends_on=["a"]),
        ])
        assert [n.id for n in graph.ready_nodes()] == ["a"]
        graph.get("a").status = "done"
        assert [n.id for n in graph.ready_nodes()] == ["b"]
