"""
RegulatorAI - Central Configuration
====================================
All settings are loaded from environment variables (.env file).
No secrets are hardcoded. No magic strings scattered across files.

Usage:
    from src.config import settings
    print(settings.OPENAI_API_KEY)
    print(settings.S3_BUCKET_NAME)
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


# ── Project Paths ──────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent  # regulator-ai/
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EVAL_DATA_DIR = DATA_DIR / "eval"
CHROMA_DB_DIR = DATA_DIR / "chromadb"

# Ensure directories exist at import time
for _dir in [RAW_DATA_DIR / "rbi", RAW_DATA_DIR / "sebi", PROCESSED_DATA_DIR, EVAL_DATA_DIR, CHROMA_DB_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)


# ── Settings (loaded from .env) ───────────────────────────────

class Settings(BaseSettings):
    """
    All configurable values in one place.
    Override any of these by setting the corresponding env variable.
    """

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAI ---
    OPENAI_API_KEY: str = Field(default="", description="Your OpenAI API key")
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="Model for answer generation")
    LLM_MODEL_PREMIUM: str = Field(default="gpt-4o", description="Model for deep analysis mode")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="Model for embeddings")
    LLM_TEMPERATURE: float = Field(default=0.1, description="Low temp = more factual, less creative")
    LLM_MAX_TOKENS: int = Field(default=2048, description="Max tokens in LLM response")

    # --- RAG Pipeline ---
    CHUNK_SIZE: int = Field(default=1000, description="Target chunk size in characters")
    CHUNK_OVERLAP: int = Field(default=200, description="Overlap between consecutive chunks")
    TOP_K_RETRIEVAL: int = Field(default=5, description="Number of chunks to retrieve per query")
    SIMILARITY_THRESHOLD: float = Field(default=0.3, description="Minimum similarity score to include a chunk")

    # --- ChromaDB ---
    CHROMA_COLLECTION_NAME: str = Field(default="regulatory_docs", description="ChromaDB collection name")
    CHROMA_PERSIST_DIR: str = Field(default=str(CHROMA_DB_DIR), description="Where ChromaDB stores data on disk")

    # --- AWS ---
    AWS_REGION: str = Field(default="ap-south-1", description="AWS region (Mumbai for low latency)")
    S3_BUCKET_NAME: str = Field(default="regulator-ai-docs", description="S3 bucket for document storage")
    S3_RAW_PREFIX: str = Field(default="raw/", description="S3 prefix for raw PDFs")
    S3_PROCESSED_PREFIX: str = Field(default="processed/", description="S3 prefix for processed chunks")

    # --- API Server ---
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    API_RELOAD: bool = Field(default=True, description="Auto-reload on code changes (dev only)")

    # --- Streamlit ---
    STREAMLIT_PORT: int = Field(default=8501)

    # --- Document Sources ---
    RBI_BASE_URL: str = Field(default="https://www.rbi.org.in")
    SEBI_BASE_URL: str = Field(default="https://www.sebi.gov.in")

    # --- Regulatory Topics (seed topics for Phase 1) ---
    SEED_TOPICS: list[str] = Field(
        default=[
            "digital_lending",
            "kyc_aml",
            "payment_systems",
        ],
        description="Initial regulatory topics to ingest",
    )

    # --- Logging ---
    LOG_LEVEL: str = Field(default="INFO")


# ── Singleton ──────────────────────────────────────────────────
# Import this everywhere: from src.config import settings

settings = Settings()


# ── Prompt Templates ───────────────────────────────────────────
# Kept here for now. Will move to src/generation/prompts.py
# once we build the generation layer.

SYSTEM_PROMPT = """You are RegulatorAI, an expert assistant for Indian financial regulations.
You help compliance officers, bankers, and financial professionals understand RBI and SEBI regulations.

RULES:
1. ONLY answer based on the provided regulatory document excerpts.
2. ALWAYS cite the specific document, section, and paragraph number.
3. If the context doesn't contain enough information, say so clearly.
4. Use precise regulatory language but explain complex terms in plain English.
5. Format citations as: [Source: <document_title>, Section <X>, Para <Y>]
6. If a regulation has been superseded or amended, note this clearly.
7. Never make up or hallucinate regulatory content.

CONTEXT FROM REGULATORY DOCUMENTS:
{context}
"""

QUERY_PROMPT = """Based on the regulatory documents provided above, answer the following question:

Question: {question}

Provide a clear, well-structured answer with specific citations to the source documents.
If the provided context is insufficient, state what information is missing.
"""