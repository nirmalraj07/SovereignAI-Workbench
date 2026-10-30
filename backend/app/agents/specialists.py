"""
Specialist agents wired to the SovereignAI subsystems:

- router/
- rag/
- sandbox/
- ocr/
- files/

Each agent implements the BaseAgent.run() contract, allowing the
PlanningAgent and Orchestrator to execute multi-step workflows.
"""

from __future__ import annotations

import base64
import binascii
import tempfile
from pathlib import Path

from .base import BaseAgent
from ..router.router import router
from ..rag import pipeline as rag
from ..sandbox import executor as sandbox
from ..ocr import pipeline as ocr
from ..files import generator as files


# ============================================================
# RESEARCH AGENT
# ============================================================

class ResearchAgent(BaseAgent):
    name = "research"

    async def run(self, instruction: str, context: dict):
        """
        Searches/uses knowledge-base context and optionally includes OCR
        output from a previous OCR node.
        """

        upstream_chunks = []

        # ----------------------------------------------------
        # Distributed-safe KB result lookup
        # ----------------------------------------------------

        for node_result in context.get("upstream", {}).values():
            if (
                isinstance(node_result, dict)
                and "retrieved_chunks" in node_result
            ):
                upstream_chunks = node_result["retrieved_chunks"]
                break

        grounding_parts = []
        citations = []

        # ----------------------------------------------------
        # Knowledge-base grounding
        # ----------------------------------------------------

        if upstream_chunks:
            grounding_parts.append(
                "\n\n".join(
                    f"[{chunk.get('filename', 'Unknown')} "
                    f"p.{chunk.get('page', '?')}]\n"
                    f"{chunk.get('text', '')}"
                    for chunk in upstream_chunks
                )
            )

            citations = [
                {
                    "source": chunk.get("filename", ""),
                    "page": chunk.get("page", 0),
                    "document_id": chunk.get("document_id", ""),
                    "relevance": chunk.get("score", 0.0),
                }
                for chunk in upstream_chunks
            ]

        else:
            kb_context = context.get("kb_chunks", [])

            if kb_context:
                grounding_parts.append(
                    "\n\n".join(
                        f"[{chunk.filename} p.{chunk.page}]\n{chunk.text}"
                        for chunk in kb_context
                    )
                )

                citations = rag.format_citations(kb_context)

        # ----------------------------------------------------
        # OCR grounding
        # ----------------------------------------------------

        ocr_text = context.get("ocr_text")

        if not ocr_text:
            upstream_ocr = context.get("upstream", {}).get("ocr")

            if isinstance(upstream_ocr, dict):
                ocr_text = upstream_ocr.get("extracted_text")

        if ocr_text:
            grounding_parts.append(
                f"UPLOADED OCR DOCUMENT:\n{ocr_text}"
            )

        # ----------------------------------------------------
        # Build prompt
        # ----------------------------------------------------

        if grounding_parts:
            sources = "\n\n".join(grounding_parts)

            prompt = (
                "Use the following source material to answer the request.\n\n"
                f"SOURCES:\n{sources}\n\n"
                f"REQUEST:\n{instruction}"
            )
        else:
            prompt = instruction

        result = await router.generate(
            prompt,
            explicit_modality="text",
        )

        return {
            "answer": result.text,
            "model_used": result.model_used,
            "citations": citations,
        }


# ============================================================
# KNOWLEDGE BASE AGENT
# ============================================================

class KnowledgeBaseAgent(BaseAgent):
    name = "knowledge_base"

    async def run(self, instruction: str, context: dict):
        top_k = context.get("top_k", 5)

        chunks = rag.retrieve(
            instruction,
            top_k=top_k,
        )

        # In-process convenience.
        context["kb_chunks"] = chunks

        return {
            "retrieved_chunks": [
                {
                    "filename": chunk.filename,
                    "page": chunk.page,
                    "score": chunk.score,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                }
                for chunk in chunks
            ],
            "count": len(chunks),
        }


# ============================================================
# CODING AGENT
# ============================================================

class CodingAgent(BaseAgent):
    name = "coding"

    async def run(self, instruction: str, context: dict):
        language = context.get("language", "python")

        upstream_code = None

        # Look for code generated by a previous coding node.
        for node_result in context.get("upstream", {}).values():
            if isinstance(node_result, dict):
                if (
                    "code" in node_result
                    or "final_code" in node_result
                ):
                    upstream_code = (
                        node_result.get("final_code")
                        or node_result.get("code")
                    )

        # ----------------------------------------------------
        # Initial generation
        # ----------------------------------------------------

        if upstream_code is None and "code" not in context:

            result = await router.generate(
                instruction,
                explicit_modality="code",
            )

            context["code"] = result.text

            return {
                "code": result.text,
                "model_used": result.model_used,
                "stage": "generated",
            }

        # ----------------------------------------------------
        # Execute and repair
        # ----------------------------------------------------

        source_code = upstream_code or context["code"]

        async def repair(code: str, stderr: str) -> str:

            fix_prompt = (
                f"This {language} code failed.\n\n"
                f"ERROR:\n{stderr}\n\n"
                f"CODE:\n{code}\n\n"
                "Return only the corrected code."
            )

            fix_result = await router.generate(
                fix_prompt,
                explicit_modality="code",
            )

            return fix_result.text

        exec_result, final_code, attempts = (
            await sandbox.execute_with_repair(
                source_code,
                language,
                repair,
                max_attempts=3,
            )
        )

        return {
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "exit_code": exec_result.exit_code,
            "attempts": attempts,
            "final_code": final_code,
            "success": exec_result.exit_code == 0,
        }


# ============================================================
# OCR AGENT
# ============================================================

class OCRAgent(BaseAgent):
    name = "ocr"

    async def run(self, instruction: str, context: dict):
        """
        Receives the uploaded image/PDF as base64 from the Celery task.

        The workflow is:

        Frontend
            ↓
        FastAPI multipart upload
            ↓
        Base64 encoding
            ↓
        Celery task
            ↓
        context["image_b64"]
            ↓
        OCRAgent
            ↓
        temporary file
            ↓
        OCR pipeline
            ↓
        RAG ingestion
        """

        image_b64 = context.get("image_b64")

        if not image_b64:
            return {
                "extracted_text": "",
                "engine_used": None,
                "mean_confidence": 0.0,
                "note": "No image uploaded",
            }

        filename = context.get("filename", "uploaded_scan.png")

        suffix = Path(filename).suffix.lower()

        if not suffix:
            suffix = ".png"

        temp_path = None

        try:
            # ------------------------------------------------
            # Remove data URL prefix if present
            #
            # Example:
            # data:image/png;base64,AAAA...
            # ------------------------------------------------

            if "," in image_b64 and image_b64.startswith("data:"):
                image_b64 = image_b64.split(",", 1)[1]

            # ------------------------------------------------
            # Decode uploaded image
            # ------------------------------------------------

            try:
                image_bytes = base64.b64decode(
                    image_b64,
                    validate=True,
                )

            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    "Uploaded image contains invalid base64 data"
                ) from exc

            # ------------------------------------------------
            # Create temporary file
            # ------------------------------------------------

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as temp_file:

                temp_file.write(image_bytes)

                temp_path = temp_file.name

            # ------------------------------------------------
            # Run OCR
            # ------------------------------------------------

            result = ocr.extract(temp_path)

            extracted_text = result.full_text or ""

            # Store for downstream in-process agents.
            context["ocr_text"] = extracted_text
            context["observations"] = extracted_text

            # ------------------------------------------------
            # Index OCR text into Knowledge Base
            # ------------------------------------------------

            document_id = None

            if extracted_text.strip():

                document_id = rag.ingest_document(
                    extracted_text,
                    filename=filename,
                )

            return {
                "extracted_text": extracted_text,
                "engine_used": result.engine_used,
                "mean_confidence": result.mean_confidence,
                "document_id": document_id,
                "filename": filename,
            }

        except Exception as exc:

            return {
                "extracted_text": "",
                "engine_used": None,
                "mean_confidence": 0.0,
                "error": str(exc),
            }

        finally:

            # ------------------------------------------------
            # Always delete temporary uploaded file
            # ------------------------------------------------

            if temp_path:

                try:
                    Path(temp_path).unlink(
                        missing_ok=True
                    )

                except Exception:
                    pass


# ============================================================
# VISION AGENT
# ============================================================

class VisionAgent(BaseAgent):
    name = "vision"

    async def run(self, instruction: str, context: dict):

        image_b64 = context.get("image_b64")

        if not image_b64:
            return {
                "analysis": "",
                "error": "No image uploaded",
            }

        result = await router.generate(
            instruction,
            explicit_modality="vision",
            image_b64=image_b64,
        )

        return {
            "analysis": result.text,
            "model_used": result.model_used,
        }


# ============================================================
# DOCUMENT AGENT
# ============================================================

class DocumentAgent(BaseAgent):
    name = "document"

    async def run(self, instruction: str, context: dict):

        result = await router.generate(
            instruction,
            explicit_modality="text",
        )

        title = context.get(
            "title",
            "Generated Report",
        )

        path = files.generate_docx(
            title,
            result.text,
        )

        return {
            "draft": result.text,
            "file_path": str(path),
        }


# ============================================================
# SPREADSHEET AGENT
# ============================================================

class SpreadsheetAgent(BaseAgent):
    name = "spreadsheet"

    async def run(self, instruction: str, context: dict):

        headers = context.get(
            "headers",
            ["Item", "Value"],
        )

        rows = context.get("rows", [])

        title = context.get(
            "title",
            "Report",
        )

        path = files.generate_xlsx(
            title,
            headers,
            rows,
        )

        return {
            "file_path": str(path),
        }


# ============================================================
# PRESENTATION AGENT
# ============================================================

class PresentationAgent(BaseAgent):
    name = "presentation"

    async def run(self, instruction: str, context: dict):

        title = context.get(
            "title",
            "Presentation",
        )

        slides = context.get(
            "slides",
            [
                {
                    "title": "Summary",
                    "bullets": [instruction],
                }
            ],
        )

        path = files.generate_pptx(
            title,
            slides,
        )

        return {
            "file_path": str(path),
        }


# ============================================================
# CALCULATION AGENT
# ============================================================

class CalculationAgent(BaseAgent):
    name = "calculation"

    async def run(self, instruction: str, context: dict):

        result = await router.generate(
            (
                "Write Python code and compute the final numeric result "
                f"for:\n{instruction}"
            ),
            explicit_modality="code",
        )

        exec_result = await sandbox.execute(
            result.text,
            "python",
        )

        return {
            "code": result.text,
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "exit_code": exec_result.exit_code,
        }


# ============================================================
# VALIDATION AGENT
# ============================================================

class ValidationAgent(BaseAgent):
    name = "validation"

    async def run(self, instruction: str, context: dict):

        # Include previous approval note if available.
        approval_note = None

        upstream_approval = (
            context.get("upstream", {})
            .get("approval_note")
        )

        if isinstance(upstream_approval, dict):
            approval_note = upstream_approval.get(
                "approval_note"
            )

        validation_input = instruction

        if approval_note:
            validation_input = (
                f"{instruction}\n\n"
                f"APPROVAL NOTE TO VALIDATE:\n"
                f"{approval_note}"
            )

        result = await router.generate(
            (
                "Validate and flag errors, omissions, "
                "inconsistencies, and unsupported claims in:\n\n"
                f"{validation_input}"
            ),
            explicit_modality="text",
        )

        return {
            "validation_notes": result.text,
        }


# ============================================================
# REPORTING AGENT
# ============================================================

class ReportingAgent(BaseAgent):
    name = "reporting"

    async def run(self, instruction: str, context: dict):

        result = await router.generate(
            instruction,
            explicit_modality="text",
        )

        title = context.get(
            "title",
            "Technical Report",
        )

        path = files.generate_docx(
            title,
            result.text,
        )

        return {
            "report": result.text,
            "file_path": str(path),
        }


# ============================================================
# APPROVAL NOTE AGENT
# ============================================================

class ApprovalAgent(BaseAgent):
    name = "approval_note"

    async def run(self, instruction: str, context: dict):
        """
        Creates an approval note using OCR observations and any available
        upstream research results.
        """

        observations = context.get("observations")

        # Distributed-safe OCR lookup.
        if not observations:

            upstream_ocr = (
                context.get("upstream", {})
                .get("ocr")
            )

            if isinstance(upstream_ocr, dict):
                observations = upstream_ocr.get(
                    "extracted_text"
                )

        if not observations:
            observations = instruction

        # ----------------------------------------------------
        # Research result
        # ----------------------------------------------------

        research_text = ""

        upstream_research = (
            context.get("upstream", {})
            .get("research")
        )

        if isinstance(upstream_research, dict):
            research_text = upstream_research.get(
                "answer",
                "",
            )

        prompt = (
            "Draft a professional approval note based on the following "
            "inspection findings.\n\n"
            f"FINDINGS:\n{observations}\n\n"
        )

        if research_text:
            prompt += (
                f"RELATED RESEARCH:\n{research_text}\n\n"
            )

        prompt += (
            "Include:\n"
            "1. Summary of findings\n"
            "2. Assessment\n"
            "3. Recommendation\n"
            "4. Required follow-up actions\n"
        )

        result = await router.generate(
            prompt,
            explicit_modality="text",
        )

        title = context.get(
            "title",
            "Approval Note",
        )

        path = files.generate_approval_note(
            title=title,
            observations=observations,
            recommendation=result.text,
            references=context.get("references", []),
        )

        return {
            "approval_note": result.text,
            "file_path": str(path),
        }


# ============================================================
# MONITORING AGENT
# ============================================================

class MonitoringAgent(BaseAgent):
    name = "monitoring"

    async def run(self, instruction: str, context: dict):

        metrics = context.get(
            "metrics",
            {},
        )

        result = await router.generate(
            (
                "Summarize system health from these metrics:\n\n"
                f"{metrics}"
            ),
            explicit_modality="text",
        )

        return {
            "summary": result.text,
            "raw_metrics": metrics,
        }


# ============================================================
# AGENT REGISTRY
# ============================================================

def build_agent_registry() -> dict[str, BaseAgent]:
    """
    Builds the registry used by the Orchestrator and Celery workers.
    """

    agents = [
        ResearchAgent(),
        KnowledgeBaseAgent(),
        CodingAgent(),
        OCRAgent(),
        VisionAgent(),
        DocumentAgent(),
        SpreadsheetAgent(),
        PresentationAgent(),
        CalculationAgent(),
        ValidationAgent(),
        ReportingAgent(),
        ApprovalAgent(),
        MonitoringAgent(),
    ]

    registry = {
        agent.name: agent
        for agent in agents
    }

    # --------------------------------------------------------
    # Dynamically loaded plugin agents
    # --------------------------------------------------------

    try:

        from ..plugins.loader import get_loaded_agents

        registry.update(
            get_loaded_agents()
        )

    except ImportError:
        pass

    return registry