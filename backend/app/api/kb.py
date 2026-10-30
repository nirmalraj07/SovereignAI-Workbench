from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from ..rag import pipeline as rag
from ..rag import extraction
from ..security.auth import get_current_user
from ..security.audit import record_event

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/ingest")
async def ingest(file: UploadFile = File(...), classification: str = Form("internal"),
                  user: dict = Depends(get_current_user)):
    raw = await file.read()
    text, page_map = extraction.extract_text(raw, file.filename)
    document_id = rag.ingest_document(text, filename=file.filename,
                                       classification=classification, page_map=page_map)
    record_event(user=user["username"], action="kb_ingest", resource=file.filename)
    return {"document_id": document_id, "filename": file.filename, "characters_extracted": len(text)}


@router.post("/query")
async def query(req: QueryRequest, user: dict = Depends(get_current_user)):
    from ..observability.metrics import kb_queries_total
    kb_queries_total.inc()
    chunks = rag.retrieve(req.query, top_k=req.top_k)
    record_event(user=user["username"], action="kb_query", resource=req.query[:80])
    return {
        "chunks": [{"text": c.text, "filename": c.filename, "page": c.page, "score": c.score} for c in chunks],
        "citations": rag.format_citations(chunks),
    }
