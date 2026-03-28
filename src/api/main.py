"""
RegulatorAI - FastAPI Application
====================================
Entry point for the API server. Initializes the RAG chain once
at startup (via lifespan) so it's shared across all requests.

Usage:
    uvicorn src.api.main:app --reload --port 8000

    # Or via the config defaults:
    python -m src.api.main
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.config import settings, ROOT_DIR
from src.generation.chain import RAGChain
from src.api.routes import router, set_rag_chain


# ── Lifespan (startup / shutdown) ──────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize expensive resources once at startup.
    The RAGChain loads the vector store and LLM client —
    we don't want to do this on every request.
    """
    logger.info("Starting RegulatorAI API server...")

    # Initialize RAG chain (loads ChromaDB + OpenAI client)
    rag_chain = RAGChain()
    set_rag_chain(rag_chain)

    collection_size = rag_chain.vector_store.collection.count()
    logger.success(
        f"RAG chain ready: {collection_size} chunks in vector store, "
        f"model={settings.LLM_MODEL}"
    )

    yield  # App is running

    logger.info("Shutting down RegulatorAI API server...")


# ── FastAPI App ────────────────────────────────────────

app = FastAPI(
    title="RegulatorAI",
    description=(
        "AI-powered assistant for navigating Indian financial regulations. "
        "Ask questions about RBI and SEBI regulatory documents and get "
        "cited answers backed by official sources."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────
# Allow Streamlit (default port 8501) and local dev to hit the API.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",     # Streamlit default
        "http://localhost:3000",     # React dev server (future)
        "http://127.0.0.1:8501",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────

app.include_router(router, prefix="/api/v1", tags=["RegulatorAI"])


# ── Root redirect ──────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to API docs."""
    return {
        "service": "RegulatorAI API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# ── CLI Runner ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # Set up file logging
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(log_dir / "api.log", rotation="10 MB", level=settings.LOG_LEVEL)

    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
    )