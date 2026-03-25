"""
RegulatorAI - Vector Store Interface
======================================
Clean wrapper around ChromaDB for retrieval operations.
Used by the RAG chain to fetch relevant document chunks.

Usage:
    from src.retrieval.vector_store import VectorStore
    vs = VectorStore()
    results = vs.search("What is V-CIP?", top_k=5)
"""

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings
from loguru import logger

from src.config import settings


class VectorStore:
    """Interface to ChromaDB for document retrieval."""

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.embed_fn = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        logger.info(f"VectorStore initialized: {self.collection.count()} documents in collection")

    def search(
        self,
        query: str,
        top_k: int = settings.TOP_K_RETRIEVAL,
        topic: str | None = None,
        regulator: str | None = None,
        doc_type: str | None = None,
    ) -> list[dict]:
        """
        Search for relevant chunks.

        Args:
            query: User's question
            top_k: Number of results to return
            topic: Filter by topic (e.g., "kyc_aml", "digital_lending")
            regulator: Filter by regulator ("RBI" or "SEBI")
            doc_type: Filter by document type ("master_direction", "circular", etc.)

        Returns:
            List of dicts with keys: text, metadata, similarity
        """
        # Build where filter for metadata
        where_filter = self._build_filter(topic=topic, regulator=regulator, doc_type=doc_type)

        # Generate query embedding
        query_embedding = self.embed_fn.embed_query(query)

        # Query ChromaDB
        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_filter:
            query_kwargs["where"] = where_filter

        results = self.collection.query(**query_kwargs)

        # Format results
        formatted = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            similarity = 1 - dist  # cosine distance to similarity

            # Skip low-similarity results
            if similarity < settings.SIMILARITY_THRESHOLD:
                continue

            formatted.append({
                "text": doc,
                "metadata": meta,
                "similarity": round(similarity, 4),
            })

        logger.debug(f"Search for '{query[:50]}...' returned {len(formatted)} results")
        return formatted

    def _build_filter(
        self,
        topic: str | None = None,
        regulator: str | None = None,
        doc_type: str | None = None,
    ) -> dict | None:
        """Build ChromaDB where filter from parameters."""
        conditions = []

        if topic:
            conditions.append({"topic": {"$eq": topic}})
        if regulator:
            conditions.append({"regulator": {"$eq": regulator.upper()}})
        if doc_type:
            conditions.append({"doc_type": {"$eq": doc_type}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}