"""
RegulatorAI - Document Embedder
=================================
Generates embeddings for document chunks and stores them in ChromaDB.

This is the bridge between processed documents and the RAG retrieval layer.
After this step, you can query your regulatory documents.

Usage:
    from src.ingestion.embedder import embed_all_chunks
    embed_all_chunks()

    # Or via CLI
    python -m src.ingestion.embedder
    python -m src.ingestion.embedder --reset  # Clear DB and re-embed everything
"""

import json
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings
from loguru import logger
from tqdm import tqdm

from src.config import settings, PROCESSED_DATA_DIR, ROOT_DIR


# ── Constants ──────────────────────────────────────────

CHUNKS_FILE = PROCESSED_DATA_DIR / "_all_chunks.json"
BATCH_SIZE = 50  # ChromaDB and OpenAI both handle batches well at this size


# ── ChromaDB Client ────────────────────────────────────

def get_chroma_client() -> chromadb.ClientAPI:
    """Get a persistent ChromaDB client."""
    client = chromadb.PersistentClient(
        path=settings.CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client


def get_or_create_collection(
    client: chromadb.ClientAPI,
    reset: bool = False,
) -> chromadb.Collection:
    """
    Get or create the ChromaDB collection.

    Args:
        client: ChromaDB client
        reset: If True, delete and recreate the collection
    """
    if reset:
        try:
            client.delete_collection(settings.CHROMA_COLLECTION_NAME)
            logger.warning(f"Deleted existing collection: {settings.CHROMA_COLLECTION_NAME}")
        except ValueError:
            pass  # Collection doesn't exist yet

    collection = client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  # Use cosine similarity
    )

    logger.info(
        f"Collection '{settings.CHROMA_COLLECTION_NAME}': "
        f"{collection.count()} existing documents"
    )

    return collection


# ── Embedding Function ─────────────────────────────────

def get_embedding_function() -> OpenAIEmbeddings:
    """Initialize OpenAI embedding model."""
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
    )


# ── Load Chunks ────────────────────────────────────────

def load_chunks() -> list[dict]:
    """Load all chunks from the processed chunks file."""
    if not CHUNKS_FILE.exists():
        logger.error(f"Chunks file not found: {CHUNKS_FILE}")
        logger.error("Run the parser and chunker first: python scripts/ingest.py --step parse && --step chunk")
        return []

    with open(CHUNKS_FILE) as f:
        chunks = json.load(f)

    logger.info(f"Loaded {len(chunks)} chunks from {CHUNKS_FILE}")
    return chunks


# ── Embed and Store ────────────────────────────────────

def embed_all_chunks(reset: bool = False, topic: str | None = None) -> int:
    """
    Generate embeddings and store all chunks in ChromaDB.

    Args:
        reset: If True, clear the collection and re-embed everything
        topic: Optional filter by topic

    Returns:
        Number of chunks embedded
    """
    chunks = load_chunks()
    if not chunks:
        return 0

    # Filter by topic if specified
    if topic:
        chunks = [c for c in chunks if c["topic"] == topic]
        logger.info(f"Filtered to {len(chunks)} chunks for topic: {topic}")

    # Initialize ChromaDB
    client = get_chroma_client()
    collection = get_or_create_collection(client, reset=reset)

    # Initialize embedding model
    embed_fn = get_embedding_function()

    # Filter out chunks already in the collection
    existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()
    new_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]

    if not new_chunks:
        logger.info("All chunks already embedded. Nothing to do.")
        return 0

    logger.info(
        f"Embedding {len(new_chunks)} new chunks "
        f"({len(existing_ids)} already in collection)"
    )

    # Process in batches
    total_embedded = 0

    for i in tqdm(range(0, len(new_chunks), BATCH_SIZE), desc="Embedding batches"):
        batch = new_chunks[i : i + BATCH_SIZE]

        # Extract texts for embedding
        texts = [c["text"] for c in batch]

        # Generate embeddings
        try:
            embeddings = embed_fn.embed_documents(texts)
        except Exception as e:
            logger.error(f"Embedding failed for batch {i // BATCH_SIZE}: {e}")
            continue

        # Prepare data for ChromaDB
        ids = [c["chunk_id"] for c in batch]
        metadatas = [
            {
                "doc_id": c["doc_id"],
                "title": c["title"],
                "regulator": c["regulator"],
                "topic": c["topic"],
                "doc_type": c["doc_type"],
                "date": c["date"],
                "section_title": c["section_title"],
                "chunk_index": c["chunk_index"],
                "total_chunks": c["total_chunks"],
                "char_count": c["char_count"],
                "token_count": c["token_count"],
            }
            for c in batch
        ]

        # Add to ChromaDB
        try:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            total_embedded += len(batch)
        except Exception as e:
            logger.error(f"ChromaDB insert failed for batch {i // BATCH_SIZE}: {e}")
            continue

    logger.success(
        f"Embedding complete: {total_embedded} chunks added. "
        f"Collection now has {collection.count()} total documents."
    )

    # Save embedding summary
    summary = {
        "total_embedded": total_embedded,
        "collection_size": collection.count(),
        "embedding_model": settings.EMBEDDING_MODEL,
        "collection_name": settings.CHROMA_COLLECTION_NAME,
    }
    summary_path = PROCESSED_DATA_DIR / "_embed_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return total_embedded


# ── Quick Test Query ───────────────────────────────────

def test_query(query: str, n_results: int = 3):
    """Quick test to verify embeddings work."""
    client = get_chroma_client()
    collection = get_or_create_collection(client)

    embed_fn = get_embedding_function()
    query_embedding = embed_fn.embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")

    for i, (doc, meta, dist) in enumerate(
        zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
    ):
        similarity = 1 - dist  # cosine distance to similarity
        print(f"\n--- Result {i + 1} (similarity: {similarity:.3f}) ---")
        print(f"Source: {meta['title']} | {meta['section_title']}")
        print(f"Topic: {meta['topic']} | Date: {meta['date']}")
        print(f"Text preview: {doc[:200]}...")

    return results


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Embed document chunks into ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Clear collection and re-embed")
    parser.add_argument("--topic", type=str, help="Filter by topic")
    parser.add_argument("--test", type=str, help="Run a test query after embedding")
    args = parser.parse_args()

    logger.add(ROOT_DIR / "logs" / "embedder.log", rotation="10 MB", level=settings.LOG_LEVEL)

    embed_all_chunks(reset=args.reset, topic=args.topic)

    if args.test:
        test_query(args.test)