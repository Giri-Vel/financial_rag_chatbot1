"""
RegulatorAI - API Models
=========================
Pydantic schemas for request validation and response serialization.
Clean contracts between frontend and backend.
"""

from pydantic import BaseModel, Field


# ── Request Models ─────────────────────────────────────

class QueryRequest(BaseModel):
    """Request body for the /query endpoint."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The regulatory question to answer",
        examples=["What are the KYC norms for V-CIP?"],
    )
    topic: str | None = Field(
        default=None,
        description="Filter by topic: digital_lending, kyc_aml, payment_systems",
        examples=["kyc_aml"],
    )
    regulator: str | None = Field(
        default=None,
        description="Filter by regulator: RBI or SEBI",
        examples=["RBI"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of chunks to retrieve",
    )
    premium: bool = Field(
        default=False,
        description="Use premium model (gpt-4o) for complex queries",
    )


# ── Response Models ────────────────────────────────────

class SourceDocument(BaseModel):
    """A source document cited in the answer."""

    title: str
    section: str
    regulator: str
    topic: str
    date: str
    doc_type: str
    similarity: float


class QueryResponse(BaseModel):
    """Response from the /query endpoint."""

    answer: str
    sources: list[SourceDocument]
    context_used: int = Field(description="Number of chunks used to generate the answer")
    model: str = Field(description="LLM model used for generation")


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: str = "healthy"
    collection_size: int = Field(description="Number of chunks in the vector store")
    model: str = Field(description="Default LLM model")
    embedding_model: str = Field(description="Embedding model in use")


class TopicInfo(BaseModel):
    """Info about a single topic."""

    topic: str
    chunk_count: int


class TopicsResponse(BaseModel):
    """Response from the /topics endpoint."""

    topics: list[TopicInfo]
    total_chunks: int


class DocumentInfo(BaseModel):
    """Info about a single document in the knowledge base."""

    doc_id: str
    title: str
    regulator: str
    topic: str
    doc_type: str
    date: str
    chunk_count: int


class DocumentsResponse(BaseModel):
    """Response from the /documents endpoint."""

    documents: list[DocumentInfo]
    total_documents: int
    total_chunks: int