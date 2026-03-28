"""
RegulatorAI - API Routes
==========================
All endpoint logic lives here. Kept separate from main.py
so the app setup stays clean.

Endpoints:
    POST /query      — Ask a regulatory question, get a cited answer
    GET  /health     — Health check + collection stats
    GET  /topics     — List available topics with chunk counts
    GET  /documents  — List all documents in the knowledge base
"""

from collections import Counter

from fastapi import APIRouter, HTTPException
from loguru import logger

from src.api.models import (
    QueryRequest,
    QueryResponse,
    HealthResponse,
    TopicInfo,
    TopicsResponse,
    DocumentInfo,
    DocumentsResponse,
)
from src.config import settings


router = APIRouter()

# RAGChain is initialized once at app startup (see main.py lifespan)
# and stored in app.state. We access it via request.app.state in each route.
# But since APIRouter doesn't have direct access to app.state,
# we store a module-level reference that main.py sets during startup.
_rag_chain = None


def set_rag_chain(chain):
    """Called by main.py during startup to inject the RAGChain instance."""
    global _rag_chain
    _rag_chain = chain


def get_rag_chain():
    """Get the RAGChain instance, raising 503 if not initialized."""
    if _rag_chain is None:
        raise HTTPException(
            status_code=503,
            detail="RAG chain not initialized. Server is starting up.",
        )
    return _rag_chain


# ── POST /query ────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_regulations(request: QueryRequest):
    """
    Ask a question about Indian financial regulations.

    The system retrieves relevant document chunks from the vector store,
    then generates a cited answer using an LLM.
    """
    rag = get_rag_chain()

    logger.info(
        f"API query: '{request.question[:80]}' | "
        f"topic={request.topic}, regulator={request.regulator}, "
        f"top_k={request.top_k}, premium={request.premium}"
    )

    try:
        # If premium is requested, create a temporary premium chain
        if request.premium:
            from src.generation.chain import RAGChain
            premium_rag = RAGChain(premium=True)
            result = premium_rag.query(
                question=request.question,
                top_k=request.top_k,
                topic=request.topic,
                regulator=request.regulator,
            )
        else:
            result = rag.query(
                question=request.question,
                top_k=request.top_k,
                topic=request.topic,
                regulator=request.regulator,
            )

        return QueryResponse(**result)

    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


# ── GET /health ────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint. Returns collection stats and model info.
    Useful for monitoring and AWS health checks.
    """
    rag = get_rag_chain()

    try:
        collection_size = rag.vector_store.collection.count()
    except Exception:
        collection_size = 0

    return HealthResponse(
        status="healthy",
        collection_size=collection_size,
        model=settings.LLM_MODEL,
        embedding_model=settings.EMBEDDING_MODEL,
    )


# ── GET /topics ────────────────────────────────────────

@router.get("/topics", response_model=TopicsResponse)
async def list_topics():
    """
    List all available topics with their chunk counts.
    Useful for populating filter dropdowns in the frontend.
    """
    rag = get_rag_chain()

    try:
        # Get all metadata from the collection
        all_data = rag.vector_store.collection.get(include=["metadatas"])
        metadatas = all_data["metadatas"] or []

        # Count chunks per topic
        topic_counts = Counter(m.get("topic", "unknown") for m in metadatas)

        topics = [
            TopicInfo(topic=topic, chunk_count=count)
            for topic, count in sorted(topic_counts.items())
        ]

        return TopicsResponse(
            topics=topics,
            total_chunks=len(metadatas),
        )

    except Exception as e:
        logger.error(f"Failed to list topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /documents ─────────────────────────────────────

@router.get("/documents", response_model=DocumentsResponse)
async def list_documents():
    """
    List all documents in the knowledge base with chunk counts.
    Shows what the system knows about.
    """
    rag = get_rag_chain()

    try:
        all_data = rag.vector_store.collection.get(include=["metadatas"])
        metadatas = all_data["metadatas"] or []

        # Group by doc_id
        doc_map: dict[str, dict] = {}
        for m in metadatas:
            doc_id = m.get("doc_id", "unknown")
            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "doc_id": doc_id,
                    "title": m.get("title", "Unknown"),
                    "regulator": m.get("regulator", "Unknown"),
                    "topic": m.get("topic", "unknown"),
                    "doc_type": m.get("doc_type", "unknown"),
                    "date": m.get("date", "unknown"),
                    "chunk_count": 0,
                }
            doc_map[doc_id]["chunk_count"] += 1

        documents = [
            DocumentInfo(**doc)
            for doc in sorted(doc_map.values(), key=lambda d: d["doc_id"])
        ]

        return DocumentsResponse(
            documents=documents,
            total_documents=len(documents),
            total_chunks=len(metadatas),
        )

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))