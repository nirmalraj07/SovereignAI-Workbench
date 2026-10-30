"""
RAG pipeline: ingestion (chunk + embed + store) and retrieval (semantic
search + citation assembly). Uses ChromaDB as the vector store (local,
on-disk/self-hosted — no external embedding API calls: embeddings are
computed with a local sentence-transformers model).
"""
from __future__ import annotations
import hashlib
import uuid
from dataclasses import dataclass

from ..core.config import settings

# Chroma client/collection and the embedding model are constructed lazily
# (on first use, not at import time) so that pure-logic functions in this
# module — chunk_text(), format_citations() — can be imported and unit
# tested without a running ChromaDB instance or the sentence-transformers
# model being downloaded/loaded.
_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        from chromadb.utils import embedding_functions

        embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        client = chromadb.HttpClient(
            host=settings.chroma_url.split("://")[-1].split(":")[0],
            port=int(settings.chroma_url.split(":")[-1]),
        )
        _collection = client.get_or_create_collection(
            name="knowledge_base",
            embedding_function=embedder,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


@dataclass
class Chunk:
    text: str
    document_id: str
    filename: str
    page: int
    chunk_index: int


@dataclass
class RetrievedChunk:
    text: str
    document_id: str
    filename: str
    page: int
    score: float


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Sliding-window chunking on whitespace-normalized text."""
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    step = max(chunk_size - overlap, 1)
    while start < len(words):
        chunks.append(" ".join(words[start:start + chunk_size]))
        start += step
    return chunks


def ingest_document(text: str, filename: str, classification: str = "internal",
                     page_map: list[tuple[str, int]] | None = None) -> str:
    """
    Ingest raw extracted text (already OCR'd/extracted if it was a scan or
    PDF/DOCX) into the KB. page_map, if provided, is a list of
    (text_segment, page_number) — chunks are then built per-segment so each
    chunk carries an accurate page citation instead of defaulting to page 1.
    """
    document_id = str(uuid.uuid4())
    source_text = text if page_map is None else " ".join(t for t, _ in page_map)
    checksum = hashlib.sha256(source_text.encode()).hexdigest()

    all_chunks: list[str] = []
    all_pages: list[int] = []
    if page_map:
        for segment_text, page in page_map:
            segment_chunks = chunk_text(segment_text)
            all_chunks.extend(segment_chunks)
            all_pages.extend([page] * len(segment_chunks))
    else:
        all_chunks = chunk_text(source_text)
        all_pages = [1] * len(all_chunks)

    ids = [f"{document_id}:{i}" for i in range(len(all_chunks))]
    metadatas = [
        {
            "document_id": document_id,
            "filename": filename,
            "classification": classification,
            "chunk_index": i,
            "page": all_pages[i],
            "checksum": checksum,
        }
        for i in range(len(all_chunks))
    ]
    if all_chunks:
        _get_collection().add(documents=all_chunks, ids=ids, metadatas=metadatas)
    return document_id


def retrieve(query: str, top_k: int = 5, classification_filter: str | None = None) -> list[RetrievedChunk]:
    where = {"classification": classification_filter} if classification_filter else None
    results = _get_collection().query(query_texts=[query], n_results=top_k, where=where)

    retrieved: list[RetrievedChunk] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for text, meta, dist in zip(docs, metas, dists):
        retrieved.append(RetrievedChunk(
            text=text,
            document_id=meta["document_id"],
            filename=meta["filename"],
            page=meta.get("page", 1),
            score=1 - dist,  # cosine distance -> similarity
        ))
    return retrieved


def format_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {"source": c.filename, "page": c.page, "document_id": c.document_id, "relevance": round(c.score, 3)}
        for c in chunks
    ]
